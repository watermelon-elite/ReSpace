# Scan to Three.js

The actual Wes Bos **capture → Codex authors Three.js → camera comparison →
correction** workflow, pinned to upstream `31b2dc9`. Read the
[method and source review](../../docs/reconstruction/INSTA_METHOD.md) and the
[original skill](.agents/skills/scan-to-threejs/SKILL.md) before modeling.
The original skill and its four linked references govern the modeling work.
The app button is connected through [the reconstruction worker](../reconstruction/README.md),
which uses an API-billed coding harness, real browser comparisons and validated
native export. The commands below remain available for interactive Codex authoring.

## Prepare a captured Room

Use Python from the existing reconstruction environment (`bash setup.sh` in
`services/reconstruction` installs NumPy, Pillow and Open3D). Node/npm are needed
for the Three.js viewer. Run from the ReSpace repository root:

```sh
services/reconstruction/.venv/bin/python services/scan-to-threejs/prepare.py \
  /absolute/path/to/saved-capture \
  --output /absolute/path/to/new-private-project --id my-room
```

Input can be an upstream `house-capture/1`–`house-capture/5` session folder or ZIP,
or a fresh ReSpace app-managed capture with its `house-capture/` child.
Use `--room N` for the **original** index if a session contains multiple rooms.
A whole `house-project/1` export requires the original `house_to_rooms.py` first;
choose its active session, preserving its placement transforms if combining rooms.
Output must be new and outside the input directory. Fresh ReSpace captures are
already native: the old adapter never runs. Their native file-integrity record
must verify before conversion. Historical ReSpace `inputs/` captures are rejected
unless `--legacy-capture` is explicitly selected for archival work.

The CLI preserves source evidence and runs the pinned upstream converters to
create the wall-aligned room, plan, upright photos and photo-colored LiDAR
reference (fusing recorded depth when no mesh exists). `--layout-reference` explicitly skips mesh coloring when diagnosing
a missing/unusable mesh; that reference is schematic. A missing floor outline
must be established from measured evidence before the baseline can render.

The result is an **authoring project**, `ready=false`, rather than a completed
room. ReSpace's baseline assumptions and missing capture metadata are recorded.
Fresh iPhone scans now record the source camera-quality fields and optional
high-resolution stills directly, with independent RGB-D and classified mesh.
On the iPhone, save the scan and choose **Create walkthrough** for the automated
Mac worker, or **Share original scan** to export the ZIP for manual authoring. High-resolution auto photos default on; regular photos remain a
fallback and their `highRes` value stays truthful. The old 60-second/900-frame
sampler is not used. Any explicit historical adapter conversion still reports
the metadata that those old captures never recorded.

## Model and compare

Open the generated project in Codex and use its
`demos/my-room/BRIEF.md` together with the original skill. Preserve every private
source photograph; inspect contact sheets and individual useful views. Author
areas under `parts/` and actual Objects under `items/`, exporting `build(ctx)`.
Custom geometry and photo-derived/procedural/PBR textures are ordinary Three.js
source and assets, without the earlier JSON worker's geometry limits.

```sh
cd /absolute/path/to/new-private-project
npm ci
npm run dev
```

Viewer: `http://localhost:5188/?room=my-room`.
Comparison render:
`http://localhost:5188/tools/capture.html?room=my-room&src=model&photo=0&size=540`.
Use `src=scan` for its reference layer. The unchanged upstream command helpers
require `zsh`, an installed `agent-browser` CLI/browser runtime and Python/Pillow:

```sh
export S="$PWD/.agents/skills/scan-to-threejs/scripts"
export CAP_URL=http://localhost:5188
export CAP_PYTHON=/absolute/path/to/ReSpace/services/reconstruction/.venv/bin/python
"$S/cmp_photo.sh" my-room 0 5 13  # choose actual available photo indices
"$S/cmp.sh" north 'room=my-room&view=n&ppm=180'
```

Each helper produces evidence for the coding agent to inspect. Continue modeling
and correcting the largest observed discrepancies, including custom finishes,
lighting, closeups and translated views. Retain source/license records for any
downloaded material maps. Check `npm run build`, browser errors, photo order and
comparison framing separately from appearance. Record reviewed views, remaining
uncertainty and visual findings in the private project before changing readiness.

All `data/`, `demos/`, comparisons, generated textures and `.env*` in a prepared
project are ignored. Preparation makes no paid API call; Codex modeling uses
the coding agent's configured account. Fresh iPhone captures use native export;
only historical captures can use the [earlier API approximation](../../docs/reconstruction/API_APPROXIMATION.md).
This authoring project has no native OBJ/USDZ publishing bridge.

## Source and checks

`UPSTREAM.json` records the repository, revision and Git blob hashes of all 59
copied source files. Those sources are byte-identical, including this user's
supplied skill. Local integration files are listed separately. `upstream/package.json`
preserves the original package; our package/config build only the reconstruction
viewer and capture page, excluding the optional playground's office-specific
import. Upstream's `LICENSE` covers reusable code/skill; none of its personal
room models, photos, graphics or other separately licensed demo assets are copied.

```sh
# From the ReSpace root; offline conversion/validation and upstream house tests
services/reconstruction/.venv/bin/python -m pytest -q \
  services/scan-to-threejs/tests \
  services/scan-to-threejs/.agents/skills/scan-to-threejs/scripts/test_house_import.py

cd services/scan-to-threejs
npm ci
npm run build
```

The template build contains no example room. Prepare a capture and build that
project to check authored room code. Tests use synthetic evidence and verify
shared mesh/camera coordinates, filtered photo order, single upright rotation,
native artifact integrity, raw depth preservation, original room selection and
unsafe archive rejection. These checks do not establish real-room likeness.
