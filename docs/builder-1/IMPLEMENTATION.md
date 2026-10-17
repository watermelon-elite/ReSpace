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

Copy `Configuration/Local.xcconfig.example` to the ignored `Configuration/Local.xcconfig`; enter the backend HTTPS origin and shared app key. `Configuration/AppInfo.plist` supplies these custom fields to Xcode's generated plist using `RESPACE_SERVICE_URL` and `RESPACE_APP_KEY`. The compiled plist was checked with non-secret configuration values. Use Xcode user-defined build settings or pass the local file:

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild \
  -project ReSpace.xcodeproj -scheme ReSpace \
  -xcconfig Configuration/Local.xcconfig \
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
