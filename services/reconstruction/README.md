# Direct Astra room generation

This branch sends scan evidence directly to `gpt-6-astra` through the OpenAI Responses API. Astra authors the entire furnished room: floor, ceiling, walls with openings, furniture, decor, colors and inferred hidden surfaces. ReSpace validates the returned scene, expands its geometry into OBJ/MTL files locally, and opens it in the native first-person viewer.

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

All ARKit mesh anchors are loaded and transformed into the original metric scan frame, then simplified to at most 1,200 triangles for the request. Calibrations and poses from every frame, RoomPlan semantics, and up to 32 sharp photos selected for viewpoint diversity accompany the summary. Images are reduced to at most 1,280 pixels on their longest side. This is bounded evidence from the whole scan, not a byte-for-byte upload of every raw depth map and mesh face. Opaque older RoomPlan exports are identified as unavailable; Astra then infers from the other evidence.

Astra returns one strict JSON scene with object-local meshes and shaped parts, entity poses, materials, a room footprint, assumptions and ignored evidence. Its instructions explicitly reject reflected rooms/furniture, mirror ghosts, spikes, transient people and contradictory measurements, and complete unseen backs, legs and room surfaces with plausible assumptions. Reflection rejection is a model judgment, not an established guarantee. Generated colors/materials are not photographic texture maps.

Local code checks references, finite metric geometry, triangle indices, nondegenerate faces, room bounds, floor and ceiling coverage, perimeter-wall coverage, safe spawn and navigation obstacles. It never executes model-produced code. All scene assets are checksummed and committed atomically only after validation. No source-mesh overlay or partial room is published on failure. These geometric checks establish an importable explorable scene; they do not establish that every real object was recognized or that inferred surfaces are accurate.

The native SceneKit viewer supports drag-to-look, held walking controls, eye-height navigation, wall/furniture collisions, reset view, and existing furniture/finish edits. Generated geometry uses lighting and materials to make its shape visible. Doors/openings remain geometric gaps; navigation stays within the modeled room.

## Cost and duration estimate

Planning estimate for one ordinary furnished room, using 24–32 photos, pooled LiDAR, a simplified mesh and one successful Standard API call:

| Component | Estimate |
| --- | --- |
| Astra input, including images | 70,000–180,000 tokens |
| Astra output, including reasoning | 12,000–35,000 tokens |
| API cost | **$1.30–$3.55**, budget roughly **$1.50–$4.50 per room** |
| Phone-to-Mac upload and evidence encoding | 15–90 seconds on a good LAN |
| Astra generation | 2–8 minutes |
| Validation, asset download and viewer import | 5–30 seconds |
| Scan finished to explorable model | **about 3–10 minutes** |

These are engineering estimates, not measured real-room latency/fidelity results. Add the time spent scanning (often another 1–3 minutes). Large captures, complex geometry, API queues and network conditions can exceed these ranges. One worker handles one room at a time; waiting behind another scan adds queue time. The local service's default room timeout is 30 minutes and the API request timeout is 15 minutes.

Pricing checked October 17, 2026: Astra Standard costs $10 per million input tokens and $50 per million output tokens, with $1 per million cached input tokens. Requests over 272,000 input tokens cost 2x input/cache rates and 1.5x output rates. The request permits at most 48,000 output tokens, including reasoning. There is no fixed dollar cap; a failed paid generation or explicit regeneration can add another call's cost. The estimates exclude electricity, taxes, cache-write charges and any separately provisioned hosting.

Each successful result's `quality.json` records returned token usage, an estimated Standard API cost, local elapsed processing time and whether the paid response was reused. Reusing a response does not incur a new generation charge; its recorded token cost describes the original response. Unknown interrupted billing outcomes block automatic repeat calls. **Retry walkthrough** explicitly permits another call after an unknown outcome or rejected generated scene; check OpenAI usage first if needed. Valid cached responses are reused across processing revisions.

Official references: [Astra capabilities and pricing](https://developers.openai.com/api/docs/models/gpt-6-astra), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), and [architectural visualization with Astra](https://developers.openai.com/blog/architectural-visualization-with-astra).

## Verification and limits

```sh
.venv/bin/python -m pytest -q
```

Offline fixtures verify all-frame evidence pooling, whole-room output, asset serving/import contracts, safe navigation, rejected incomplete/invalid scenes, paid-response caching and explicit retry behavior. They do not call the paid API. Live Astra quality, reflection suppression, real-device frame rate, actual tokens and generation time still require a fresh LiDAR-device scan and a configured API key. A complete generated room can contain plausible approximations; this branch does not claim survey accuracy or photorealism.

To reproduce the native import test, export a synthetic scene from this directory with `PYTHONPATH=. .venv/bin/python tests/export_astra_scene.py --output /tmp/astra-fixture` (use a fresh directory). From the repository root, run `RESPACE_TEST_ASTRA_SCENE=/tmp/astra-fixture/results/1 swift test`. The generated fixture uses a mocked Astra response and makes no network request.

The generated scene supports one horizontal floor and ceiling, up to 128 entities and 24,000 triangles. Large/multilevel/nonhorizontal spaces need a separate contract. Existing non-Astra implementations remain available for historical tests/direct CLI selection; `run.sh` always selects Astra. Their documentation is retained in [WALKTHROUGH_README.md](WALKTHROUGH_README.md) and [LEGACY_README.md](LEGACY_README.md). No cloud deployment is performed by these changes.
