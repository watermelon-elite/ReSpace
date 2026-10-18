# Model decision for complete, segmented room reconstruction

Research date: October 17, 2026 (America/Los_Angeles).

Current scope: reconstruct the captured room as a realistic explorable model with independent object instances, preserving its furniture and wall decor. Gemini editing comes later. Physically correct relighting is out of scope. Target: at most $5 per room and about 30 minutes. Local hardware: 8 GB Apple Silicon Mac; SAM 2 installation is underway/available in the parent implementation work, with no provisioned NVIDIA worker. This is a refreshed primary-source investigation, not a model benchmark. No model weights were downloaded, no captures uploaded, and no paid inference run for this research.

## Decision

**Choose the observed mesh + photo textures + multi-view SAM 2 instance pipeline as the reconstruction backbone. Choose official Pixal3D multi-view as the first object-completion model to test on an isolated NVIDIA worker.** Preserve captured visible surfaces and project real photos onto them; use generated geometry/appearance selectively for unobserved regions after alignment and validation.

**Internal fallback:** retain the measured/photo-textured segmented assets and architectural shell as checkpoints when furniture completion fails. Do not publish an incomplete room or replace the real furniture with generic assets. If a better occlusion-conditioned geometric prior is needed, test **WorldSculpt geometry-only + source-photo texturing** next, using exactly the same object evidence. **SAM 3D Objects with supplied pointmaps** is the third test for objects with only one good view, after access and hardware are available. Request a rescan when captured evidence prevents a usable room; infrastructure or budget failures require operational recovery, not rescanning.

This is a decision about the next implementable experiment, **not a claim that Pixal3D has won a ReSpace fidelity/cost benchmark**. None of the reviewed releases establishes that it can satisfy the full requirement unattended on this 8 GB Mac within 30 minutes. No current tested configuration establishes the $5 ceiling either. The generative tier therefore remains an external-worker integration with measured release gates, not a dependency to squeeze into the current worker.

Why this selection:

- Real calibrated captures should determine visible appearance, dimensions, decor and object identity. Re-generating the whole room needlessly risks changing those observations.
- Pixal3D has an actual maintained multi-view CLI, distinct multi-view weights visibly present in its first-party model repository, and an explicit textured GLB output path. It is more directly testable for appearance-preserving object completion than a geometry-only scene demo.
- WorldSculpt accepts off-center posed crops and is trained for occluded multi-view inputs, a strong match for room capture. Its released default currently skips texture generation, so adopting it as a finished photorealistic pipeline would overstate what was released.
- The strongest newly found RGB-D-specific alternative, RecGen, has a direct noncommercial product restriction; whole-scene Seen2Scene is geometric completion rather than the complete photo-textured instance solution.

## What is actually released

“Released” below means inspected official source/weight listing; it does not mean installed, reproduced or production-proven here.

| Candidate | Verified input and output | Release / hardware | Decision |
| --- | --- | --- | --- |
| DN-Splatter / AGS-Mesh | Posed RGB-D, depth/normal supervision; optimized Gaussians and extracted surface meshes | Public code, per-scene optimization; Linux/CUDA environment | Neural observed-surface benchmark; not an object-completion model |
| OMeGa | COLMAP images/cameras, initial mesh, normal maps; jointly optimized mesh and mesh-bound 2D Gaussians | Public CUDA/PyTorch code; default 30,000 optimization steps | Research challenger for surface quality; not automatic segmentation or hidden furniture completion |
| Pixal3D MV | Masked posed views of one object → generated geometry and textured GLB | Public code and separate MV checkpoints verified; TRELLIS.2/CUDA dependencies | **First completion test** |
| WorldSculpt | RGB views + existing instance masks + 3D boxes → separate generated objects in metric world | Public code and LoRA weights verified; released shell script is geometry-only | **Second test for occluded geometry**; real-photo texturing required |
| SAM 3D Objects | One image + object mask, optional pointmap → object shape/appearance/layout | Public code, gated weights; official Linux/NVIDIA ≥32 GB | Single-good-view challenger, no default official calibrated multi-view interface |
| RecGen | RGB + depth + mask + intrinsics, optional multiple views → mesh/splat/6-DoF pose | Public CUDA code; noncommercial license | Technically strong comparison; product use blocked without permission |
| Seen2Scene | Partial fused TSDF + layouts → completed scene geometry, boxes, volumes | Public Linux/CUDA code, declared pretrained checkpoints | Whole-room geometry experiment; no verified appearance/instance-completion contract |
| InSpace | Single equirectangular panorama/depth → textured room/layout/object meshes | Public code/checkpoints; Linux ≥24 GB; explicit research-only dependency warning | Plausible full-room generation reference, not default measured multi-view reconstruction |
| MIDI | Segmented single-image instances → compositional generated objects | Public code/models; single-image generative assumptions | Older scene-generation reference; not a stronger use of our RGB-D evidence |

Sources for this comparison: [DN-Splatter/AGS-Mesh](https://github.com/maturk/dn-splatter), [OMeGa README](https://raw.githubusercontent.com/Hao7un/OMeGa/main/README.md), [Pixal3D MV interface](https://github.com/TencentARC/Pixal3D#multi-view-inference), [WorldSculpt](https://github.com/AlayaLab/WorldSculpt), [SAM 3D Objects](https://github.com/facebookresearch/sam-3d-objects), [RecGen](https://github.com/TRI-ML/recgen), [Seen2Scene](https://github.com/quan-meng/seen2scene), [InSpace](https://github.com/naver/inspace), [MIDI](https://github.com/VAST-AI-Research/MIDI-3D).

## Reconstruction: DN-Splatter/AGS-Mesh versus OMeGa

DN-Splatter's paper targets Gaussian geometry/appearance using depth and normal priors; AGS-Mesh adds filtering and extraction. These methods can improve observed surface reconstruction, especially indoor regions poorly constrained by RGB alone. They do not provide persistent object identity, complete hidden chair backs, or separately reconstructed background behind furniture. [DN-Splatter paper](https://arxiv.org/abs/2403.17822), [project results](https://maturk.github.io/dn-splatter/)

The actual DN-Splatter project pins Nerfstudio 1.1.3 and gsplat 1.0.0. Its Pixi environment targets `linux-64`, CUDA 11.8 and PyTorch 2.2. A short 5,001-step Polycam example exists, but that is not evidence of full-room end-to-end processing time. Keep its environment separate from the current worker and from current gsplat main. Avoid optional normal predictors initially by testing depth-derived normals where supported. [Python dependencies](https://raw.githubusercontent.com/maturk/dn-splatter/main/pyproject.toml), [environment/example](https://raw.githubusercontent.com/maturk/dn-splatter/main/pixi.toml)

OMeGa's contribution is to keep mesh geometry in the optimization rather than extract it only afterward. Its paper reports improved indoor geometric metrics versus 2DGS; those are not object-completion or real-phone deployment results. Appearance remains attached to Gaussians, so an explicit mesh does not independently imply a faithful UV-textured export. [OMeGa paper](https://arxiv.org/abs/2509.24308)

**Selection:** DN/AGS before OMeGa for the first neural reconstruction comparison because its input adapters explicitly address smartphone RGB-D. Keep the current Open3D/OpenMVS conventional baseline. OMeGa is a follow-up if the mesh/appearance coupling materially helps quality. Adapting either method to preserve semantic ownership and measured coordinates remains ReSpace work. Its requirements include another incompatible Python stack (`numpy<2`, a pinned old PyCOLMAP fork), reinforcing isolation. [OMeGa requirements](https://raw.githubusercontent.com/Hao7un/OMeGa/main/examples/requirements.txt)

## Why Pixal3D MV is the first completion test

The paper explicitly addresses input fidelity through pixel-to-3D feature projection and extends it by combining views. Its “near reconstruction” language is a quality claim, not an exact visible-surface constraint. Generated surfaces can still change the sofa silhouette, number of legs, upholstery or artwork. [Pixal3D paper](https://arxiv.org/abs/2605.10922)

The public inference path is concrete:

```text
masked object views + transforms.json
  -> multi-view sparse-structure generation
  -> shape generation/decoding
  -> texture generation
  -> O-Voxel mesh postprocessing and GLB export
```

The official model listing contains `pipeline_mv.json` and actual `*_mv` sparse-structure, 512/1024 shape and 1024 texture safetensors. These were verified by viewing listings, not downloading them. The repository totals 46 GB including single- and multi-view models; do not download every file blindly. Each selected stage/decoder and auxiliary checkpoint must be pinned separately. [Model listing](https://huggingface.co/TencentARC/Pixal3D/tree/main), [checkpoint listing](https://huggingface.co/TencentARC/Pixal3D/tree/main/ckpts)

**Adapter work:** `inference_mv.py` uses camera-to-world Blender/NeRF conventions, horizontal FOV and a canonical main camera, with alpha as mask. It does not accept arbitrary ARKit intrinsics plus depth/confidence as an RGB-D reconstruction loss. ReSpace must derive object scale from depth, transform all views into one object frame, and resample/recalibrate crops to the model's framing contract. Using guessed four-view orbit cameras for handheld images is invalid. Its code builds DINOv3 conditioning and uses CUDA even with low-VRAM mode; SDPA substitutes for FlashAttention, not for CUDA. [Actual MV inference code](https://raw.githubusercontent.com/TencentARC/Pixal3D/master/inference_mv.py)

Low-VRAM mode loads stages on demand and lowers default resolution. It does not establish 8 GB host-memory or Apple MPS support. TRELLIS.2's official base requirements are Linux/NVIDIA ≥24 GB; its published seconds-per-asset timings use H100 and exclude ReSpace capture preprocessing, segmentation, alignment, validation and room assembly. [TRELLIS.2 requirements/timings](https://github.com/microsoft/TRELLIS.2#-installation)

Use generated geometry as a candidate. Align it to all confident object observations; retain/recover the photographed surface where supported, then reproject source images. Restrict generated texture to unobserved regions and keep a seam/visibility margin. Combining observed and generated surfaces robustly is itself an implementation task; a hard cut between two intersecting meshes is not an acceptable “completion” algorithm.

## What WorldSculpt adds—and what its release does not

WorldSculpt adapts Pixal3D to partially occluded multi-view scene objects and evaluates compositional generation in cluttered scenes. Its paper's synthetic benchmark and generated-world demonstrations do not establish fidelity on a measured iPhone room with real artwork. [WorldSculpt paper](https://arxiv.org/abs/2609.05416)

The official input preparation expects already-associated per-instance masks and world AABBs. It produces normalized crops, actual crop intrinsics, camera poses and a canonical-to-metric transform. This supports off-center cameras, making its geometry interface closer to unconstrained room capture than Pixal3D's simple orbit-style MV interface. It does **not** remove the instance-association problem. [Crop contract](https://raw.githubusercontent.com/AlayaLab/WorldSculpt/main/prepare_crops_scene.py)

The exact released shell path passes `--no_tex --no_glb` into reconstruction, then `--normal` into scene composition. Thus its default produces geometry-only scene GLBs, not captured furniture textures. The public checkpoint root visibly contains sparse-structure and shape adapters, not a released texture adapter folder. Code for textured mode exists but requires texture configuration/checkpoints that this default never supplies. Do not present that path as demonstrated textured completion. [Inference shell](https://raw.githubusercontent.com/AlayaLab/WorldSculpt/main/inference.sh), [published adapter folders](https://huggingface.co/AlayaLab/WorldSculpt/tree/main), [composition mode](https://raw.githubusercontent.com/AlayaLab/WorldSculpt/main/compose_scene.py)

Operational positives: batch reconstruction loads models once, supports selected instances/view caps/low VRAM, skips completed `mesh.pt` instances, and catches per-instance failures. A wrapper must inspect object completion records because a batch can finish despite failures. Remeshing and geometry export are separate substantial stages; do not measure only diffusion time. [Batch implementation](https://raw.githubusercontent.com/AlayaLab/WorldSculpt/main/reconstruct_batch.py), [object reconstruction/export](https://raw.githubusercontent.com/AlayaLab/WorldSculpt/main/reconstruct_object.py)

**Verdict:** a strong second experiment for occluded geometry, combined with real-photo texturing and the measured shell. It is not a complete ready-made raw-scan service, and its attractive whole-scene description does not justify replacing the backbone.

## SAM 3D Objects, RecGen and Seen2Scene

SAM 3D Objects reconstructs full masked objects from one image; its official setup requires Linux/NVIDIA ≥32 GB and gated checkpoint access. That access is not established here. [Setup](https://raw.githubusercontent.com/facebookresearch/sam-3d-objects/main/doc/setup.md), [model access gate](https://huggingface.co/facebook/sam-3d-objects)

Crucially, it can use measured geometry: the public `Inference.__call__` accepts `pointmap`, and its wrapper sets the renderer to PyTorch3D while disabling texture baking/mesh postprocessing and using vertex colors. Backprojecting a registered ARKit depth map can supply a candidate pointmap after checking its expected axes/shape and invalid-depth behavior. This improves its relevance versus an RGB-only caricature, but does not imply exact reconstruction or official multi-view supervision. [Inference source](https://raw.githubusercontent.com/facebookresearch/sam-3d-objects/main/notebook/inference.py), [pointmap pipeline](https://raw.githubusercontent.com/facebookresearch/sam-3d-objects/main/sam3d_objects/pipeline/inference_pipeline_pointmap.py)

RecGen is the most directly relevant newly identified alternative: its released interface accepts image/depth/mask/intrinsics and supports several views, generating object geometry, appearance and pose. More-view fusion increases compute; a stochastic mode trades some quality for latency. Its OBJ fallback and baked GLB have different appearance/export requirements. **Its TRI license expressly excludes revenue-generating products/services without a separate written license**, and inherited renderer code has additional restrictions. Keep it as a research comparison if permission is later obtained; it cannot silently become the commercial default. [Interface](https://github.com/TRI-ML/recgen), [actual license](https://raw.githubusercontent.com/TRI-ML/recgen/main/LICENSE)

Seen2Scene directly addresses partial scans with visibility-guided TSDF generation and layout boxes, trained with real-world incomplete scans. Its paper is a better fit for unknown whole-room **geometry** than single-view image generation. [Paper](https://arxiv.org/abs/2603.28548)

Its released code includes ARKitScenes processing, partial-scan completion and mesh/volume/box export. It requires Linux CUDA with fVDB, TorchSparse and FlashAttention builds. The README gives pretrained paths, but the linked model repository was not accessible through the research browser, so actual weight availability/access was **not independently verified**. No exact minimum VRAM or texture/instance-fidelity guarantee was established. Its output still needs source-photo appearance and persistent ownership. Therefore test it only if simple measured-plane shell completion fails; it is not today's complete product winner. [Executable instructions](https://raw.githubusercontent.com/quan-meng/seen2scene/github/README.md), [third-party notices](https://raw.githubusercontent.com/quan-meng/seen2scene/github/THIRD_PARTY_NOTICES.md)

InSpace is more turnkey for generated room/layout/asset GLBs but starts from one panorama, not the measured multi-view capture contract. Its README explicitly restricts the required runtime dependency stack to research/evaluation. GenRC completes sparse RGB-D meshes but does not itself provide persistent object instances. MIDI is single-image compositional generation. These are useful comparisons, not better defaults for preserving the captured room. [InSpace interface/license warning](https://raw.githubusercontent.com/naver/inspace/main/README.md), [GenRC](https://minfenli.github.io/GenRC/), [MIDI paper](https://arxiv.org/abs/2412.03558)

## Actual commercial and unattended-execution gates

Pixal3D's NOTICE explicitly includes released code/parameters/weights under MIT while preserving other components' terms. WorldSculpt has its own Apache components, MIT Pixal3D backbone, and gated DINOv3 weights under their own license. An ungated mirror URL in code does not replace the original model's terms. [Pixal3D NOTICE](https://raw.githubusercontent.com/TencentARC/Pixal3D/master/NOTICE), [WorldSculpt dependency map](https://raw.githubusercontent.com/AlayaLab/WorldSculpt/main/THIRD_PARTY_LICENSES.md)

The TRELLIS.2 setup script fetches nvdiffrast **v0.4.0** and a particular `nvdiffrec` **renderutils** fork. Inspection of those exact license files still shows research/noncommercial limits for others. “PBR output” or an MIT repository badge does not clear those executed paths. Before production, identify and replace restricted rendering/export functions or obtain permission; retain a tested, appropriately licensed geometry/texture export path. [Exact setup](https://raw.githubusercontent.com/microsoft/TRELLIS.2/main/setup.sh), [nvdiffrast v0.4.0 license](https://raw.githubusercontent.com/NVlabs/nvdiffrast/v0.4.0/LICENSE.txt), [renderutils fork license](https://raw.githubusercontent.com/JeffreyXiang/nvdiffrec/renderutils/LICENSE.txt)

SAM 3D Objects uses the custom SAM license rather than Apache/MIT; it grants broad uses subject to its stated conditions. Do not mislabel it categorically noncommercial. Dependencies and weights still need separate review. [SAM license](https://raw.githubusercontent.com/facebookresearch/sam-3d-objects/main/LICENSE)

To run unattended, prefetch approved checkpoints once, pin every repository/revision/config/seed, cache auxiliary encoders and upsamplers, verify hashes, and disable network fetching during jobs. WorldSculpt documents first-use `torch.hub`/remote-code dependencies. Public interactive demos have neither a demonstrated production SLA nor an established $5-per-room contract.

## Apple Silicon alternatives were checked

There are real community ports; “all 3D generation requires CUDA” is too broad:

- Hunyuan3D-Swift provides MLX shape/paint implementations. The author's current table reports about **5.6 GB** for small shape generation, but **25–39 GB** for painted/full pipelines. It does not establish this room's complete photo-faithful meshes on an 8 GB Mac. Model/algorithm terms remain separate from the Swift MIT license. [Port and measured author results](https://github.com/ZimengXiong/Hunyuan3D-Swift)
- `mlx-spatial` documents a SAM3D MLX bundle and CLI with optional pointmap. Its primary documented output is a Gaussian PLY, explicitly not a watertight mesh. No verified 8 GB whole-room performance or complete mesh export contract was established. Treat it as a separate local experiment, not a drop-in replacement. [Port documentation](https://github.com/appautomaton/mlx-spatial/blob/main/docs/sam3d.md)

Do not infer an 8 GB production path from shape-only memory, a successful model import, or a Gaussian preview. Keep CPU/SAM 2 reconstruction usable while evaluating an external completion tier.

## Preserve furniture, artwork and completeness independently

Proposed policy for this product:

1. Reconstruct and identify observed objects from images/depth, maintaining stable 3D IDs across views. Never replace an object merely because RoomPlan labels its category.
2. Build the measured architectural shell with actual openings and source-photo textures. Fill only missing architectural regions justified by those surfaces.
3. Treat flat wall art/screens/photos as their own thin surface instances with **captured image textures**. Do not ask an asset generator to redraw artwork, text, family photos or patterns. A mural can remain part of the wall texture with its own selection region if separate geometry would add nothing.
4. Complete only objects whose missing geometry affects exploration. Prefer multiple real views. Label unknown sides inferred; a plausible generated back is not a recovered observation.
5. Reject a generated candidate if its visible geometry/texture conflicts with observations. Retain the original visible object and report completion unavailable, or request targeted capture. Completion must not destroy the better evidence to hide a hole.
6. Merge instances with shell/background in one scene, without duplicated original furniture. Measure object identity, source-photo fidelity and newly exposed views separately.

These are engineering policies, not pretrained features. Existing measurements stay on immutable measured originals; retain the approved original/derived drift flag `max(5 cm, 2% of original dimension)` as documented in [the implementation plan](IMPLEMENTATION_PLAN.md).

## Smallest decisive test and budget

Do not run every model over the entire room first. Prepare one room with **three furniture objects**: one richly textured object, one partially occluded object, one thin/complex object, plus **one wall-decor instance**. Use 4–8 sharp spatially varied views per furniture object and additional withheld views; verify masks/calibration manually once so model comparison is meaningful. Use identical evidence for both candidates.

**Local preparation, no model downloads or paid work:** produce object masks/3D IDs, calibrated source-view overlays, observed surface meshes, projected dimensions, evidence coverage, and decor textures. Audit the actual capture upload first: the earlier read-only inventory found its declared original `scene_mesh` missing while RGB/depth/confidence/calibration were present. Do not rewrite its immutable manifest or fabricate that original.

**First bounded external experiment, only after a worker is available:** one Pixal3D MV object at 1024/low-VRAM settings, then WorldSculpt geometry-only on the same hard object. Load models once per batch, disable decorative renders, include export and source-photo baking in timing. Test SAM 3D with the object's measured pointmap only if both fail or only one useful view exists. Do not spend on scene-wide processing before one asset proves useful.

Record visible-view silhouette/texture comparison, depth residuals, hidden-side usability, alignment/contact, whole-object export integrity, peak VRAM/RAM, startup/cache time, total seconds and billed compute/storage/transfer. The winning candidate must preserve actual furniture and not change decor. Image scores alone cannot establish complete geometry.

Cost accounting, not a vendor quote:

```text
room_cost = worker_hourly_rate * billed_seconds / 3600
            + API/segmentation charges + storage/transfer + retry cost
```

At 30 billed minutes, compute alone must cost at most $10/hour to remain under $5, and less when other charges apply. Cold model downloads/builds must be amortized outside individual jobs or included honestly. Stop/reject when projected completion cost exceeds the remaining per-room budget. With nine detected objects, a 10-minute fixed preprocessing/export allowance leaves roughly 133 seconds/object sequentially; that is a planning envelope, **not an achieved speed**. Object count varies and some scenes will need additional detection beyond RoomPlan.

Promote the winner only after three full rooms meet measured quality, memory, 30-minute and $5 gates including failures/retries. If neither does, retain segmented observed reconstruction and expose the shortfall. The source-backed decision today is **Pixal3D MV first, WorldSculpt geometry plus real-photo texture second; no claim of a ready-made complete 8 GB local solution**.

## Follow-up: an executable non-NVIDIA experiment for the actual Mac

The parent implementation's read-only cloud audit found the existing VM is a terminated CPU instance and the account's global GPU quota is zero. Therefore the external candidates above remain conditional; they cannot be benchmarked on that account today. This section selects a smaller **Apple-local object experiment**, not a replacement whole-room model. It updates the earlier brief Apple survey with actual source/export inspection. No installation, download, resource change or inference was performed for this follow-up.

### First local candidate: Hunyuan3D-Swift shape-small, then source-photo texture

**Yes: separate shape generation from learned painting.** The released Swift `shape` command actually calls the MLX shape generator and writes triangle GLB geometry. Its minimal writer contains positions and indices, with no UVs, normals, textures or metric pose. This gives us real surface geometry rather than only Gaussian splats. ReSpace must add alignment, normals and UV/photo projection. [Shape CLI source](https://raw.githubusercontent.com/ZimengXiong/Hunyuan3D-Swift/main/Sources/hy3d/Shape.swift), [GLB writer](https://raw.githubusercontent.com/ZimengXiong/Hunyuan3D-Swift/main/Sources/Hy3DMLX/GLB.swift)

The published small bundle is actually listed: `config.yaml` and a **3.82 GB** fp16 safetensors checkpoint repackaged from Hunyuan3D-2mini. It includes the layout expected by the Swift loader. Its shape pipeline consumes **one object image**, not calibrated multi-view depth or an existing partial mesh. Alpha preprocessing recenters the object and composites onto white; use a correct SAM 2 RGBA crop, not the unmasked full room. [Weight listing/provenance](https://huggingface.co/zimengxiong/hunyuan3d-mlx-shape-small/tree/main), [preprocessing](https://raw.githubusercontent.com/ZimengXiong/Hunyuan3D-Swift/main/Sources/Hy3DMLX/Preprocess.swift)

The author reports shape-small at ~5.6 GB peak for 30 steps and octree 256, whereas paint/full-generation paths exceed this Mac's memory. That report is **not a measurement on our Mac**. The 8 GB is shared with macOS, other apps, host copies, loading/quantization temporaries and geometry processing. Loading and running SAM 2, Open3D and the shape model concurrently could exhaust it. [Author timings/memory](https://raw.githubusercontent.com/ZimengXiong/Hunyuan3D-Swift/main/README.md)

The inspected loader keeps weights fp16, caps the MLX cache, supports 4/8-bit quantization of eligible DiT/DINO linear layers, clears intermediate cache between stages and exposes cancellation. Its comments estimate 4-bit resident weights near 1.4 GB, but the code initially reads fp16 weights before packing them: **1.4 GB is not a verified process peak**. Quantization can also change geometry. Use the quantized route for the first capacity probe, and compare fp16 only when safe. [Generator/quantization source](https://raw.githubusercontent.com/ZimengXiong/Hunyuan3D-Swift/main/Sources/Hy3DMLX/ShapeGenerator.swift)

Build requirements are explicit: Swift tools 6.0, macOS 14 target and mlx-swift in the 0.31.x line, with `Package.resolved` supplying the reproducible resolution. Isolate it from the app/worker; save the exact repository commit and dependency lock. Example for a **future authorized run**, not executed here:

```sh
swift build -c release
.build/release/hy3d shape object-rgba.png -o candidate.glb \
  --weights /absolute/path/to/shape-small \
  --quantize 4 --octree 256 --steps 30 --seed 42
```

[Package manifest](https://raw.githubusercontent.com/ZimengXiong/Hunyuan3D-Swift/main/Package.swift)

**Photo-baking adapter proposal:** generate one candidate; terminate the model subprocess to release its memory; convert/alignment-fit the geometry into the object's measured frame; validate it against every retained object mask and confident depth; and use our existing calibrated OpenMVS `TextureMesh` path or a visibility-aware CPU/Metal baker to project **real source photos**. Supply mask-conditioned images/visibility so surrounding furniture is not painted onto the object. Only unseen surfaces receive texture continuation/inferred colors. This avoids loading Hunyuan's painting model entirely. It does not fill true missing image evidence, solve visible-shape drift, or turn the single-view generator into a multi-view model. Joint geometry blending and seam handling remain our implementation work.

**Commercial gate:** the Swift source is MIT, but the small weights use Tencent's community terms. The inspected original license excludes EU/UK/South Korea territory, including use/display of outputs outside its territory, and has additional distribution/use/commercial conditions. It is not an unrestricted worldwide product default, nor categorically research-only. Establish applicability before including it in the product. [Weight license declaration](https://huggingface.co/zimengxiong/hunyuan3d-mlx-shape-small/raw/main/README.md), [actual Tencent license](https://raw.githubusercontent.com/Tencent-Hunyuan/Hunyuan3D-2/main/LICENSE)

### Other non-NVIDIA paths worth distinguishing

| Path | Actual inspected support | Why it is not the first 8 GB experiment |
| --- | --- | --- |
| `mlx-spatial` TRELLIS.2 | Released single-object shape-OBJ script; native Metal/CPU mesh/UV/texture GLB path, no CUDA runtime. Uses upstream safetensors plus separate DINOv3; RGBA can avoid RMBG. | No verified 8 GB peak here; native remesh is a behavior approximation and reference-scale equivalence remains unestablished. More components than the small Swift shape path. [TRELLIS docs](https://raw.githubusercontent.com/appautomaton/mlx-spatial/main/docs/trellis2.md), [shape script](https://raw.githubusercontent.com/appautomaton/mlx-spatial/main/scripts/trellis2/generate_shape.py) |
| `mlx-spatial` SAM3D | Root capability table advertises optional GLB; architecture names mesh decoder/export modules. Detailed recommended script currently writes Gaussian PLY/trace and accepts a single image/mask. | Mesh-export code could not be retrieved for independent inspection; do not assume a splat-to-solid conversion. No verified 8 GB mesh path or multi-view fit. [Root capabilities](https://github.com/appautomaton/mlx-spatial), [architecture](https://raw.githubusercontent.com/appautomaton/mlx-spatial/main/docs/architecture.md), [recommended script](https://raw.githubusercontent.com/appautomaton/mlx-spatial/main/scripts/sam3d/reconstruct.py) |
| `mlx-spatial` Pixal3D | Checkpoint-backed staged MLX and native GLB export documented. | Explicitly in development; no verified released calibrated multi-view Apple path or 8 GB peak. No production-equivalence claim. [Port status](https://raw.githubusercontent.com/appautomaton/mlx-spatial/main/docs/pixal3d.md) |
| TripoSR CPU | Official CLI explicitly falls back to CPU without CUDA; real OBJ/GLB extraction and CPU marching-cubes fallback. Public 1.68 GB model listing, MIT model/code. | Useful **license-simpler fallback**; single-image generative fidelity and actual CPU time/peak remain unbenchmarked. Several image arguments are separate objects, not joint multi-view inference. [CLI](https://raw.githubusercontent.com/VAST-AI-Research/TripoSR/main/run.py), [extraction](https://raw.githubusercontent.com/VAST-AI-Research/TripoSR/main/tsr/models/isosurface.py), [weights](https://huggingface.co/stabilityai/TripoSR/tree/main), [MIT release](https://github.com/VAST-AI-Research/TripoSR) |
| Official Stable Fast 3D | CPU supported, MPS experimental, textured GLB. Official docs recommend CPU below 32 GB unified memory; MPS was tested on a 64 GB M1 Max. | Does not substantiate an 8 GB MPS solution; gated weights and community commercial terms apply. [Official requirements](https://raw.githubusercontent.com/Stability-AI/stable-fast-3d/main/README.md) |
| Community SF3D MLX | Real port source; author reports MLX/NumPy finishing with marching tetrahedra still on CPU PyTorch and module-level parity checks. | Interesting next experiment, but no verified peak-memory figure or 8 GB result found. Its speed comparisons do not establish that memory/quality on our Mac. Stability community terms include commercial conditions/attribution. [Port report](https://github.com/bahaehmimdi/stable-fast-3d-mlx), [terms](https://raw.githubusercontent.com/bahaehmimdi/stable-fast-3d-mlx/main/LICENSE.md) |

An Apple-native export path can avoid **executing** NVIDIA CUDA renderers; its actual implementation/derivative and weight licenses still require inspection. It is not automatically subject to every upstream optional CUDA path, and a “native” label is not blanket commercial clearance either.

No reviewed local generator jointly consumes our posed RGB-D observations and partial mesh to guarantee completed furniture while holding visible evidence fixed. Multi-view measured observations should therefore be used for alignment, candidate rejection and real-photo texture after generation. Running independent single-view generations and unioning them would not solve consistent object completion.

### Smallest useful local experiment

After an approved checkpoint is available, use **one modest, well-masked furniture object** with 3–5 real calibrated views: generate from the best single image using shape-small Q4/octree-256, then hold the other views out of generation for silhouette/depth validation. Do not test artwork, mirrors, glass, or a fused room as the first object. Persist the unmodified observed object and candidate separately. Avoid all model previews and learned paint; unload SAM 2 and stop reconstruction worker processes during the capacity probe without changing capture data.

Measure total process RSS/MLX allocation, system memory pressure/swap, loading/quantization peak, mesh extraction peak and full wall time. Abort cleanly on memory pressure or the explicit process deadline; do not rely only on the model's steady-state allocation. If Q4 fails capacity or gives poor shape, try TripoSR CPU on the same object with reduced extraction resolution/chunk size, retaining the best observed reconstruction. A reduced-resolution smoke test is not a quality result.

Only if the candidate matches withheld views should the next experiment align it to depth and bake a small source-photo atlas after the model exits. Check that source-supported upholstery/detail survives, the back is plausible and labeled inferred, and the object remains independent in the scene. Repeat on a thin object before batching. Local compute avoids a paid GPU bill but does not establish the 30-minute room target, full hidden-surface fidelity or acceptable license coverage. **Practical immediate choice: one isolated Hunyuan shape-small + photo-bake experiment; TripoSR CPU fallback; keep the current segmented observed room as the usable output.**

## Local implementation postscript

The parent subsequently installed the pinned TripoSR CPU recipe and tested the official bundled chair example at extraction resolutions 64 and 128. Both runs exported OBJ files, but both were non-watertight and self-intersecting. The higher-resolution run therefore did not resolve the structural failure. This supports retaining TripoSR as a bounded candidate experiment, **not** adopting it as a completed captured-furniture stage. It does not establish that other inputs or extraction settings fail, and it is not a room-fidelity benchmark. Exact runtimes, memory samples, tests and remaining integration work are in [implementation status](IMPLEMENTATION_STATUS.md).
