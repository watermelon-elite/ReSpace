# Builder 1 implementation

This implements `BUILDER_1_SPEC.md` in the existing iOS target. The app requires a LiDAR iPhone, iOS 18+, and portrait orientation. Simulator launches deliberately stop at the compatibility screen. There is no production fixture/sample bypass.

## Ownership and integration boundaries

| Directory | Owner / purpose |
| --- | --- |
| `ReSpace/App/` | Builder 1: hardware gate, configuration, device identity, room operation coordination |
| `ReSpace/Domain/` | Builder 1: Swift value types and client admission/input rules |
| `ReSpace/Networking/` | Builder 1: transport, wire encoding, schema/geometry checks, recovery |
| `ReSpace/Persistence/` | Builder 1: exact pending requests, drafts, deletion records |
| `ReSpace/Capture/` | Builder 1: RoomPlan, calibrated keyframes, raw artifacts and upload/finalize recovery |
| `ReSpace/Rooms/` | Builder 1: list, rename, delete, room review and planning UI |
| `ReSpace/Design/` | Builder 1: intent, conversation, selected context, sheet and Undo UI |
| `ReSpace/Rendering/` | Builder 1: RealityKit entities, stand-ins, immutable asset cache and camera |
| `ReSpace/ShoppingPresentation/` | Builder 1: labeled display/navigation only; demo products never enter canonical scenes |
| `Tests/ReSpaceCoreTests/` | Builder 1: executable client contracts and operation-lifecycle tests |
| `server/perception/`, `server/geometry/`, `server/solver/` | Reserved for Builder 2; untouched |
| Other `server/`, `scripts/`, `assets/`, backend contract fixtures | Reserved for Builder 3; untouched |

The Xcode project uses a filesystem-synchronized `ReSpace/` group. New Swift files are discovered automatically. Builders 2/3 should not need to edit `project.pbxproj` or client files. The standalone root `Package.swift` tests the actual client code without adding test-target entries to the Xcode project. Client fixture JSON lives under `Tests/`, not the shared `fixtures/contracts/` path. Do not treat it as cross-builder agreement.

## Configure and run

### Temporary local scan testing

`RESPACE_LOCAL_CAPTURE = YES` is currently the default in `Configuration/App.xcconfig`. Rebuild and run on a LiDAR iPhone without supplying any service address or app key. New Scan runs RoomPlan, samples the same calibrated photo/depth artifacts, and saves the completed raw RoomPlan JSON plus a parametric USDZ preview on the phone. Tap a saved room to inspect it in the 3D-only viewer (orbit, pinch to zoom, two-finger pan, Reset view); long-press to rename or delete it. Completed scans survive relaunch, and failed local exports offer Retry save. Network loss does not interrupt local scanning; backgrounding or loss of AR tracking still does.

Local captures live under `Application Support/ReSpace/LocalTesting/Captures`, separate from connected captures. They do not claim server acknowledgment, evict raw files, create canonical backend snapshots, or upload automatically when connected mode is restored. AI perception, generation, and chat editing are unavailable in this temporary local screen. Interrupted incomplete acquisitions are removed on relaunch; completed captures are retained until deletion.

When Builders 2/3 are ready, set `RESPACE_LOCAL_CAPTURE = NO` in `Configuration/Local.xcconfig` and rebuild to restore the existing connected My Rooms and review/design flow. Local rooms remain on the device but are hidden in connected mode; setting YES again makes them visible.

### Connected mode

Copy `Configuration/Local.xcconfig.example` to the ignored `Configuration/Local.xcconfig`; replace the examples with the deployed backend HTTPS origin and its shared app key. Keep the URL's `https:/$()/` spelling: Xcode expands it to `https://`, while a literal `//` starts an xcconfig comment. Use the origin without `/v1`; the client adds `/v1/` itself.

Both Debug and Release automatically load this file through `Configuration/App.xcconfig`, including when using Xcode's Run button. `Configuration/AppInfo.plist` supplies `RESPACE_SERVICE_URL` and `RESPACE_APP_KEY` to the app as `ReSpaceServiceURL` and `ReSpaceAppKey`. Rebuild and run the app after changing them; these values are embedded at build time, not entered in iPhone Settings. You can also override them using Xcode user-defined build settings.

The exact error “The room service is not configured” is raised locally before any network request when the service URL is missing, does not use HTTPS, or the app key is empty. This checkout contains the iOS client, not a deployed backend or real credentials. Obtain the HTTPS origin and matching shared `X-App-Key` from the backend owner; the example values will not enable scanning. The service must implement the endpoints below, including room creation before RoomPlan starts.

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild \
  -project ReSpace.xcodeproj -scheme ReSpace \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /tmp/ReSpaceBuilder1 CODE_SIGNING_ALLOWED=NO build

DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test \
  --scratch-path /tmp/ReSpaceCoreTests
```

Select a physical LiDAR iPhone for actual scanning. No provider credentials belong in the app. The device UUID is stored in Keychain. An unconfigured service produces an explicit unavailable state; there is no local design generator or fake success path.

## Client wire proposal for Builders 2 and 3

These are implemented proposals, **not approved backend capabilities**. Coordinate agreement and server persistence remain integration requirements. `ReSpace/Domain/` and the valid JSON under `Tests/ReSpaceCoreTests/Fixtures/` are the complete client record definitions. JSON field names are snake_case; schema envelopes carry `schema_version: 1`. Budget is a positive decimal string in USD. `Data` fields are JSON base64 strings. IDs are opaque and path-escaped. Timestamps are UTC ISO 8601 strings.

Requests carry `X-Device-Id`, `X-App-Key`, and mutation `Idempotency-Key`. The service origin is followed by `/v1/`. JSON success responses are required, including explicit deletion confirmation. Unknown-operation lookup must return a structured `unknown_operation` error; a generic 404 is intentionally insufficient evidence to replay a command.

| Endpoint | Client expectation |
| --- | --- |
| `POST /rooms` | `operation_id`, requested `capture_id`, stable date-based name, `mode: home` → `DraftRoomResult`; preserve the requested capture identity |
| `GET /rooms[?cursor=…]` | `RoomList` with device-scoped summaries and optional `next_cursor` |
| `GET /rooms/{id}` | `RoomRecord`: summary, current immutable snapshot, planning revision |
| `PATCH /rooms/{id}` | Name + expected metadata revision → updated `RoomSummary` |
| `DELETE /rooms/{id}` | Idempotent identity → `{schema_version:1, deleted:true}` only after deletion is durable; invalidate concurrent operations |
| `POST /rooms/{id}/keyframes` | Multipart `meta` (CaptureFrame JSON), `jpeg`, `metadata`, optional `depth` and `confidence`; frame ID is idempotency identity → `FrameUploadResult` |
| `POST /rooms/{id}/finalize` | Stable `operation_id`, expected manifest, base64 raw `captured_room` JSON bytes and optional base64 thumbnail → `FinalizeResult` with canonical room or operation and complete storage receipts |
| `GET /rooms/{id}/snapshots/{snapshot_id}` | Exact `RoomSnapshot`, including its scan-to-room transform |
| `GET /rooms/{id}/conversation[?cursor=…]` | `ConversationPage`, canonical event IDs, context/base/version associations |
| `POST /rooms/{id}/planning-commands` | `CommandRequest` with selected object and frozen snapshot/planning revision → `RoomOperation`; never a design mutation |
| `POST /rooms/{id}/designs` | `GenerationRequest` with snapshot/planning and active-pointer preconditions → `RoomOperation` |
| `POST /designs/{id}/chat` | `CommandRequest` with selected item and active-pointer preconditions → atomic canonical `RoomOperation` |
| `POST /rooms/{id}/undo` | Expected active ID/revision + operation ID → operation that persists the parent pointer |
| `GET /operations/{id}` | `RoomOperation`, with `id`, `room_id`, kind, state, outcome/failure, clarification and message IDs |
| `POST /operations/{id}/clarifications` | Original operation, question, unique reply ID, reply token, reply and base64 original request bytes → same operation |
| `POST /operations/{id}/dismiss-clarification` | Original operation, question, unique dismissal ID → same operation with no scene change |
| `GET /designs/{id}` | Exact immutable `DesignVersion`; never enriched/mutable geometry |

The renderer consumes asset descriptors carried by scene items. A separate catalog-manifest request is unnecessary for current rendering; no client product resolution is performed. Missing assets fall back to measured category stand-ins. Product details and alternatives cannot apply swaps or navigate to retailers. Totals are displayed only when their supplied `design_id` matches the active version.

### Geometry and calibration handoff (Builder 2)

- Meters; right-handed, Y up; floor points `[x,z]`; scene position `[x,y,z]` is bottom-center. Size is `[width,depth,height]`. Yaw is radians around +Y with forward +Z.
- Objects carry explicit `base_elevation`. Openings carry `wall_id`, offset, width, bottom and height. Each wall includes its height. Invalid-boundary snapshots can have an empty floor but must supply validity reasons.
- The frame metadata stores sensor-oriented JPEG dimensions, `[fx,fy,cx,cy]` scaled to those actual encoded dimensions, and 16 column-major camera-to-original-scan-world floats. Snapshot `scan_to_room_transform` is returned by Builder 2; the app does not invent it.
- Optional native depth is packed row-by-row as little-endian float16 meters, with actual dimensions. Confidence is tightly packed ARKit uint8 with independent recorded dimensions. Both come from the same ARFrame as the JPEG and pose.
- Supply stable object IDs or `object_aliases` on late snapshots. Review selection follows aliases; planning persistence remains canonical on the backend.
- Removed existing items need `last_valid` placement. Removed new products are omitted from visible items. Ghost visibility and camera movement are presentation state only.
- USDZ assets declare immutable ID/revision, HTTPS URL, meter units, bottom-center pivot, +Z forward and authored bounds. `normalized: true` assets are fitted once to target dimensions. Already dimensioned assets must match the supplied dimensions; mismatches use a stand-in instead of double scaling.

### Durable operations and storage handoff (Builder 3)

The app journals exact request bytes and identity before submitting. A pending generation, planning command, edit, clarification or Undo locks only its room. Navigating away never cancels that request. A timeout retains the lock and requires lookup. Only explicit `unknown_operation` permits resending the same original identity/payload. Definitive rejection, failure and unavailable capability never mutate local geometry.

Terminal operation reconciliation retrieves the canonical room, conversation, active immutable design and its exact snapshot before clearing the local journal. Active version is independent of newest version. Undo moves the server pointer; subsequent edits use that restored version as parent. Canonical event IDs are deduplicated on display. Server commits must atomically preserve event associations, planning revisions, scene versions and pointer changes. Server-side execution must survive client disconnection.

Clarifications retain the original operation and base request; each answer/dismissal has its own persisted identity. A pending uncertain answer cannot be replaced with a competing reply. No-op, clarification, rejection and unavailable outcomes must not create design versions. Stale bases must reject explicitly; never silently rebase.

Capture artifacts are stored incrementally in Application Support with byte lengths and SHA-256 checksums. Upload storage acknowledgment is separate from perception status. Detector failure may be terminal while artifacts remain durable. Local eviction requires successful finalization and a matching durable receipt for **every** expected artifact, including export and thumbnail. Retain completed raw data on the backend without expiry until room deletion. A finalization retry must return the original canonical result and receipts.

Restart abandons an incomplete acquisition; it cannot resume. The client records deletion intent and retries cleanup. Completed captures retain upload/finalization recovery separately. Deletion must include raw assets, snapshots, conversation, history and metadata, and prevent late operations from resurrecting the room.

## Verification and remaining evidence

The simulator and physical-iPhone Release builds and 22 executable core/lifecycle tests pass. Tests cover strict USD/style input, coordinate/size interpretation, sampling caps and pressure, concave floor topology, exact durable journals and recovered multipart bytes, checksum acknowledgment gates, unknown/running/lost-response reconciliation, clarification identities, atomic rejection, duplicate prevention, persisted Undo branching and deletion racing a command. The app was launched in the iOS simulator and its compatibility gate was visually inspected.

Physical LiDAR capture, optional sceneDepth availability during RoomPlan, interruption/relocalization behavior, at least three real calibration projections, iOS 18 device rendering/gesture performance, actual USDZ assets and backend retention/operation semantics still need joint device/service verification. No real capture fixtures, backend deployment or cross-builder contract approval is claimed by this implementation.

### Local room viewing and color

Local room previews use a camera-controlled SceneKit scene instead of Quick Look, so viewing a room never offers AR mode or starts an AR session. The existing backend review/design viewer remains a virtual-camera RealityKit scene.

`RoomColorizer` loads the retained parametric USDZ and estimates one diffuse color per geometry node from the saved ARKit RGB JPEGs. It projects visible model intersections through the matching saved camera pose and resized intrinsics in sensor coordinates. Model ray tests reject occluded geometry; a median limits highlights and shadows. It processes one photo at a time off the main actor, supports cancellation, and leaves existing authored textures intact. Saved local scans can use their retained photos without rescanning. Raw capture files and the USDZ on disk are unchanged; these estimated colors are applied when opening the preview.

This is approximate surface color, not photo texture mapping or a photorealistic reconstructed mesh. Unobserved geometry retains the exporter’s materials. Geometry differences, unmodeled occluders, sparse photo coverage and changing lighting can affect color accuracy. Verify scan-coordinate alignment, RGB orientation, gesture behavior and color quality on a physical LiDAR iPhone. The RGB acquisition and calibration already existed before this change; the new step connects them to the local viewer. Backend assets already preserve embedded USDZ materials and stand-ins use `render.tint`; backend room color estimation remains the service’s responsibility.

### Measured local surface capture

New local scans now use a shared ARSession, pre-run with `.mesh` reconstruction and supported `.sceneDepth` before creating RoomCaptureView. The final current frame’s mesh anchor set is copied to a validated, hashed binary `scene_mesh` artifact. Native positions, normals, indices and anchor transforms are retained in scan meters. No furniture fitting or geometry beautification is applied to this viewer; local RoomBuilder processing uses no `.beautifyObjects`. Backend captures keep the existing wire protocol and do not emit the mesh artifact.

The local viewer prefers that measured mesh, samples registered photo colors per vertex with depth/confidence visibility checks, and offers a two-point distance ruler. Old local scans remain explicitly marked as simplified; corruption of a recorded mesh produces an error rather than silently displaying simplified geometry. Mesh/color processing is bounded, cancellable and off the main actor. The final anchor snapshot avoids installing an ARSession delegate that could interfere with RoomPlan.

See `MEASURED_SCAN_VALIDATION.md` for implementation details, completed synthetic/software checks and the outstanding physical-device accuracy procedure. This supersedes the preceding local-preview paragraph for new scans; the old per-node color path remains for earlier scans.
