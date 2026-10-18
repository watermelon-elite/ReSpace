# ReSpace segmented room walkthrough

The default `RESPACE_PIPELINE=walkthrough` builds one explorable, segmented room from a complete retained LiDAR capture. It preserves captured object surfaces and photographs, builds clean room surfaces behind furniture/decor, and publishes a version-2 scene only after geometry, texture, navigation and asset-integrity checks. Gemini is deferred. The walkthrough does not call OpenAI or Gemini.

## Setup and run

Requires Python 3.11/3.12 and sufficient disk space for the public detector/SAM checkpoints. From this directory:

```sh
bash setup-walkthrough.sh
./run.sh
```

Setup installs pinned dependencies, public Grounding DINO tiny and SAM 2.1 tiny checkpoints. It creates an ignored private `.env` with a random service token. Set the existing iPhone `Configuration/Local.xcconfig` endpoint/token to this worker, rebuild, open a saved room and choose **Create walkthrough**. Use HTTPS for remote workers. Local HTTP remains restricted to local addresses. Never put model-provider credentials in the app.

The existing deployment bootstrap now installs these models too. Deployment is a separate action: creating a GitHub branch does not deploy or start a cloud worker.

## Reconstruction

1. Verify every immutable source artifact, including the original ARKit mesh, RGB/depth/confidence frames, scaled intrinsics, poses and RoomPlan export.
2. Detect proposed furniture/decor with gravity-corrected Grounding DINO images; segment with SAM 2; associate independent depth-visible views and reconcile RoomPlan identities. Built-ins stay fixed. Ambiguous storage requires better evidence rather than becoming silently movable.
3. Partition the captured mesh with depth-visible masks and constrained connected components. Reject ambiguous movable-object fragments. Preserve captured surfaces; never substitute a box or catalog furniture model.
4. Complete simple occlusion boundaries while retaining observed faces. Reject nonmanifold, open or self-intersecting results and generated geometry contradicting observed free space. Complex missing geometry uses the optional completion-worker contract below; it is not silently replaced by a generic object.
5. Rectify planar wall decor from original photo pixels into independent assets. Rebuild full measured wall/floor/ceiling polygons with doors/windows protected. Exclude occluding objects and coplanar decor from texture baking, then continue unseen texture regions from captured boundary colors. This is harmonic texture continuation, not a trained image-inpainting model.
6. Bake real photographs onto independent object meshes, group material runs for native import, and retain internal source/completion provenance. Generate safe floor navigation, static obstacles and object colliders.
7. Write assets into an unpublished `.building` directory, validate the scene graph and dependencies, hash every asset and atomically commit the completed revision. Failed rooms never publish a partial walkthrough.

The native SceneKit viewer loads the actual assets through Model I/O. Drag to look and use walking controls to move with collision checks. Tap furniture/decor to move or remove it; tap a finish surface for paint/tile/wallpaper. Structure and built-ins cannot move. Changes save locally per reconstruction revision, support Undo, and reopen against the same scene identities. Wall decor remains on its supporting wall. Users see the completed room without estimate labels.

## Complex object-completion worker

No GPU model is automatically provisioned or billed. Default measured-boundary completion works only when captured topology supports safe closure. If it cannot, the room is withheld and requests clearer coverage. To enable a local/GPU completion model, set `RESPACE_OBJECT_COMPLETION_COMMAND` to a JSON argument array, for example `["/opt/room-model/bin/python", "/opt/room-model/complete.py"]` in the server environment. In a shell `.env`, quote the complete JSON value.

The worker invokes that command with `--request REQUEST_JSON --output COMPLETED_OBJ`, without a shell. The request contains the observed mesh/hash, calibrated frames and source paths, object masks, metric object transform/dimensions, `request_fingerprint`, `maximum_cost_usd`, and an object-local-meter output contract. Return a triangulated OBJ and a sibling `completed.receipt.json`:

```json
{"request_fingerprint":"EXACT_REQUEST_FINGERPRINT","cost_usd":0.0}
```

The adapter must honor the supplied maximum cost before starting paid computation and run in the foreground. The pipeline validates its mesh itself; a worker success exit is insufficient. Completed geometry must be watertight, avoid self-intersections, fit measured bounds, retain measured surfaces within 5 mm, and pass scan free-space checks. Textures come from captured photographs, not generated artwork.

Reservations and receipts persist across retries in `work/walkthrough/completion-budget.json`, with a $5 completion ceiling per capture. Unknown billing outcomes block another automatic request. Completed candidates are checksummed and reused. This controls the adapter's declared computation budget; cloud VM, disk and networking costs still require deployment accounting. The total $5/room and 30-minute target are not established by the synthetic tests. No Pixal3D/WorldSculpt/SAM-3D GPU deployment is bundled or claimed validated; see the [model research](../../docs/reconstruction/COMPLETION_MODEL_DECISION.md).

## Delivery and operations

The original v1 upload API remains compatible. Finished results add `scene_filename` and `scene_schema_version: 2`, alongside aggregate `model.obj`. Scene entities own assets/materials/supports and retain meter/Y-up coordinates. The client validates identities, graph references, navigation, dependencies, quality readiness and all downloaded/cached hashes before native import. Failed/stale revisions cannot expose the new walkthrough.

One worker processes one room at a time. `RESPACE_ROOM_TIMEOUT_SECONDS` defaults to 1800; the service terminates the worker process group on timeout. Inputs and internal checkpoints remain intact. Reconstruction failures distinguish missing/insufficient scan evidence from unavailable models, failed workers, time/budget limits and unknown billing outcomes. A valid scan must not be discarded to fix infrastructure.

Limits: 512 files / 512 MiB per result, 128 MiB per asset, one million final triangles, original-mesh admission of 800K triangles, planar single-floor room shell. Curved/sloped structures and complex incomplete furniture are not proven by this baseline. Real-room visual fidelity, segmentation completeness, hidden-surface plausibility and minimum-device frame rate still require fresh LiDAR-device validation.

## Verification

```sh
.venv/bin/python -m pytest -q
```

Tests include analytic calibrated room reconstruction, closed captured-object completion, original-pixel wall decor, a clean wall behind a removable poster, opening-safe polygons, immutable result caching, budget reservations and failed-revision publication. Swift tests import the Python-produced textured fixture through Model I/O and exercise scale, identities, collision movement and scene validation. Synthetic fixtures contain no private capture data.

For the retained Astra/TSDF/OpenMVS inspector, explicitly select `RESPACE_PIPELINE=legacy`; its original documentation is in [LEGACY_README.md](LEGACY_README.md). It is not the new finished-room experience.
