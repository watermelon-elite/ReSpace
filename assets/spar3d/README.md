# SPAR3D catalog reconstruction

Offline image-to-mesh reconstruction for catalog Product assets, using Stability
AI's [SPAR3D](https://github.com/Stability-AI/stable-point-aware-3d). One product
photograph in, one textured GLB out.

This is the first half of the asset pipeline required by [`SPEC.md`](../../SPEC.md)
§11. The second half is [`assets/prepare.py`](../prepare.py), which converts GLB to
USDZ and applies verified dimensions:

```
product photo -> run_spar3d.py -> mesh.glb -> prepare.py -> model.usdz
```

**A reconstruction establishes appearance only.** Every mesh comes out normalized
to roughly unit size, so it carries no physical scale at all; this was measured,
not assumed. Real dimensions come from Product evidence and are applied by
`prepare.py --dimensions`. Never infer a size from generated geometry.

Runs offline, outside the API request path. No live image-to-3D generation is
required for discovered Products.

## Layout

Code is versioned here; the runtime, weights and generated meshes are not, because
they are large and reproducible.

| Where | What | Size |
|---|---|---|
| `assets/spar3d/` (this repo) | scripts and this document | small |
| `$SPAR3D_LAB`, default `~/spar3d-lab` | venv, upstream checkout, images, meshes | ~8 GB |
| `~/.cache/huggingface` | model weights, shared between labs | 6.8 GB |

Do not put the lab under `/tmp`. macOS clears it on reboot, which has already
destroyed one full run.

## Prerequisites

- Apple Silicon Mac. Homebrew and [uv](https://docs.astral.sh/uv/) on `PATH`.
- A Hugging Face account that has accepted the Stability AI Community License at
  <https://huggingface.co/stabilityai/stable-point-aware-3d>. The weights are
  gated; anonymous download returns HTTP 401.
- A read token exported as `HF_TOKEN`, or `hf auth login`. Pass it through the
  environment only. Never commit it.
- ~15 GB free disk.

Confirm license eligibility before using output for anything beyond evaluation.

## Quick start

```sh
bash assets/spar3d/setup.sh                      # ~10 min, idempotent
python assets/spar3d/scrape_ikea.py              # test inputs only, not catalog
export HF_TOKEN=hf_...
~/spar3d-lab/.venv/bin/python assets/spar3d/run_spar3d.py --device cpu
```

Output lands in `~/spar3d-lab/out/<slug>/` as `mesh.glb`, `points.ply` (the
intermediate point cloud), `input.png` (the background-removed crop fed to the
model) and `done.json`.

Useful flags: `--limit N`, `--only <substring>`, `--redo`, `--texture-resolution`.

## Measured results

15 IKEA products (6 tables, 3 shelf units, 6 lamps), Apple M5 Max / 128 GB,
macOS 26.6.2, torch 2.14.1, CPU, 1024px textures, 2026-10-18.

| | |
|---|---|
| Inference | **79 s per product** (77.6–84.0 s), strikingly consistent |
| One-time model load | ~60 s per process |
| Mesh size | 3.7k–32.3k vertices, 340 KB–1.9 MB |
| Total | 16.4 MB for 15 models; **all under SPEC's 3 MB target** |
| Textures | 1024px baked atlas on all 15 |
| Watertight | none — expected for single-image reconstruction |

At SPEC's catalog scale (~60 Products) that is roughly 80 minutes of unattended
offline work, which is acceptable for a step outside request latency.

## Device support

**`--device cpu` is the default and the right choice while anyone is using the
machine.** `--device mps` now works and is about 2.5x faster, but it visibly
degrades the desktop; prefer it only for unattended bulk preparation.

| | CPU | MPS |
|---|---|---|
| Inference, same product | 78.7 s | **31.3 s** |
| Mesh | 3709v / 5608f / 340 KB | 3723v / 5580f / 346 KB |
| Bounds, volume, texture | — | equivalent within 2% |

Verified on one product (the smallest mesh, 3.7k vertices) with the
`pca_lowrank` patch below. **Not yet verified across all 15**, and in particular
not at the largest mesh (32k vertices), where the patched path matters most.

Stability caveat, observed first-hand: MPS runs contend with WindowServer for the
GPU. One run produced a brief UI freeze — it recovered without a watchdog report,
but an earlier GPU hang on this machine escalated to a forced reboot. Treat MPS
as disruptive, and do not run a GPU batch on a machine someone is working on.

The rest of this section records why MPS failed before the patch.

Before the patch, `--device mps` appeared to deadlock. The network itself runs on
the GPU, but post-processing stalled here:

```
uv_unwrapper/unwrap.py:555 _align_mesh_with_main_axis
  -> torch.pca_lowrank -> _svd_lowrank -> torch.linalg.svd
     -> _linalg_check_errors -> Tensor::item<bool>()
        -> mps_copy_ -> dispatch_sync   [blocks forever]
```

`torch.linalg.svd` is implemented on MPS, so `PYTORCH_ENABLE_MPS_FALLBACK=1` never
triggers. Its internal error check reads one value back from the GPU using
`dispatch_sync` on the same serial Metal queue it is waiting on, so the queue
cannot drain. `run_spar3d.py` already routes SVD through the CPU, which clears
that specific call, but the hang then moves to the next `.cpu()` copy — so one
patch is not sufficient.

### Root cause (confirmed): an upstream torch 2.14 regression

The stall is not a deadlock. It is `torch.linalg.qr` on MPS materializing a full
`m x m` Q instead of the reduced `m x q`, reached once per mesh through
`uv_unwrapper/unwrap.py:555` → `torch.pca_lowrank(vertices, q=2)`.

Measured on this hardware, torch 2.14.1:

| `linalg.qr` input | CPU | MPS |
|---|---|---|
| (1000, 2) | instant | 0.22 s |
| (4444, 2) | instant | **23.5 s** |
| (17377, 2) | instant | **unfinished after 216 s** |
| (200000, 3) via `pca_lowrank` | fine | `RuntimeError: Invalid buffer size: 149.01 GiB` |

149.01 GiB is exactly 200000^2 x 4 bytes, confirming the `m x m` workspace. Our
meshes run 3.7k–32k vertices, so the buffer (4.2 GB at 32,336) fits in 128 GB and
does not raise — it simply grinds, which presents as a hang. `pca_lowrank` issues
three such QRs per mesh. A stack sample showed 100% of main-thread time in
`waitUntilCompleted`, with the GPU pinned at 100% and CPU frozen: the GPU
genuinely executing an oversized kernel, not a wedged queue.

This is [pytorch#187567](https://github.com/pytorch/pytorch/issues/187567),
a regression introduced in 2.14 when the MPSGraph linalg path was replaced with
hand-written Metal kernels. Affects 2.12–2.14.1; fixed on main, shipping in 2.15.
`linalg.svd` itself is fine on MPS at these sizes, so the earlier SVD patch
addressed the wrong call — `pca_lowrank` runs QR first.

`run_spar3d.py` now also routes `torch.pca_lowrank` to the CPU. With that patch
applied, `--device mps` reconstructs end to end — verified on one product, as
recorded under Device support, and not yet across the full set. When torch 2.15
is released, drop both patches and raise `TORCH_VERSION` in `setup.sh` instead.

Two practical notes:

- **SIGINT cannot stop a process blocked in `waitUntilCompleted`** — Python
  cannot run its handler inside a blocking C call. Two SIGINTs with 75 s of grace
  had no effect; it exited only on SIGTERM. Any watchdog needs SIGTERM in the
  ladder. Still never SIGKILL.
- A single tiny tensor pinned the GPU at 100% for about four minutes. Treat MPS
  experiments as disruptive on a machine someone is using.

Repro scripts are kept outside the repo at `~/spar3d-mps-lab/repro/`: `t1_svd.py`
isolates SVD and `pca_lowrank`, `t2_qr.py` measures the full-vs-reduced Q shape
across realistic vertex counts, and `guard.py` runs either under a wall-clock
budget escalating SIGINT to SIGTERM.

**Downgrading torch is not an escape route.** torch 2.6 and older ship a
`c10/util/strong_type.h` that specializes `std::is_arithmetic`, which current
Apple clang rejects (`-Winvalid-specialization`), so neither native extension
compiles. Newer torch compiles but deadlocks; older torch does not compile.
Upstream calls Apple Silicon support experimental.

Expected upside if MPS is ever fixed is moderate, not dramatic: SPAR3D only uses
`bfloat16` autocast on CUDA, so Metal would run full `float32`, and `uv_unwrapper`
is CPU-only C++ regardless of device.

> **Never `kill -9` a process holding GPU work.** Doing so wedged the Metal
> command queue, WindowServer hit a userspace watchdog timeout, and the machine
> rebooted. Use SIGINT and wait.

## Upstream workarounds

All five are applied by `setup.sh` and marked `WORKAROUND` in it.

| # | Problem | Handling |
|---|---|---|
| 1 | AlphaCLIP's `setup.py` imports `pkg_resources`, removed in setuptools 81+ | pin `setuptools==69.5.1`, install with real pip (uv silently re-upgrades it) |
| 2 | `uv_unwrapper` compiles with `-fopenmp`; Apple clang ships no libomp | `brew install libomp`, export `CPATH`/`LIBRARY_PATH` |
| 3 | torch ≤2.6 headers do not compile with current Apple clang | pin torch 2.14.1; do not downgrade |
| 4 | `requirements.txt` lists the two extensions by relative path, and both import torch in `setup.py` | install separately with `--no-build-isolation` |
| 5 | `transparent-background` imports a GUI module; current flet renamed its controls | pin `flet==0.24.1` |

Upstream `run.py` is not used: it names outputs by batch index, losing the Product
name, and reads an argparse option that only exists when the optional remeshing
libraries are installed. `run_spar3d.py` calls `SPAR3D.run_image` directly.

## Interruption behaviour

Reconstruction is expensive, so the runner is built to be interrupted:

- Each Product writes a `done.json` marker keyed to its input image's sha256.
  Re-running skips completed work; changing an image rebuilds only that Product.
- Meshes and manifests are written to a `.part` file and renamed, so an
  interrupted write cannot leave a truncated file that looks complete.
- Progress is appended to an fsync'd `out/events.jsonl` rather than rewriting one
  results file. A crash loses at most the Product in flight.
- A failure is recorded and the batch continues. `results.json` is a convenience
  view, rebuilt from the durable markers.
- `scrape_ikea.py` verifies images by sha256 and is seeded, so re-running
  reproduces the same set.

This has been exercised twice in anger — an unexpected reboot and a session
teardown — and in both cases resuming cost only the item in flight.

## Known limits

- MPS verified on one product only, and not at the largest mesh. CPU remains the
  default. See Device support.
- Remeshing is disabled: `gpytoolbox` and `pynanoinstantmeshes` are not installed,
  so `--remesh` options are unavailable. Meshes are raw marching-cubes output.
- No mesh has been inspected in RealityKit yet, and the GLB→USDZ conversion of
  SPAR3D output has not been run through `prepare.py`. Orientation and the yaw
  needed for the `+Z` forward convention are unconfirmed.
- Open structures (bookcase cavities, thin frames) are the expected failure mode
  for single-image reconstruction and have not been graded.
- `scrape_ikea.py` produces test inputs only. Those Products carry no verified
  dimension evidence and must not be promoted to catalog assets.
