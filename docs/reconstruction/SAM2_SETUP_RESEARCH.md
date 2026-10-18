# SAM 2.1 Hiera tiny setup facts

Checked October 17, 2026 (America/Los_Angeles). Read-only source research; no package installation, repository clone, checkpoint download, or inference was performed. These are setup instructions for implementation, not an assertion that SAM 2 works or meets room-processing budgets on this Mac.

## Pin and platform boundary

Use the official `facebookresearch/sam2` source at commit **`2b90b9f5ceec907a1c18123530e92e794ad901a4`** as a reproducible initial pin. It includes an upstream MPS fix removing a problematic pinned-memory operation. The package reports version `1.0`, so package version alone does not identify source compatibility. [Upstream commit](https://github.com/facebookresearch/sam2/commit/2b90b9f5ceec907a1c18123530e92e794ad901a4), [pinned package metadata](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/setup.py)

**Official installation requirements describe Linux/CUDA**, Python ≥3.10, PyTorch ≥2.5.1 and matching torchvision. CUDA is used for an optional connected-components extension, not an unavoidable requirement for every image-predictor operation. A macOS CPU/MPS experiment is source-compatible in principle but is not equivalent to a documented, tested Linux/CUDA deployment. Upstream's MPS-specific fix is evidence of maintenance, not a guarantee of model quality, speed, or complete operator support on Apple GPUs. [Pinned installation guide](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/INSTALL.md)

Suggested baseline: native Python 3.12 with **`torch==2.5.1` and `torchvision==0.20.1`** in an isolated environment. This is the upstream minimum pair and an explicitly published macOS wheel pair; it is not the newest PyTorch recommendation. PyTorch also publishes newer matched pairs, which need a separate compatibility run before updating the lock. `torchaudio` is unnecessary for the SAM image path. Freeze all resolved dependencies after the actual install; the upstream package leaves transitive versions broadly constrained. [Official PyTorch version pairs](https://pytorch.org/get-started/previous-versions/#v251)

## Exact model and minimal installation

| Item | Exact value |
|---|---|
| Checkpoint | `sam2.1_hiera_tiny.pt` |
| Official checkpoint URL | [Meta public checkpoint](https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt) |
| Hydra config argument | `configs/sam2.1/sam2.1_hiera_t.yaml` |
| Config source | [Pinned tiny config](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/sam2/configs/sam2.1/sam2.1_hiera_t.yaml) |
| Optional Hugging Face model ID | `facebook/sam2.1-hiera-tiny` |

The filename/config pair is verified by upstream's builder mapping. Do not pair the old SAM 2 tiny config with a SAM **2.1** checkpoint. Record the downloaded checkpoint's SHA-256 after retrieval; no official checksum was established in this pass. [Pinned builder mapping and loader](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/sam2/build_sam.py)

After checking out the pinned source and entering its repository root, the minimal commands are:

```sh
python -m pip install torch==2.5.1 torchvision==0.20.1
SAM2_BUILD_CUDA=0 python -m pip install --no-build-isolation -e .
```

These commands were **not run**. `SAM2_BUILD_CUDA=0` explicitly prevents CUDA extension compilation, appropriate for CPU/MPS. `--no-build-isolation` uses the already installed, pinned torch rather than a separate build environment; the upstream installation guide documents that option for build issues. Do not install the `[notebooks]`, `[dev]`, or demo extras merely to perform image inference: base dependencies already include NumPy, Pillow, Hydra, iopath and tqdm. [Pinned install guide](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/INSTALL.md), [base and optional dependencies/build flags](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/setup.py)

`SAM2_BUILD_ALLOW_ERRORS=0` has a different purpose: it makes extension build failure fatal; it does **not** disable CUDA. Leaving connected-component hole/sprinkle cleanup off is intentional on this path. Image mask prediction remains available without that optional extension. [Pinned extension documentation](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/INSTALL.md)

## Actual segmentation APIs

An implementation-owned CPU smoke test can use the following adapter. It assumes `rgb` is a decoded `H×W×3`, `uint8`, RGB NumPy image; `xyxy` is a pixel-coordinate box in that exact image, not a resized or normalized coordinate frame:

```python
import numpy as np
import torch
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

network = build_sam2(
    "configs/sam2.1/sam2.1_hiera_t.yaml",
    ckpt_path=checkpoint_path,
    device="cpu",
)
segmenter = SAM2ImagePredictor(
    network, max_hole_area=0, max_sprinkle_area=0
)
with torch.inference_mode():
    segmenter.set_image(rgb)
    masks, quality, logits = segmenter.predict(
        box=np.asarray(xyxy, dtype=np.float32),
        multimask_output=False,
    )
```

`build_sam2` defaults to CUDA unless explicitly overridden. `predict` supports XY pixel points with foreground/background labels, XYXY pixel boxes, or previous low-resolution mask logits. It returns masks at original image dimensions, predicted quality scores, and 256×256 low-resolution logits. Multimask output supplies alternative masks for ambiguity, not separate semantic objects. The predictor holds image embedding state: do not concurrently share one predictor instance among unrelated frames without serialization. The image encoder is reused for subsequent prompts on the same image. [Pinned builder](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/sam2/build_sam.py), [predictor implementation/API](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/sam2/sam2_image_predictor.py)

For class-agnostic proposals, import `SAM2AutomaticMaskGenerator` from `sam2.automatic_mask_generator`, construct it with the network, and call `generate(rgb)`. Each record includes an actual pixel `segmentation`, XYWH `bbox`, pixel `area`, `predicted_iou`, `stability_score`, seed points and crop box. Defaults use a 32×32 prompt grid and were selected for Hiera large. A smaller grid/batch and zero crop layers can bound a tiny-model smoke test, with reduced recall explicitly measured. Set `min_mask_region_area=0` to avoid the extension-dependent cleanup path. Binary masks need no COCO encoder; `coco_rle` requires `pycocotools`. This API does not name objects or guarantee one mask per physical instance. [Automatic generator source](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/sam2/automatic_mask_generator.py)

Keep rectangular detector/RoomPlan prompts labeled as **prompts** until actual returned masks pass checks. Never relabel their bounding rectangles as SAM segmentation when the package/model is unavailable. Model absence or failure must be an explicit capability failure, not silent success.

## macOS CPU/MPS execution limits

Start with CPU float32 under `torch.inference_mode()`, without CUDA autocast or CUDA-specific compilation. Then test `device="mps"` only if `torch.backends.mps.is_available()` returns true. PyTorch's versioned MPS guidance describes moving modules/tensors onto MPS and checking whether the backend was built and is usable. This checks accelerator availability, not SAM compatibility. [PyTorch 2.5.1 MPS documentation](https://github.com/pytorch/pytorch/blob/v2.5.1/docs/source/notes/mps.rst)

For MPS experiments, set `PYTORCH_ENABLE_MPS_FALLBACK=1` before importing torch or launching the process. PyTorch defines this as CPU fallback for unsupported MPS operations. It can change latency and is not a guarantee every failure is recoverable. Keep CPU as an explicit backend option, and log the chosen device/fallback configuration. [Versioned MPS environment variables](https://github.com/pytorch/pytorch/blob/v2.5.1/docs/source/mps_environment_variables.rst)

There is no need to install CUDA/NVCC on the Mac. For this image path, predictor hole/sprinkle areas set to zero avoid calling the custom connected-component kernel; ordinary mask interpolation still occurs. Do not confuse the builder's `apply_postprocessing` stability option with that optional CUDA cleanup. [Mask transform implementation](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/sam2/utils/transforms.py)

Required first-run evidence: installed source commit/config/checkpoint hash and dependency versions; one real-image box-prompt mask with correct dimensions and nonempty meaningful foreground; one repeat prompt on the cached image; clean model-missing failure; CPU timing/memory; then equivalent MPS output and timing if available. Neither inference success nor the accepted $5/room and 30-minute room-processing targets are established by setup research.
