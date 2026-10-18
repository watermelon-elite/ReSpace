> Historical backend/inspector documentation. The current iOS saved-room screen only displays completed v2 walkthroughs; these old inspector controls are not its current UI. Use the current README for setup.

# ReSpace reconstruction worker

For a separate server that does not depend on the Mac's network connection, use the [Google Cloud deployment](deploy/README.md). It provisions a persistent Ubuntu worker and changes the iPhone endpoint only after HTTPS readiness succeeds.

FastAPI + SQLite + files, one subprocess at a time, running locally or on the deployed server. Original iPhone captures remain intact. The worker uses Open3D 0.19 TSDF fusion and OpenMVS 2.4 refinement/texturing, then calls **GPT-6 Astra** to generate supported missing surface/object parts from selected photos, calibrated LiDAR samples, mesh geometry and RoomPlan data. The worker validates the structured scene and compiles it to an explorable OBJ. COLMAP itself is not required.

## Run on a Mac

Requires Python 3.11 or 3.12 (Open3D 0.19 does not support the Mac's default Python 3.14). On Apple Silicon:

```sh
cd services/reconstruction
./setup.sh
# Add OPENAI_API_KEY to the private .env before starting (see .env.example).
./run.sh
```

If Python is installed elsewhere, use `PYTHON_BIN=/absolute/path/to/python3.12 ./setup.sh`. Setup installs into `.venv`, downloads the official arm64 OpenMVS release into `.tools`, verifies its SHA-256, and generates a random token in ignored, owner-readable `.env`. Other hosts can provide installed OpenMVS tools through `RESPACE_OPENMVS_BIN`. Open3D and OpenMVS run CPU stages sequentially with four OpenMVS threads, suited to this 8GB Mac. Input/output budgets bound storage and asset size; large or unusually complex scans can still exceed the available RAM and fail without deleting the original.

Keep the Mac awake and connected while processing. A stopped service recovers running jobs on its next start. Run one Uvicorn process; startup refuses a second process sharing the data directory. No processing timeout is imposed.

## Astra configuration and behavior

Set `OPENAI_API_KEY` in the reconstruction server's private environment. For the local worker, add it to `services/reconstruction/.env`; for systemd, use `/etc/respace-reconstruction.env` and restart the service. The key must never be embedded in the iOS app. `.env.example` documents the settings. The default `RESPACE_SCENE_GENERATOR=astra` calls `gpt-6-astra` through `POST https://api.openai.com/v1/responses` with high reasoning, strict JSON-schema output, a 32,768-token output budget and `store=false`. Set `RESPACE_SCENE_GENERATOR=measured` to run only the geometric/photo pipeline.

`RESPACE_ASTRA_IMAGE_LIMIT` defaults to 32 (allowed 1–40). The selector evaluates up to 160 frames across the scan, discounts blur/poor exposure, and favors different camera positions and directions. It sends up to the configured number of JPEGs resized to a 1280px maximum edge, explicit camera calibration/poses, up to 192 confident metric depth samples per selected view, original and reconstructed meshes simplified to 1,200 triangles each, and RoomPlan surfaces/objects/openings. The original full-resolution data stays on the worker. Request payloads are capped at 32 MiB; responses at 8 MiB. The OpenAI call has a 900-second network timeout and no automatic retries. An interrupted call can have an unknown billing outcome; a user-requested retry can incur a new call.

Mesh evidence excludes unused vertices after decimation and remaps triangle indices. Geometry/calibration JSON is additionally capped at 256 KiB before making a billable request; exceeding it retains a partial measured result with an actionable error. These size guards bound payload growth, not exact token counts or dollar cost. Check actual usage for each scan before running a batch.

Astra describes missing geometry as triangles with materials and evidence references. No model-generated code is executed. The compiler checks schema, unique identities, indices, finite coordinates, at least two supporting views where available, confidence, original scan bounds, semantic openings, duplicate measured surfaces and conflicts with observed LiDAR free space. It caps additions at 16,000 vertices/24,000 triangles and the combined model at one million triangles. Checks are conservative heuristics, not a proof of reconstruction accuracy. New materials use model-selected colors; existing photo UVs/textures and measured geometry are retained. This produces a scan-based scene with inferred additions, not a native OpenAI photogrammetry output or a guarantee of photorealism.

Successful responses are checkpointed under `work/astra-response.json` against a fingerprint of the exact request and prompt version. Local processing retries with identical evidence reuse that completed response. Changed evidence/configuration produces a new request. Invalid geometry responses are archived as `astra-rejected-response.json` so an explicit retry can request a corrected scene. A durable `astra-inflight.json` marker prevents automatic restart recovery from repeating an interrupted, possibly billed request; the app's explicit **Retry processing** action clears that marker. Such a retry can incur another API charge. `work/astra-evidence.json` records the geometry/calibration sent (without image bytes). Result assets include `astra.obj`, `astra.mtl`, `astra-scene.json`, `astra-provenance.json`, and the original texture assets. The report records model, response ID, token usage, selected frames, accepted/rejected components and exact generated face ranges. The inferred overlay includes all accepted AI triangles, and any generated geometry requires review. The Original view remains available for measurements.

Missing credentials, API errors/refusals, incomplete output or validation failures produce a retryable partial result with the measured/photo model intact. No fallback is labeled as an Astra model. Supplying the key and choosing **Retry processing** completes the generation stage. Earlier successful measured jobs can be upgraded with **Generate AI model**. Users see that selected photos and scan geometry are sent to OpenAI before choosing generation. OpenAI processes those inputs; `store=false` does not itself establish zero data retention. See the official [Responses API](https://developers.openai.com/api/docs/guides/responses) and [data controls](https://developers.openai.com/api/docs/guides/your-data).

## Connect the iPhone

In ignored `Configuration/Local.xcconfig`, retain existing values and add:

```xcconfig
RESPACE_LOCAL_CAPTURE = YES
RESPACE_RECONSTRUCTION_URL = http:/$()/YOUR-MAC.local:8008
RESPACE_RECONSTRUCTION_TOKEN = TOKEN_FROM_SERVICES_RECONSTRUCTION_ENV
```

The slash substitution is required by xcconfig. Use `scutil --get LocalHostName` to find the Mac name. Both devices must be on the same LAN. Rebuild the app; allow Local Network access and the Mac's incoming-network permission if macOS asks. Open a saved room and tap **Generate AI model**. Upload is explicit and sequential, streams from disk, and retries only missing committed artifacts. The worker continues when the viewer or app closes. Reopening the viewer resumes status checks/downloads. Interrupted uploads resume with **Generate AI model** or **Retry processing**. The viewer opens the **AI model** when ready; **Original** retains the measured view and ruler. **Highlight inferred geometry** overlays geometric repairs and all AI additions in orange. **Report** shows overall room spans, generation details, review warnings and stage failures. Measured-only or failed-generation results appear as **Processed**.

The local token is a development shared secret. HTTP is restricted by the client to local addresses and is not encrypted. Use HTTPS with appropriate authentication outside a trusted LAN. Configuration embeds the development token in the app; do not ship this development credential as a production authentication mechanism.

### Retrying scans from the initial client build

The initial client encoded path components twice: UUID hyphens became `%252D` and result filename dots were also encoded twice. The server rejected the first manifest with 422, and subsequent status checks returned 404 because no job had been created. The corrected client appends raw URL components once, treats a not-yet-created job as retryable submission intent, and distinguishes HTTP failures from local storage failures. Rebuild the iPhone app, reopen the saved room, and tap **Generate AI model** again. Existing scan data and the service/token configuration can be reused.

## Capture and processing contract

- New local scans require 180 seconds before Done. Up to 900 keyframes are retained, at a nominal 0.5-second interval with motion/angle admission and one encoder. JPEGs retain up to 2560px at quality 0.9; high-resolution 30fps camera formats are selected when available. Source resolution is a device capability, not a promise of additional optical detail. Registered metric depth/confidence, calibration, poses, RoomPlan export and final ARKit mesh are retained. A 2GiB capture ceiling and 512MiB free-space reserve protect the phone. Photo admission stops ahead of the ceiling to reserve 192MiB for final mesh/room export; users can still finish the scan after the minimum. Existing connected captures retain the 40-frame profile.
- `PUT /v1/reconstructions/{capture_id}` commits the version-1 capture manifest. The response lists `missing_artifact_ids`. Repeating identical input is idempotent; changing input under an existing ID returns 409.
- `PUT .../artifacts/{id}` streams an individually sized/SHA-256-verified artifact to a temporary file and atomically commits it. Limits: 128MiB per artifact, 2GiB total, 900 frames, 8MiB manifest. Inputs become immutable at submission.
- `POST .../run` queues one job and returns immediately. `GET ...` returns `uploading`, `queued`, `running`, `succeeded`, `partially_processed` or `failed`, stage, revision, error and result assets. `POST .../retry` requeues failed/partial work without deleting successful checkpoints. Unknown-outcome requests reuse the capture identity.
- Result assets are enumerated with byte lengths and SHA-256. Download using `GET .../results/{revision}/assets/{filename}`; the app verifies them before exposing the model. Results are OBJ + MTL + photo atlases, plus depth fallback, baseline PLY and `quality.json`, all in original ARKit meter/Y-up coordinates. The worker enforces a 512MiB result budget and 128MiB per file.
- Open3D fuses depth at 1.5cm voxel size with 6cm TSDF truncation, rejects low-confidence/invalid depths and samples registered color. It applies two mild Taubin smoothing iterations and limits the baseline to 400K triangles. RGB coloring is not image-derived depth estimation.
- OpenMVS imports our existing calibrated camera poses via COLMAP text files with explicit ARKit/OpenCV axis and pixel-center conversion. Depth-verified vertex observations supply image visibility. All available depth frames are fused; photo refinement uses at most 240 frames spread over the full scan to bound image memory (override with `RESPACE_PHOTO_LIMIT`, range 12–900). RefineMesh deforms the fused mesh using images, followed by TextureMesh. This is not a joint optimization that guarantees LiDAR constraints during photo refinement. All OpenMVS automatic hole closing is disabled. Untextured faces use gray.
- Repair closes convex, planar boundary loops at most 20cm in diameter. It also fills missing cells on detected RoomPlan wall/floor planes, preserving their transforms and polygon boundaries. Floors require their native polygon; curved walls are skipped. Added cells remain at least 4cm from existing geometry. Completion excludes overlapping RoomPlan doors/windows/openings and skips if supplied transforms cannot be understood. Larger furniture holes and complex unsupported surfaces remain open. Exact repaired baseline face indices, semantic source IDs and boundary coordinates live in `quality.json`; the final-mesh overlay transfers labels by closest baseline face and is approximate. It is not a complete map of all inferred or uncertain reconstruction surfaces. Apple's [polygonCorners documentation](https://developer.apple.com/documentation/roomplan/capturedroom/surface/polygoncorners) specifies local plane coordinates.
- Review is flagged for any accepted Astra geometry or if overall axis-aligned room spans drift by more than max(5cm, 2%) from the original ARKit mesh. Median and 95th-percentile original-vertex-to-derived-surface distances are also reported. Overall spans are not individual wall measurements or ground-truth accuracy. The ruler is available only on the original scan.
- Photo-stage failure retains the Open3D fallback as `partially_processed`; core depth failure is `failed`, leaving original and intermediate files available. Logs remain on the Mac under each job's `worker.log` / `work/openmvs.log`.

Files remain in `data/{sha256(capture_id)}` until explicitly removed while the service is stopped; `jobs.sqlite3` records the original capture identity. Deleting a local room in the app deletes that iPhone copy, not its server copy. No automatic data eviction is implemented.

## Verify

```sh
.venv/bin/python -m pytest -q
```

Tests run offline with generation disabled by default; dedicated Astra tests intercept the HTTPS transport and exercise selection, multimodal request contents, completed-response caching, schema/refusal/error handling, geometry constraints, texture-preserving export and the complete pipeline through checksummed downloadable model assets. They make no paid API calls. A live Astra/device quality check still requires a configured server key and a retained real scan.

Tests exercise upload integrity/idempotency, schema/path/calibration rejection, queue/restart/retry behavior, retained partial results, asset allowlisting, repair provenance, semantic opening protection, concave floor boundaries, camera coordinates and an actual synthetic TSDF pass with photo-stage fallback. To test a running service end-to-end through OpenMVS: `RESPACE_TEST_LIVE=1 .venv/bin/python -m pytest tests/test_live_worker.py -q`. This creates a synthetic room job on the local service and verifies downloaded checksums. Apple's Model I/O loader was also verified against generated textured geometry. Real-room completeness, thin furniture retention, image overlap/blur, texture quality, phone capture temperature, storage use and measurements must be validated using LiDAR-device scans; no real-room quality claim follows from the synthetic test.

Swift regressions exercise the actual reconstruction client against a URLSession test protocol to validate UUID paths and recovery after rejected first submissions. `ReconstructionTests.testLiveSwiftClientUploadsProcessesAndDownloadsRetainedScan` is an opt-in full Swift-client integration check: set `RESPACE_TEST_SWIFT_RECONSTRUCTION_FIXTURE` to a directory containing a synthetic capture manifest/artifacts and provide `RESPACE_RECONSTRUCTION_TOKEN` in the environment. The default origin is `http://127.0.0.1:8008`, overridable through `RESPACE_TEST_ORIGIN`. It verifies file uploads, queue/poll responses, checksummed model/material/texture downloads, and retention of the original scan.

Pinned Python resolution is in `requirements.lock`. OpenMVS binaries are not checked in. Consult [OpenMVS licensing](https://github.com/cdcseacave/openMVS/blob/v2.4.0/LICENSE) and dependency licenses before product distribution/hosting.
