# Direct Astra room generation

This branch sends scan evidence directly to `gpt-6-astra` through the OpenAI Responses API. Astra authors intentional room contents, including furniture, decor, appliances, electronics and installed features, with plausible hidden object surfaces. The local service builds walls, floor and ceiling from measured RoomPlan geometry, preserving recorded openings and extending partial wall heights to a consistent measured ceiling level. ReSpace validates the returned scene, expands its geometry into OBJ/MTL files locally, and opens it in the native first-person viewer.

The generation path contacts only `https://api.openai.com/v1/responses`. It uses no Google Cloud, Gemini, OpenMVS, detection/segmentation models, hosted tools, object-completion commands or external reconstruction services. A small service on your Mac keeps the API key private, accepts the phone's saved scan, and converts/validates Astra's output. This local service and local libraries are still needed; Astra's API returns structured text rather than a native 3D binary file.

## Run locally

Requires Python 3.11/3.12. From this directory:

```sh
bash setup.sh
# Add your OpenAI API key to OPENAI_API_KEY in the private .env.
./run.sh
```

Setup installs Python geometry/runtime dependencies; it downloads no reconstruction model checkpoints or OpenMVS binaries. The run script forces `RESPACE_PIPELINE=astra`, including when an older `.env` is present, and requires an API key before accepting jobs. Stop an old reconstruction service before starting this branch's service.

Point `Configuration/Local.xcconfig` at this Mac's LAN address on port 8008 and copy the service token from `.env`. Use the existing local-network setup, rebuild the iPhone app, open a saved scan, and choose **Create walkthrough**. Do not use a retained Google Cloud endpoint. Keep the OpenAI key out of the app. For access beyond your local network, configure authenticated HTTPS yourself.

## Evidence and generation

All immutable input artifacts are checked against their declared lengths and SHA-256 hashes. Every retained frame contributes its valid LiDAR pixels (0.1–6 meters, ARKit confidence >= 1) to a weighted XYZ/RGB voxel summary. Voxel resolution adapts to keep at most 6,000 cells: it preserves counts and weighted sums from every valid pixel rather than dropping later frames. Invalid depths are omitted. The full-resolution files stay local and unchanged.

All ARKit mesh anchors are loaded and transformed into the original metric scan frame, then simplified to at most 1,200 triangles for the request. Calibrations and poses from every frame, RoomPlan semantics, and up to 32 sharp photos selected for viewpoint diversity accompany the summary. Images are reduced to at most 1,280 pixels on their longest side. This is bounded evidence from the whole scan, not a byte-for-byte upload of every raw depth map and mesh face. A parsed RoomPlan floor and walls are required for the local shell; missing structure fails before any paid request. Opaque coreModel payloads are omitted from the API evidence.

## Detailed, staged generation

The default path makes multiple serial OpenAI calls, with independent saved responses:

1. **Inventory:** all selected room photos and scan summaries identify intentional room contents and installed features and create complete coarse objects. The response targets 1–3 parts per item, at most 64 entities/80 total parts, and has a 32,000-output-token limit.
2. **Object detail:** each item gets its own call, with up to six object-specific 1,536-pixel photo crops, calibrated crop bounds and nearby LiDAR voxels. Objects can contain 64 parts, 384 explicit vertices and 768 explicit triangles each, with separate materials for wood, fabric, metal and other finishes. The output limit is 24,000 tokens per object. Larger furnishings receive detail priority.
3. **Photo materials:** local depth-checked projection maps original photographs onto visible generated faces. Photographs are retained at up to 2,048 pixels and UV coordinates reference actual captured pixels. Faces without sufficient depth agreement retain their generated material. Roughness/metallic values survive native import; mirrors and highly reflective material slots do not bake reflected room imagery.
4. **Assembly:** the measured local shell and all objects are validated, textured, checksummed and committed as one first-person walkthrough. The native viewer adds ambient occlusion and displays how many items received detailed geometry.

Include everything meaningfully belonging to the room: furniture/decor, appliances (including microwaves, refrigerators, ovens, dishwashers, kettles and coffee machines), TVs/computers/other electronics, cabinetry, countertops, sinks/faucets/plumbing fixtures, lights, vents, outlets, trim, door panels, window frames/glazing/shades, functional equipment and organized intentional contents. The local wall/floor/ceiling shell and openings remain authoritative and are not regenerated by Astra.

Exclude random incidental junk: brooms/mops and loose cleaning tools, cleaning bottles/dish soap, wrappers, open gum packets, disposable packaging, food scraps, stray papers/notebooks, scattered dishes/cutlery, stray cables/chargers and personal clutter. Room context distinguishes an intentional functional setup from transient mess; useful or small items are not automatically junk. Installed/built-in/plumbed items stay fixed; freestanding items remain movable. Internally, `kind=furniture` denotes the movable-object class, while `category=appliance`, `electronics`, etc. identifies what it actually is. Objects above head height and low floor coverings do not obstruct walking underneath/over them.

The detail response can mark clutter/people/reflections in photo crops; those regions are excluded from photo selection and filled locally from neighboring image pixels where referenced by a texture. Model classification, exclusion polygons and photo alignment are fallible. Larger inventories may use fewer photo sources per item to stay within the mobile file budget.

Each real item stays one entity. Separate material slots belong to its parts; handles/legs/cushions do not become independently movable objects. Every inventory item remains in the room, even if it cannot receive an extra detail call. An invalid, incomplete or unaffordable detail response retains the complete coarse item and records the reason in `quality.json`. The viewer's item count makes this distinction visible. Photographic coverage is recorded per object as `photo_surface_fraction`. This is improved geometry and captured-photo appearance, not a validated promise of photorealism, scan accuracy, texture de-lighting or perfect hidden surfaces. Normal maps and generated photographic inpainting are not implemented.

Local checks cover schema, references, finite metric geometry, closed furniture meshes, object envelopes, room bounds, floor/ceiling coverage, perimeter walls, safe spawn and mobile asset budgets. Both the shell and inventory are checked before spending on object detail. Model output is data and is never executed as code.

Open a saved room and use **Improve detail · $10 limit** to generate the staged version without rescanning. Rebuild the iPhone app for the updated material bindings, progress labels and increased geometry budget. A failed upgrade retains the previous files and offers **Open previous version**. The older single-call helper is retained only for coarse-contract tests; the service defaults to staged generation.

## API budget, retries and duration

The user-authorized **$10 USD model-token reservation ceiling** is fixed per retained capture for this staged pipeline. It includes inventory, successful/failed detail calls and retries recorded from this version onward. Earlier single-call pipeline charges are historical and are not retroactively included. This is a local request-control policy at recorded Astra Standard prices, not an OpenAI account-wide spending limit or an all-in bill cap; taxes, hosting and future provider price changes are outside it.

Before each generation, `/v1/responses/input_tokens` counts the actual text, images and schema. The service reserves the full maximum output (including reasoning) and counted input plus 1%/256-token headroom at the highest applicable input/cache-write rate. Long-context uplifts are included. A durable reservation is committed before the paid request. Actual returned ordinary/cached/cache-write/output usage settles it; unused reservation becomes available to the next object. Requests explicitly use the Standard/default service tier and no paid hosted tools. If another detail call cannot fit, generation stops adding detail and uses complete coarse geometry for the remaining items.

Reservations and receipts live in `work/astra-budget-v3.json`. Responses live separately in `work/astra-v3/inventory/response.json` and `work/astra-v3/OBJECT_ID/response.json`. Normal retries reuse paid responses and preserve the cumulative ledger; they do not reset the $10 ceiling. Failed detail responses are retained and not blindly repurchased. Unknown billing outcomes keep their entire reservation and stop further paid calls, including after a restart or Retry. Review OpenAI usage and reconcile the receipt before proceeding; do not delete the ledger to bypass it. A saved response recovered after a crash can settle without another paid request.

Pricing basis checked October 17, 2026: Astra Standard input $10, cached input $1, cache writes $12.50 and output $50 per million tokens. Over 272,000 input tokens, input/cache/write rates double and output is 1.5x. The local report includes all known staged-call costs; retry reports refer to cumulative costs, not a fresh charge for cached responses.

Expect more time than the original one-call path. A provisional planning range is **10–30 minutes for a furnished room**, depending on object count, API latency and the available budget; this has not been measured against fresh real-room staged generation. One worker handles one room at a time. API calls time out after 15 minutes each. The default whole-room timeout is 60 minutes; an existing `RESPACE_ROOM_TIMEOUT_SECONDS` setting overrides it. Object checkpoints survive worker failure. A timeout during an active request is an unknown billing outcome and blocks another paid call until reconciled.

Official references: [Astra capabilities/pricing](https://developers.openai.com/api/docs/models/gpt-6-astra), [input-token counting](https://developers.openai.com/api/docs/guides/token-counting), and [per-run spending controls](https://developers.openai.com/cookbook/articles/per_run_spending_controller_responses_api).

## Verification and limits

```sh
.venv/bin/python -m pytest -q
```

Offline fixtures verify all-frame evidence pooling, whole-room output, asset serving/import contracts, safe navigation, rejected incomplete/invalid scenes, paid-response caching and explicit retry behavior. They do not call the paid API. Live Astra quality, reflection suppression, real-device frame rate, actual tokens and generation time still require a fresh LiDAR-device scan and a configured API key. A complete generated room can contain plausible approximations; this branch does not claim survey accuracy or photorealism.

To reproduce the native import test, export a synthetic scene from this directory with `PYTHONPATH=. .venv/bin/python tests/export_astra_scene.py --detailed --output /tmp/astra-fixture` (use a fresh directory). From the repository root, run `RESPACE_TEST_ASTRA_SCENE=/tmp/astra-fixture/results/1 swift test`. The generated fixture uses a mocked Astra response and makes no network request.

The generated scene supports one horizontal floor and ceiling, up to 64 Astra room-content entities plus measured shell surfaces, and 200,000 total exported triangles. Large/multilevel/nonhorizontal spaces need a separate contract. Existing non-Astra implementations remain available for historical tests/direct CLI selection; `run.sh` always selects Astra. Their documentation is retained in [WALKTHROUGH_README.md](WALKTHROUGH_README.md) and [LEGACY_README.md](LEGACY_README.md). No cloud deployment is performed by these changes.
