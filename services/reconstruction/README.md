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
Native rendering uses ambient/directional lighting; Three.js fixture lights,
postprocessing and shaders are not a byte-identical SceneKit renderer. Unsupported
features must be baked to supported geometry/materials before export. The final
asset comparison is a visual gate, not a numerical accuracy certificate.

## Charges, recovery and limits

Walkthrough modeling uses `gpt-6.1-sol` with high reasoning; independent photo
review uses the same model with medium reasoning. Other pipelines retain their
configured models. The fixed **$10 USD per generation**
ceiling covers coding and visual-review token calls at the recorded Standard
rates, including failed calls. It excludes tax and any unrelated image generation.
Input token counts include tool definitions; each request reserves input/cache
write plus maximum reasoning/output before calling OpenAI. Unknown billing
outcomes block more paid work. Do not delete the ledger to bypass that block.
A budget/time failure preserves the scan, authored source and paid responses;
it does not publish a schematic substitute.

Normal Retry resumes `work/threejs/agent-state.json`, tool state, response
checkpoints and `spending.json`. Explicit **Generate from scratch** creates a new
isolated run and a new $10 limit, using a persisted restart UUID to avoid duplicate
runs after lost acknowledgements. Published revisions stay immutable. One room
runs at a time; the default room deadline is one hour. Native upload limits:
30,000 files, 512 MiB per input, 8 GiB total. Native results: one million triangles,
512 files, 128 MiB per asset and 512 MiB total. These are mobile/storage limits,
not a restriction to boxes or a fixed count of modeled parts.

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

The earlier JSON/API worker is retained for historical regression tests under
explicit `astra`/`insta` selection. Its old room-JSON/product-placement and realistic
image behavior is documented in [API_APPROXIMATION.md](../../docs/reconstruction/API_APPROXIMATION.md),
[ROOM_JSON.md](../../docs/reconstruction/ROOM_JSON.md), [WALKTHROUGH_README.md](WALKTHROUGH_README.md)
and [LEGACY_README.md](LEGACY_README.md). New Three.js walkthroughs do not claim a
planning-ready `room.json`; native scan planning remains separate.
