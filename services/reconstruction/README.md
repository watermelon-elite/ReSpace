# Scan to Three.js worker

**Create walkthrough** now sends fresh `house-capture/5` scans to this worker.
The default pipeline is `threejs`. It prepares the original metric capture with
Wes Bos's pinned converters, has an OpenAI coding agent author actual Three.js
modules and custom textures, renders source-camera comparisons, revises, and
exports verified OBJ/MTL/PNG/USDZ assets into the native walkthrough.

The worker runs on your Mac. **Runpod is not required**; the app's previous
Runpod URL has been replaced with the Mac's local-network address. The iPhone
and Mac must be on the same network and the Mac must stay awake during processing.
OpenAI performs the modeling/vision calls; the Mac handles capture storage,
conversion, browser rendering and export. No provider key is shipped in the app.

## Setup and run

Use Python 3.11/3.12 and Node 22.12 or newer (Node 24 LTS recommended).
From this directory:

```sh
./setup.sh
# Set OPENAI_API_KEY in the private .env, then:
./run.sh
```

Setup installs Python geometry/export dependencies, pinned Three.js dependencies,
and a separate pinned Playwright/Chromium runtime. On a Linux host, install its
OS dependencies with `npm exec --prefix ../scan-to-threejs/worker -- playwright install-deps chromium`
(as root). Node and browser work inherit a scrubbed environment with no provider
keys or service token. The run script selects `RESPACE_PIPELINE=threejs` even if
an older environment selected another worker. It starts a single durable queue
on port 8008. Do not use `--reload` or multiple Uvicorn workers.

`Configuration/Local.xcconfig` holds `RESPACE_RECONSTRUCTION_URL` and the matching
`RESPACE_RECONSTRUCTION_TOKEN`. The URL uses xcconfig's `http:/$()/HOST.local:8008`
escaping. Rebuild the iPhone app after changing it and allow Local Network access.
The token must match `services/reconstruction/.env`. Keep that file private;
`OPENAI_API_KEY` belongs only there. The authenticated `/health` response names
`pipeline: threejs` and `native_upload_schema_version: 2`.

### Scan-only device check

Planning is not needed for scanning/reconstruction. Start only this service with `bash services/reconstruction/run.sh` from the repository root. Verify the Mac's current `scutil --get LocalHostName` matches the app service address; a renamed Mac makes an older baked hostname unreachable. The app's Settings → 3D model service can check and save the current address without rebuilding. It requires authenticated `/health` success with `pipeline=threejs` and `native_upload_schema_version=2`. It does not purchase a generation.

For this validation stage, `RESPACE_DESIGN_FEATURES=NO` hides deferred decoration, shopping and image actions. Capture remains fully local until Build 3D model is explicitly confirmed. Keep the phone unlocked and both devices on the same network for upload; after the Mac accepts the job, background model work continues independently. Existing scans and paid-work checkpoints remain retained.

## Capture to native walkthrough

1. Save a fresh native scan. Original photos, poses, intrinsics, mesh, RGB-D and
   RoomPlan remain together, with the capture's original integrity inventory.
2. Tap **Create walkthrough** and accept the disclosed $10 API-token limit.
   The app builds a schema-2 upload envelope over those original files. Stable
   path-derived identities and byte hashes allow sequential uploads to resume
   only missing files. The older capture adapter is never used for fresh scans.
3. The worker verifies every uploaded byte and the native seal before queueing
   paid work. It runs the unchanged source converters and prepares upright photos
   in the converted array order, the floor/wall-aligned metric plan and a colored
   mesh reference. A missing layout is a capture/recovery error, not an invented room.
4. The Responses coding harness loads the supplied skill and **all four**
   references. It inspects contact sheets covering all photos, reads measurements,
   authors modular Three.js geometry, rectifies source-photo graphics/finishes,
   and can fetch suitable Poly Haven CC0 PBR maps with the original helper.
   Source-camera and orthographic renders use the upstream full PBR capture page.
   There is no primitive JSON scene schema, three-attempt limit or coarse fallback.
5. Submission checks TypeScript and exports the actual geometry, normals, UVs,
   images and PBR channels. An independent page reloads the delivered OBJ/MTL/PNG
   assets without authored code and renders cameras spread over the original
   capture route (up to 12). A separate vision review must cover every chosen
   view and pass before publication. Rejections return concrete discrepancies
   to the coding agent. A custom source-photo texture must actually be used in
   an exported material. An empty baseline or unused texture cannot pass the gates.
6. The validated result is published atomically as an immutable revision. The
   phone downloads only listed assets, checks sizes/SHA-256 and opens the
   viewing-only SceneKit walkthrough. Captured photo/canvas textures, UV repeats,
   tint, roughness, metalness, normals, emission, opacity and unlit graphics survive
   export. The separate USDZ embeds its images for sharing.

This is **ReSpace's API-billed automation of the coding workflow**, not the video's
interactive Codex subscription or a one-click feature supplied by upstream.
The original converters, skill, runtime and comparison page remain byte-identical
at revision `31b2dc9da3fb541e501f2f0936e55b32afb70ee8`; local integration files are
recorded separately. See [INSTA_METHOD.md](../../docs/reconstruction/INSTA_METHOD.md).
Native rendering uses ambient/directional lighting and a one-time reflection
probe from the delivered room at its starting position. SceneKit's radiance probe
and the independent Three.js cube capture restore environment response on metals;
they do not recover measured fixture lighting or identical renderer output. Three.js fixture lights,
postprocessing and shaders are not a byte-identical SceneKit renderer. Unsupported
features must be baked to supported geometry/materials before export. The final
asset comparison is a visual gate, not a numerical accuracy certificate.

## Charges, recovery and limits

New walkthroughs use `gpt-6.2-sol` with high reasoning for both modeling and
independent photo review. Retry uses the generation's original model settings
to recover paid responses. The fixed **$10 USD per generation**
ceiling covers coding and visual-review token calls at the recorded Standard
rates, including failed calls. It excludes tax and any unrelated image generation.
Input token counts include tool definitions; each request reserves input/cache
write plus maximum reasoning/output before calling OpenAI. Unknown billing
outcomes block more paid work. Do not delete the ledger to bypass that block.
A budget/time failure preserves the scan, authored source and paid responses;
it does not publish a schematic substitute.

Normal Retry resumes `work/threejs/agent-state.json`, tool state, response
checkpoints and `spending.json`. Explicit **Rebuild model** creates a new
isolated run and a new $10 limit, using a persisted restart UUID to avoid duplicate
runs after lost acknowledgements. Published revisions stay immutable. One room
runs at a time; the default room deadline is one hour. Three.js stops before new
paid requests and between native review renders at that deadline. A request
already in flight may finish and save its billing receipt; a separate hard
watchdog allows 17 minutes of grace for the bounded provider request and local
cleanup. Retry retains those receipts and the same generation budget. This
avoids the old hard one-hour kill creating an unknown billing outcome solely
because a healthy paid request crossed the deadline. Native upload limits:
30,000 files, 512 MiB per input, 8 GiB total. Native results: one million triangles,
512 files, 128 MiB per asset and 512 MiB total. These are mobile/storage limits,
not a restriction to boxes or a fixed count of modeled parts.

The author can batch independent reads, photo inspections and texture crops in
one Responses request. Local tools still execute in order, checkpointing each
result; visual outputs are retained across interruption and returned after the
batch's tool outputs. Deadline checks also run between tools. This avoids a
mandatory paid round trip per small operation while preserving ordered edits
and the same budget/review safeguards. See OpenAI's
[function-calling contract](https://developers.openai.com/api/docs/guides/function-calling).

After the first independent review, author context rolls over after 40 responses.
The full history is archived under `work/threejs/context-*.json`; the continuation
uses current source-file identities, the latest review, the remaining original
budget and contact sheets covering every source photo. Current files and paid
responses remain untouched. In-flight tools, reserved calls and already-saved
responses keep their input identity until recovery completes. This bounds old
edit/image accumulation without buying a separate summarization call or resetting
the generation budget. The full visual publication gate still applies.

Each review retains its exact delivered renders under the submission's
`evidence/` directory. Rejection supplies up to four failed camera positions as
paired source photos and native renders to the correcting author, also retained
when context rolls over. This exposes export-specific artifacts directly rather
than relying only on written findings or the differently lit authoring view.
Older checkpoints without retained review images continue with their findings.
Each structured review request constrains camera IDs and array length to its
actual batch. Runtime validation additionally rejects missing or duplicate views;
neither malformed responses nor prose completion claims can publish a room.

## Verification

```sh
.venv/bin/python -m pytest tests ../scan-to-threejs/tests -q
npm run build --prefix ../scan-to-threejs
```

The synthetic integration uses real Chromium, authored curved geometry, source
photo crops, PNG baking, native OBJ reload and ARKit-compliant USDZ packaging;
only the paid model/reviewer responses are mocked. It checks interrupted upload
recovery, native source integrity, revision reuse and refusal to publish rejected
reviews. Swift tests cover the native upload and verified import contracts; the
Simulator build covers the app button and SceneKit renderer. A real fresh iPhone
scan and paid modeling run remain the device/visual acceptance test.

For a real exported result, run this from the repository root on macOS:

```sh
RESPACE_TEST_CAPTURED_SCENE=/absolute/path/to/exported-result \
  swift test --filter testCapturedSceneImportsWithNativeMaterialsAndNavigableSpawn
```

This opt-in check reads existing files only: it validates the scene and referenced
assets, imports every object/material through ModelIO and SceneKit, and checks the
spawn and movement using the app’s navigation code. It makes no provider calls.
It does not certify visual likeness or replace the final iPhone walkthrough check. The Debug-only `--ui-walkthrough-audit` app route renders an unpublished checkpoint for native visual diagnosis; see [UI studio](../../docs/ui-studio.md).

The independent browser review transforms its light from scan coordinates with the scene. Its illumination is calibrated against SceneKit previews, but Three.js/ACES and SceneKit HDR are not identical renderers. A coordinate-frame relabel must preserve the review image; the browser regression checks that invariant.

The earlier JSON/API worker is retained for historical regression tests under
explicit `astra`/`insta` selection. Its old room-JSON/product-placement and realistic
image behavior is documented in [API_APPROXIMATION.md](../../docs/reconstruction/API_APPROXIMATION.md),
[ROOM_JSON.md](../../docs/reconstruction/ROOM_JSON.md), [WALKTHROUGH_README.md](WALKTHROUGH_README.md)
and [LEGACY_README.md](LEGACY_README.md). New Three.js walkthroughs do not claim a
planning-ready `room.json`; native scan planning remains separate.

## Current-view realistic images

The rendition endpoint supports both historical captures and native schema-2 `house-capture/5` bundles. Native photos come from the original integrity inventory; size/hash checks precede their use. Up to six photos span the capture route. No legacy frame conversion is needed.

Both the original walkthrough and a saved Design can capture the current first-person camera. The saved Design sends its active Item placements and Product titles with a clean RealityKit reference; removed ghosts, labels and highlights are excluded. Optional `perspective` and `design` fields are persisted with the generation and included in request identity. Older requests retain their existing identity. Image generation remains separately billed; Retry/reopen reconciles the same request and explicit Refresh creates a new one. The app retains the last request to reopen it without recreating the exact camera position.

This produces an AI concept image and does not modify the original reconstruction, the saved Design, purchases or placement validation. Actual provider image quality still requires live testing. Use `bash services/run-local.sh --check` from the repository root to check both planning and reconstruction configuration; `--live` starts both without importing demo rooms. See [backend setup](../../backend/README.md).
