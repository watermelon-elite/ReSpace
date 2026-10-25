# Earlier API approximation on `instaMethod`

This is the earlier implementation from 22 October 2026. It is retained for the
historical native Create walkthrough contract. Fresh native captures use source
bundle export and refuse this worker. It is **not Wes Bos's method**: it
uses structured JSON geometry, CPU flat previews, bounded API correction attempts
and a photo-projection pass. The supplied skill and source were examined on
24 October; the actual Codex/Three.js workflow is documented in
[INSTA_METHOD.md](INSTA_METHOD.md) and implemented under `services/scan-to-threejs`.
Only the historical compatibility button runs this worker. Its API budget and result
formats do not describe the new authoring workflow.

## Run and capture

From `services/reconstruction`, run `bash setup.sh`, set `OPENAI_API_KEY` in the
private `.env`. Historical direct CLI tests can explicitly select
`RESPACE_PIPELINE=insta`; `./run.sh` now selects the replacement `threejs` worker.
Direct CLI/API worker launches default to the same method. The model key stays
on the service; the app uses its existing private service token. An existing
service process needs restarting to load this source. These changes do not deploy
or restart any remote service or purchase model work.

Use a LiDAR-equipped iPhone with this branch's app. Existing acquisition already
records the native RoomPlan export, ARKit mesh anchors, sensor-basis JPEGs up to
2560 pixels, matching poses/intrinsics, and optional registered depth/confidence
at approximately 3 Hz. The local one-minute minimum and bounded storage remain.
Move around Objects and capture overlapping views from several positions. A
completed saved scan can enter this method if its artifacts pass integrity checks;
video-only captures from other branches lack the required LiDAR/RoomPlan evidence.

Point the iPhone at the authenticated reconstruction service as described in the
[service README](../../services/reconstruction/README.md), then choose Create
walkthrough. Progress distinguishes inventory, Object modeling, photo comparison,
whole-room checking and photo texturing. The screen discloses photo/measurement
transfer to OpenAI and the existing per-generation $10 model-token limit.

## Modeling contract

1. Verify original artifacts and calibration. Pool all retained valid LiDAR
   evidence and select diverse inventory photos using the existing evidence
   collector. Build the immutable wall/floor/ceiling shell locally from RoomPlan,
   retaining openings and the existing partial-wall ceiling-height inference.
   Estimate shell finish colors from nearby colored LiDAR voxels; these retain
   captured lighting and are not recovered physical reflectance.
2. Ask `gpt-6-astra` for a coarse inventory of actual intentional Objects and
   supports. Approximate Object bounds/poses remain model estimates informed by
   measured evidence; they are not verified Product dimensions or survey data.
3. For each Object, rank all retained frames by depth-visible coverage. Require
   at least three views separated by 0.15 m of camera translation. Select at most
   four: two or three construction views plus one validation view. Only depth
   with confidence 2, finite values and 0.1–5 m range supports numerical checks.
   Mismatched depth/confidence dimensions fail instead of being rescaled.
4. Render the complete current model on the CPU with Open3D ray casting, using
   each photo's actual sensor-basis camera pose and scaled pinhole intrinsics.
   The preview uses the final compiler's wall-aligned transforms, part materials
   and inter-Object occlusion. Pair the original photo with its render, identically
   resized to at most 1280 pixels. A magenta estimated target rectangle supplies
   context; it is not a segmentation mask. Preview shading is flat, without PBR
   lighting, shadows or photo textures.
5. Ask OpenAI to construct/correct one Object as schema-constrained parts and
   materials. Locally validate identity, support, finite geometry, closed explicit
   solids, approximate envelope and vertical contact. Preserve the inventory pose,
   yaw and identity; an incorrect initial placement must fail comparison rather
   than be silently moved. Check the composed room's geometry, support export and
   navigation before accepting a candidate.
6. Compare rendered optical-axis depth with captured depth. Each assessed target
   view requires at least 16 supported depth pixels; at most 20% may differ by
   more than 0.15 m. These initial engineering tolerances are recorded in reports;
   they do not prove complete observed geometry or measurement accuracy. Pixels
   with no rendered target or no confident depth cannot establish agreement.
7. Ask OpenAI for a per-view visual critique. Every supplied frame must appear
   exactly once, with consistent verdict/issues. Feed fitting discrepancies back
   into the next construction request, up to three construction attempts. Local
   depth failures skip the paid critique and become numerical correction feedback.
8. Once fitting views pass, check the reserved Object view separately. Its images
   and feedback never enter that Object's correction calls. A validation failure
   stops publication. This is held out from Object construction only: inventory,
   global poses and LiDAR summaries are shared priors, not an independent survey.
9. Recheck the assembled room from up to eight assessed viewpoints, including
   omissions/blocked openings, after all Objects pass. For an empty inventory,
   check up to four chronological room views. A failure retains evidence without
   publishing a coarse substitute as a finished room.
10. Project original photos onto depth-visible nonreflective Object faces using
    the existing photo baker. Unseen faces retain generated material colors;
    mirrors and highly reflective material faces are excluded. Unseen faces keep
    their procedural texture maps and original UVs. Revalidate assets
    and publish separate OBJ/MTL Objects, scene/room JSON and a packaged USDZ with
    the existing atomic revision/checksum contract. No generated code executes.

The method supports ADR-0002's fixed room structure and moves toward ADR-0004's
captured appearance through photo-guided modeling/projection. It does not certify
exact replicas, unseen detail, photographic realism or editability; the merged
viewing-only decision in SPEC §3.5 still overrides the historical editing ADRs.
This worker's geometry, camera tests and exports are separate from the upstream
Three.js authoring implementation. No dimensional-accuracy claim is certified.

## Calls, receipts and recovery

Requests use the OpenAI Responses API with high reasoning effort, structured JSON
outputs, `store=false`, Standard/default tier and no hosted tools. Inputs include
private selected photos, rendered previews and spatial/calibration evidence.
Official contracts: [image inputs](https://developers.openai.com/api/docs/guides/images-vision)
and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
`store=false` alone is not a zero-retention guarantee.

A typical successful Object uses a construction call, a fitting-review call and
a validation-review call, in addition to inventory and final room review. Failed
fitting can add two correction/review pairs. Inventory has a 24,000-output-token
allowance, construction 16,000 and critique 4,000, including reasoning. Actual
latency/cost and how many Objects fit the existing $10 ceiling are unmeasured.

Use the existing `work/astra-budget-v3.json` ledger so changing methods cannot
reset known spending or unresolved reservations. Content-addressed responses live
under `work/insta-v1/responses/HASH/response.json`; byte-equivalent requests reuse
the same response even across correction stages. Photo/render pairs, cameras,
depth comparisons, rejected candidates and critiques live under `insta-v1/objects/`
and `insta-v1/room-check/`. Retained response fingerprints include exact prompts,
model, schema, calibration and encoded images. Interrupted/unknown billing stops
additional paid calls. No automatic paid request retry bypasses that reservation.

Normal Retry reuses matching work in the same generation. Explicit Generate from
scratch retains the existing confirmation and isolates all work/budget under
`work/runs/UUID/`. Prior successful results remain intact. API errors, invalid
schema, insufficient coverage, failed reviews or exhausted budget fail the job
without publishing a partial room. Local input/paid-response retention permits
diagnosis; some failures need a better scan or a new explicit generation.

## Verification boundary

`services/reconstruction/tests/test_insta_method.py` uses an analytic captured
room, real ray casting, real geometry/support validation, photo projection and
USDZ export with a mocked OpenAI transport. It checks projection/depth at image
edges, disjoint construction/validation views, correction feedback, failed-view
rejection, checkpoint reuse, asset corruption and budget refusal. These are
software checks, not fresh-device capture or live model quality evidence. Real
room appearance, walking stability, latency and actual API usage need a configured
service and a real scan. Keep that distinction when reporting results.

Verified locally on 22 October 2026: the reconstruction regression suite passed
257 tests with one opt-in skip; the final focused method suite passed all 11
tests, including fresh-generation isolation and unknown-outcome handling. Both
Swift suites passed with two opt-in skips, and the new synthetic photo-textured
OBJ/USDZ then passed the opt-in native ModelIO/SceneKit import test. The unsigned
iPhone Simulator app build succeeded. No live OpenAI generation, real-device
capture or remote deployment was performed.

The earlier description-only worker remains selectable via `RESPACE_PIPELINE=astra`
when launching the Python worker directly. The retained service README's semantic
batch sections describe that compatibility path.
