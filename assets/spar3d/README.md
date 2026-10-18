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
~/spar3d-lab/.venv-prepare/bin/python assets/spar3d/grade.py   # convert and grade
```

Two environments, and they are not interchangeable. `.venv` runs SPAR3D on
trimesh 4.4.1, which the upstream extensions require; `.venv-prepare` runs
`assets/prepare.py` on the trimesh 5.1.1 that `assets/requirements.txt` pins.
Build the second with:

```sh
uv venv --python 3.11 ~/spar3d-lab/.venv-prepare
VIRTUAL_ENV=~/spar3d-lab/.venv-prepare uv pip install -r assets/requirements.txt
```

Output lands in `~/spar3d-lab/out/<slug>/` as `mesh.glb`, `points.ply` (the
intermediate point cloud), `input.png` (the background-removed crop fed to the
model) and `done.json`.

Useful flags: `--limit N`, `--only <substring>`, `--redo`, `--texture-resolution`.

## Measured results

First round: 15 IKEA products (6 tables, 3 shelf units, 6 lamps), Apple M5 Max
/ 128 GB, macOS 26.6.2, torch 2.14.1, CPU, 1024px textures, 2026-10-18. A second
round added 15 more (3 each of chairs, armchairs, sofas, desks, plants) on MPS;
see Device support for its timings.

| | |
|---|---|
| Inference | **79 s per product** (77.6–84.0 s), strikingly consistent |
| One-time model load | ~60 s cold, 6.7–8.1 s once the weights are cached |
| Mesh size | 3.7k–32.3k vertices, 340 KB–1.9 MB |
| Total | 16.4 MB for 15 models; **all under SPEC's 3 MB target** |
| Textures | 1024px baked atlas on all 15 |
| Watertight | none — expected for single-image reconstruction |

At SPEC's catalog scale (~60 Products) that is roughly 80 minutes of unattended
offline work, which is acceptable for a step outside request latency.

## Reconstruction quality

All 30 test products were converted through `assets/prepare.py` and rendered
from four azimuths, textured and as untextured clay, against the source
photograph. Clay is the deciding view: a baked photo texture paints detail onto
flat geometry and makes a slab look like a bookcase.

Every one of the 30 packaged, kept its baked texture and came in under SPEC's
3 MB ceiling (684 KB–2.2 MB). Packaging is not quality; the verdicts below are
by eye, from the sheets.

Evidence level differs by category and the table says so. The first 15 were
each reviewed individually. Of the second 15, all three chairs, all three
plants and two of three desks were reviewed, but only four of the six sofas and
armchairs. Where a category says "n of m reviewed", the rest are packaged but
unseen, and the first round is the reason that matters: tables split two good,
two partial and two failing inside a single category.

| Category | Verdict | What happens |
|---|---|---|
| Lamps (6/6) | **use** | Shades, turned stems, thin twin-stalk frames and glass globes all survive. Pleating on ÅRSTID is real geometry, not texture. |
| Chairs (3/3) | **use, check colour** | The strongest new category for geometry. Legs stay separate, the seat survives as a surface and the gap under the backrest stays open. SKOGSTA resolves every Windsor spindle and the leg stretchers. Legs splay in profile, the usual single-image depth ambiguity. SKOGSTA's black finish came back pale grey; see "Colour is not reliable". |
| Tables (2 good, 2 partial, 2 fail) | **gate individually** | Open steel frames reconstruct well. Tops seen edge-on detach and float. |
| Desks (3/3 geometry, 1 leaning) | **gate individually** | Trestles and thin tops survive. TROTTEN leans uncorrected; LÄNGDHOPP's two-tier pull-out garbles into a recognizable but wrong structure. |
| Sofas and armchairs (4 of 6 reviewed) | **use front-facing only** | Arms, separate back and seat cushions and turned legs all land. Every one is hollow underneath. Boxy forms also get a thin back panel; HERRÅKRA's curved tub back came back properly closed, so that part is form-dependent. Fine against a wall, wrong if seen from below. |
| Shelf units (0/3) | **stand-in** | BILLY comes back a solid slab with the shelves painted on. No cavity, no opening. |
| Plants (0/3) | **stand-in** | FEJKA fuses every blade into one solid brick. The texture hides it; the clay view is unambiguous. |

Per [`SPEC.md`](../../SPEC.md) §11, bookcases must use a stand-in, and plants
join them. Lamps and chairs are safe. Tables and desks need a per-Product check
before promotion. Upholstery is usable where it is placed against a wall, which
is where a solver puts it anyway.

Rugs, art and mirrors were deliberately not tested. SPEC §11 already allows
them to render as textured panels, so a mesh buys nothing.

What predicts success is not thickness but whether the silhouette explains the
shape. Thin tube frames photographed whole (VITTSJÖ, SIMRISHAMN) come back
accurate; a horizontal plane viewed edge-on has almost no silhouette, so
tabletops detach and drift (ÖSTAVALL, ÖRTRÄSK, OLSERÖD). Repeated interior
cavities read as surface texture and fill in solid (all three BILLYs). The
single large cavity of the BILLY height-extension unit partly opened, but
warped, with an open back and an invented blue patch where the photo showed
nothing.

The second round sharpened this. Chairs were the open question — thin legs like
the frames that worked, but a flat seat like the tops that failed — and they
passed, seat included. So an edge-on plane is not fatal by itself; what killed
the tabletops was a plane with nothing around it to fix its depth. A seat
bounded by legs and a backrest is constrained from several directions at once.

FEJKA restates the cavity failure at a finer scale: hundreds of gaps between
grass blades, none individually resolvable, all filled in. The rule is the same
one that sinks BILLY, and the practical test is whether the detail that matters
survives in the clay view, since the baked photo texture will paint it back on
either way.

What the second round added is a failure the first could not show: the open
shell. Sofas and armchairs are convincing from the front and hollow underneath,
because no part of a single front-on photograph constrains a surface the camera
never saw. That is invisible in the metrics — all six packaged cleanly — and
obvious in the clay views from 90° and 180°.

### Colour is not reliable

Geometry and colour fail independently, and the second round found colour
failing on products whose shape came back well.

| Source finish | Result |
|---|---|
| SKOGSTA, black stain | pale grey — badly wrong, on the best geometry in the set |
| HERRÅKRA, warm tan | shifted yellow-green |
| Greys, creams, sage, pale wood | faithful |

The pattern across what was reviewed is that **neutral finishes survive and
dark or saturated ones do not** (inferred from six products, not confirmed —
nobody has tested a saturated colour deliberately). The likely cause is the
delighting step, which has to separate the photograph's lighting from the
object's own colour and has the least to work with at the dark end.

This matters more than it looks. A catalog Product's appearance includes its
colour, a reconstruction establishes appearance, and a black chair arriving
grey is wrong in a way no size check catches. **Check colour against the source
photograph before promoting any Product with a dark or saturated finish**, and
prefer a tinted stand-in over a mesh whose colour is wrong.

### Every mesh leans

No output is upright. Measured as the angle between vertical and the axis
joining the top and bottom decile centroids:

| | tilt from vertical |
|---|---|
| Lamps | 1.8°–10.8°, consistently backwards |
| Shelf units | 3.1°–16.6° |
| Chairs | 4.6°–6.8°, small enough to need no correction |
| Tables, desks | inflated by detached parts; the metric assumes a tall axial shape |
| Sofas, armchairs | reads 33°–39°, which the renders contradict; they sit level. The metric is measuring width, not lean. Do not trust it here. |

The cause is that product photography shoots slightly from above and the
reconstruction is in camera space, not world space.

`assets/spar3d/upright.py` proposes a correction, applied through the
`prepare.py --pitch` option added for it:

```sh
~/spar3d-lab/.venv-prepare/bin/python assets/spar3d/upright.py   # writes pitch.json
```

It fits a plane to the vertices the object rests on and measures how far that
plane is from level. **Opt-in, defaulting to none**, because it is only
trustworthy for some shapes and Kenney sources are authored upright already.

Only pitch is corrected, never roll. The error has one known cause, a camera
looking down, which is a single rotation about the horizontal axis across the
view. Solving for the full plane normal also rolls the model sideways, which was
measured to skew slab reconstructions that were not leaning that way at all.

| | Result |
|---|---|
| Lamps | all six visibly upright from every azimuth; this is the category that passed grading |
| Tables | correctly declined on two, negligible change on the rest |
| Chairs | declined on all three, correctly: thin legs give too narrow a base, and at 4.6°–6.8° they did not need it |
| Desks | corrected two well (11.4°→4.1°); declined TROTTEN, which does lean and is left leaning |
| Sofas, armchairs | declined on all three sofas; applied 3.1°–7.7° to the armchairs with no visible harm |
| Shelf units | over-corrected, because their reconstructed underside is itself slanted |
| Plants | refused one at 69°, which the limit caught |

The shelf failure is tolerated, not solved: those Products take stand-ins. It
does mean the estimate is a **proposal**. Check it on a grading sheet before
trusting it for a category that has not been through this.

The narrow-base guard cuts both ways. It is right on chairs, which do not need
a correction, and wrong on TROTTEN, which does and is refused for the same
reason: trestle feet are too narrow to fit a plane to. A thin-legged Product
that genuinely leans has no correction available today.

Where the base is one leg tip or a floating fragment, the plane is numerically
fine and physically meaningless, so the estimator declines instead of guessing,
and refuses any correction beyond 30°. The chosen angle is recorded per model as
`source_pitch_degrees`, so a conversion stays reproducible and auditable.

### Reproducing the grading

```sh
~/spar3d-lab/.venv-prepare/bin/python assets/spar3d/grade.py [slug-substring]
```

`grade.py` converts every mesh through `prepare.py`, records size, texture
survival and tilt, and writes one comparison sheet per Product to
`~/spar3d-lab/grade/sheets/`. `render.py` behind it is a small software
rasterizer: no GPU, no OpenGL, no window, so it cannot disturb anyone using the
machine and cannot repeat the MPS incident. All 30 take about 2.5 min on CPU.

A software renderer is deliberate. `qlmanage` hangs indefinitely on USDZ on this
machine — including on the Kenney assets already committed, so it is the tool
that is broken, not our output — which left no way to see what was being
packaged.

## Device support

**`--device cpu` is the default and the right choice while anyone is using the
machine.** `--device mps` is roughly 7x faster and is now verified across a
full batch, but it visibly degrades the desktop; prefer it only for unattended
bulk preparation.

| | CPU | MPS |
|---|---|---|
| Inference per product | 77.6–84.0 s (16 products) | **9.8–11.4 s** (14 products) |
| One-time model load | 6.7 s | 7.1–8.1 s |
| Mesh, same product | 3709v / 5608f / 340 KB | 3723v / 5580f / 346 KB |
| Bounds, volume, texture | — | equivalent within 2% |

Verified 2026-10-18 across 14 products spanning 11.8k–32.2k vertices, which
includes the largest mesh, where the `pca_lowrank` patch below matters most.
Fourteen products reconstructed in 2 min 45 s wall including model load.

This supersedes an earlier figure of 31.3 s measured on a single product. The
gap is almost certainly cold Metal shader compilation on that first-ever GPU
run, cached on disk by the time of this batch (inferred, not confirmed — the
original condition cannot be recreated now that the cache is warm). The CPU
figure was unchanged between the two measurements, so the difference is on the
GPU side rather than in how the two were timed.

Stability caveat, observed first-hand: MPS runs contend with WindowServer for the
GPU. One run produced a brief UI freeze — it recovered without a watchdog report,
but an earlier GPU hang on this machine escalated to a forced reboot. Treat MPS
as disruptive, and do not run a GPU batch on a machine someone is working on.

### Reconstruct one at a time

**Do not parallelize reconstruction.** A single generation already saturates the
GPU, so every way of running more at once measured slower than running them in
sequence. `assets/spar3d/throughput.py` records the ramp; rerun it if the
hardware or torch version changes, because the conclusion is a property of this
machine and not of the code.

| Configuration | Per product | Throughput | Memory |
|---|---|---|---|
| 1 process, 1 image | 11.52 s | 5.2/min | 15.3 GB |
| 1 process, 2 images | 11.31 s | 5.3/min | 15.3 GB |
| 1 process, 4 images | 13.94 s | 4.3/min | 15.3 GB |
| 2 processes, 1 image | 13.55 s | 4.4/min | 30.5 GB |

Two processes cost 15% throughput for twice the memory, and a batch of four
costs 21%. A batch of two is within noise of serial — 10.08 s against 10.36 s
mean inference, against a ±0.42 s spread inside the serial run itself — and is
not worth the weaker failure mode, since an interrupted chunk loses two products
instead of one. `run_image` does accept a list and batches genuinely, stacking
into one tensor; it simply buys nothing here.

Memory is the second reason, and it binds sooner than the arithmetic suggests.
A worker holds **15.3 GB**: 7.7 GB of live weights on the GPU, ~4.5 GB of
allocator pool PyTorch reserves and does not return, and ~3 GB of runtime and
CPU-side copies. Unified memory means the GPU's share counts against the same
128 GB the system uses, so eight workers project to ~122 GB and would starve the
window server rather than merely swap. `throughput.py` refuses any configuration
projecting past 55% of physical memory for that reason.

One measurement worth knowing when reading any of these numbers: inference
drifts slower within a run, 9.52 s to 10.77 s across eight consecutive products
(13%). Compare configurations over equal-length runs, or the drift outweighs
what is being measured.

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

- MPS is verified across 14 products including the largest mesh, but CPU remains
  the default because MPS degrades the desktop, not because it is unproven. See
  Device support.
- Reconstruction does not parallelize on this hardware; one at a time is the
  fastest configuration measured. See "Reconstruct one at a time".
- Colour is unverified for dark and saturated finishes, and wrong on the two
  tested. See "Colour is not reliable".
- Two of the six sofa and armchair reconstructions have not been looked at.
- Remeshing is disabled: `gpytoolbox` and `pynanoinstantmeshes` are not installed,
  so `--remesh` options are unavailable. Meshes are raw marching-cubes output.
- The upright correction is verified on lamps only, over-corrects shelf units,
  and is opt-in for that reason. See "Every mesh leans".
- Opening a packaged USDZ on an iPhone confirms the format is readable by
  Apple's loader, so the `qlmanage` hang is a desktop tooling fault and not a
  defect in our output. Appearance on device beyond "it opens" is unaudited.
- The `+Z` forward yaw per Product has not been determined. The grading sheets
  render 0/90/180/270 and are the input to that decision.
- Open structures were the expected failure mode and the grading confirms it for
  shelf units; thin frames, against expectation, reconstruct well.
- `scrape_ikea.py` produces test inputs only. Those Products carry no verified
  dimension evidence and must not be promoted to catalog assets.
