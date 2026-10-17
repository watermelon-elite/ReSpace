# ReSpace — Builder 1: iOS and 3D Specification

> **Status: complete review candidate, awaiting confirmation of shared understanding.** Product behavior reflects the interview. Exact API contracts below are proposed handoffs and still require agreement with Builders 2 and 3.

## Authority and scope

- `SPEC.md` is the sole source specification for this work. Older specifications and flow documents are excluded.
- Builder 1 owns the iOS client for the selected feature scope: capture, navigation, rendering, interactions, API integration, local state, and shopping UI using placeholder data.
- Builder 2 owns perception and geometry calculations. Builder 3 owns backend services, AI, and product resolution.
- This document will define the exact data and behavior the iOS client requires from those builders. Proposed changes to shared contracts require agreement with the responsible builder; this interview does not establish their approval.
- Time budgets, staffing schedules, and hourly milestones do not constrain this specification.
- The final deliverable is this separate specification; `SPEC.md` remains unchanged.

## Glossary

| Term | Meaning |
|---|---|
| Room | A single physical space being reviewed and redesigned, including its structure and existing furnishings. |
| Existing item | A furnishing already present before redesign, distinct from a product proposed for purchase. |
| Product | A purchasable furnishing with a store listing, price, and available descriptive information. |
| Design | A proposed arrangement of existing items and selected products. |
| Keep in place | An instruction to preserve an existing item's position; movement or removal requires explicitly unlocking it. |
| Let the design decide | The default planning state, allowing changes permitted by the selected intent. |
| Remove from design | An instruction to exclude an existing item from the proposed arrangement while preserving it in the original room. |
| Room snapshot | The fixed room state used by a design, unaffected by later detections. |
| Saved room | A completed scan retained for later review and redesign, including measured room data, detected items, thumbnail, associated designs, and raw capture artifacts. |
| Design version | A saved, unchanging arrangement produced by generation or one successfully committed design command. |
| Planning instruction | A natural-language instruction controlling what a future design may change; it does not alter the measured scan or an already saved design. |
| Active design version | The version currently chosen for a room, including one restored through Undo; this is the design reopened from My Rooms. |
| Ghost | A faint representation of removed existing furniture, preserving visual context without occupying space in the proposed arrangement; it can be hidden. |

## Product specification

### Feature boundary

- Use P0 as the starting point, with these explicit changes: shopping is UI/navigation only; natural-language editing, versioning, Undo, and saved-room management are included; manual model editing is excluded.
- All model edits use a typed natural-language composer. Ordinary keyboard dictation may be used; there is no custom voice-recording feature. No dragging, rotation gestures, or direct manual model-editing controls are required.
- Spot intent, Before/After toggle, walk mode, Day/Evening toggle, sharing, and other unselected P1/P2 features are excluded. The original room state is still preserved as data; this does not require a Before/After UI.
- Personal and business usage are identical and follow the personal-use experience. Remove the mode selector, business labels, seat target, and business-specific controls. If the original API still requires mode, Builder 1 sends home.
- Only LiDAR-capable iPhones may use the app. There is no sample-room feature, non-LiDAR browsing path, or iPad support. Unsupported devices show a compatibility screen and cannot enter room/design flows. The source baseline is iOS 18; portrait layout remains the proposed interface baseline.
- Dedicated accessibility work and acceptance criteria are outside this scope. Do not deliberately disable standard platform behavior.
- Offline operation is not required. Retaining failed capture data for retry is a recovery requirement, not a promise of offline scanning or editing.
- Include shopping UI with placeholder data for display and navigation only. Do not simulate product replacement, price recalculation, purchase, or shopping-driven save/Undo behavior. Builder 1 does not implement product search, selection/ranking logic, pricing policy, or backend product resolution. Product cards, alternatives screens, prices/totals, and Buy affordances remain UI responsibilities, as defined under Shopping presentation below.
- Budget input uses USD. Retailer-market restrictions, merchandise subtotal policy, and budget overrides are not Builder 1 responsibilities. Data presentation and user-input forwarding are client responsibilities.
- Retain completed scans as measured rooms, detected items, thumbnails, and associated designs until explicit deletion. Raw camera data follows the separate retention policy. Saved rooms remain reusable for redesign; offline reopening is not required.

### My Rooms and saved scans

- On supported devices, launch into My Rooms with a New Scan entry point. No sample-room entry point exists.
- Each saved room shows a thumbnail, editable name, and scan date. There is no home/business type distinction.
- Opening a saved room enters room review with an option to reopen its persisted active design, which need not be its newest-created version.
- Delete requires confirmation and removes associated room data.
- New scans never replace previous completed scans.

### Design screen and navigation

- The 3D room fills the design screen behind a draggable product sheet with collapsed, medium, and expanded positions.
- Model selection selects and reveals its card; card selection highlights its model.
- The sheet has Assistant and Items tabs, with the text composer available in both. Assistant shows the room conversation; Items shows item cards and placeholder shopping navigation.
- Undo, Reset View, ghost visibility, and processing/error status appear above the scene. Reset View changes camera framing only.
- Selecting a model switches to Items, reveals its card, and shows a selected-item indicator beside the composer. Preserve sheet height unless expansion is needed to reveal the card. Clearing selection removes that context. If an edit removes its target, clear stale selection.
- Gestures control camera navigation and selection only. No Move mode or gesture-based model mutation exists.
- Apply successful edit results immediately without animating model changes. Show a concise description of the change and offer Undo.
- A selected item supplies context for phrases such as "move this." If the target remains ambiguous, ask a clarification rather than silently selecting an item.
- Removed existing furniture appears as a faint ghost by default. Provide an option to hide ghosts and inspect only the proposed design. This visibility control does not change the design.
- Ghosts do not participate in placement validation and cannot be moved as present furniture. Removed new products disappear. Undo restores removals; existing-item removal never erases the item from the saved scan.
- A command such as "bring back the lamp" restores its last valid pre-removal placement, subject to current placement checks. An occupied location triggers an explanation and another placement request. Successful restoration creates a new version without rewinding unrelated edits.

### Intent inputs

- Show Add a few things and Full redesign only; default to Add. Spot intent is excluded.
- Free text supplements the selected intent and never silently changes it. A conflicting request such as "replace everything" under Add prompts the user to choose Full redesign. Semantic conflict detection ownership and response must be specified in the shared contract.
- Budget is a required positive amount entered through a numeric field, with no prefilled amount and a USD label. iOS validates the input format and forwards it; Builder 3 owns interpretation and enforcement.
- Default style is Match what I have. It is mutually exclusive with named styles.
- Named styles are Cozy, Minimal, Japandi, Industrial, Boho, and Mid-century. They support multiple selection. Selecting any named style clears Match what I have; selecting Match clears named styles.
- If the final named style is deselected, return to Match what I have. Text is optional; a valid budget is required. Preserve the form draft through navigation and failure. Parse USD as decimal with at most two fractional digits.
- Retain this intent form for initial generation. During room review, natural-language commands change planning instructions only; arrangement changes occur after generation. The measured scan remains unchanged.

### Generation lifecycle

- Generation continues if the user returns to My Rooms or backgrounds the app. The room shows Generating and retrieves its result when reopened.
- Prevent duplicate submissions for the same pending request. Builder 3 must provide request identity and status/result retrieval; the original API is insufficient.
- Failure preserves the intent form, saved room, and previous successful design. Show the reason and Retry.
- A timeout first reconciles the original request's status before another submission. A failed redesign never replaces the previous successful design.
- Generating again uses the selected saved-room snapshot and current planning instructions, then links success to the previous active design. Undo can return to that previous design. Only the first design has no predecessor.
- Leaving the generation screen does not cancel processing. No separate cancellation of an already submitted generation is required; room deletion invalidates its pending results.

### Existing-item planning states

- Each existing item has exactly one planning state: Keep in place, Let the design decide, or Remove from design.
- Default: Let the design decide.
- Keep in place prohibits redesign movement and removal.
- Remove from design explicitly excludes the item from the proposed arrangement while preserving the original room record.
- Add intent preserves existing furniture unless the user explicitly requests removal.
- Keep in place prohibits movement and removal until explicitly unlocked through natural language. Unlock changes the planning state to Let the design decide.
- Room-review planning choices affect the next generation and never rewrite an existing design. Unlocking within a design is undoable. An explicit "unlock and move" command may perform both operations atomically in one version.

### Edits, validation, and history

**Decision rationale:** Immutable versions replace the source specification's mutable manual edits so Undo consistently reverses a complete user command. The trade-off is additional stored versions and an explicit atomic commit API. Storing the active version separately from creation order preserves Undo across reopening and supports new branches. Linking regeneration to the previous active version makes it reversible too. These product decisions are accepted; shared API and persistence changes still require Builder 3 agreement.

- A successfully committed natural-language design command creates exactly one immutable design version, including when it contains several operations. Validate and commit the whole command atomically. If any requested operation cannot be completed, explain the failure and leave the design unchanged.
- Undo returns to the preceding version. It changes the persisted active pointer rather than creating a duplicate scene.
- An edit after Undo creates a new branch from the restored version and makes it active. Preserve other versions on the backend without providing Redo or history browsing.
- Reopening the room restores the active version, not necessarily the newest-created version. Undo is available only when a parent exists and cannot undo a scan.
- Natural-language edit proposals must pass Builder 2's placement validation before becoming saved designs. Clear, valid commands apply automatically without a separate approval screen or speculative scene preview.
- Clarifications do not commit changes. Ambiguous targets are resolved explicitly; selected-item context may disambiguate them.
- Natural-language commands may add or replace products when Builder 3 returns the resulting scene, even though shopping screens remain placeholders. Builder 1 forwards the command and renders the result; it does not search, rank, calculate prices, or simulate product replacement. Show an honest unavailable state until that backend capability exists.
- Rejected placements leave the last valid arrangement intact and explain the specific reason.
- Network failures restore the last saved state and offer Retry. Ambiguous server outcomes and retry deduplication require an explicit contract.
- Generation, planning commands, design commands, and Undo share one per-room mutation lock. Keep camera navigation available and disable further submissions and Undo until resolved. Show Updating design… while processing, and Saving… only if the backend reports that stage.
- Rename may proceed using its separate metadata revision. Confirmed deletion supersedes the mutation lock: mark the room deleted and prevent outstanding operations from committing or resurrecting it.
- Pending natural-language operations continue when the user leaves or backgrounds the app. The affected room blocks further commands and Undo; other rooms remain usable. Recover the same operation on reopening and apply any completed result without animation.
- Room-review commands atomically update a planning revision, not a design version. No-op commands, clarification, rejection, failure, and unavailable capability create no design version.
- Undo does not revert the scan or room-review planning instructions. To change a review instruction, submit another review command. Inside a design, unlocking is a versioned edit.
- Each immutable design includes its own snapshot, dimensions, transforms, product references, and asset revisions. Later enrichment cannot silently change a saved version's geometry.
- Builder 2 owns placement validation; Builder 3 must agree to version creation, rejection behavior, and the resulting API contract.

### Conversation persistence

- Retain one conversation per room, including commands, clarifications, results, and Undo events. Each entry is labeled room review or design editing and successful edits reference their versions.
- Reopening restores conversation and active design. Undo never erases messages; historical messages retain their original version associations.
- Persist the operation identity and exact command/context before submission. A missing response must not cause automatic replay with a new identity.
- Clarification replies carry the original operation/question identity and base snapshot/version, plus a unique reply ID for deduplicating that submission. Dismissal likewise has its own idempotency identity. Permit an answer or dismissal without speculative mutation; do not permit a second competing operation while the question is pending.
- Canonical planning/design changes, active-pointer changes, and associated conversation outcomes persist atomically or through a recoverable protocol that records each event exactly once. Operation outcomes return message/event IDs so reconciliation cannot duplicate conversation entries or lose the record of a successful change.
- Preserve unsent text during ordinary navigation. Keep the composer visible above the keyboard. Whitespace-only messages cannot be sent.

### Shopping presentation

- Cards/details show labeled demo imagery/text, store, price, reason, and supplied totals. Existing furniture can have cards without shopping fields.
- Use explicit scene item IDs for model/card links. Do not imply that unrelated demo merchandise is the real product represented by a model.
- Alternative cards navigate to detail views only. They never apply replacements, change totals, or create versions.
- Buy is a labeled unavailable/demo affordance. Retailer navigation, cart, checkout, and purchases are outside this build.
- Do not calculate totals locally. Hide or mark a demo total unavailable if it no longer applies to the active scene; never invent an updated amount after a language edit.
- Language-driven product changes are separate: render Builder 3's returned scene and presentation data as supplied. Missing backend capability produces an honest unavailable result.

### Capture interruption and validity

- An interrupted scan must restart; do not offer continuation or Use partial scan after interruption.
- Backgrounding, phone lock, session failure, loss of the coordinate frame, or network failure during scanning requires restarting. Display: "Scan interrupted. Start again to capture this room."
- On Restart Scan, discard the incomplete capture and create a fresh capture with a fresh coordinate frame. Previously completed scans remain intact.
- Transient tracking degradation pauses acceptance of keyframes and displays guidance. Resume only when tracking recovers in the same session. The user may cancel and restart while tracking is degraded.
- Missing small details produce warnings without blocking the flow.
- An unusable room boundary blocks generation and offers Rescan. Sample rooms are excluded.
- Builder 2 supplies room validity and reasons; iOS displays the result.

### Room snapshots and late detections

- Incorporate new detections during room review.
- If processing remains incomplete when generation is requested, offer Wait for details or Continue with current room.
- Generation uses a frozen room snapshot. Late detections never silently alter an existing design.
- Incorporating later results requires a new design.

### Raw-data lifecycle

- Store all recorded capture artifacts, including photos and available depth, without automatic expiry. This is sampled capture, not a promise to record full-frame-rate video or inaccessible internal sensor data.
- Permanently retain completed scans' raw photos, depth, calibration, camera poses, and room exports on the backend until explicit room deletion. Local copies may be cleared after verified upload and successful finalization.
- Restart discards interrupted incomplete captures, as previously agreed. Permanent retention applies to completed scans, not abandoned interrupted acquisitions.
- Failed and pending local uploads remain until retried or discarded. Interrupted acquisition cannot resume; Restart Scan discards that incomplete capture.
- Deleting a room removes its raw assets, snapshots, designs, conversation, and metadata. A late operation must not recreate deleted data. Keep deletion retryable until the backend confirms it.
- Abandoning an interrupted acquisition requests deletion of that draft capture and its uploaded artifacts. Persist cleanup identity if connectivity prevents immediate cleanup; retry on reconnection. Completed scans remain untouched.
- Builder 3 must agree to the backend retention and deletion behavior.

## Screen completion and lifecycle rules

```text
Launch → device gate → My Rooms
                         ├─ New Scan → permission/connectivity → capture → finalize → review
                         └─ Saved room → review → reopen active design

Review → planning commands → intent form → generation → design
Design → language command → clarification OR validation → new active version
Design → Undo → parent becomes active
Review → generate again → result linked to previous active version
```

| Surface | Completion and failure behavior |
|---|---|
| Device gate | Require iPhone hardware and `RoomCaptureSession.isSupported`; unsupported devices have no bypass. |
| Permission | Ask for camera permission on New Scan. If denied, offer Settings and return to My Rooms; do not treat permission denial as incompatible hardware. |
| My Rooms | Empty state offers New Scan. Use a default room name based on scan date, with disambiguation; rename changes metadata, not design history. |
| Scan setup | Require successful backend draft room/capture creation, connectivity, and writable storage before acquisition. Store the device UUID in Keychain as in the source; no login. |
| Scan | RoomPlan camera, outlines, and coaching; Done and Cancel Scan. Cancellation confirms discard and never deletes earlier completed scans. |
| Done | Stop acquisition, obtain the finalized CapturedRoom, and persist it before finalization. Do not serialize an intermediate update as the completed export. |
| Finalization | Show the usable normalized room as soon as available. Do not wait for every optional detector before rendering large geometry. |
| Review | Poll every two seconds while visible for an initial 20-second window. If still processing, retain the honest pending state with Refresh/Continue; elapsed time is not completion. |
| Intent | Disable submission until positive USD budget is valid. Preserve inputs after failure. Keep semantic intent checks on the backend. |
| Generation | Display Generating and known room context from `story`; do not invent completion percentages or claim an unreported pipeline stage completed. |
| Command | Display pending state; no speculative local geometry. Clarification/rejection/no-op leaves the current scene unchanged. |
| Deletion | Confirm deletion of scan, photos, designs, and conversation. If server confirmation fails, retain a visible retryable state. Late results cannot resurrect a deleted room. |

A 60-second client request wait follows the source but is not proof that an operation failed. Reconcile its ID before retrying. Leaving a generation/edit screen is navigation, not cancellation. Mutating controls remain blocked for the affected room while the outcome is uncertain, including on relaunch.

An ambiguous phrase such as “move the chair” with several chairs must trigger clarification. Selected-item context can resolve “this,” but must not silently override a different explicitly named target. Dismissing a clarification applies nothing and releases the room for another command.

Preserve the source's first-generation addition targets (Add: 1–5; Full redesign: 5–20) as Builder 3 responsibilities. Initial generation may report dropped/unplaced additions with explicit warnings as in the source; natural-language edits to an existing design are strictly all-or-nothing.

## Capture implementation and data integrity

### Shared session and sampling

- Use the RoomPlan AR session as the coordinate source. Sample `arSession.currentFrame` without replacing RoomPlan's AR-session delegate.
- Follow source candidate triggers: 1.5 seconds, 0.5 m translation, or 20° turn since the last accepted frame. Coalesce simultaneous triggers and accept at most 40 frames per capture.
- Reject candidates when tracking is not normal, the source's motion-speed proxy exceeds 0.3 m/s, or bounded processing capacity is unavailable.
- The keyframe cap stops sampling only, not RoomPlan scanning. The source's 60–120 seconds is capture guidance, not an automatic stop timer.
- Write accepted artifacts incrementally to disk. Proposed client bounds: one image/depth encoding task, four upload requests in flight, and at most the capture's 40 disk records queued. Do not retain an unbounded queue of full camera buffers.
- Each accepted frame stores imagery, pose, intrinsics, orientation, timestamp, and optional depth/confidence from the same frame.
- JPEG: longest edge at most 1280 pixels, quality 0.7, sensor orientation preserved. Store actual dimensions and scale intrinsics to those dimensions.
- Camera pose: camera-to-original-scan-world, 16 floats in column-major order. Persist the explicit transform to the normalized room coordinate system.
- Depth is optional. Record actual dimensions and format; never assume every device/session produces 256×192. Proposed transport is tightly packed little-endian float16 meters, explicitly converted from the native buffer. Builder 2 must agree to this encoding.
- If confidence is recorded, preserve its dimensions, format, and association with the corresponding depth observation. Missing depth invokes Builder 2's geometry-raycast fallback.
- Preserve raw RoomPlan exports, submitted JPEGs, calibration, poses, timestamps, available depth/confidence, and capture metadata. No continuous video or textured room reconstruction is required.
- A detector response may contain repeated sightings; the scanner must not present their sum as a count of unique objects. Use a backend distinct count or neutral detail-processing text.

### Failure boundaries

| Event | Required response |
|---|---|
| Tracking briefly degrades | Pause frame acceptance, retain same session, show guidance; resume only after valid recovery. |
| Background, lock, session failure, coordinate-origin loss | Interrupt and require restart; no continuation or partial-scan acceptance. |
| Connectivity/transport failure during active acquisition | Interrupt and require restart. No offline capture queue mode. |
| Optional perception failure returned over a functioning connection | Preserve raw data, mark details failed, allow a RoomPlan-only result. This is not a network interruption. |
| Retryable server response while still connected | At most one retry under the source upload policy, using the same frame identity. Actual transport loss follows restart instead. |
| Restart/Cancel | Abandon the incomplete draft/capture and uploaded artifacts; create a fresh identity and coordinate frame for a new scan. |
| Local storage/write failure | Stop with an actionable error; never claim required artifacts were retained. Preserve earlier saved rooms. |
| Network failure after acquisition has completed | Retain finished artifacts and recover upload/finalization idempotently; this is not resuming an interrupted scan. |
| Later generation/edit network failure | Reconcile the operation; do not rescan or blindly resend. |

Finalize supplies the expected frame/artifact manifest and the completed RoomPlan export. The backend distinguishes expected artifacts, durably stored artifacts, pending detection, failed detection, and completed detection. Failed optional processing must not remain permanently pending.

The phone may clear raw files only when the complete manifest is durably acknowledged and finalization succeeds. A successful detector call or usable room alone is insufficient evidence. Keep missing local artifacts for retry and display upload-recovery state.

Late perception creates new immutable room snapshots. Builder 2 must preserve stable object identities or provide explicit aliases so Keep/Remove instructions and selections are not silently lost when merging detections. Generation binds the selected snapshot and planning revision atomically.

## Rendering specification

- Use RealityKit `RealityView` with a virtual camera and default elevated orbit/top-down framing. Support camera orbit, pan, and zoom; Reset View frames the room. Camera gestures never mutate item transforms.
- Build the floor polygon, thin walls, and openings from normalized geometry. Fade/cut away camera-facing walls to expose the interior.
- Source styling: warm off-white walls by default; wood/concrete floor from style hints; translucent light-blue windows; darker door panels.
- Existing furniture uses category stand-ins scaled to measured dimensions and tinted with supplied attributes. Render labels such as Sofa · 2.1 m.
- New catalog assets use backend-provided USDZ models. Other products use category stand-ins/tints or panels for rugs, art, and mirrors. Builder 1 does not create product models.
- Load assets asynchronously and cache by immutable asset ID/revision. On failure use a correctly sized category stand-in, then a labeled box. Missing textures use neutral materials.
- Replacing a fallback must preserve identity, placement, dimensions, and selection. Do not reset the entire scene for an individual download or new conversation message.
- Use neutral indoor environment lighting, a directional window light when available, and grounding shadows where supported. No Day/Evening controls.
- Removed existing-item ghosts are approximately 20% opacity at the server-supplied last-valid position. Hidden ghosts do not intercept taps. Ghosts are not placement obstacles.
- Scene updates are immediate and unanimated. Normal keyboard/sheet/navigation behavior is unaffected by the ban on model-change animation.
- Camera position, sheet height, tab, selected item, and ghost visibility are presentation state, not design versions.

### Proposed coordinate conventions — Builders 2/3 must agree

| Value | Exact convention |
|---|---|
| Units | Meters for geometry; USD for budget and money presentation. UI dimensions use meters. |
| Frame | Right-handed normalized room frame, Y up, floor at Y=0; floor coordinates `[x,z]`. |
| Size | `[width,depth,height]`, mapped to X,Z,Y. |
| Scene position | `[x,y,z]` at bottom-center of oriented asset bounds, including explicit bottom elevation for wall/non-floor objects. |
| Yaw | Radians, right-handed rotation about +Y; zero faces +Z, forward vector `[sin(yaw),0,cos(yaw)]`. |
| Footprint center | `[x,z]`, with explicit base elevation when not on the floor. Do not infer elevation from category. |
| Camera | Original ARKit camera-to-scan-world, column-major, plus scan-to-normalized-room transform. Do not confuse camera forward with model forward. |
| Openings | Wall ID, offset from endpoint A, width, bottom/sill elevation, height. Required dimensions must be present or have an agreed explicit fallback. |
| Assets | Bottom-center pivot, forward +Z; declare authored bounds, units, and whether normalized or already dimensioned. Never scale catalog assets twice. |

Validate these conventions using asymmetric objects and projected fixture geometry before integration.

## Proposed API and shared data contracts

These are concrete proposals for agreement, not existing backend capabilities. The original synchronous endpoints and mutable item PATCH do not satisfy durable operations, immutable versions, clarification, or persisted Undo. Builder 3 chooses its execution infrastructure; the app must not replace missing backend capabilities with simulated success.

### Common rules

- HTTPS, `/v1`, device ID and source-configured app-key headers. Perception/LLM/product-service credentials remain on the backend.
- Opaque string IDs; UTC ISO 8601 timestamps; declared schema version on transport envelopes.
- Persist a generated operation UUID and exact request before sending. Same identity and payload produce one logical result; reuse with another payload is an error.
- Capture frame uploads and finalization are also idempotent. A lost acknowledgment must not create another frame or room.
- Mutations carry expected active-version/active-pointer revision or expected planning revision. A stale base returns conflict and current IDs; refresh and request resubmission rather than silently applying to another arrangement.
- Operation states: `queued`, `running`, `needs_clarification`, `succeeded`, `rejected`, `failed`, `cancelled`. A disconnected client does not define server state.
- If lookup reports no operation record, resend the original payload with the same identity. If running/uncertain, keep mutation controls blocked. A retry of the same intended mutation reuses its identity until its outcome is known. Once any terminal outcome is reconciled, a new user command may receive a new identity.
- Clarification continuation retains the parent operation ID but deduplicates each reply by its own `reply_id`. Different replies are not mistaken for altered resubmissions of the original command. Dismissals use a separate `dismissal_id` with the same retry rule.
- Error envelope: `code`, readable `message`, `retryable`, optional `field`, `operation_id`, `current_revision`, and structured `details`. Preserve the draft and never expose raw stack traces.
- Outcome codes include invalid room, intent conflict, ambiguous target, kept item, collision, blocked doorway, unavailable capability, stale base, and server failure.

### Required records

| Record | Fields/invariants |
|---|---|
| `RoomSummary` | Room ID/name, metadata revision, scan and creation timestamps, thumbnail, capture state, latest snapshot ID, active design ID, active-pointer revision, current operation ID/state, warnings. |
| `RoomSnapshot` | Immutable ID/revision; room/capture IDs; validity/reasons; height, floor polygon/area, walls, corners, openings, stable-ID objects with dimensions/transforms/attributes, wall features, zones, style hints, story, processing counts. |
| `CaptureManifest` | Capture/frame/artifact identities, types, byte lengths/checksums, storage acknowledgments, image/depth metadata, timestamps, coordinate transforms. |
| `PlanningState` | Room ID, planning revision, object-ID instructions `keep|decide|remove`; absent instruction means decide. |
| `DesignVersion` | Immutable ID, parent ID, room/snapshot IDs, planning snapshot, generation inputs, summary/warnings, canonical scene items, supplied monetary presentation, creation time. |
| `SceneItem` | Stable item ID; optional original-object ID; origin existing/new; status existing/moved/removed/new; category/label; position/yaw/size; planning state; original and last-valid placement; render descriptor; optional product metadata; reason. |
| `RenderDescriptor` | Kind catalog/standin/panel; immutable asset ID/revision/URL, category, tint/texture, authored bounds/units, pivot/forward conventions. |
| `Operation` | ID/kind/room, captured base IDs/revisions, state, timestamps, optional actual stage, clarification or outcome, new active/planning revision, conversation message/event IDs, readable failure. |
| `Clarification` | Original operation and question IDs, question text, optional candidate IDs/labels, frozen base context and reply token. |
| `ConversationEntry` | Message ID/room, context review/design, role/event type, text/time, operation ID, base design ID, room snapshot ID, planning revision, selected object/item context, optional resulting version, delivery/outcome state. Undo events include from/to design IDs. |

Scene items and snapshots carry enough placement/elevation metadata that the renderer never guesses geometry. Existing furniture may have no product record. Removed new products may be absent from the current rendered array, but the backend retains their identity and pre-removal state for restoration.

### Endpoint handoffs

| Endpoint | Request and canonical result |
|---|---|
| `POST /rooms` | Idempotent draft room/capture creation; default personal flow (`mode: home` if retained). |
| `GET /rooms` | Device-scoped RoomSummary list; cursor if paginated. |
| `PATCH /rooms/{id}` | Rename with expected metadata revision → updated summary. Does not change active-design revision or invalidate a pending design. |
| `DELETE /rooms/{id}` | Idempotent deletion, including pending-operation invalidation and associated artifacts → deletion status. Also used to abandon an incomplete draft. |
| `POST /rooms/{id}/keyframes` | Multipart JPEG, optional depth/confidence, calibration/pose/frame/capture IDs → durable storage acknowledgments and perception state/results. |
| `POST /rooms/{id}/finalize` | Capture manifest, final raw RoomPlan export, idempotency identity → snapshot/validity or operation reference. |
| `GET /rooms/{id}` | Summary, latest snapshot, planning state, capture/detail status, active design reference. |
| `GET /rooms/{id}/snapshots/{snapshot_id}` | Exact immutable snapshot. |
| `POST /rooms/{id}/planning-commands` | Text, selected object, snapshot/planning revision, operation ID → clarification/rejection or atomic new planning state. |
| `POST /rooms/{id}/designs` | Intent/styles/USD budget/text, snapshot/planning revision, expected active ID/revision, operation ID → operation reference or canonical result. |
| `POST /designs/{id}/chat` | Message, selected item ID, expected active ID/revision, operation ID → clarification/rejection or one canonical child scene/version. |
| `GET /operations/{id}` | Durable state and complete outcome or explicit unknown-operation response. |
| `POST /operations/{id}/clarifications` | Question ID, reply ID, reply/context → idempotent continuation of the same atomic operation. |
| `POST /operations/{id}/dismiss-clarification` | Question ID and dismissal ID → idempotently dismiss the outstanding question without applying a change. |
| `GET /designs/{id}` | Exact immutable design, not a version whose geometry changes after enrichment. |
| `POST /rooms/{id}/undo` | Operation ID and expected active ID/revision → parent scene and persisted active-pointer update. |
| `GET /rooms/{id}/conversation` | Context-labeled persisted entries and cursor where needed. |
| `GET /catalog/manifest` | Rendering asset IDs/revisions, URLs and dimensional conventions; not a client shopping resolver. |

Builder 2 supplies geometry/validity/placement behavior; Builder 3 exposes and persists these APIs. Builder 1 owns their Swift models and client. The original direct item PATCH, sharing/shopping-list routes, and sample routes are not used by this client.

### Valid request examples

Generation:

```json
{
  "schema_version": 1,
  "operation_id": "op_generate_001",
  "room_snapshot_id": "rs_12",
  "planning_revision": 4,
  "expected_active_design_id": null,
  "expected_active_revision": 0,
  "intent": "add",
  "styles": ["cozy"],
  "budget": "300.00",
  "currency": "USD",
  "text": "Create a warm reading corner"
}
```

Design edit:

```json
{
  "schema_version": 1,
  "operation_id": "op_edit_002",
  "expected_active_design_id": "d_31",
  "expected_active_revision": 5,
  "message": "Unlock this sofa and move it against the window wall",
  "selected_item_id": "i_sofa"
}
```

Clarification, which creates no version:

```json
{
  "schema_version": 1,
  "operation_id": "op_edit_002",
  "state": "needs_clarification",
  "clarification": {
    "question_id": "q_1",
    "text": "Which window wall?",
    "candidates": [
      {"id": "w1", "label": "Wall with the large window"},
      {"id": "w3", "label": "Wall with two small windows"}
    ]
  }
}
```

Field names, decimal-string budget encoding, and envelopes need Builder 3 agreement. Freeze complete valid JSON fixtures for all outcomes before integration; the source's illustrative `...` and pipe-separated enum examples are not valid fixtures.

## Client organization and implementation gates

Use the existing `ReSpace/` Xcode target; the source's proposed `ios/` folder does not exist. The repository currently contains a starter SwiftUI view. This specification task does not implement production code.

| Client area | Responsibility |
|---|---|
| App | Hardware gate, navigation, Keychain device identity, configuration. |
| Capture | RoomPlan lifecycle, sampler, artifacts, uploads, interruption/cleanup. |
| Rooms | List/rename/delete, review, planning instructions, thumbnails. |
| Design | Intent, conversation/composer, operation reconciliation, active version/Undo. |
| Rendering | Entities, assets/fallbacks, camera, selection, ghost visibility. |
| ShoppingPresentation | Static labeled cards/details/alternatives/navigation only. |
| Networking | Versioned Codable records, idempotent requests, operation lookup, structured errors. |
| Persistence | Capture manifests, pending identities, drafts, caches, cleanup/deletion records. |

Update UI on the main actor. Encoding, disk operations, large decoding, and asset processing must not block capture or navigation. Avoid rebuilding scenes when only conversation, keyboard, or sheet state changes.

The current project targets iOS 27 and both iPhone/iPad. Implementation must adopt the source's iOS 18 baseline and iPhone-only targeting; portrait UI remains the stated baseline for final review.

### Integration evidence

1. **Builder 1 capture:** physical LiDAR iPhone records usable RoomPlan output with calibrated frames, optional depth evidence, bounded storage/queues, and interruption/network restart behavior.
2. **Builders 1/2 calibration:** project known geometry into at least three images; verify orientation, resized intrinsics, matrix order, normalized-frame transform, size order, elevation, and yaw.
3. **Builders 1/2/3 contract freeze:** agree to schema fixtures, stable identities, snapshot immutability, validity, planning revisions, model bounds, and canonical scene outputs.
4. **Builder 3 operations:** demonstrate background continuation, idempotency, lookup after lost responses, clarification, atomic rejection/commit, conflicts, and deletion preventing resurrection.
5. **Builder 3 history:** demonstrate persisted active pointer, regeneration parent linkage, Undo/branching, and conversation associations.
6. **Builder 3 storage:** acknowledge complete private artifact manifests, retain completed artifacts without expiry, and delete explicit rooms/abandoned captures.
7. **Builder 1 viewer:** verify virtual-camera rendering, selection, camera controls, sheet/composer, fallbacks, and unanimated updates on the target OS/device.

## Acceptance and verification

| ID | Scenario | Pass condition |
|---|---|---|
| B1-01 | Unsupported hardware | Compatibility screen only; no room/design/shopping/sample bypass. |
| B1-02 | Permission denied | Settings guidance and return path, with no broken camera screen. |
| B1-03 | Complete scan | Durable calibrated artifacts and usable normalized room; review opens. |
| B1-04 | Sampling pressure/cap | ≤40 accepted frames, ≤4 uploads, bounded encoding; scanner may continue after frame cap. |
| B1-05 | Missing depth/detector failure | Optional data tolerated; RoomPlan-only review with honest warning. |
| B1-06 | Tracking degradation | Pause/resume within same session; no cross-origin merge. |
| B1-07 | Network loss/lock/background during capture | Interrupted, restart required, fresh capture/origin; completed rooms survive. |
| B1-08 | Finished capture acknowledgment lost | Finished data retained and idempotently recovered; no unnecessary new scan or duplicate room. |
| B1-09 | Invalid room boundary | Generate disabled with reason and Rescan only. |
| B1-10 | Late detections | Review updates preserve identities/instructions; existing designs remain unchanged. |
| B1-11 | Review command | Planning revision changes; measured geometry and saved designs do not. |
| B1-12 | Intent form | Two intents, style exclusivity, positive USD budget with no prefill, retained drafts. |
| B1-13 | Conflicting intent text | Backend clarification; no silent mode switch. |
| B1-14 | Generation backgrounded | Room shows pending state; reopening retrieves same operation/result. |
| B1-15 | Generation fails | Form, scan, and previous active design remain intact. |
| B1-16 | Model edits | Text commands only; camera gestures cannot move furniture. |
| B1-17 | Multi-action request with one failure | Entire change rejected; no partial scene/version. |
| B1-18 | Ambiguous target | Clarification; visible selected-item context; no random target. |
| B1-19 | Kept item | Movement/removal requires explicit unlock; unlock-and-move may be one atomic version. |
| B1-20 | Successful command | Exactly one child version; concise summary; no scene-change animation. |
| B1-21 | Lost edit response/relaunch | Same operation reconciled; no blind replay or duplicate versions. |
| B1-22 | Undo and branch | Parent persists as active, reopening matches, next edit branches; no Redo required. |
| B1-23 | Generate again | New result links to previous active design; Undo can return across snapshots. |
| B1-24 | Remove/restore | Existing ghost/new disappearance; restore validates last-valid placement without rewinding unrelated edits. |
| B1-25 | Ghost visibility | View-only toggle; hidden ghosts cannot intercept taps. |
| B1-26 | Conversation | Context/version associations, clarifications, outcomes, and Undo events persist. |
| B1-27 | Shopping | Navigable labeled placeholders; no applied swaps, purchases, calculated totals, or simulated versions. |
| B1-28 | Language product change | Canonical Builder 3 result renders; absent capability is honestly unavailable. |
| B1-29 | Asset failure | Correct-size stand-in/box; room and commands remain usable. |
| B1-30 | My Rooms/delete | Multiple scans retained; rename/reopen work; confirmed deletion removes associated data and prevents resurrection. |
| B1-31 | Retention | No completed raw expiry; local eviction only after complete durable acknowledgment/finalization; restart discards incomplete acquisition. |

### Performance targets and tests

- Source target: ≥30 FPS on iPhone 13 Pro with ≤40 scene items; visible ghosts count toward rendering load.
- Target large geometry within three seconds after Done and optional details within 15 seconds under healthy service conditions. Slow/failed detection stays visibly pending/failed; never fake completeness to meet a timer.
- Shared end-to-end targets: generation p50 ≤20 seconds, p95 ≤35 seconds; language edits ≤8 seconds. Backend latency is a dependency, not a client-only guarantee.
- Keep selection, text entry, sheet navigation, and camera controls responsive during processing. The source's sub-300-ms local drag/swap target is superseded by their removal.
- Builder 2 owns position-accuracy and collision/clearance validation. Builder 1 supplies captured fixtures and diagnostics rather than claiming geometry correctness from appearance.
- Decode complete agreed contract fixtures. Test semantic invariants: atomic rejection, stable snapshot/selection identity, retry deduplication, stale revisions, active-pointer Undo, branching, and raw-storage acknowledgment.
- Validate actual capture, calibration, and interruptions on physical supported hardware. Test doubles may exercise API failures; they are not a shipping sample-room or simulated-shopping feature.

## Platform evidence and remaining technical gates

- [RoomCaptureSession.isSupported](https://developer.apple.com/documentation/roomplan/roomcapturesession/issupported) supplies the RoomPlan/LiDAR capability check; iPhone-only use is an additional product restriction.
- [RoomPlan enhancements](https://developer.apple.com/videos/play/wwdc2023/10192/) and [shared-session integration](https://developer.apple.com/documentation/roomplan/scanning-the-rooms-of-a-single-structure) document RoomPlan/ARKit integration.
- [ARSession.currentFrame](https://developer.apple.com/documentation/arkit/arsession/currentframe) and [ARFrame](https://developer.apple.com/documentation/arkit/arframe) support sampling imagery, camera data, and timestamps.
- [RealityView virtual camera](https://developer.apple.com/documentation/realitykit/realityviewcamera/virtual) and [camera controls](https://developer.apple.com/documentation/swiftui/view/realityviewcameracontrols(_:)) support the iOS 18 viewer architecture. Actual gesture behavior and performance require device validation.
- [sceneDepth](https://developer.apple.com/documentation/arkit/arframe/scenedepth) is optional. Shared-session support does not guarantee nonnil depth throughout RoomPlan capture. [Apple's depth sample](https://developer.apple.com/documentation/arkit/displaying-a-point-cloud-using-scene-depth) uses native float32; float16 transport requires explicit conversion.

## Final review boundary

The product decisions are incorporated above. Final confirmation covers the full behavior and the proposed portrait layout; it does not imply Builders 2 and 3 have accepted the transport contracts. Mark this document final after confirmation of shared understanding. Keep shared API agreements and physical-device evidence explicit until they are actually completed.
