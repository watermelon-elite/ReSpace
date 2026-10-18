# ReSpace — Complete Product Specification

Status: consolidated implementation specification. Product behavior and conflict resolutions are agreed; runtime implementation and live integration evidence remain to be completed.

This document governs the product. Earlier specification drafts are historical inputs and do not override it. Requirements are organized by product functionality and system components. Targets and examples are not claims of measured performance or completed implementation.

## Problem Statement

A person redesigning a room must reconcile its actual shape, existing furnishings, intended activities, style and budget. Photos alone do not reliably communicate dimensions or usable space. Shopping listings have inconsistent measurements, duplicate offers, stale prices and packs whose purchase quantity differs from the number of Items placed. Attractive recommendations can still block a doorway, collide with furniture or leave a lamp without a supporting table.

The person needs a dependable path from a measured room to an understandable arrangement of real Products. They must be able to protect possessions, express priorities, understand trade-offs, refine the arrangement, recover from interruptions and reverse changes. Saved designs must retain the geometry, purchases and evidence originally used rather than changing when observations or catalogs are updated.

## Solution

ReSpace captures one room on a supported LiDAR iPhone, reviews native measurements, asks an adaptive sequence of useful questions, discovers and verifies real Products, then produces a validated 3D design. The user chooses Add a few things or Full redesign, provides a positive USD budget and optionally specifies styles and instructions.

The sequential planning workflow receives native room measurements and verified Product specifications before asking questions. It clarifies priorities and requests explicit approval before increasing the budget. After choices are finalized, perception and spatial processing assemble the processed room. Gemini proposes named spatial relationships; a deterministic solver computes metric placements and validates them.

The design screen combines a navigable 3D room, persistent conversation and real Product cards. Users can request language edits, swap a compatible alternative, remove an Item, find additional Products, open the selected merchant offer and Undo a committed change. A multi-action edit saves its valid successful parts with explicit warnings for failures. The resulting complete Scene is one immutable version; Undo reverses that whole committed result.

The product uses one personal-room experience, requires a supported LiDAR iPhone and has no sample-room bypass. Completed Rooms and capture artifacts remain until explicit deletion. Backend operations survive app closure and worker interruption, pause at unanswered questions, and support explicit cancellation while preserving earlier saved results.

## User Stories

1. As a room owner, I want to start without an account, so that I can scan without registration.
2. As an iPhone user, I want a clear compatibility screen, so that I understand why unsupported hardware cannot enter the product.
3. As a room owner, I want camera-permission guidance, so that I can recover from denial.
4. As a room owner, I want every completed scan in My Rooms, so that new captures preserve earlier work.
5. As a room owner, I want thumbnails, names and scan dates, so that I can identify the correct room.
6. As a room owner, I want renaming independent of design history, so that organization does not change arrangements.
7. As a room owner, I want confirmed deletion of associated room data, so that retained scans remain under my control.
8. As a room owner, I want retryable deletion status, so that I know whether deletion actually completed.
9. As a room owner, I want native scanning guidance, so that I can capture usable structure and Objects.
10. As a room owner, I want responsive capture during storage and uploads, so that background work does not disrupt acquisition.
11. As a room owner, I want poor keyframes rejected, so that transient tracking problems do not corrupt the room.
12. As a room owner, I want interrupted acquisition restarted cleanly, so that different coordinate frames are never mixed.
13. As a room owner, I want finished capture data retained after a lost response, so that I do not needlessly rescan.
14. As a room owner, I want optional depth absence tolerated, so that useful room capture remains possible.
15. As a room owner, I want truthful upload progress, so that deferred detection is not presented as already complete.
16. As a room owner, I want native room review before server processing, so that I can promptly describe my goals.
17. As a room owner, I want choices mapped to stable physical Objects, so that processing never redirects Keep or Remove.
18. As a room owner, I want Keep to preserve position and presence, so that protected possessions remain unchanged.
19. As a room owner, I want explicit unlocking, so that changing a protected Object is deliberate.
20. As a room owner, I want unlock and a permitted change in one command, so that the interaction is concise.
21. As a room owner, I want removal from a design to preserve the original room, so that the scan remains trustworthy.
22. As a room owner, I want Let the design decide as the default, so that I need not classify every Object.
23. As a room owner, I want review commands to update instructions, so that measured geometry and saved designs remain unchanged.
24. As a room owner, I want Add to preserve existing furnishings unless explicitly changed, so that small improvements remain small.
25. As a room owner, I want Full redesign to permit broader changes, so that I can explore another arrangement.
26. As a room owner, I want conflicting intent and text clarified, so that intent never silently changes.
27. As a room owner, I want a required positive USD budget without a default amount, so that the design starts from my spending limit.
28. As a room owner, I want Match what I have or combined named styles, so that I can state a visual direction.
29. As a room owner, I want form drafts preserved, so that navigation and failures do not lose input.
30. As a room owner, I want measured context and verified listing dimensions supplied before questions, so that recommendations are grounded.
31. As a room owner, I want questions about activities, occupants and priorities, so that recommendations fit how I use the room.
32. As a room owner, I want known answers skipped, so that questions do not repeat my instructions.
33. As a room owner, I want one clear question at a time, so that the interaction is understandable.
34. As a room owner, I want choice cards, images and numeric controls, so that initial planning can finish without typing.
35. As a room owner, I want optional free text, so that I can explain preferences missing from the choices.
36. As a room owner, I want Skip and Decide for me, so that I control participation within approved constraints.
37. As a room owner, I want pending questions restored, so that closing the app does not decide for me.
38. As a room owner, I want answers revisable between steps, so that I can change my mind while preserving history.
39. As a room owner, I want preferences distinguished from must-haves, so that flexible priorities remain flexible.
40. As a room owner, I want incompatible requirements explained, so that I choose which constraint can change.
41. As a room owner, I want whole-room trade-offs, so that one upgrade does not obscure effects on other purchases.
42. As a room owner, I want within-budget substitutions considered first, so that spending increases are exceptional.
43. As a room owner, I want explicit ceiling-increase approval, so that preference is never mistaken for spending authorization.
44. As a room owner, I want fresh live discovery compared with saved candidates, so that choices are not catalog-only.
45. As a room owner, I want searches to respond to answers, so that feedback changes recommendations.
46. As a room owner, I want up to three eligible choices including the selection, so that alternatives remain manageable.
47. As a room owner, I want fewer choices when evidence is insufficient, so that unsuitable listings do not fill a quota.
48. As a room owner, I want exact variants grouped across merchants, so that duplicates do not consume alternatives.
49. As a room owner, I want actual exact-variant dimensions, so that estimates and packaging sizes cannot determine fit.
50. As a room owner, I want stale offers checked, so that price and availability are reasonably current.
51. As a room owner, I want inaccessible pages distinguished from unavailable stock, so that uncertainty is described honestly.
52. As a room owner, I want reasons and expandable evidence, so that I understand recommendations.
53. As a room owner, I want relative value compared with similar Products, so that raw cheapness is not called a bargain.
54. As a room owner, I want insufficient comparison evidence disclosed, so that market values are not invented.
55. As a room owner, I want whole-pack cost and surplus disclosed, so that totals match what must be purchased.
56. As a room owner, I want tax and shipping exclusions shown, so that the budget boundary is clear.
57. As a room owner, I want preliminary suitability distinguished from validated fit, so that listing selection does not imply placement success.
58. As a room owner, I want available observations used after detector failure, so that one missed detail does not block a usable room.
59. As a room owner, I want genuine unusable-boundary recovery and Rescan, so that the system never fabricates valid geometry.
60. As a room owner, I want Priority to govern optional placement, so that a large unimportant Addition does not crowd out an important one.
61. As a room owner, I want prohibited collisions, blocked access and unsupported Items rejected, so that saved arrangements are coherent.
62. As a room owner, I want permitted fit repairs attempted first, so that minor issues do not repeatedly interrupt me.
63. As a room owner, I want approval before materially changing a must-have, so that recovery respects my decisions.
64. As a room owner, I want the full room rendered, so that existing Objects and new Products have context.
65. As a room owner, I want orbit, pan, zoom and Reset View, so that I can inspect without moving furniture.
66. As a room owner, I want model/card selection linked, so that geometry and Product information stay connected.
67. As a room owner, I want Assistant and Items tabs with a composer, so that conversation and browsing share one screen.
68. As a room owner, I want correctly sized asset fallbacks, so that media failures do not make the design unusable.
69. As a room owner, I want representative models labeled, so that generic geometry is not mistaken for the exact Product.
70. As a room owner, I want optional ghosts of removed Objects, so that visual context is preserved without occupying space.
71. As a room owner, I want language-directed addition, replacement, movement, removal and restoration, so that I can refine without dragging.
72. As a room owner, I want selected-item context for “this,” so that short commands can identify their target.
73. As a room owner, I want ambiguous targets clarified, so that the wrong Object is never changed.
74. As a room owner, I want successful parts of a command saved with failure warnings, so that useful changes survive partial infeasibility.
75. As a room owner, I want failed changes to preserve current placements, so that unsuccessful moves never reset earlier work.
76. As a room owner, I want dependents reconsidered after removal, so that Items never float above removed supports.
77. As a room owner, I want one Undo for a partial-success command, so that I can reverse its complete committed result.
78. As a room owner, I want responsive swap previews followed by validated results, so that a preview is never mistaken for saved state.
79. As a room owner, I want Find more to preserve selection, so that discovery never silently replaces a Product.
80. As a room owner, I want Buy to open the exact offer, so that I can purchase the chosen Product externally.
81. As a room owner, I want saved dimensions, prices and evidence preserved, so that reopening never rewrites history.
82. As a room owner, I want regeneration linked to the previous active design, so that Undo can cross generation boundaries.
83. As a room owner, I want edits after Undo to branch, so that earlier versions remain intact.
84. As a room owner, I want reopening to restore the active version, so that Undo survives navigation.
85. As a room owner, I want persistent room conversation, so that commands, explanations and Undo remain understandable.
86. As a room owner, I want background continuation, so that leaving a screen does not cancel progress.
87. As a room owner, I want actual stages and explicit Cancel, so that I can understand and stop work.
88. As a room owner, I want slow work recoverable beyond performance goals, so that elapsed time alone does not lose a valid result.
89. As a room owner, I want identity-preserving retries, so that lost responses cannot duplicate logical actions.
90. As a room owner, I want other Rooms usable during pending work, so that a room-specific lock is not an app-wide lock.
91. As a room owner, I want raw capture retained until deletion, so that saved evidence supports later redesign.
92. As a room owner, I want private scan media and server-held credentials, so that public rendering assets do not expose them.
93. As a beta user, I want deployed services, so that the product works without a developer laptop.
94. As a product implementer, I want complete versioned contracts and observable acceptance checks, so that components agree on behavior.
95. As a product implementer, I want preserved failures and deterministic diagnostics, so that incorrect results can be reproduced.

## Implementation Decisions

### 1. Product boundary and domain invariants

#### 1.1 Supported product

- Target iOS 18 or later, LiDAR-capable iPhone hardware and supported RoomPlan capture. Portrait is the interface baseline. Unsupported devices show compatibility information and cannot enter room/design flows.
- Use one personal-room experience. No business mode, mode selector, seat target or business-specific input/clearance workflow is required. A retained compatibility `mode` has the sole value `home`.
- Support one physical room per capture and multiple saved Rooms. No multi-room reconstruction is included.
- Support `add` and `redesign` intents, defaulting to Add. Spot selection and its coordinate-based input are excluded.
- Shopping uses real verified Products, supplied totals, Find more, validated Swap/Remove and exact Buy links. Placeholder shopping does not meet acceptance.
- Furniture position changes use language commands. Camera gestures, Item selection, direct Swap and direct Remove remain supported. Furniture dragging and direct rotation are excluded.
- Connectivity is required. Finished-upload recovery does not constitute offline scanning, editing or reopening.
- Retain completed capture artifacts until explicit Room deletion. The application does not automatically expire completed raw data.

#### 1.2 Domain distinctions

An **Object** is already present in the scan. An **Item** is one design entry: an Object left alone, moved or removed, or one physical unit of a new **Addition**. A **Product** is purchasable; a **Purchase offer** identifies a merchant, exact variant or pack, price and supplied contents. An existing Object can have an Item card without a Product.

An Addition carries a stable request identity and category through Product discovery and selection; its concrete **Anchor** is assigned during spatial planning after processed room identities are available. Its **Priority** determines placement order, with 1 most important. Product ranking chooses among candidate Products and is a separate score. A **must-have** is a hard requirement, not merely a high Priority or score.

**Kept** protects an Object's presence and pose by user instruction. **Fixed** describes what cannot change in a particular solve: Kept Objects, permanent fixtures and unaffected Items can all be Fixed. Explicit unlocking releases Keep but never physical immovability.

**Measured room context** is available from native capture before deferred processing. A **Room snapshot** fixes the processed measurements at one revision. A **Design version** fixes its referenced snapshot, geometry, Products, purchases, evidence and planning state. An **active version** is the user's current selection, including an older parent restored by Undo.

#### 1.3 Result invariants

1. Gemini selects valid identities and named spatial relationships; the solver alone computes metric placements.
2. Selected purchase Products require verified exact-variant width, depth and height. Scanned Object estimates are a separate evidence class.
3. Every saved Scene passes applicable boundary, collision, support and access checks.
4. Keep, permanent fixtures, approved budget and must-haves constrain automatic changes.
5. Saved versions are immutable; evolving search and operation records cannot rewrite them.
6. One active Room operation serializes planning, generation, edits, Find more and Undo. Rename uses separate metadata revision; deletion supersedes pending work.
7. One committed command produces at most one child. Partial success is explicit per action, and its successful subset is saved together.
8. Retries cannot duplicate answers, options, versions, conversation outcomes or purchases.
9. App closure is neither cancellation nor consent, Skip or budget approval.
10. Deleted Rooms and cancelled operations cannot be resurrected by late results.

### 2. Screens and navigation

#### 2.1 Screen sequence

| Screen/state | Content and entry | Completion and next state |
|---|---|---|
| Device gate | Platform and RoomPlan support. | Supported → My Rooms; unsupported → compatibility information only. |
| My Rooms | Rooms, thumbnails, editable names, scan dates and actual pending-state badges. | New Scan → permissions/setup; saved Room → review with Reopen design when available. |
| Scan setup | Camera permission, connectivity, backend draft capture and writable storage. | Valid prerequisites → acquisition; otherwise actionable recovery. |
| Capture | Native camera, outlines/coaching, Done and Cancel Scan, capture/upload status. | Done → finalized native export; interruption/cancel → discard/restart. |
| Finalization | Stored artifacts, manifest and final native room export. | Durable completed capture → native room review; no server perception here. |
| Room review | Native geometry/photos, measured Objects, planning choices and conversation. | Planning commands, intent, reopen design, rename or delete. |
| Intent | Add/Full redesign, styles, required USD budget and optional text. | Valid submission → persistent generation. |
| Interactive planning | Actual phase, one question, choices/images, optional text, Skip, Decide for me and Cancel. | Final selection → spatial processing; unanswered question persists. |
| Processing | Actual persisted phase and known context, with no fabricated percentage. | Valid result → design; conflict → question; unusable room → recovery/Rescan; failure → explanation/retry. |
| Design | Full 3D room, Assistant/Items sheet, composer, selection, Undo, Reset View, ghosts and status. | Chat, Swap, Remove, Find more, Buy, Undo or navigation. |
| Product detail/options | Real image, offer, dimensions, evidence, explanation and eligible alternatives. | Buy opens offer; Swap validates a child; browsing changes no design. |

#### 2.2 My Rooms

- Launch into My Rooms. The empty state offers New Scan, with no sample entry.
- Give each new Room a default scan-date-based name with disambiguation. Show thumbnail, name and scan date.
- Rename changes metadata only. It does not invalidate a design operation or modify design history.
- New captures create new Rooms; they do not replace completed scans.
- Opening a Room enters review, with an option to reopen its persisted active design. The active version can be older than another saved branch.
- Show actual pending state such as Generating or Awaiting answer. Navigation away does not cancel work.
- Confirm deletion of scan, photos, designs and conversation. Keep a visible retryable state until backend confirmation.
- Deletion prevents outstanding operations from publishing or restoring the Room.

#### 2.3 Review and planning controls

- Review native measurements, geometry and photos before deferred perception. Do not display a fabricated fused RoomModel or small detections that have not run.
- Each observed Object has exactly one instruction: Keep in place, Let the design decide or Remove from design. Absence means Let the design decide.
- Keep and Remove cannot overlap. Ordinary Remove does not override Keep; explicit unlock is required, possibly within the same command.
- Review commands update a planning revision without changing the measured scan or any saved design.
- Preserve instructions through navigation/failure and map native identities to the same normalized Objects during processing. Never redirect unresolved identity mappings to another Object.
- Reject design start when capture evidence is already known to be unusable. If deferred normalization later cannot establish a usable boundary, prevent publication, attempt defined recovery and offer Rescan on failure.
- There is no pre-generation “Wait for late detections / Continue with current room” branch. Spatial processing follows selection finalization.

#### 2.4 Intent form

- Show Add a few things and Full redesign only; default to Add.
- Add targets 1–5 new Items and prohibits AI-initiated movement/removal of existing Objects. Explicit user changes remain subject to Keep, physical constraints and intent clarification.
- Full redesign targets 5–20 new Items and permits appropriate moves/removals. Targets never require ineligible Products, overspending or invalid placement; explained optional omissions can result in fewer Items.
- Free text supplements intent. “Replace everything” under Add requires a question proposing Full redesign; never switch silently.
- Budget is a required positive USD decimal with at most two fractional digits, a visible USD label and no prefilled amount. The client validates format; the backend enforces meaning and arithmetic.
- Default style is Match what I have. Named styles are Cozy, Minimal, Japandi, Industrial, Boho and Mid-century and support multiple selection.
- Named styles clear Match. Match clears named styles. Deselecting the final named style returns to Match.
- Text is optional. Preserve the full form draft across navigation, failure and retry.

#### 2.5 Questions and generation display

- Start with a soft target of roughly three useful questions about activities, usual occupants/guests and the desired improvement. Skip answers already supplied. Three is neither quota nor cap.
- One question is visible at a time. Prefer single-choice cards, multi-select chips, listing-image comparisons and numeric controls; free text is optional.
- Initial planning must finish without typing. Custom audio recording is excluded; ordinary keyboard dictation is allowed.
- Ask practical questions that can materially affect the plan, rather than repeated arbitrary Product comparisons. Finish when decisions are resolved/delegated and validation passes.
- Questions about concrete Products use known verified listings, images, labeled measurements, checked offers and price implications.
- Ordinary preferences are flexible. Explicit must-have and avoid choices, Keep, approved budget and spatial constraints are hard requirements; ask which can change when they conflict.
- Distinguish explicit answers from assumptions and delegation. Store every question, option set, response, skip and revision.
- Skip cannot authorize extra spending or waive a hard requirement. Decide for me delegates remaining choices within approved constraints.
- Answers can be revisited between sequential steps. Complete or cancel active work before processing a competing revision.
- Restore exact unanswered questions on reopen. Closing the app does not answer, skip, delegate or cancel them.
- Show actual phases and pending states. Never claim an unreported step completed or invent progress percentages. A 90-second goal is not a failure deadline.

#### 2.6 Design screen

- Fill the screen with the room behind a draggable sheet with collapsed, medium and expanded positions.
- Assistant shows conversation; Items shows cards and shopping. The composer is available in both tabs and remains visible above the keyboard.
- Selecting a model switches to Items, reveals its card and shows selected-item context beside the composer. Preserve sheet height unless expansion is needed to reveal it.
- Selecting a card highlights the corresponding Item by stable ID. Clearing selection clears command context; committed removal clears stale selection.
- Place Undo, Reset View, ghost visibility and actual processing/error state above the scene. Reset View changes framing only.
- Camera gestures orbit, pan and zoom; selection gestures select. They cannot alter furniture position/rotation.
- Keep camera navigation available during room operations. Disable competing mutations and Undo until the operation is resolved.
- Apply committed geometry immediately without animating model changes. Ordinary keyboard, sheet and navigation behavior is unaffected.
- Language edits do not preview speculative geometry. Swap has a separately labeled temporary preview; the saved child is authoritative.
- Camera pose, tab, sheet height, selection and ghost visibility are presentation state and create no design version.

### 3. Capture, storage and recovery

#### 3.1 Acquisition integrity

- Before acquisition, create an idempotent draft Room/capture and confirm connectivity and writable local storage.
- Request camera permission on New Scan. Denial offers Settings and return to My Rooms, not an unsupported-device result.
- Use RoomPlan's AR session as the coordinate source; sample its current frame without replacing its AR-session delegate.
- Collect poses only after capture-session start, within the same run that produces the final CapturedRoom. A restart uses fresh identities and a fresh frame.
- On Done, stop acquisition, obtain and persist the finalized native room. Never submit an intermediate live update as the completed export.
- Approximately 60–120 seconds is capture guidance, not an automatic timer. Reaching the frame cap ends sampling only.

#### 3.2 Sampling and bounded work

| Setting | Contract |
|---|---|
| Triggers | Approximately 1.5 s elapsed, 0.5 m translation or 20° turn since last accepted frame; coalesce simultaneous triggers. |
| Tracking | Accept only normal tracking; pause on transient degradation. |
| Motion | Reject if the motion-speed proxy exceeds 0.3 m/s. |
| Frame count | At most 40 accepted keyframes per capture. |
| Encoding | One image/depth task at a time; reject candidates when bounded capacity is unavailable. |
| Upload | One in-flight upload per Room. |
| Queue | Incremental disk records, at most the capture's 40 accepted frames; no unbounded camera-buffer queue. |
| JPEG | Longest edge ≤1280 px, quality 0.7, native sensor orientation retained. |
| Calibration | Actual uploaded dimensions and intrinsics scaled to those dimensions. |
| Pose | Camera-to-original-scan-world, 16 floats, column-major. |
| Identity | Persist capture/frame IDs, index and timestamp before sending. |
| Depth | Optional tightly packed Float32 little-endian meters, row-major, sensor orientation, actual width/height. |
| Confidence | Optional matching UInt8 map: 0 low, 1 medium, 2 high; tied to the same depth observation. |

Imagery, calibration, pose and available depth/confidence come from the same source frame. Remove buffer row padding when packing. Depth resolution is read at runtime; a common 256×192 size is not a protocol constant. Sensor orientation is not rotated to match portrait display.

Uploads only store inputs and return durable receipts. They do not invoke detection. Capture counters describe accepted/stored/pending artifacts, not unique detected Objects or accumulated repeated sightings.

#### 3.3 Failure boundaries

| Event | Required behavior |
|---|---|
| Temporary tracking degradation | Pause sampling, retain session, guide user; resume only after valid same-frame recovery. |
| Background, phone lock, session failure or origin loss during acquisition | Interrupt; display “Scan interrupted. Start again to capture this room.” Require restart. |
| Transport/network failure during acquisition | Interrupt and restart; no offline capture continuation. |
| Retryable server response while connected | At most one upload retry with the same identity; actual transport loss follows restart. |
| Storage/write failure | Stop with actionable error; do not claim retained artifacts. |
| Cancel/Restart | Confirm discard as appropriate; abandon incomplete draft and uploaded artifacts; restart with fresh capture/origin. |
| Network failure after acquisition completed | Retain finished artifacts; reconcile receipts and retry upload/finalization idempotently without unnecessary rescan. |
| Deferred optional detection failure | Record failure, retain evidence and continue with usable observations; this is not an acquisition interruption. |

Previously completed Rooms survive restart/cancellation of another acquisition. Interrupted acquisition cannot resume or use a partial scan.

#### 3.4 Manifest and retention

- Finalize with final RoomPlan export and expected artifact manifest: identities, kinds, byte lengths and checksums.
- Distinguish expected/stored/missing artifacts from pending/successful/failed processing. Capture completion is not perception completion.
- Clear local raw copies only after the entire manifest is durably acknowledged and finalization succeeds. A successful detector result or usable room alone is insufficient.
- Persist completed-upload recovery across relaunch. Keep local missing/unacknowledged artifacts until retry or explicit discard.
- Retain completed raw photos, depth/confidence where recorded, calibration, poses, timestamps, exports and metadata privately without automatic expiry.
- This is sampled evidence, not full-frame-rate video, inaccessible sensor data or textured reconstruction.
- Abandoned interrupted captures request backend deletion. Persist cleanup identity and retry on reconnection if necessary.
- Explicit Room deletion removes its media, snapshots, designs, conversation and metadata. Shared Product records are separate; retaining them must not retain deleted private room evidence.

### 4. Sequential generation and operations

#### 4.1 Phase ordering

| Phase | Work | Durable result |
|---|---|---|
| Capture complete | Native export and artifact receipts. | Native measured context and capture identity. |
| Preparing context | Intent, native measurements/Objects, instructions and initial database/live search. | Initial verified Product batch, or explicit empty batch with reasons. |
| Interview | Sequential model actions, questions, answers, searches and refinements. | Decision revisions, evidence and approved constraints. |
| Selection finalized | Validate variants/offers, dimensions, quantities, assumptions and budget. | Fixed selection snapshot. |
| Processing room | Stored-frame detection sequentially, then normalization, lifting and merge. | Validity, identity mapping and immutable processed Room snapshot. |
| Planning layout | Gemini receives processed geometry, actual IDs and selected Products. | Validated Anchor-based plan. |
| Validating placement | Deterministic placement, collision/support/access checks and repairs. | Valid Scene or structured conflicts. |
| Repair/question | Allowed repair or verified equivalent; ask before a material protected change. | Revalidated candidate or persistent question. |
| Complete | Save design, active pointer, purchases/evidence and conversation outcome once. | Immutable version and reconciliable operation outcome. |

No search or spatial task runs behind an unanswered question. Upload and finalize never start perception. No parallel speculative branches or overlapping room operations are required. Later edits may reuse unchanged capture/geometry by exact input identity.

#### 4.2 Context before processing

- Supply available native dimensions with their meaning, height, walls/openings, Object poses, stable capture IDs and planning choices.
- Include units, source, time/capture identity and reported uncertainty. Bounding extents are not a rectangular floor plan; missing confidence/measurements are not invented.
- Preserve measured context across interactive turns. Each concrete listing brings verified axis-labeled dimensions, exact variant, checked offer, pack contents and source/time.
- Use dimensions for query guidance and obvious limit checks. Early eligibility is Product verification, not final collision/support certification.
- Preserve or map native identities during normalization so existing choices retain their physical targets.

#### 4.3 Model-visible actions

| Action | Inputs | Backend execution |
|---|---|---|
| `search_products` | Requirements, measured constraints, preferences, quantities, refinements. | Database plus fresh live discovery, verification, ranking and persistence; return known IDs/images/evidence. |
| `ask_user` | Typed question, choices, verified listing references, decision and price implications. | Validate and store; expose question; release worker until response or explicit delegation. |
| `finalize_selection` | Selected variants/offers, purchase quantities, approved constraints, assumptions and reasons. | Validate, save selection, end interview and start spatial phase. |

The backend controls state and executes tools. Gemini cannot bypass verification, approve spending, invent successful checks, execute arbitrary shell/database/browser instructions or start spatial work early. Merchant text is evidence, not workflow instruction. Questions reference stored listing media/identities.

Persist actions, evidence and concise reasons. Recovery does not depend on private model reasoning, provider conversation retention or one request remaining alive.

#### 4.4 Durable operation rules

- Persist operation UUID and exact payload before submission, including Room, input revision, capture/snapshot and expected active ID/revision.
- Coarse states: `queued`, `running`, `needs_clarification`, `succeeded`, `rejected`, `failed`, `cancelled`. Actual phase is separate.
- Partial successful edit → `succeeded` plus explicit action outcomes/warnings. A no-match or invalid-room domain result is distinguishable from provider/worker failure.
- One active Room operation blocks competing planning/generation/edit/search/Undo submissions, including after relaunch. Rename has independent metadata revision; deletion invalidates all outstanding writes.
- Stale base returns conflict and current IDs. Refresh and request resubmission; never silently apply against a different layout.
- Unknown operation lookup → resend identical payload with identical identity. Running/uncertain → retain lock and reconcile. Terminal reconciled outcome → a new intentional request may use a new identity.
- Same identity with different payload is an error. Repeated delivery with the original payload returns the same logical result.
- A 60-second client wait is an HTTP boundary, not logical failure. Individual external attempts have timeouts; total elapsed duration does not fail/cancel generation.
- Leaving/backgrounding preserves work and questions. Reopen reconciles the same operation and applies saved results without model animation.

#### 4.5 Answers, cancellation and dispatch

- Question replies carry operation/question identity, frozen base context and a unique reply ID. Replay applies once; a different reply is not a modified replay of the original command.
- Dismissal carries its own identity and terminates a standalone command-clarification operation without applying changes, then releases its Room lock. A generation interview or fit-repair question remains pending for a valid Answer, allowed Skip/Decide for me, or explicit Cancel; dismissing a view cannot leave an active generation unlocked.
- Persist response before continuation. Keep answer revisions and previous decision context.
- Explicit budget approval records old/new ceiling and resulting total. Preference, Skip, silence and closure are insufficient.
- Cancel stops further scheduling and blocks late publication. Preserve current Room/design plus completed evidence and diagnostics.
- In-flight external calls may finish after cancellation; commit checks current operation and deletion state before accepting their output.
- Use durable bounded steps. Record completion before acknowledging cloud delivery and recover failed dispatch without losing logical work.

### 5. Planning state, edits, history and conversation

#### 5.1 Planning and snapshot boundaries

- Per-Object instruction values are `keep`, `decide`, `remove`; absent means `decide`.
- Keep protects position and presence until explicit unlock. “Remove this” alone cannot override it; “unlock and remove this” can.
- Permanent `fixed_in_place` fixtures remain immovable/nonremovable after unlocking. Explain this physical restriction.
- Room-review commands change planning revisions, not capture measurements, processed snapshots or saved designs.
- Inside a design, instruction changes belong to the resulting version. Undo restores that version's planning snapshot, not room-review instructions created separately.
- Generation binds a completed capture and planning revision. It need not reference a processed snapshot that does not yet exist under deferred processing.
- Regeneration may reuse an exact processed snapshot or create a new one from changed evidence; it links success to the previous active design.
- New observations/reprocessing cannot silently mutate a Room snapshot already referenced by a design. Incorporating them requires a new generation.
- If a command mixes instruction changes and geometry changes, each reported successful action must be effective in the committed result. Report an unsuccessful or unnecessary instruction change honestly; do not claim an unlock/move succeeded when neither changed.

#### 5.2 Targets and supported changes

- Language commands can add, replace, move, remove, restore and explicitly unlock appropriate Items/Objects.
- Original Objects have stable Object IDs and corresponding Item IDs. Previously added Products have stable Item IDs even when `object_id` is null.
- Selected-item context resolves phrases such as “this.” It must not override a different explicitly named target.
- Ambiguous references require concise image/label clarification. Stale selection is not permission to choose a replacement target.
- Fix unaffected base Items in the solver. Explicitly targeted Items and permitted dependents can change within Keep, physical, budget and must-have constraints.
- Resolve only changed Products; reuse unchanged geometry and evidence without rewriting their historical snapshots.
- “Bring back the lamp” restores the last valid pre-removal placement if current checks pass. If occupied or unsupported, explain why and accept another placement request; preserve unrelated edits.
- Keep removed new-Item identity and pre-removal state even though it is not in the rendered array. Existing-object removal never erases the original Object.
- No-op, clarification-only, rejected and unavailable-capability outcomes create no design version.

#### 5.3 Partial action success

For a multi-action command, save valid successful parts and warn about failed parts. “Move the sofa and add a lamp” can save the sofa move while explaining that no eligible lamp fit. The successful subset must remain a complete valid Scene.

| Case | Required outcome |
|---|---|
| All actions succeed | One child containing all changes and a concise success summary. |
| Some independent actions succeed | One child containing that valid subset; individual failures have reasons and unchanged target state. |
| No effective action succeeds | No child; preserve active design and return the failure/no-op explanations. |
| Target is ambiguous | Clarify before mutating that target; do not guess or label an ambiguous action successful. |
| Action violates Keep or permanent fixation | Leave it unapplied with a specific reason; unrelated valid actions may still succeed. |
| Action would exceed approved budget | Do not commit that spending change; use allowed within-budget resolution or obtain explicit approval. |
| Required support/Anchor action fails | Dependent changes cannot assume it happened. Revalidate against the surviving Scene. |
| Combined successful candidates are invalid | Reconcile/reject the offending candidates before publication; warnings cannot excuse invalid geometry. |

Evaluate requested actions and their dependency consequences against the captured base. Failed movement preserves the current saved pose, not the scan's original pose. Failed replacement preserves the prior Product, dimensions and purchases. Failed addition adds no Item or purchase line.

For changes whose success depends on another change, treat the relationship explicitly: a lamp cannot be placed on a table that failed to be added; a table cannot be removed while a dependent lamp remains floating. This is necessary validation within one command, not a new concurrent orchestration system.

When a required question is outstanding, candidate work remains private and no child is published. Continue after its response, or terminate a dismissed standalone command without changes. Publish at most one child for the completed command; do not commit independent actions early and create a second child after clarification.

Each reported successful action must be reflected in the final Scene. Per-action records preserve request identity, target, outcome, reason and any affected Item IDs. The response summarizes successes and failures in plain language. Do not silently reinterpret the user request merely to report success.

Commit the final successful subset once, after full scene/purchase validation. Version, active pointer and conversation outcome persist atomically or through an exactly-once recoverable protocol. Partial product success is distinct from partial database writes.

#### 5.4 Removal consequences and constraints

- Re-evaluate Items supported by or anchored to a removed Item.
- Relocate dependents only when valid and permitted. An optional dependent may be omitted with an explanation; a must-have requires clarification before material change.
- If no valid permitted consequence exists, leave the offending removal uncommitted while retaining unrelated successful changes.
- Group a successful removal and all necessary permitted consequences into the same child. One Undo restores the whole committed action.
- Recalculate physical placed units and whole-pack purchases. A removed unit is not automatically a removed paid pack.
- A request to move/remove a Kept Object requires explicit unlock. If the user supplied an explicit combined command, evaluate it with the target constraints; permanent fixation still wins.
- Never silently weaken a hard requirement to make a partial-success result appear valid. A failed attempt can be reported while the prior satisfying state remains unchanged.

#### 5.5 Versioning and Undo

- Each immutable version includes parent, Room/capture/snapshot, planning snapshot, generation inputs, full Scene, dimensions, transforms, products, purchases, totals, reasons, evidence/check times and asset revisions.
- Generation and any committed edit each create exactly one version. Several successful changes in one command are not separate versions.
- Undo sets the persisted active pointer to the parent and loads that exact saved Scene. It does not rediscover Products, recalculate old prices or create a duplicate.
- Undo of partial success reverses all changes actually committed in that child. Failed actions have no state to reverse.
- Editing after Undo branches from the restored active version. Preserve other versions without requiring Redo or a history-browser UI.
- Reopening uses active pointer rather than newest creation time. Undo requires a parent and cannot undo a scan.
- Regeneration may link across Room snapshots; Undo restores the parent's exact snapshot and arrangement.
- Later price/dimension refreshes and asset updates cannot silently resize furniture, change saved totals or rewrite explanations.

#### 5.6 Conversation and drafts

- Keep one persistent Room conversation covering commands, clarifications, answers, outcomes and Undo.
- Label entries as room review or design editing and preserve base snapshot/version/planning context. Successful outcomes reference their resulting version.
- Undo never erases messages. Record from/to version IDs and retain historical associations after branching.
- Before send, persist exact command, operation identity, selected context and base revision. Never replay an ambiguous outcome under a new identity automatically.
- Return stable message/event IDs so result reconciliation cannot duplicate conversation entries or lose a successful change's explanation.
- Preserve unsent text during ordinary navigation; prohibit whitespace-only sends.
- Show Updating design while working and Saving only when the backend reports that phase.

### 6. Shopping interface and actions

#### 6.1 Cards, evidence and options

- Show real image, title, merchant, price, reason, verified dimensions and check times. Existing Objects need no shopping fields.
- Link every model and card by Item ID. Distinguish selected Product identity from rank.
- The initial ranked three include the main Product and up to two alternatives. Fewer are valid; rejected/unverified candidates are not selectable placeholders.
- Cheaper/style-match tags are optional evidence-based labels, not compulsory alternative categories.
- Cards give concise comparisons; expandable detail shows component scores, measurement evidence and uncertainty. Scores are judgments, not probabilities.
- One reliably identified exact physical variant appears as one choice with retained merchant offers underneath. Different colors/sizes are distinct variants.
- Show whether spatial fit remains pending. Product verification before the interview does not certify final placement.
- Label generic stand-ins/representative geometry honestly. Model reconstruction cannot establish actual physical dimensions.

#### 6.2 Find more

- Run another broad database-plus-fresh-live search, retaining its context and evidence.
- Append up to three unseen eligible options while preserving prior choices and selection. Search alone creates no Design version.
- Search records are separate from immutable Scenes. An option selected later must be revalidated against the current intended parent/layout and budget.
- Deduplicate previously displayed exact variants and their merchant duplicates. Retain offers rather than showing duplicate Product cards.
- Insufficient eligible results can yield fewer or none, with a reason. Do not loosen verification to satisfy display counts.

#### 6.3 Swap, preview and direct Remove

- Swap uses the alternative's actual verified dimensions at the existing position and orientation. It must fit without silently moving surrounding furniture and remain within approved budget.
- Supply complete alternative/render metadata for a temporary local preview. Clearly distinguish preview from saved design; it changes neither active pointer, purchases nor Undo history.
- On success, adopt the authoritative child. On failure/cancellation, restore saved geometry and explain why. A preview is not fit evidence.
- Validate changed dimensions against collision, support, openings and clearances. Revalidate if the layout has changed since options were produced.
- One successful Swap produces one child containing the selected offer, dimensions, purchase consequences and evidence snapshot.
- Direct Remove follows language-removal constraints and dependency rules. A Kept Object first requires an explicit unlock.
- Removed original Objects become ghosts; removed new Products disappear from rendering, while their identities/pre-removal states remain recoverable.
- Recompute purchases on the backend. Removing one placed unit need not eliminate a pack still required by another unit.

#### 6.4 Buy and total presentation

- Buy opens the exact selected merchant offer. Cart, checkout and payment are outside the application.
- A secondary Amazon search destination may be provided when an Associates tag exists; label it as search, not the verified selected offer. No Amazon product API integration is required.
- Compute totals using server-side decimal arithmetic. The client only renders returned amounts and does not invent prices after an edit.
- Display USD purchase total, whole packs, paid surplus and tax/shipping exclusions.
- Saved totals retain their price/check-time snapshot. Discovery or refresh does not silently update them.
- An invalid, unavailable or newly over-budget replacement leaves its target Product/placement and purchases unchanged. A direct failed Swap creates no child; a multi-action command may still commit unrelated valid successes.

### 7. Discovery, verification, ranking and purchase planning

#### 7.1 Discovery breadth and retention

- Every new search, including Find more, searches relevant stored candidates and fresh Google Shopping results through SerpApi in US/USD. Good cached matches never eliminate live exploration.
- Request fresh provider results; stored query history is not a replacement for the live call.
- Each pass retrieves up to 50 relevant database candidates and performs three materially different relevant live queries. Collect available results before narrowing; use fewer if the sources are exhausted.
- These are work-defined passes, not overall time deadlines. Do not stop broad discovery merely because two or three attractive results appeared.
- Use meaningful query variation rather than assuming unsupported offset/page-size parameters work. Verify provider pagination/cache behavior during integration.
- Curated catalog IDs seed candidates, but have no exemption from verification, ranking or preferences.
- Persist all discovered candidates, including rejected candidates and missing fields. Retain up to ten ranked candidates per source, with provenance, requirements, reasons and outcomes.
- Internal provisional shortlists may await checks. They are not selectable user options until eligible.
- If no candidate qualifies, consider remaining relevant candidates and verified catalog fallback. Explain an optional omission or return no match if nothing useful remains. Never invent an eligible match.

#### 7.2 Exact physical dimensions

- Require width, depth and height of the actual exact variant before concrete listing choice, placement or selectable alternatives. Thin rugs still require thickness/height.
- Accept exact unit conversion. Reject package-only measurements, absent axes, ambiguous variants and estimates invented from category, photo or title.
- Resolve merchant/manufacturer pages using deployed Playwright. Prefer explicit structured measurement data, then visible specifications.
- Flash extraction may map published labels/units and distinguish item from package measurements. It may not manufacture absent values.
- Preserve source URL, exact variant, original labels/values/units, extraction/check time and normalized dimensions.
- Range checks detect package/unit/axis mistakes; they do not justify silently clamping a verified Product to a different size. Missing or unresolved evidence makes the Product ineligible.
- Reuse exact-variant dimension evidence for seven days. Expiry triggers re-verification, not deletion of the retained Product or mutation of a saved design.
- The curated catalog uses this same policy. A generated mesh, stand-in or apparent visual fit is not dimension evidence.

#### 7.3 Offer freshness and retry

- Store offer check time separately from dimension evidence time.
- After provisional selection, verify selected database offers with Playwright if older than 24 hours or missing timestamp. Check exact variant, price and availability.
- Combine offer and dimension extraction in one visit when both require refresh.
- If refreshed evidence makes a selection unavailable, invalid or over budget, rerank retained replacements and continue useful fallback.
- Inaccessible means unverified, not confirmed out of stock. Retry a transient page/provider failure once, then retain the reason and continue.
- Do not repeatedly retry confirmed missing dimensions or unavailable stock within one search. A later new search can reconsider.
- Optional further database verification requires a provisional overall score more than five points above the weakest selected eligible choice on the same current benchmark. With cutoff 80, skip 84/85 and check 86.
- This cutoff never bypasses mandatory stale-offer checks or useful fallback when fewer than three eligible choices exist. Prefer fresh near-equivalent candidates when additional checks are discretionary.
- Stale-price scores are uncertain, not mathematical upper bounds. Changed answers, prices or comparison membership require reranking before applying the cutoff.

#### 7.4 Variant and offer identity

- Group exact physical variants across merchants only when identity evidence is reliable; title similarity alone is insufficient.
- Distinct sizes/colors remain distinct variants. Store retained merchant offers under their shared variant.
- Select the cheapest eligible checked offer for an otherwise identical physical variant; do not lose alternative offer evidence.
- A pack offer defines actual supplied contents. Verify each component's identity/dimensions and reject ambiguous bundles from options while retaining their candidate record.

#### 7.5 Shared ranking

| Component | Weight | Meaning |
|---|---|---|
| Practical/request fit | 60% | Activities, priorities, function and applicable request requirements. |
| Style fit | 30% | Explicit style preferences and observed context. |
| Relative value | 10% | Price advantage/premium against comparable discoveries. |

- Apply hard eligibility before ranking. Each component and overall score uses 0–100; retain reasons and scoring-rule version.
- No database/live source bias is allowed. Rendering fidelity breaks otherwise equal scores, not hard eligibility or superior fit.
- Absolute price constrains budget/allocation. It does not replace relative value with raw cheapness. An explicit cheapest preference guides feasible downstream selection.
- “Best” means best among relevant eligible discoveries, not the entire market. Do not invent quality, durability or comfort evidence.

#### 7.6 Comparable value calculation

- Group comparable Products by type/function, approximate size/capacity, known materials/features and condition, using discoveries from both sources.
- Do not group solely by price. Deduplicate physical Products and use one valid representative offer per comparable Product.
- Normalize verified identical-unit packs for comparison only. Purchase budgeting still uses whole offers/packs.
- Require at least three other distinct comparable Products with usable recent price evidence before asserting unusual value/overpricing.
- With insufficient evidence, assign value 50/100 and display insufficient comparison evidence. The Product can remain eligible on other grounds.
- With sufficient evidence, value is `50 + 100 × (1 − candidate_price / comparable_median)`, bounded to 0–100; comparable prices must be positive.
- At median $200, a $150 candidate scores 75, $200 scores 50, and $250 scores 25. This value contributes only 10% of the total score.
- Preserve membership, inclusion reasons, sample count, prices/check times and uncertainty. A stale provisional comparison is not a verified bargain claim.
- Freeze one comparison snapshot per completed batch. New results/offer refreshes create another snapshot and rerank both sources together. Never compare scores across different benchmarks or rewrite historical explanations.

#### 7.7 Purchases, packs and budget

- Purchase total is actual offer price times purchased quantity, including whole packs and paid surplus. Exclude existing Objects, removed purchase lines, tax and shipping. Unknown prices cannot be invented.
- Distinguish variant, merchant offer, purchased pack count, contents supplied, placed-unit IDs and unused paid units.
- Two $100 two-chair packs cost $200 and supply four chairs. Placing three still costs $200 and requires disclosure of the spare unit.
- Removing a placed unit does not automatically remove a still-required pack. Recompute whole purchases for the accepted successful Scene.
- Evaluate trade-offs as complete affected purchase sets: upgrades/downgrades, added/removed Products, total cost difference and functional consequences. Reallocate provisional item budgets within the approved ceiling.
- Consider within-budget substitutions first. A rare ceiling increase requires a concrete reason, verified evidence, quantities, resulting total and explicit old/new ceiling approval.
- An upgrade that fits within the existing approved ceiling needs no ceiling increase. Preference, silence, Skip or Decide for me never authorizes a larger ceiling.
- Retain historical price/time snapshots in versions. Later Product checks must not alter them in place.
- Physical unit counts may inform personal occupancy/use trade-offs, but there is no business seating-target input, business acceptance path or business-only geometry policy.

### 8. System architecture and component boundaries

#### 8.1 Runtime components

| Component | Technology and purpose | Boundary |
|---|---|---|
| Native client | SwiftUI, RoomPlan, ARKit and RealityKit virtual-camera rendering on iOS 18+. | Capture, local durable pending state, navigation, presentation and versioned HTTP client. |
| Public API/controller | Python 3.12, FastAPI, Pydantic, HTTP clients and official google-genai SDK. | Validate requests, persist operations, execute one sequential workflow and return canonical results. |
| Durable continuation | Cloud Tasks with Cloud Run workers. | Bounded sequential steps, retries and resumability; release workers while awaiting answers. |
| Perception | Perceptron Mk1.5, with supported Mk1 fallback configuration. | Image → typed 2D detections or a distinguishable failure. |
| Geometry | Deterministic normalization, raycasting, lifting, clustering and color sampling with NumPy/geometry libraries. | Native capture and observation arrays → immutable processed room data. |
| Placement | Deterministic geometric solver and validation using polygon operations such as Shapely. | Anchor plans, verified Product dimensions and base Scene → valid candidate/outcomes or conflicts. |
| Product discovery | Plain database queries plus SerpApi Google Shopping. | Broad fresh candidate collection with provenance. |
| Verification/browser | Playwright hosted in the cloud; Flash-assisted extraction of explicit facts. | Exact-variant dimension and offer evidence; no invented facts. |
| Persistence | Tiger Data as ordinary managed Postgres, psycopg, SQL and JSONB. | Durable Room, operation, design, product and evidence records; no ORM/vector/time-series layer. |
| Object storage | Google Cloud Storage. | Private capture media; renderable product images/models with appropriate public access. |
| Asset preparation | Offline Kenney stand-in conversion and SPAR3D catalog reconstruction to validated USDZ. | Prepared versioned assets, outside user request latency. |

The API and browser runtime run in deployed services. No required workflow depends on an extraction script or database running on a developer laptop. Model tiers remain configurable: Pro-tier planning, Flash-tier extraction/ranking/chat; verify actual available model IDs before integration acceptance.

#### 8.2 Native application components

| Component | Required behavior |
|---|---|
| Application/navigation | Hardware gate, My Rooms entry, per-Room navigation, Keychain device identity and service configuration. |
| Capture | Native session lifecycle, bounded sampler/encoder, artifacts, manifests, upload and interrupted-capture cleanup. |
| Rooms | List, rename, delete, native review, planning instructions and thumbnails. |
| Planning/conversation | Intent, typed questions, operation reconciliation, active version and Undo. |
| Rendering | Room surfaces, entities, assets/fallbacks, camera, selection, previews and ghosts. |
| Shopping | Real cards/details, evidence, options, Find more, Swap/Remove and exact-offer navigation. |
| Networking | Versioned Codable records, idempotent mutation payloads, lookup/polling and structured errors. |
| Local persistence | Pending identities, exact requests, drafts, capture artifacts/manifests, caches and cleanup records. |

Update UI on the main actor. Encoding, filesystem work, large decoding and asset processing must not block capture or interaction. Avoid rebuilding the Scene for conversation, keyboard or sheet-only changes. Cache assets by immutable identity/revision.

#### 8.3 Geometry and solver interfaces

Only detection performs external I/O. Geometry/solver calculations are synchronous, deterministic and pure: typed records and decoded arrays in, typed records/outcomes out. The controller loads Postgres/storage data and orchestrates execution; algorithms do not fetch storage or manage cloud jobs.

| Interface | Inputs | Output and semantics |
|---|---|---|
| `detect` | JPEG bytes and personal-room label configuration. | Detection list on success, including an empty successful list; typed failure/exception separately on provider/parse/timeout failure. |
| `decode_depth` | Depth bytes, optional confidence bytes, actual width/height. | Float32 depth array in meters and optional UInt8 confidence array; validates byte lengths/formats. |
| `normalize_room` | Final native room export and capture identity. | Base measured RoomModel, frame transform, validity and native identity mapping. |
| `lift_keyframe` | Base room, calibrated Keyframe, Detections, decoded sensor-orientation RGB image and optional DepthFrame. | KeyframeLift with 3D detections, color samples and explicit rejected observations. |
| `merge` | Base room, stored KeyframeLifts and optional previous processed room. | Processed RoomModel with stable Object identities, colors, features and status. |
| `solve` | Room snapshot, validated plan, verified selection records keyed by immutable selection ID, request constraints and optional base Scene. | Candidate Scene, action outcomes, placements/omissions and structured conflicts. Unaffected base Items are Fixed. |
| `check_overlaps` | Room, candidate Scene and Item ID. | Collision references only; never mutates placements. Support/access validation accompanies it before save. |

Store each KeyframeLift with its keyframe so unchanged data can be reused. Persist detector success/failure distinctly. Do not collapse failed detection to a successful empty list.

#### 8.4 Security and input boundaries

- HTTPS and versioned API; device ID groups Rooms and is stored in Keychain. It is not authentication or proof of a real-world identity.
- There is no sign-in or shared application-key gating. Do not embed provider credentials in the client.
- Keep capture media private and avoid returning private storage credentials. Product/model assets may be accessible for rendering without exposing scan storage.
- Validate IDs, enums, revisions, numerical finiteness, sizes, quantities and external URL inputs at the boundary. Never trust model output to satisfy a business or geometry invariant.
- Browser requests must be to validated external product evidence URLs, not arbitrary model-provided internal services. Page text cannot instruct tools or escape the verification task.
- Return readable errors without stack traces or provider secrets. Preserve detailed diagnostics server-side.
- Treat unauthenticated device grouping as the selected product boundary; do not describe it as an account or authorization system.

### 9. Perception and processed room geometry

#### 9.1 Coordinate conventions

| Value | Canonical meaning |
|---|---|
| Units | Geometry in meters; yaw in radians; money in USD decimal strings. |
| Room frame | Right-handed, Y up, floor at Y=0; floor coordinates are `[x,z]`. |
| Normalization | Translation only: floor to Y=0 and floor bounding-box minimum to X=0/Z=0. No rotation. |
| Frame transform | Explicit `room_from_world` 4×4 column-major transform; retain source/capture relationship. |
| Camera transform | Camera-to-original-scan-world, column-major; camera looks down local −Z. |
| Image coordinates | Native sensor orientation; origin top-left, u right and v down. |
| Size | `[width,depth,height]` along local X,Z,Y; do not confuse with native width,height,depth ordering. |
| Item position | `[x,y,z]` at bottom-center of oriented bounds, including non-floor elevation. |
| Yaw | Right-handed about +Y; zero faces +Z; forward in X/Z is `[sin(yaw),cos(yaw)]`. |
| Non-floor Items | Explicit bottom elevation, Mount and support/wall relationship. Never infer elevation from category alone. |
| Openings | Wall ID, offset from endpoint A, width, bottom/sill elevation and height. |
| Render assets | Bottom-center origin, +Z forward, declared authored units/bounds and normalized/already-dimensioned scaling mode. |

Use asymmetric Objects and projected geometry to validate axis order, yaw and pivots. Do not silently rotate Room coordinates to suit the display camera.

#### 9.2 Native export normalization

- Decode flat 16-float column-major matrices correctly. A defensive importer may accept an explicitly understood nested matrix form; it must not silently interpret row-major data as column-major.
- Native enums commonly encode as single-key objects with payload. Read the case and payload, ignore unknown keys and parse attribute variants leniently.
- Ignore opaque internal blobs when building geometry while retaining the raw export as capture evidence.
- Native wall/surface transforms use the first axis along the surface, second up and translation at its center; surface dimensions provide width and height.
- Native Object sizes arrive as width,height,depth and are reordered to width,depth,height.
- Use parent surface identities to attach doors/windows to walls; associate otherwise unparented openings with the nearest appropriate wall.
- For multiple floors/sections, use the largest relevant room section; multi-room output is not supported.
- Floor height comes from the floor transform, or wall center elevation minus half height. It is not assumed to be native world zero.
- Compute/store translation to the normalized room frame and apply it consistently to native geometry and camera-origin coordinates.
- Preserve original identifiers in a source-to-normalized map. Stable planning references survive deterministic normalized ID assignment and later category refinement.
- Verify native JSON shape, attributes, opening dimensions and Object facing with actual target-device exports. Unsupported shape is reported and diagnosed rather than guessed into a valid Scene.

#### 9.3 Walls, floor and corners

1. Project wall segments onto X/Z and snap endpoints within 0.3 m.
2. Build the floor polygon from the walls. Native floor polygon coordinates are a cross-check until their local axes are validated on fixtures.
3. Close appropriate gaps with marked virtual wall segments. Virtual walls bound the floor but are never valid `against_wall` or `on_wall` targets.
4. Approximate curved walls with segments about 0.5 m long, maximum eight segments per curve. If curve metadata cannot be parsed, use the straight segment between its endpoints and retain the approximation diagnostic.
5. Order walls so the signed X/Z polygon area is positive. Number deterministically from the wall nearest the normalized origin.
6. For segment A→B with delta `(dx,dz)`, inward normal is `(-dz,dx)/length` under that winding.
7. Create corner Anchors only at two real walls meeting at 45°–135°.
8. Validate usable, finite, nondegenerate floor/structure before claiming a processed room. Virtual gap closing is not permission to manufacture an arbitrary usable boundary from insufficient evidence.

Doors/windows/openings retain real dimensions and elevation required for rendering/collision. Missing required geometry has an explicit validity/warning outcome rather than a renderer guessing from category.

#### 9.4 Objects, features and categories

- Use one versioned category registry for native normalization, detection labels, Gemini enums, Product categories, collision classes and stand-ins.
- Each category specifies ID, Mount, collision class, default measured-object size, plausible range, stand-in and default tint, native source mappings, optional detection label and duplicate-absorption compatibility.
- Native attributes may refine categories: shelf storage → shelf, stool chair → stool, and table types → appropriate table categories.
- Native Objects use deterministic normalized IDs, ordered by category and position at initial normalization, while preserving native IDs. Subsequent processing does not reassign IDs because colors or categories changed.
- `against_wall` marks an Object within 0.3 m of a real wall with compatible parallel orientation.
- Validate which native local axis faces forward using an asymmetric fixture; apply a fixed normalization correction once if required.
- Wall features are only outlet, light_switch and vent. They are fixed architectural information and are never redesigned.
- Wall-mounted art, mirror, TV and curtain are Objects, with explicit wall/elevation, and may be Kept/moved/removed subject to constraints.
- Ceiling/pendant lights use ceiling Mount and do not obstruct the floor. A radiator is a floor Object marked `fixed_in_place` and cannot be moved/removed.
- Tabletop Objects have explicit supporting Object/Item and bottom elevation. A category capable of resting on a table can still be observed on the floor.
- `attrs.color` is sampled hexadecimal RGB. There is no detector-supplied material field; material interpretation can use planning photos without being presented as measured fact.

#### 9.5 Door and opening access zones

- Every door and doorless opening creates a room-side keep-clear rectangle along its wall's inward normal.
- Width is opening width plus 0.15 m at each side.
- Depth is the greater of the personal-room minimum 0.9 m and assumed swing depth.
- For a door, assumed swing depth is full width; if width exceeds 1.2 m, use half-width as a double-door approximation. Native capture does not certify actual hinge/swing type.
- Doorless opening swing depth is zero. Clip zones to the floor polygon.
- Only rugs and wall-mounted Items may overlap keep-clear zones under the collision model. Existing blocking geometry must be reported, not ignored to claim a valid final arrangement.
- These are product geometry defaults, not regulatory certification. Business counter/register zones and business seating groups are excluded.

#### 9.6 Detection service

- The documented detector baseline uses model IDs `perceptron-mk1.5` and fallback `perceptron-mk1`, selected through `PERCEPTRON_MODEL`. Confirm current IDs, supported models and account access during integration.
- The documented API base is `https://api.perceptron.inc/v1` with Bearer authentication; the recorded Python SDK baseline is `perceptron` 0.4.0 with AsyncClient. Verify the installed SDK against the service rather than treating the recorded version as a permanent pin.
- Use one boxes-only request per keyframe. A service that supports only one annotation format is not asked for boxes, polygons and points in the same call.
- Preferred `POST /v1/detect` accepts the `categories` label list and returns pixel boxes. Verify its actual model/quality before adoption; its supported model may differ from chat model selection.
- If necessary, use chat vision with `vision_config.annotation_format` set to `box`, parse the SDK annotation accessor, and normalize its 0–1000 top-left grid: pixel X = grid X × image width / 1000, pixel Y = grid Y × image height / 1000. The recorded SDK accessor is `response.annotations()`.
- Labels for this product: table_lamp, floor_lamp, plant, wall_art, mirror, rug, curtain, ceiling_light, outlet, light_switch, radiator, vent.
- Do not redundantly request TV/shelf/stool categories already covered by native capture; category registry mappings still support rendering and Product selection.
- Detect only category and image location. Colors/materials are not requested from the detector.
- Point-like features use box centers later; rugs are reconstructed from box-derived rays.
- Process stored frames sequentially after selection finalization. Maximum accepted frames remains 40.
- An attempt has an approximately 20-second timeout. A rate-limit response permits one retry respecting Retry-After. Record usage, failure kind and attempt outcome.
- Return successful empty detections as an empty list. Propagate provider, parsing or timeout failure separately so operation state can distinguish it.
- Partial detection failure does not require user permission to continue with usable native/other observations. No usable boundary remains a genuine failure.

#### 9.7 Pixel-to-room lifting

For pixel `(u,v)` and intrinsics `(fx,fy,cx,cy)`, the camera ray with unit forward-depth component is `((u−cx)/fx, −(v−cy)/fy, −1)`. Rotate by the camera rotation; transform the ray origin into the room frame. A direction vector is rotated, not translated. The normalizing frame currently adds translation only.

Depth is optical-axis Z depth, not ray length. The depth point is camera origin plus depth times the rotated unit-forward-component ray, without a cosine correction. Validate this against physical/device fixtures, including image-edge points.

Scale pixel coordinates and intrinsics to actual depth dimensions. Preserve aspect/orientation association; reject inconsistent calibration instead of assuming 256×192. Depth refinement uses only finite positive depth below 5 m with confidence 2. If confidence is unavailable, use raycasting without claiming high-confidence depth refinement.

| Category/Mount | Image point | Allowed raycast surfaces |
|---|---|---|
| Wall Object or Wall feature | Box center. | Real wall rectangles. |
| Ceiling light | Box top-center. | Ceiling plane at room height. |
| Table lamp, plant or decor capable of resting on a surface | Box bottom-center. | First hit on a valid support top; otherwise floor. |
| Other floor Object, including floor lamp/radiator | Box bottom-center. | Floor only; do not stop at an unrelated tabletop. |
| Rug | Bottom-left, bottom-right and top-center. | Floor; retain points for fitting across observations. |

Valid support categories include table, desk, nightstand, dresser, counter and shelf where actually present as a supported category; their appearance does not introduce a business mode.

Convert observation points to the canonical bottom-center before producing an Object: a normalized native Object center gives base elevation center Y minus half height; a wall box-center hit gives hit Y minus half estimated height; a ceiling box-top hit gives hit Y minus estimated height. A floor/tabletop support hit already gives bottom elevation. Keep the original observation point/method as evidence. Floor Item placement uses the normalized supporting floor, and non-floor Items retain explicit support/wall association.

Raycasting is primary. If the qualified depth point lies within 0.3 m of the raycast point, refine X/Z from depth and retain the surface Y; otherwise use the raycast. Record `raycast` or `raycast+depth` per 3D detection.

Estimate observed-object width as box pixel width × distance / fx, and height as box pixel height × distance / fy. Out-of-range observed sizes use the category default; this estimation never supplies purchasable Product dimensions. A hidden base may bias one ray; multi-view aggregation reduces the error and diagnostics retain its evidence.

Reject floor/tabletop/ceiling observations outside the floor polygon shrunk by 0.05 m. Wall observations must be within 0.15 m of a real wall along its normal and between its ends. Log label/keyframe/reason for rejections, including reflections through windows/mirrors.

#### 9.8 Color sampling

- For native Objects, render a low-resolution z-buffer, approximately 160×120, of walls and oriented Object bounds from each calibrated camera.
- Use nearest-box IDs as visibility masks and erode Object masks by 2 px.
- If qualified depth is available, retain pixels within ±0.15 m of the predicted depth.
- Emit median RGB and visible pixel count for a sample with at least one usable pixel; aggregate quality thresholds apply during merge.
- For detected Objects, sample median RGB from the central 50% of each detector box.
- Merge the best 3–5 views ranked by usable pixel count. Native Objects require at least 200 total usable pixels; otherwise omit color and render default tint.
- Store hexadecimal RGB. This is observed camera color affected by illumination/white balance, not a calibrated material property.
- The projected z-buffer and box corners also provide the calibration overlay diagnostic. No client-side color inference is required.

#### 9.9 Merge, stable identities and snapshots

1. Gather all completed KeyframeLifts for the same capture/input revision.
2. Cluster same-label 3D detections within 0.4 m; use 0.2 m for Wall features. Average compatible positions.
3. Require at least two observations per cluster, except rugs and wall art may survive with one.
4. Fit a minimum rotated rectangle over each rug cluster's floor intersection points.
5. Absorb compatible detected clusters within a native Object footprint expanded by 0.2 m, refining its category rather than creating a duplicate.
6. Snap Wall features to a real wall within 0.15 m and retain wall, offset and height.
7. Reuse prior detected Object IDs when category/proximity within 0.4 m matches; allocate new monotonically increasing IDs otherwise. Never reuse an old number within a Room.
8. Preserve explicit identity aliases/mappings where refinement or absorption affects references. Planning/selection identities cannot disappear silently.
9. Aggregate colors, retain observation counts/source/method and generate completed/failed processing counts.
10. Validate the result and persist a new immutable snapshot; do not mutate an existing design's referenced geometry.

Serial operation ordering prevents competing room recomputations. Retries still check input/revision identity before publication. Stored lifts permit repeatable merge without repeating provider calls or unchanged raycasting.

### 10. Layout planning, placement and validation

#### 10.1 Structured spatial plan

- After room processing, provide Gemini the compact RoomModel with actual wall/corner/Object identities, relevant planning photos, approved instructions, selection snapshot and verified Product dimensions.
- Retain 2–3 relevant capture photos for context, including observed style/material interpretation; do not infer metric Product dimensions from them.
- The structured plan specifies removals, moves and Additions using supported named Anchors. The model never invents metric placement coordinates or unknown IDs.
- Use a flat Anchor shape with `type` required and type-specific optional fields. Validate required combinations semantically even when the provider schema represents fields as nullable.
- Initial generation validates IDs, intent limits, category compatibility, Keep, approved budget and must-haves independently of the model.
- Invalid optional planned entries may be dropped with a recorded reason. Retry malformed planning once when more than half the proposed entries are invalid. A hard requirement cannot disappear under that filtering rule.
- Actual provider failures get one bounded retry, then a recoverable failure. A schema-successful response is not necessarily a valid plan.
- Request edits retain per-action identity and outcomes so optional initial-plan filtering cannot masquerade as unexplained loss of requested actions.

#### 10.2 Anchors

| Anchor | Required references | Placement semantics |
|---|---|---|
| `against_wall` | Real wall; alignment; optional offset. | Item back 0.05 m from wall, facing inward. Yaw is atan2(inward normal X, inward normal Z). Left/right judged by a person inside facing the wall; offset measured from that end, default 0 and ignored for center. |
| `corner` | Real corner ID. | 0.05 m wall gaps. Seating faces the inward bisector; other Items align with the longer wall. |
| `under` | Referenced Object/Item. | Rugs only, centered on target footprint with matching yaw. |
| `next_to` | Target and side. | Own-target left/right/front orientation, 0.10 m gap. Match target yaw except front placement faces the target. |
| `facing` | Target; optional distance. | In front of and facing target. Default footprint gap 0.45 m for tables, 0.8 m for seating. |
| `in_front_of_window` | Window opening ID. | Against its real wall and centered on window. If taller than sill, try permitted nudges; unresolved placement becomes omission/conflict according to constraints. |
| `room_center` | None. | Floor polygon centroid, aligned with longest wall; still subject to containment and collision validation. |
| `on_wall` | Real wall, alignment, optional height. | Default center elevation 1.45 m or 0.25 m above furniture directly below, whichever is higher. Convert explicitly to bottom-center placement. |
| `on_top_of` | Valid support Object/Item. | Centered on support top. Reject footprint larger than usable top or missing support. |

`at_spot` and business `seating_group` are not supported types in this product. Targets may refer to an original Object, a current Item or a specified new Addition unit; references are typed and validated. Forward references resolve only when their target exists in the same accepted candidate. Cyclic or missing support references are conflicts, not guessed coordinates.

#### 10.3 Collision and support rules

Every relevant footprint collision check includes a 0.05 m margin. The margin is a validation clearance, not a change to measured physical size.

| Collision class | Checks |
|---|---|
| `floor` | Other floor Items, room boundary/walls and keep-clear zones. Small detected Objects such as plants occupy space. |
| `rug` | Other rugs and room boundary/walls; can lie under furniture and in keep-clear zones. |
| `wall` | Other wall Items, openings and floor Items against the same wall extending above its bottom edge. |
| `tabletop` | Other Items on the same top; required support identity, elevation and footprint containment. |
| `ceiling` | Does not obstruct floor placement; remains associated with valid room/ceiling geometry. |
| `none` | Informational features do not create ordinary furniture collisions. |

Removed ghosts are not obstacles or present supports. Every active support relationship refers to an active surviving Item/Object. Dependent changes after movement/removal are revalidated before publication. Permanent fixtures are obstacles even when omitted from explicit move lists.

`check_overlaps` reports Item IDs and structure references: `wall`, `door:<opening_id>` and `keep_clear:<zone_id>`. It does not reposition anything. Structured validation augments those references with reason codes for invalid room, missing support, outside boundary, bad Anchor or protected target.

#### 10.4 Solver sequence

1. Validate room and plan identities and construct the initial candidate from the measured room or exact base Scene.
2. Mark Fixed every unaffected Item, Kept Object and permanent fixture. A provided base Scene does not make all Items unconditionally immutable.
3. Use verified purchase dimensions unchanged. Observed-object estimates may use category defaults/ranges; unverified purchase sizes never enter placement.
4. Resolve required support/Anchor dependencies before their dependents. Among actions whose prerequisites are satisfied, apply permitted removals and their valid consequences, then moves, then Additions. A move onto a newly added support waits for that support; cycles/missing targets become conflicts. Preserve action outcomes throughout.
5. Among dependency-ready Additions, sort by ascending Priority; for equal Priority, larger footprint first. Missing Priority falls back to plan order with an explicit diagnostic, not an invented model preference. Dependencies determine readiness, not a new preference score.
6. Expand quantity into physical units with deterministic Item IDs. Distinguish requested placed quantity from purchased pack quantity.
7. Resolve Anchor and candidate yaw/elevation; validate footprint, containment, support and clearances.
8. On a collision, try bounded adjustments: slide along wall in ±0.1 m steps up to ±1.0 m, then 90° rotation, then a supported alternative Anchor. Only attempts allowed by the explicit choice/constraints are eligible.
9. Recheck access connectivity for Full redesign: shrink free floor by 0.45 m, representing half the 0.9 m passage baseline, and check that door keep-clear areas remain connected to usable free area. Remove lowest-priority optional new Items and repeat only when the removal is allowed. Never remove an original Object to repair access without its explicit permitted plan action.
10. Validate the complete candidate, attach outcomes/warnings/conflicts and return it to the controller. Persist only after geometry, instructions and purchases all pass.

Determinism applies for the same room, plan, Products, base Scene and constraints. Stable tie-breaking and IDs must survive replay; random nudging is not a substitute for reproducible placement.

#### 10.5 Failed placement and repair

| Situation | Result |
|---|---|
| Optional new Addition cannot fit during initial generation | Omit it with a reason and recompute selected purchases; never force an invalid placement. |
| Explicit must-have cannot fit | Return unresolved conflict after permitted repairs; controller selects an allowed verified equivalent or asks a targeted question. |
| Initial-generation Object move fails | Keep its measured starting placement and warn, provided the resulting arrangement is valid. |
| Edit move fails | Keep the base version's current placement and mark that requested action failed. |
| Optional part of a multi-action edit fails | Preserve that target state; save unrelated valid successful parts once. |
| Same-pose Swap fails | Keep previous Product/pose/purchases; do not move surrounding furniture silently. |
| Support removal has no valid permitted consequence | Do not commit that removal; unrelated valid actions may still succeed. |
| Fixed original geometry already violates a required final constraint | Return conflict instead of pretending Fixed means valid. Ask to resolve permitted changes where possible. |

The controller may try a retained verified equivalent preserving explicit requirements and budget, then revalidate sequentially. Material changes to explicit choices or must-haves require a question. Retain existing room evidence and interview history during repair; do not restart the entire workflow.

Do not implement an automatic lamp-near-outlet score bonus. Outlet positions can inform Gemini's Anchor choice; explanations may claim proximity only when the resulting evidence supports it.

### 11. 3D rendering and asset preparation

#### 11.1 Room and Items

- Use RealityKit with a virtual camera and default elevated orbit/top-down framing. Support orbit, pan, zoom and framing reset on the target OS/device.
- Build floor mesh from the polygon, thin wall geometry from normalized segments, and openings from explicit dimensions/elevations. Fade/cut away camera-facing walls to reveal the interior.
- Default walls are warm off-white; floor uses supplied wood/concrete style hints; windows are translucent light blue and door panels darker.
- Existing Objects use category stand-ins scaled to measured dimensions, with sampled color or registry default tint. Show useful labels such as category and measured width in meters.
- Catalog Products use prepared USDZ assets. Other Products use correctly scaled category stand-ins/tints; rugs, art and mirrors may use textured panels.
- Load asynchronously and cache by immutable asset ID/revision. Fallback order is requested asset → category stand-in → labeled correctly sized box. Missing textures use neutral materials.
- Replacing a fallback preserves identity, placement, dimensions, selection and camera state. Do not rebuild the room for one download or conversation update.
- Respect declared scaling mode. A dimensioned catalog model is not scaled twice; a normalized stand-in is scaled to explicit width/depth/height in X/Z/Y order.
- Use neutral indoor environment lighting, directional light from a known window where applicable, and grounding shadows where supported. No Day/Evening control or walk camera is included.

#### 11.2 Ghosts and restoration

- Removed original Objects render as approximately 20%-opacity ghosts at the server-supplied last valid placement.
- Ghost visibility is a presentation toggle. Hidden ghosts do not intercept taps; visible ghosts are not placement obstacles or present supports. A removed ghost cannot be moved as active furniture; restore it through validation first.
- Removed new Products disappear instead of becoming original-room ghosts. Their backend identity/state remains available for explicit restoration.
- Undo restores the exact saved prior state. Explicit restore is a new validated command, not a rewind of unrelated changes.
- Preserve original and last-valid transforms even though Before/After is excluded; they support ghosts, restoration and history.

#### 11.3 Asset pipeline

- Prepare broad personal-furnishing category coverage, initially about twenty stand-in categories and roughly sixty verified catalog Products across styles/prices. Coverage goals do not justify unverified entries.
- The category registry and asset manifest must use the same category IDs. Examples include sofa, armchair, chair, stool, dining/coffee/side table, desk, bed, shelf/cabinet, TV stand, floor/table lamp, plant, mirror, wall art and rug.
- Use the agreed Kenney furniture-kit basis where suitable. Normalize stand-ins to declared bounds with bottom-center pivot and +Z forward, then convert to USDZ and inspect in RealityKit.
- Catalog reconstruction uses offline SPAR3D image-to-mesh work, outside the API request path. Use a separate suitable compute environment and verify model access, license and actual runtime/memory requirements before bulk generation.
- Convert generated GLB to USDZ through a tested pipeline. Check textures, orientation, thin/hidden surfaces and physical scale against verified dimensions and source photos.
- Aim for assets below 3 MB through reasonable mesh/texture reduction. Reject poor reconstructions in favor of stand-ins.
- A generated mesh establishes appearance only. Product evidence establishes size. No live image-to-3D generation is required for discovered Products.
- Version asset identity, bounds, units, pivot, forward axis and URLs so historical designs can retain the rendering contract used when saved.

### 12. Canonical data contracts

#### 12.1 Common encoding and validation

- Transport envelopes declare `schema_version`, initially 1. Use opaque string identifiers and UTC ISO 8601 timestamps.
- JSON numbers used for geometry must be finite. Positions/axes have the exact arity stated below; dimensions are positive except explicitly zero-thickness source surfaces before render representation.
- Money is encoded as base-10 decimal strings with at most two fractional digits and `currency: USD`. Budgets/prices are validated without binary floating-point arithmetic.
- Array ordering is deterministic where geometry/identity depends on it; selection refers to identity, never array index.
- Nullable references are explicitly null or absent as specified; absence cannot mean both “unknown” and “known empty.” Empty detection success is distinct from failed processing.
- Unless stated optional, fields listed as record invariants are required. Complete contract fixtures must demonstrate nullable cases, failures, revisions and each outcome before client/server integration.
- Mutations carry `operation_id` and relevant expected revision. Identical replay returns the same logical result; changed payload under the same identity is rejected.
- Changes to schema semantics require an explicit versioned contract update. Clients must not guess geometry, money or missing operation state.

#### 12.2 Identity and reusable values

| Value | Shape and invariant |
|---|---|
| `Vec2` | Two finite numbers `[x,z]` in meters. |
| `Vec3` | Three finite numbers `[x,y,z]` in meters. |
| `Size3` | Three positive numbers `[width,depth,height]` in meters. |
| `Matrix4` | Sixteen finite numbers in column-major order; declared transform direction. |
| `Placement` | `position: Vec3`, `yaw: number`, `size: Size3`, Mount, optional wall/support reference where applicable. Position is bottom-center. |
| `EntityRef` | `kind` and `id`; kinds distinguish native Object, normalized Object, Scene Item and new Addition unit. New-unit references also identify the Addition and unit index. |
| `BaseContext` | Room ID; capture ID; optional processed snapshot ID; planning revision; optional active Design ID; active-pointer revision; applicable decision revision. Native references carry capture identity. |
| `Money` | Amount decimal string plus currency USD. |
| `Warning` | Stable code, readable message and relevant Object/Item/action/field references. No raw trace. |
| `SpatialConflict` | Code, target references, violating structure/support/constraint, readable reason, affected action IDs and permitted recovery context. |

Room IDs identify saved/draft rooms; capture IDs identify one acquisition frame. Native Object IDs remain associated with their capture. Normalized Object IDs identify stable observed Objects. Item IDs identify design entities across their version lineage. Product/variant/offer identities are separate from all of these.

Existing-Object Item IDs are deterministic from Object ID, such as `i_<object_id>`. Addition units use `i_<add_id>_<unit_index>`. Addition IDs are never reused within the Room's design lineage, including branches, so retries/Undo cannot confuse new Items with old ones. A replacement preserves the target Item identity where it remains the same design entry and records the changed Product in the new version.

#### 12.3 Room and capture records

| Record | Required fields/invariants |
|---|---|
| `RoomSummary` | `room_id`, name, metadata revision, creation/scan time, optional thumbnail until available, capture state, latest capture ID, optional latest processed snapshot ID, optional active Design ID, active-pointer revision, optional current operation ID/state and warnings. |
| `CaptureManifest` | Room/capture IDs, final export artifact ID, accepted frame IDs/indexes and expected artifact descriptors, completion identity and capture timestamps. It is the expected-input inventory, not a detector-completion claim. |
| `ArtifactDescriptor` | Artifact ID, capture ID, optional frame ID, kind, format, byte length, checksum and relevant image/depth dimensions/orientation. |
| `ArtifactReceipt` | Artifact identity, acknowledged byte length/checksum, durable storage outcome and time; missing/failed storage has explicit reason. Do not expose storage credentials. |
| `CaptureStatus` | `draft`, `capturing`, `upload_pending`, `complete`, `interrupted` or `abandoned`; expected/stored/missing artifact counts and finalization outcome. Room deletion state remains separately visible until confirmed. |
| `MeasuredRoomContext` | Capture ID/time, source units/frame, native identified Objects/poses, available wall/opening measurements, height/extents with meaning, source confidence/uncertainty where available and raw-export reference. Missing information stays explicit. |
| `PlanningState` | Room ID, planning revision, capture identity, per-Object EntityRef/instruction and current instructions/intent context; values `keep`, `decide`, `remove`. |
| `RoomSnapshot` | Snapshot ID/revision, Room/capture IDs, creation time, immutable RoomModel, identity mapping/aliases, validity and processing outcome counts. |
| `RoomDetail` | RoomSummary, measured context/capture status, current PlanningState, optional latest RoomSnapshot reference, current operation reference and active design reference. |

Frame/artifact receipts are idempotent. Same identity with incompatible content is an error rather than silent replacement. A snapshot includes exactly the processed inputs it used; later inputs produce another snapshot rather than editing it.

#### 12.4 Keyframe upload and observation records

Multipart keyframe parts are `jpeg`, optional `depth`, optional `confidence` when depth exists, and `meta`.

| Metadata field | Constraint |
|---|---|
| `schema_version`, `operation_id` | Protocol version and stable upload retry identity. |
| `capture_id`, `frame_id`, `idx` | Capture/frame identity and stable nonnegative accepted-frame index. |
| `w`, `h`, `orientation` | Actual JPEG dimensions and native sensor orientation. |
| `intrinsics` | `fx`, `fy`, `cx`, `cy` in uploaded-image pixels; focal lengths positive. |
| `transform` | Camera-to-scan-world Matrix4 from the same frame. |
| `timestamp` | Capture-frame timestamp with declared source/time association. |
| `depth_w`, `depth_h`, `depth_format` | Required with depth; positive dimensions and `float32_le_m`. |
| `confidence_format` | Required with confidence; `uint8`, matching depth dimensions. |
| Artifact descriptors | Checksums/byte lengths for each supplied part, linked to manifest identities. |

Reject depth length other than width × height × 4 bytes and confidence length other than width × height bytes. Missing depth has no placeholder byte array. Depth/confidence mismatch is explicit invalid input, not silently rescaled data.

| Record | Required data |
|---|---|
| `Detection` | Category label and `box_px` of four finite uploaded-image pixel coordinates, normalized/clipped or rejected consistently for image bounds. |
| `DetectionOutcome` | Frame identity, `succeeded` or `failed`, attempt/time/usage diagnostics, successful detections or structured failure. Successful empty detections are valid. |
| `DepthFrame` | Decoded Float32 depth array and optional matching UInt8 confidence array, dimensions and units. |
| `Detection3D` | Category, keyframe index, room-frame position, optional estimated Size3, Mount, optional wall/support identity, optional rug floor points and method `raycast` or `raycast+depth`. |
| `ColorSample` | Native/normalized Object or detection reference, RGB triple and usable pixel count. |
| `KeyframeLift` | Frame/capture/input identities, 3D detections, color samples and rejected-observation reasons. |
| `ProcessingCounts` | Expected frames, not-started/pending/succeeded/failed detection counts and applicable lifted/completed counts. Failed optional processing never remains indefinitely pending. |

The public upload response acknowledges storage and explicitly reports deferred processing as not started. Detection failure is recorded later by the operation that actually runs it.

#### 12.5 Processed RoomModel

| Field | Required content |
|---|---|
| `room_id`, `capture_id` | Identities of measured evidence. |
| `height`, `frame` | Positive room height and explicit `room_from_world` Matrix4. |
| `floor` | Ordered Vec2 polygon and computed area in square meters; usable/nondegenerate when validity is true. |
| `walls` | Stable ID, endpoints A/B, length, inward unit normal and virtual flag; deterministic winding/order. |
| `corners` | Stable ID, position and two real wall IDs satisfying corner-angle rule. |
| `openings` | Stable ID, type `door`, `window` or `opening`, wall ID, offset from A, width, bottom/sill and height. Required dimension uncertainty is explicit. |
| `objects` | Object records defined below, including non-floor placement information. |
| `wall_features` | Stable ID, type outlet/light_switch/vent, wall ID, offset and height; optional source confidence. |
| `zones` | Stable ID, type `keep_clear`, reason door/opening and polygon. |
| `style_hints` | Optional observed/derived floor and wall descriptions with appropriate uncertainty. |
| `validity` | Usable flag and structured reasons/warnings. A false flag prevents final placement publication. |
| `processing` | Actual processing counts/outcomes; no fake completion. |
| `identity_map` | Native IDs/aliases mapped to normalized Object and surface references. |

An Object record includes stable `id`, retained native/source IDs, category, source (`roomplan`, `mk1` or refined evidence), X/Z footprint `center`, explicit `base_y`, yaw, Size3, Mount, optional real wall/support Object reference, optional `against_wall`, `fixed_in_place`, observed attributes and supporting evidence/observation count. `sightings`, if retained for compatibility, is the number of 3D observations in a cluster, not the number of unique Objects.

Wall-mounted Objects require their elevation/wall association; tabletop Objects require their elevation/support association. The renderer and solver do not reconstruct these from category defaults. `attrs.color` is optional `#RRGGBB`; a missing sampled color uses a default tint. No required measured-material field exists.

Precomputed story strings are not required transport or progress signals. Actual operation phases replace the earlier story-cycle dependency.

#### 12.6 Intent, decisions and questions

| Record | Required fields/invariants |
|---|---|
| `GenerationRequest` | Schema/operation ID, Room/capture ID, optional existing snapshot ID for exact reuse, planning revision, expected active ID/revision, intent `add` or `redesign`, styles or Match, positive budget decimal, USD currency and optional text. |
| `DecisionSnapshot` | Decision revision, current explicit answers, delegated choices/assumptions, hard must-have/avoid constraints, soft priorities, approved budget and selection references. |
| `Question` | Question ID, operation ID, kind, text, valid choice IDs/labels, optional verified listing/image references, selection cardinality/numeric constraints, skip/delegate policy, frozen BaseContext and decision revision. |
| `BudgetProposal` | Old/new ceiling, affected purchase set, checked evidence/quantities, resulting total and explanation. |
| `AnswerRequest` | Question/operation ID, unique reply ID, expected current decision revision, expected question revision, selected choice IDs or optional text/numeric input, explicit budget approval where applicable, and optional `revision_of_answer_id` only for an intentional earlier-answer revision. |
| `Clarification` | Question with ambiguous target/constraint context, candidate EntityRefs/labels/images and original command identity. |
| `DismissalRequest` | Operation/question ID and unique dismissal ID; applies nothing. |
| `SelectionSnapshot` | Immutable selected records with unique `selection_id`, chosen variant/offer, intended physical quantities, purchase packs, verified dimensions/evidence, approved constraints/budget and reasons. It does not certify final layout. |

Questions must state whether they are resolving ambiguity, an intent conflict, a hard requirement or a purchase trade-off. Choice IDs from another question/revision are rejected. Intentional earlier-answer revision identifies `revision_of_answer_id`, its original question/choice snapshot and the current decision revision at a sequential boundary; this is distinct from an accidental stale reply. Persist the old answer and append its revision, then reconsider affected selections/evidence before continuing. A budget approval cannot be inferred from choosing an unrelated Product option.

#### 12.7 Plans, Anchors and action outcomes

| Record | Fields and semantics |
|---|---|
| `Anchor` | Required supported `type`; optional real wall/alignment/offset, corner, typed target, side/distance, opening and height according to section 10. No arbitrary X/Z placement coordinates. |
| `PlanMove` | Action ID, target EntityRef, Anchor and reason. Initial Object targets and previously added Item targets are both expressible. |
| `PlanRemove` | Action ID, target EntityRef and reason, evaluated against Keep/dependencies. |
| `PlanReplace` | Action ID, existing target Item ID, selected `selection_id` and reason. Uses verified dimensions from that selection record at the existing pose; an explicitly requested move is represented separately. A direct Swap uses this same validation path. |
| `PlanRestore` | Action ID, removed Item ID and reason; uses its retained last-valid placement and Product snapshot, then revalidates current constraints. |
| `PlanUnlock` | Action ID, Kept Object/Item reference and explicit-user-unlock context; does not override permanent fixation. |
| `Addition` | Unique `add_id`, action ID, category, Priority, positive physical quantity, Anchor, selected `selection_id` and reason. Optional query/catalog seeds and provisional maximum price belong to discovery context. |
| `DesignPlan` | Summary, decision/base references, moves, removes, adds, replaces, restores and unlocks using their defined action records. All references use actual room/Scene/selection identities. |
| `ActionOutcome` | Requested action ID/type, target if any, outcome `applied`, `failed` or `no_op`, readable reason/code, affected Item IDs and dependent consequences. |
| `SolveResult` | Candidate Scene when available, action outcomes, placements/omissions, warnings and unresolved SpatialConflicts. Candidate existence does not bypass final validation. |

The solver receives a lookup keyed by `selection_id`, containing exact chosen variant, verified dimensions and evidence for new Additions and replacements alike. Each Addition or replacement names its selected record, avoiding an Addition-only lookup that cannot resolve a changed existing Item. Unchanged base Items retain their saved dimensions even if current selection evidence for the same variant differs.

Plans distinguish an original Object from an existing Scene Item and a newly requested Addition unit. A reference to a removed or failed support is invalid unless an accepted consequence resolves it. Every omitted requested action is visible in its outcome; mandatory constraints are never silently filtered out.

#### 12.8 Products, evidence and search

| Record | Required data |
|---|---|
| `ProductCandidate` | Candidate identity, source/provider/source key, discovered time/query, title/category, known variant references, raw/missing fields, retained rejection reasons and eligibility state. |
| `ProductVariant` | Stable physical identity, title/category, known differentiating options such as size/color, image references, style/features and dimension evidence reference. |
| `DimensionEvidence` | Exact variant, source URL, original axis labels/values/units, normalized width/depth/height, item-versus-package classification, verification time/expiry and outcome. |
| `PurchaseOffer` | Offer/merchant/variant identity, exact product URL, USD price when known, availability outcome, check time and verified supplied pack contents. |
| `PackContents` | Verified component variants and units per purchased pack, with component dimensions; ambiguous bundles are ineligible. |
| `ComparisonSnapshot` | Snapshot/rule version, comparison context, distinct members and representative offers, criteria/reasons, checked prices, median, sample count and uncertainty. |
| `RankedChoice` | Variant and chosen offer, eligible context, component/overall scores, comparison snapshot ID, explanations, optional supported labels and rendering metadata. Selection remains separate from rank. |
| `ProductSearch` | Search/operation ID, intended parent/context, source candidate pools, up-to-ten shortlists per source, comparison snapshots, displayed choices, previously seen identities and completion/no-match/failure state. |
| `OptionSet` | Selection identity and ordered eligible choices for that context, with complete evidence/render details and any preliminary-fit disclaimer. |

Missing price/dimensions are explicit missing evidence on candidates, not fabricated zeros. Selectable choices have all required verified fields. A seven-day query-history expiration does not erase evidence needed by saved versions.

#### 12.9 Purchases and complete Scene

| Record | Required data |
|---|---|
| `PurchaseLine` | Offer/variant identity snapshot, unit/pack price, purchased pack count, verified contents, supplied unit count, linked placed Item IDs, paid surplus count, line total and check time. |
| `PurchaseSummary` | Lines, USD total, approved ceiling, explicit tax/shipping exclusions and relevant warnings. Existing Objects do not appear as paid lines. |
| `RenderDescriptor` | Kind `catalog`, `standin` or `panel`; category, asset ID/revision/URL where applicable, tint/texture, authored bounds/units, scaling mode, bottom-center pivot and +Z forward convention. |
| `SceneItem` | Stable ID, original Object ID or null, Addition ID or null, origin existing/new, status existing/moved/removed/new, category/label, Placement, planning instruction, original/last-valid placement, support/Anchor references, render descriptor, optional Product/purchase references and reason. |
| `Scene` | Complete room geometry or exact immutable room-snapshot payload/reference sufficient for rendering; all original Object Items including ghosts; active new Items; selected Product/evidence snapshots; purchase summary; summary/warnings; action outcomes and design/parent identity. |
| `DesignVersion` | Immutable ID, parent ID or null, Room/capture/snapshot IDs, planning and decision snapshots, generation inputs, plan, complete Scene, creation time and exact evidence/asset revisions used. |

Removed original Objects remain represented as removed Items with their last-valid placement. Removed new Products may be absent from the current rendered array, but backend version/removal history retains their stable identity, Product and last-valid state for restoration.

A version's initial option/evidence snapshots are historical. Later Find more results are returned through separate search records; they do not append mutable options into an immutable saved Scene. Live interfaces can present current search results alongside the saved design while retaining that distinction.

#### 12.10 Operations, errors and conversation

| Record | Required data |
|---|---|
| `Operation` | ID, kind, Room, immutable original request/base context, state, actual phase, timestamps, decision/question revision, persisted question/answer history, optional pending question, outcome or failure, and cancellation/deletion checks. |
| `OperationOutcome` | Result kind, resulting design/snapshot/planning/search references as applicable, new active/planning revision, action outcomes, warnings and conversation message/event IDs. |
| `ConversationEntry` | Message ID, Room, context review/design, role/event kind, text/time, operation, base version/capture/snapshot/planning references, selected EntityRef and optional result version. Undo adds from/to IDs. |
| `ErrorEnvelope` | Code, readable message, retryable flag, optional field/operation/current revision and structured details. |

Operation kinds include generation, planning command, design edit, Swap, Remove, Find more and Undo. Upload/finalization/room metadata mutations also use stable deduplication identities even when completed synchronously.

Domain error codes distinguish invalid room, intent conflict, ambiguous target, kept Object, permanent fixture, collision, blocked doorway, missing support, unavailable capability, no verified match, budget conflict, stale base and genuine server/provider failure. Warnings on a successful partial edit use specific failed-action codes; do not turn the whole result into a misleading generic success message.

`unknown_operation` means lookup found no durable record and the original payload may be resent with the original ID. It does not mean a known operation failed. A disconnected client is not a server state.

### 13. Public API and client reconciliation

#### 13.1 Common HTTP behavior

- Use HTTPS under `/v1`. Send the installation's persistent `X-Device-Id` for Room grouping. Do not require or send a shared application secret.
- Mutating requests carry schema version and stable operation/deduplication identity. Apply same-payload replay semantics to Room creation, uploads and finalization as well as design work.
- Return `202 Accepted` with operation identity for queued/running work. A completed request can return its canonical outcome immediately; both paths use the same records and lookup behavior.
- Reads return canonical persisted state, not client speculation. A successful transport response need not mean generation is complete.
- Validation errors identify the field/code. Stale-revision or competing-operation conflicts identify the current state/reference. Unknown entities and unknown operations are distinct outcomes.
- Preserve error semantics across synchronous and durable execution. Returning a domain rejection must not discard its conversation explanation or turn it into a raw provider exception.
- List responses support cursors when paginated; callers preserve IDs and ordering rather than inferring total completion from a page size.
- Private capture media references are handled through the backend's authorized storage access mechanism; public asset URLs do not grant raw-bucket access.

#### 13.2 Room and capture endpoints

| Method and path | Request | Canonical response and invariant |
|---|---|---|
| `POST /rooms` | Stable operation ID, optional initial name and personal compatibility mode if retained. | Draft RoomSummary, capture identity and creation result. Lost acknowledgment cannot create a second Room on replay. |
| `GET /rooms` | Device grouping and optional cursor. | RoomSummary list including current active/pending references, names, dates and thumbnails. |
| `GET /rooms/{room_id}` | Room identity. | RoomDetail with native capture context, planning state, processing status, active design and current operation. |
| `PATCH /rooms/{room_id}` | Name, expected metadata revision and deduplication identity. | Updated RoomSummary/metadata revision. Does not alter active-pointer revision. |
| `DELETE /rooms/{room_id}` | Stable deletion identity. | Confirmed deletion or retryable deletion status/reference. Invalidates pending publication and removes associated private data. Also abandons incomplete drafts. |
| `POST /rooms/{room_id}/keyframes` | Multipart artifact parts and calibrated metadata. | Durable ArtifactReceipts and capture status. Perception remains not started; no detection side effects. |
| `POST /rooms/{room_id}/finalize` | Capture ID, final raw export/descriptor, expected manifest and stable identity. | Finalization/storage outcome and measured native context, or durable operation reference. No normalization/lifting/detection triggered. |
| `GET /rooms/{room_id}/snapshots/{snapshot_id}` | Exact snapshot identity. | Immutable processed RoomSnapshot, which is available only after spatial processing. |
| `GET /rooms/{room_id}/conversation` | Optional cursor. | Persisted context-labeled entries with original message/event IDs. |

Capture finalization distinguishes an incomplete upload from an interrupted acquisition. A completed local capture can retry missing uploads; an interrupted acquisition must be abandoned/restarted. The server does not create a second capture merely because finalization response delivery was lost.

#### 13.3 Planning, generation and question endpoints

| Method and path | Request | Canonical response and invariant |
|---|---|---|
| `POST /rooms/{room_id}/planning-commands` | Text, optional selected native/normalized Object reference, capture/planning revision, operation ID. | Question/rejection or new planning revision and conversation outcome. No measured geometry or existing version changes. |
| `POST /rooms/{room_id}/designs` | GenerationRequest against completed capture/current planning and expected active revision. | Generation operation reference or complete canonical result. Do not require a processed snapshot before first processing. |
| `GET /operations/{operation_id}` | Exact original identity. | Durable Operation with phase, question, full outcome and message/event IDs, or explicit unknown operation. |
| `POST /operations/{operation_id}/answers` | AnswerRequest for the current question, or an intentional earlier-answer revision with `revision_of_answer_id` against the current decision revision; includes Skip/delegation/explicit approval where allowed. | Idempotent stored response and continued operation state. Covers ordinary questions and command/constraint clarification through one typed contract. |
| `POST /operations/{operation_id}/dismiss-clarification` | Original standalone command question ID and unique dismissal ID. | Terminal command outcome without mutation and released lock. Not a silent dismissal of a live interview/repair requirement. |
| `POST /operations/{operation_id}/cancel` | Stable cancellation identity and expected operation context. | Persisted cancellation state that prevents subsequent publication. Existing Room/design remains. |

Planning commands and generation use the same room-level serialization rules. Answer continuation is part of its original operation; it does not acquire an unrelated second operation identity. Revising an earlier answer identifies its original answered question and `revision_of_answer_id`, validates choices against that stored question, and compares the current decision revision. Accept only at a sequential boundary, preserve the prior answer, append the new revision and reconsider affected selection evidence. A stale ordinary reply without this explicit revision intent remains a conflict. Operation retrieval includes question/answer history needed to present this flow.

An intent-conflict answer can explicitly choose the proposed allowed intent change. Budget approval is a separate explicit typed answer; neither choosing a Product nor ordinary delegation implies it.

#### 13.4 Designs, shopping and history endpoints

| Method and path | Request | Canonical response and invariant |
|---|---|---|
| `GET /designs/{design_id}` | Exact version identity. | Immutable DesignVersion and complete Scene, retaining historical dimensions, prices, evidence and asset revisions. |
| `POST /designs/{design_id}/chat` | Text, optional selected Item, operation ID and expected active ID/revision. | Operation/question or one complete child for the valid successful subset, with all action outcomes. |
| `POST /designs/{design_id}/swap` | Item, selected variant/offer/search-context reference, expected active ID/revision and operation ID. | Same-pose validated child or structured rejection/question. No authoritative client mutation. |
| `POST /designs/{design_id}/remove` | Target Item, expected active ID/revision and operation ID. | Validated removal/consequences as one child, or unchanged target with explanation. Keep still requires explicit unlock. |
| `POST /designs/{design_id}/find-more` | Target Item, search refinements, expected parent/context and operation ID. | Search operation/result reference; selected Product and saved version remain unchanged. |
| `GET /searches/{search_id}` | Exact search identity. | ProductSearch and appended eligible choices, including context and selected identity separate from rank. |
| `POST /rooms/{room_id}/undo` | Expected active ID/revision and operation ID. | Exact parent version plus persisted new active-pointer revision and conversation event IDs. |
| `GET /catalog/manifest` | Optional requested manifest revision. | Versioned category/render asset metadata and dimensional conventions. |
| `GET /health` | No application mutation. | Operational service health without secrets or private diagnostics. |

Buy is ordinary exact-offer navigation, not a purchase API. There is no mutable item-transform PATCH, sample-room route, sharing flow or public web design endpoint. The Scene already provides the purchase details required by the retained shopping UI.

#### 13.5 Revision and idempotency scenarios

| Scenario | Required behavior |
|---|---|
| Generate acknowledgment lost | Lookup original operation; if unknown resend identical request/ID, otherwise reconcile. No duplicate generation. |
| Edit result committed but response lost | Lookup returns same child, active revision and message IDs. UI applies once and keeps one Undo step. |
| User taps submission twice | Same persisted pending intent prevents a second competing operation; server rejects/replays consistently. |
| Same ID reused with different payload | Explicit identity/payload conflict, never a second interpretation. |
| Answer redelivered by network/task | One stored answer and one continuation; no duplicated purchase quantity or version. |
| Different answer for a stale question | Revision conflict/current question reference; no silent overwrite. |
| Undo response lost | Reconcile original operation; do not Undo a second parent on retry. |
| Rename while generating | Metadata revision changes independently; generation's active-base guard stays valid. |
| Deletion while work runs | Invalidate operation and Room; late results cannot commit/recreate artifacts. |
| Cancel races with provider completion | Final commit checks persisted cancellation; no publication after cancellation takes effect. |
| Find more returns after active context changed | Preserve evidence but do not apply a swap; later selection requires validation against the current intended parent. |

#### 13.6 Polling and display recovery

- Use request/response plus polling; persistent streaming is not required.
- While a room/operation screen is visible, an initial two-second polling cadence over roughly twenty seconds supports prompt feedback. If work remains pending, keep an honest pending state and Refresh/continued reconciliation; elapsed polling time is not completion.
- Poll operation identity for generation/questions/results, not a fabricated processed RoomModel before the spatial phase exists.
- When returning to My Rooms, show actual pending status and reconcile the operation when reopening. The room remains mutation-locked while its outcome is uncertain.
- Reuse server event/message IDs when refreshing conversation. Do not append another “completed” message for a result already displayed.
- Preserve local drafts separately from submitted immutable requests. Editing the visible draft does not alter an already running operation's payload.
- No fabricated success, synthetic Product replacement or local price recalculation may cover for an unavailable backend capability.

### 14. Persistence, transactions and retention

#### 14.1 Stored data groups

Use plain Postgres tables and JSONB for documents read/written together. The following are logical data groups, not a requirement for one table per displayed record; physical layout must preserve the stated identities, uniqueness and atomic boundaries.

| Data group | Persisted information | Required lookup/invariant |
|---|---|---|
| Rooms | Device grouping, metadata revision, capture references, planning revision, active pointer/revision, pending operation and deletion state. | Device/Room lookup; separate metadata and design revisions. |
| Captures/artifacts | Raw export references, manifests, frame/artifact checksums, storage receipts, acquisition/finalization status and cleanup identity. | Exact capture/frame identity; no content replacement under a replay ID. |
| Keyframes | Image/depth/confidence references, calibration, pose, dimensions/orientation, timestamps, detector outcomes and stored lifts. | Capture/index uniqueness and input revision for reuse. |
| Room snapshots | Immutable processed geometry, source mapping, validity and counts. | Exact snapshot read; no in-place enrichment. |
| Planning state | Instructions against native/normalized references, revision and command associations. | Compare-and-update revision; original capture untouched. |
| Designs | Parent, capture/snapshot/request/plan/Scene, decisions, Product/purchase/evidence/asset snapshots and creation time. | Immutable version ID and Room lineage. |
| Operations | Original identity/payload, kind/base, state/phase, question/decision revision, completed steps, outcome and cancel state. | Deduplicated identity and one active per Room. |
| Conversation | Messages/events, contexts, operations, base/result references and delivery/outcome. | Stable IDs and exactly-once associations. |
| Products/variants | Discovered facts, source identities, missing fields, rejections and verified dimension evidence. | Category/variant/source lookup and deduplication. |
| Offers/packs | Merchant exact URL, variant/contents, price/availability/check time and evidence. | Variant/offer identity; correct whole-pack arithmetic. |
| Searches/comparisons | Queries, fresh-source pools, top-ten shortlists, shown choices, benchmark versions and explanations. | Search/context lookup separate from saved designs. |
| Query history | Provider request/response evidence and fetched time. | Seven-day ordinary history retention; not a live-search substitute. |
| Asset metadata | Category mappings, immutable revisions, bounds/units/pivots and render references. | Asset identity/revision and manifest lookup. |

Use SSL-enabled database connections, a small bounded pool and indexes for Room/device/design/product/operation access. An initial pool of five connections per Cloud Run instance is the source baseline; validate against deployed concurrency and database limits. Use a simple explicit SQL schema without adding ORM, migration framework, vector or time-series infrastructure.

#### 14.2 Commit boundaries

- Compare expected active/planning revision and active operation at the final commit point, not only when accepting the request.
- Save a child version, active-pointer update and associated conversation outcome as one transaction where possible. A recoverable protocol must still guarantee one logical visible result and event.
- For partial-success edits, the successful subset is the transaction unit. Never persist each requested action as its own version or expose an intermediate invalid Scene.
- Save an answer/revision before dispatching continuation. A recorded dispatch failure remains recoverable and must not lose the answer.
- Save stage output/evidence before acknowledging task delivery. Redelivery observes the stored completion rather than repeating the logical effect.
- Store cancellation/deletion state that is checked before publication. A late provider call can leave diagnostic evidence but cannot create a forbidden active result.
- Undo atomically updates active pointer/revision and its conversation event; it does not mutate the parent/child Scene bodies.
- Search writes do not mutate saved designs or selected identity. A subsequent Swap is a separate validated operation.
- Keep data needed to reconcile terminal results long enough for client retry/reopen; no automatic terminal-result expiry is introduced by this specification.

#### 14.3 Evidence and deletion

- Seven-day dimension freshness controls reuse, not deletion. Twenty-four-hour offer freshness controls checks, not rewriting historical prices.
- Seven-day query-history expiry does not remove Products, rejected candidates or evidence referenced by saved designs.
- Retain all discovered candidates and their rejection/missing-field reasons; do not turn failed verification into invisible disappearance.
- Completed raw room evidence remains privately stored without automatic expiry until explicit Room deletion.
- Abandoned incomplete acquisition is deleted through retryable cleanup. Completed captures are not swept as abandoned.
- Deletion removes Room-specific private artifacts, snapshots, versions and conversation. Retain only the minimal deletion/retry identity required to prevent resurrection and finish cleanup; it is not a surviving copy of private room content.
- Product/model assets and globally reusable candidate evidence are separate data. Avoid embedding deleted room photos or private conversation in those reusable records.

### 15. Deployment, diagnostics and performance

#### 15.1 Deployment

- Run the public API, sequential worker and browser extraction in Cloud Run with Cloud Tasks continuation, managed Postgres and Google Cloud Storage.
- Release workers/model calls while awaiting user input. Human wait time cannot require an open HTTP request or allocated browser session.
- Configure provider credentials server-side and verify actual Gemini/Perceptron model access in the deployment environment.
- Verify Playwright browser dependencies, merchant reachability and request limits in the deployed runtime. Local fixture success is not evidence of cloud extraction coverage.
- Make catalog/stand-in media accessible to the client with stable revisions and a fallback path. Keep capture storage private.
- Support a real TestFlight-compatible iPhone build against deployed services. Signing/distribution and actual target-device behavior are acceptance gates, not assumptions.
- Tune instance scaling/concurrency from measured workload; durable state, not always-allocated CPU or one long request, guarantees continuation.
- Offline catalog preparation may use separate GPU compute; no live catalog generation is required in a user's design request.

#### 15.2 Diagnostics

- Log stage outcomes, revision/base identity, provider and extraction failures, missing evidence, rejected candidates, schema/ID rejection, query counts, retries and token/usage data.
- Record detector outcome separately from successful empty results, plus observation rejection reasons and raycast/depth method.
- Record comparison membership/rule version and selected-offer evidence so ranking explanations can be reproduced.
- Record per-action edit outcomes and final validation failures; debugging partial success must identify what actually committed.
- Preserve user-readable recovery explanations separately from stack traces and provider details. Logs and evidence are data, not instructions.
- Provide a top-down diagnostic plot of walls/normals, virtual segments, openings, keep-clear zones, Object/Item footprints, IDs and Anchor targets.
- Provide calibrated image overlays of native box corners, z-buffer masks and lifted detections. Misalignment blocks confidence in downstream geometry.
- Use recorded captures and synthetic rooms for repeatable diagnosis without adding a shipping sample-room path.

#### 15.3 Performance targets and measurement boundaries

| Target | Measurement and interpretation |
|---|---|
| Capture responsiveness | At most 40 accepted frames, one encoder and one upload per Room; no unbounded full-frame queues or blocked native UI. |
| Native review | Aim to show available large/native geometry within three seconds after Done under healthy conditions; does not imply deferred perception already ran. |
| Optional spatial details | Retain the earlier 15-second detail-processing aspiration measured from actual deferred spatial start; show pending/failed truthfully if exceeded. |
| End-to-end generation | Primary sequential-workflow goal: about 90 seconds of active system processing, reporting user-answer wait separately. Also record total wall time. This is never an automatic failure/cancellation deadline. |
| Fast generation path | Track the earlier p50 ≤20 s and p95 ≤35 s aspiration for paths with resolved decisions and reusable evidence; do not claim it for fresh broad discovery plus human interaction. |
| Language edit | Target ≤8 s for simple edits with reusable evidence; measure extra verification/questions separately and retain recovery beyond the target. |
| Local swap preview | Target sub-300 ms response once option assets/data are available. Server validation/commit is a separate measured latency. |
| Rendering | At least 30 FPS on iPhone 13 Pro with up to 40 rendered Items; visible ghosts count toward load. |
| Small-object positioning | Approximately 15 cm accuracy on representative recorded/physical captures, evaluated with projection diagnostics and measured references. |
| Final validity | Zero prohibited overlaps, unsupported placements and blocked required access in accepted outputs; intentional rug/underlay relationships are not prohibited overlap. |

Report slow/failed work honestly and keep interaction responsive. Do not fake completeness, discard valid work or skip verification to meet a timer. Existing pricing, credit-runway and demo-scale per-session cost estimates are not validated for broad live discovery and interactive cloud execution; measure actual provider/browser/storage usage before stating an operating budget.

#### 15.4 Device and provider verification gates

- Verify a real finalized native export containing doors/windows, enum/attribute encoding, floor/elevation and curve handling.
- Project known geometry into at least three actual keyframes to verify native room/camera alignment, matrix order, orientation and resized intrinsics.
- Verify facing using asymmetric Objects and the normalized bottom-center/+Z model convention.
- Probe actual optional sceneDepth/confidence behavior during RoomPlan. A bounded configuration experiment may be used only if it preserves the session coordinate frame; otherwise raycasting remains sufficient.
- Validate optical-axis depth against edge-of-image points and real distances; do not silently switch semantics to hide calibration errors.
- Compare dedicated detection quality/model behavior with chat box annotations, verify normalization and measure latency/usage.
- Validate live model structured output/tool calls, provider errors and malformed responses against the backend contracts.
- Confirm asset conversion/scale/texture behavior in RealityKit and merchant verification coverage through cloud-hosted browsers.

## Testing Decisions

### 1. Test boundaries and existing state

The primary application test seam is the public backend API. Exercise capture submission, operation start, questions/answers, discovery, finalized selection, spatial work, saved versions and edits through that boundary. Use controlled Gemini, Perceptron, SerpApi, Playwright, storage, task-dispatch and geometry responses to make controller behavior repeatable. Assert returned state, persisted/reopened state, external calls and visible outcomes rather than private methods, internal class layout or exact model wording.

The current application is a SwiftUI starter; there is no existing backend suite or established helper convention to preserve. Use one API-level harness and shared representative evidence fixtures. Avoid separate mocking conventions for every internal module.

Pure geometry needs its own algorithm tests because an API stub cannot prove calibration, containment or collision correctness. Keep those tests deterministic and independent of provider/network access. Small calculation tests are appropriate for decimal money, whole-pack rounding, unit/axis conversion and ranking boundaries. Native device tests are required for capture, camera, rendering and lifecycle behavior that a backend harness cannot establish.

Good tests exercise observable requirements and failure boundaries. They should remain valid when internal implementation is refactored. Do not test helper names, exact model prose or incidental call arrangement unless sequential ordering itself is the requirement.

### 2. Contract fixture requirements

Produce complete executable transport fixtures, with no ellipses, pipe-separated pseudo-enums or undocumented fields. Validate the same fixture corpus through server validation and client decoding. Example sketches in historical drafts are not sufficient.

| Fixture group | Required cases |
|---|---|
| Room list/detail | Empty list, several completed Rooms, native-only Room, processed snapshot, active older branch, pending question, upload recovery, deletion pending. |
| Capture manifest/receipts | All stored, missing upload, lost acknowledgment, duplicate same payload, conflicting same ID, optional depth absent, malformed byte lengths. |
| Native context | Actual walls/door/window, Object IDs, nonzero original floor elevation, optional confidence absent and native-to-normalized mapping. |
| Processed room | Rectangle, L-shaped boundary, larger room with multiple doors, virtual gap, wall/tabletop Objects, fixed fixture, sampled/default colors, invalid boundary. |
| Generation | Initial capture reference without processed snapshot, exact snapshot reuse, empty verified initial batch, questions, no match, delayed processing, success and cancellation. |
| Questions | Single/multi choice, numeric budget, listing image, optional text, Skip, delegation, revised answer, stale reply, target ambiguity and required approval. |
| Product evidence | Exact dimensions, missing axis, package-only measurements, unit conversions, stale evidence, inaccessible page, unavailable offer and multiple merchant offers. |
| Ranking | Equal scores/tie-break, current versus old comparison snapshot, sparse evidence, full evidence and optional refresh threshold boundaries. |
| Purchases | Single unit, identical-unit pack, paid surplus, dependent removal affecting pack need, ambiguous bundle and budget increase proposal. |
| Scene/version | Existing/moved/removed/new Items, original/last-valid placements, non-floor elevation, verified Product, missing asset fallback, parent and active-pointer revisions. |
| Edit outcomes | All applied, partial applied/failed, all failed, no-op, ambiguous target, failed restore, protected target and dependency failure. |
| Reconciliation | Same result after lost response, unknown operation, running operation, stale base, terminal failure and cancelled late worker. |
| Conversation | Review/design entries, stable reply/event IDs, partial-result summary, Undo from/to IDs and historical association after branching. |

Contract tests check that fields necessary to render or enforce rules are present. In particular, require explicit non-floor elevation/support, complete Product choices, amount/currency, active pointer and per-action outcomes; do not permit the client to fill them by guessing.

### 3. Product acceptance criteria

#### 3.1 Entry, Rooms and capture

| ID | Scenario | Pass condition |
|---|---|---|
| AC-001 | Unsupported device | Compatibility screen only; no sample, shopping or design bypass. |
| AC-002 | Camera permission denied | Settings guidance and return to My Rooms; no broken camera state. |
| AC-003 | Empty My Rooms | New Scan available; no sample entry or business selector. |
| AC-004 | Several completed scans | Each remains separately named/dated with thumbnail; creating another does not replace one. |
| AC-005 | Rename while generation runs | Metadata updates; active-base revision and generation remain valid. |
| AC-006 | Reopen after Undo | Persisted active parent opens rather than newest-created child. |
| AC-007 | Confirm Room deletion | Private artifacts, snapshots, designs and conversation are removed; pending results cannot restore them. |
| AC-008 | Deletion acknowledgment lost | Same deletion reconciles/retries visibly; no false confirmation or recreated Room. |
| AC-009 | Scan setup lacks storage/connectivity | Acquisition cannot begin; actionable error preserves earlier Rooms. |
| AC-010 | Normal complete scan | Final native export and calibrated sampled artifacts persist; native review is available. |
| AC-011 | Capture resource pressure | At most one encoder and one upload; ≤40 accepted records; no unbounded camera buffers. |
| AC-012 | Frame cap reached | RoomPlan scanning remains usable; only sampling stops. |
| AC-013 | Simultaneous sampling triggers | One accepted frame, not duplicate frame records. |
| AC-014 | Motion/tracking rejection | Poor candidates skipped and coaching shown without fabricating observations. |
| AC-015 | Transient same-session tracking degradation | Sampling pauses/resumes safely without changing capture identity/frame. |
| AC-016 | Background/lock/origin loss during acquisition | Interrupted message and restart required; no partial-scan continuation. |
| AC-017 | Transport loss during acquisition | Restart flow, cleanup of incomplete capture and fresh origin on retry. |
| AC-018 | Connected retryable upload failure | At most one same-ID retry; no duplicate artifact. |
| AC-019 | Storage write fails | Capture stops honestly; previously saved Rooms remain available. |
| AC-020 | Done response/upload acknowledgment lost | Completed local artifacts retained and recovered idempotently without another scan. |
| AC-021 | Incomplete raw manifest but usable native preview | Local files are not evicted until all required receipts and finalization succeed. |
| AC-022 | Missing optional depth/confidence | Capture still completes; no fabricated sensor data or fixed-resolution assumption. |
| AC-023 | Depth/confidence malformed | Explicit format/length error; no silently misdecoded arrays. |
| AC-024 | Cancel/restart while offline after interruption | Cleanup identity retained and retried; new capture uses fresh IDs/frame. |
| AC-025 | Completed raw-data retention | No automatic expiry; local eviction follows complete verified upload/finalization only. |
| AC-026 | Upload/finalize handler execution | Stores inputs/receipts without calling detector, normalization, lifting, merge or placement. |

#### 3.2 Review, intent and questions

| ID | Scenario | Pass condition |
|---|---|---|
| AC-027 | Native review before processing | Shows actual native geometry/photos/Objects and no nonexistent fused detections. |
| AC-028 | Keep/Remove before normalization | Source identity mapping preserves the exact target after normalization/refinement. |
| AC-029 | Missing planning instruction | Uses decide; does not silently Keep/remove an Object. |
| AC-030 | Review command | Updates one planning revision and conversation; measured geometry and saved designs remain unchanged. |
| AC-031 | Ordinary Remove on a Kept Object | No removal; explicit unlock requirement explained. |
| AC-032 | Explicit unlock/change | Allowed target can change; permanent fixation still prevents physical movement/removal. |
| AC-033 | Intent form | Only Add/Full redesign; required positive USD/no prefill; style exclusivity and drafts work. |
| AC-034 | Text contradicts Add | Explicit intent-conflict question; no silent switch. |
| AC-035 | Add planning | No AI-initiated existing-object moves/removals; optional count target does not force invalid additions. |
| AC-036 | First interactive model request | Includes measured native context and verified initial listing batch or explicit empty batch/reasons. |
| AC-037 | New listing introduced after answer | Verified dimensions/offer/context accompany the next relevant reasoning turn. |
| AC-038 | Initial questions | Useful activity/occupancy/priority questions skip known answers; no forced quota. |
| AC-039 | Choice-only planning | User can finish initial generation without typing through valid choices/delegation. |
| AC-040 | Optional free text | Stored and incorporated without invalidating explicit constraints. |
| AC-041 | Question pending | No search/spatial action remains in flight; worker/model call released. |
| AC-042 | Close/reopen question | Same question/choices/base revision returns; no implicit answer, Skip or delegation. |
| AC-043 | Skip/Decide for me | Existing hard constraints and budget remain; no extra-money permission inferred. |
| AC-044 | Revise earlier answer | Revision history retained; subsequent work uses new accepted context at a serial boundary. |
| AC-045 | Explicit must-have/avoid conflict | Explain conflict and ask what may change; do not silently soften negative/positive requirements. |
| AC-046 | Proposed budget increase | Old/new ceiling, affected purchases and total visible; explicit typed approval required. |
| AC-047 | More expensive preference still within ceiling | May be selected without unnecessary ceiling approval; remains fully validated. |
| AC-048 | Duplicate/stale answer | Duplicate applies once; stale revision/foreign choice IDs rejected with current context. |
| AC-049 | Dismiss standalone command clarification | Original command terminates without mutation; Room lock releases once. |
| AC-050 | Leave an interview/fit-repair question | Generation remains pending/locked until answer, allowed skip/delegation or Cancel. |

#### 3.3 Product evidence, ranking and purchases

| ID | Scenario | Pass condition |
|---|---|---|
| AC-051 | Database already has good candidates | Fresh live discovery still runs; cached history is not substituted. |
| AC-052 | Broad search pass | Relevant database pool and three different live queries collected before narrowing, subject to actual source exhaustion. |
| AC-053 | Candidate rejected | Candidate/missing evidence/reason retained, but absent from selectable options. |
| AC-054 | Missing dimension axis or thin-item thickness | Product remains ineligible; no category/photo estimate fills the gap. |
| AC-055 | Package dimensions/ambiguous variant | Rejected from choices and placement while evidence retained. |
| AC-056 | Valid unit/axis conversion | Normalized width/depth/height match labeled exact-variant evidence. |
| AC-057 | Dimension evidence expired | Reverified after seven days; old saved design unchanged. |
| AC-058 | Selected database offer stale/missing timestamp | Price/availability/variant checked after 24 hours or absent time. |
| AC-059 | Page inaccessible | Classified unverified, not confirmed out of stock; one transient retry only. |
| AC-060 | Confirmed missing measurements | No repeated same-search retries; candidate retained for possible later reconsideration. |
| AC-061 | Optional refresh cutoff 80 | 84 and 85 do not qualify; 86 does, using one current benchmark. Mandatory checks remain mandatory. |
| AC-062 | Fewer than three valid choices | Useful fallback continues; display fewer without unverified filler. |
| AC-063 | Same variant at several merchants | One Product choice with retained offers; cheapest eligible exact offer selected. |
| AC-064 | Different size/color or weak identity evidence | Do not incorrectly merge distinct/uncertain variants by title alone. |
| AC-065 | Ranking | 60/30/10 practical/style/value; source-neutral, with render fidelity only breaking equal scores. |
| AC-066 | Sparse comparables | Fewer than three other distinct comparables with usable recent prices → neutral value 50 and explicit insufficient-evidence label. |
| AC-067 | Comparable median $200 | Candidate prices $150/$200/$250 yield value 75/50/25, with bounded total contribution. |
| AC-068 | Benchmark changes | New comparison snapshot; rerank both sources together; historical scores/reasons unchanged. |
| AC-069 | Cheap Product poorly fits purpose | Raw cheapness does not override practical constraints or redefine the value formula. |
| AC-070 | Two $100 two-chair packs, three placed units | Total $200, four supplied, three placed and one paid surplus. |
| AC-071 | Remove one unit while pack still needed | Pack cost remains as appropriate; no invented refund. |
| AC-072 | Ambiguous bundle/component size | Ineligible choice; ambiguity retained as evidence. |
| AC-073 | Whole-room trade-off | Full affected purchase set and consequences evaluated within approved total before requesting an increase. |
| AC-074 | Find more | Another broad fresh pass; up to three unseen options appended; selection/version unchanged. |
| AC-075 | New evidence changes offer eligibility | Intended new choice reranked/revalidated; saved historical total does not change silently. |

#### 3.4 Perception, geometry and layout

| ID | Scenario | Pass condition |
|---|---|---|
| AC-076 | Selection finalized | Deferred detector/geometry work begins only now, with no competing room operation. |
| AC-077 | Successful detector returns no boxes | Recorded successful empty outcome, distinct from failure. |
| AC-078 | Detector timeout/provider/parse failure | Explicit failed outcome, usage/attempt diagnostics and nonblocking usable-room fallback. |
| AC-079 | All optional detection fails | Usable native boundary can still generate; no false claim that small Objects were fully observed. |
| AC-080 | No usable boundary | Recovery or Rescan; no invented floor or final Scene. |
| AC-081 | Camera round trip | Known synthetic 3D points project/lift within 1 cm, catching signs, matrix order, intrinsics and floor offset. |
| AC-082 | Float32 transport | Exact byte count/endianness decode; optional UInt8 confidence associates with the same depth. |
| AC-083 | Depth disagreement/low confidence | Raycast wins unless positive, confidence-2, <5 m depth lies within 0.3 m. |
| AC-084 | Reflections/outside-room observations | Rejected by Mount-specific position tests with logged reasons. |
| AC-085 | Wall winding/normal | Positive X/Z winding and inward normals; virtual walls never become furniture Anchors. |
| AC-086 | Non-floor Object | Explicit bottom elevation and wall/support survives all contracts and rendering. |
| AC-087 | Native/detector duplicate | Compatible category refinement absorbs into stable Object rather than creating a duplicate. |
| AC-088 | Repeated merge | Stable existing IDs reused; new IDs never recycle old numbers; input replay deterministic. |
| AC-089 | Color insufficient | Default tint used; no fabricated sampled/material result. |
| AC-090 | Door/opening clearance | Personal minimum, swing approximation and side margins applied consistently; rugs/wall Items use stated exceptions. |
| AC-091 | Optional placement ordering | Dependency-ready Additions use Priority first and footprint tie-break; fallback order logged if missing. |
| AC-092 | Targeted edit | Target/permitted dependents can change; unaffected base Items remain Fixed. |
| AC-093 | Addition/support dependency | Support resolves before dependent despite priority/type ordering; cycles/missing targets return conflict. |
| AC-094 | Initial optional Addition does not fit | Explained omission and correct purchases, not invalid placement. |
| AC-095 | Must-have cannot fit | Structured conflict after allowed repair; no silent drop or material Anchor change. |
| AC-096 | Full-redesign access repair | Optional lowest-priority new Items removed only when permitted; hard constraints and original Objects preserved. |
| AC-097 | Fixed original obstacle violates final validity | Conflict reported; “Fixed” is not treated as proof of valid layout. |
| AC-098 | Final Scene checks | Zero prohibited collision, missing support or required access violation before publication. |

#### 3.5 Editing, rendering and history

| ID | Scenario | Pass condition |
|---|---|---|
| AC-099 | Model/card selection | Same stable Item highlighted/revealed; sheet/composer context preserved. |
| AC-100 | Camera gesture/Reset View | Only presentation changes; no transform mutation or design version. |
| AC-101 | Asset download/texture failure | Correct-size stand-in/box or neutral material; room and commands stay usable. |
| AC-102 | Fallback upgraded | Identity/placement/dimensions/selection/camera preserved; no full Scene reset. |
| AC-103 | Removed original Object | Ghost at last-valid placement, absent from obstacles/support; hidden ghost cannot intercept taps. |
| AC-104 | Removed new Item | Hidden from active rendering, with identity/pre-removal state retained for restoration. |
| AC-105 | Restore into occupied pose | Target remains removed with explanation; unrelated valid command actions may still commit. |
| AC-106 | Selected “this” versus named target | Selection disambiguates “this” but does not override another explicit name. |
| AC-107 | Ambiguous target | Persistent clarification; no guessed mutation. |
| AC-108 | All edit actions succeed | Exactly one immutable child, explicit success summary and one Undo. |
| AC-109 | Sofa move succeeds, lamp addition fails | Save sofa move once; failed addition absent, warning specific, purchases correct. |
| AC-110 | Move of already-moved Object fails | Current base-version pose retained, not scan-original pose. |
| AC-111 | Failed replacement plus unrelated valid change | Old target Product/purchases retained; unrelated success committed and failure disclosed. |
| AC-112 | No edit action succeeds | No child or active-pointer change; explanations persist. |
| AC-113 | Remove support with unresolved dependent | No floating Item; removal uncommitted unless permitted valid consequences exist. |
| AC-114 | Optional dependent relocation/omission | Complete valid consequences committed with removal as one child and explained. |
| AC-115 | Dependent must-have would materially change | Ask for approval; no implicit omission under partial-success policy. |
| AC-116 | Partial edit combined Scene invalid | Offending candidates excluded/resolved before commit; warnings never excuse invalid output. |
| AC-117 | Swap preview | Temporary, visibly pending and outside saved history; success adopts canonical child, failure restores saved state. |
| AC-118 | Same-pose Swap incompatible | No silent surrounding movement or later resize; old target preserved. |
| AC-119 | Buy | Exact selected verified offer opens; secondary search is clearly distinct. |
| AC-120 | Undo partial-success command | All committed successes reversed together; failed actions remain without effect. |
| AC-121 | Undo/reopen/branch | Parent persists active; later edit branches; old versions unmodified. |
| AC-122 | Generate again | Success links previous active design; Undo restores it even across snapshots. |
| AC-123 | Conversation after Undo | Original context/result associations retained, with stable from/to Undo event. |
| AC-124 | Later price/dimension/asset enrichment | Saved version geometry/total/evidence not silently rewritten. |
| AC-125 | Pending operation elsewhere | Affected Room locked, camera usable, other Rooms usable. |
| AC-126 | Lost commit response/relaunch | Same child/message IDs reconciled; no second version, action or Undo. |
| AC-127 | Worker redelivery/dispatch failure | Durable step recovery with one logical result and no duplicated purchases/options. |
| AC-128 | Cancel/Room deletion race | No late publication or resurrection; previous valid saved state preserved unless Room was deleted. |
| AC-129 | Exceed generation goal | Honest running state and recovery; no timer-caused failure or unverified shortcut. |
| AC-130 | Actual physical viewer load | At least 30 FPS target with ≤40 rendered Items including visible ghosts, with responsive selection/composer. |

### 4. Focused deterministic tests

#### 4.1 Geometry fixtures and diagnostics

- Use a rectangular personal room, an L-shaped room, and a larger approximately 8×6 m room with fixed Objects and two doors. Their purpose is geometric coverage, not a shipping sample feature or business-mode requirement.
- Include asymmetric furniture, a window with sill height, a narrow door, a wide door, a doorless opening, a real corner, a virtual gap segment, a rug under furniture, a wall Object and a tabletop support chain.
- Create camera round-trip fixtures with known 3D points, calibrated pixel projections and optional depth/confidence; recover within 1 cm in ideal synthetic data.
- Test native-to-room translation, Y sign, column-major decoding, resized intrinsics, optical-axis depth, positive polygon winding, inward normals and local-versus-world dimensions independently of model output.
- Test thresholds on both sides of clustering, containment, confidence, depth refinement, observation-count and sampled-color gates. Use boundary cases with meaningful geometric expectations rather than snapshots of helper output.
- Assert category-specific allowed overlap, support validity, deterministic IDs, stable merge identities, priority fallback and preservation of failed move base poses.
- Use overlays/top-down plots for real-fixture diagnosis; appearance alone does not prove correctness.

#### 4.2 Product and money calculations

- Decimal addition/multiplication and whole-pack rounding must produce exact cents; binary floating rounding cannot create budget eligibility errors.
- Unit conversion and axis mapping retain original evidence and reject package/ambiguous measurements.
- Verify 60/30/10 weighting, relative-value 75/50/25 examples, 0–100 bounds, positive-price requirements and neutral sparse evidence.
- Verify the strict greater-than-five-point cutoff, same-benchmark restriction and mandatory-refresh exception.
- Verify variant/merchant deduplication without conflating colors/sizes or relying only on similar titles.
- Verify placed-unit removal versus purchased-pack retention, paid surplus and complete trade-off totals.

#### 4.3 Stateful API recovery cases

- Drive the same logical request through response loss, retry, worker restart, dispatch failure and app reopen. Assert identical operation/result/message identities and exactly one visible mutation.
- Inject stale active/planning/answer revisions and verify explicit conflicts without reinterpretation.
- Pause at a question and assert no provider/spatial work remains in flight; verify resumption only after durable answer/delegation.
- Cancel at each bounded stage and delete a Room while an external call is in flight; verify commit guards prevent publication.
- Exercise partial successful edits with independent actions and support dependencies. Assert one final valid version rather than a sequence of intermediate snapshots.
- Exercise unknown-operation reconciliation distinctly from known terminal failure. A timeout is not a server outcome.

### 5. Live acceptance

1. Capture a real personal room on supported hardware, preserving actual native export, JPEGs, poses, intrinsics and optional depth evidence.
2. Verify alignment by projecting known native wall/Object corners into at least three frames; inspect near image edges and after floor normalization.
3. Complete native review and initial planning using choices, verify real fresh product discovery and exact-variant evidence in deployed browsers, then run deferred perception and placement.
4. Render the complete room with correct pivots/dimensions and representative assets; verify selection, sheet/composer, fallbacks, ghosts and performance.
5. Demonstrate a valid design, a partial multi-action edit with explicit failure warning, a support-dependent removal, same-pose Swap, Find more, Buy and Undo/branch/reopen.
6. Close/reopen while awaiting a question and while work runs. Restart a worker and verify the original operation resumes without duplicate effects.
7. Cancel work and delete a Room during pending processing; verify no late result becomes active and deletion actually cleans associated private storage.
8. Confirm model IDs/provider capabilities, merchant coverage, asset licenses/conversion and actual cloud/runtime dependencies. Fixtures alone do not establish live readiness.
9. Record generation/edit latency with user wait distinguished, frame rate, extraction success, query/browser/model usage, storage and cloud cost. Report observations rather than assuming source estimates.

## Out of Scope

- Business mode, mode selector, business labels, explicit seating-target controls, business seating-group placement and business-only counter/register clearance workflows.
- Spot intent, tapped-placement input and `at_spot` Anchors.
- Sample-room entry/recovery, unsupported-device browsing, iPad and Android.
- Before/After UI, walk mode, Day/Evening toggle, sharing screenshots/shopping lists and public hosted design sharing.
- Furniture dragging, direct rotation, mutable direct-transform PATCH and manual model-editor tools. Camera gestures and validated Swap/Remove remain included.
- Cart, checkout, payments, Amazon Product API and an additional commerce backend. Exact-offer Buy and an optional secondary configured search link remain included.
- User accounts/login, a shared app-key gate or a new authentication project. Input validation, private capture media and server credentials remain required.
- Offline capture/edit/reopen guarantees, interrupted-acquisition continuation and Use partial scan. Recovery of completed uploads remains included.
- Multi-room reconstruction, textured mesh/Gaussian splats, photorealistic room rebuilding, live camera AR placement or erasing physical furniture from camera images.
- On-demand 3D generation for live results, optional photoreal inspiration images and model review of rendered Scenes. Offline catalog asset preparation remains included.
- Custom voice recording, Redo/history browsing, cross-room preference profiles and a preference-reuse interface.
- Concurrent speculative spatial work, searches behind unanswered questions, parallel per-Room branches, overlapping mutations and future dependency-graph orchestration. Local action dependency validation remains required.
- Extra agent frameworks, multi-agent runtime, microservices, Kubernetes, ORM/migration framework, vector search or time-series infrastructure.
- Dedicated accessibility feature work/acceptance beyond preserving normal platform behavior; standard controls must not deliberately disable it.
- Implementation schedules and new feature discovery. The specification describes the complete selected product, not future releases.

## Further Notes

### Implementation readiness and evidence

The product decisions here are settled. Implementation must encode the defined records and endpoint behavior as executable contracts and fixtures, then meet the stated API, geometry and device acceptance gates. This document does not claim those artifacts or the runtime already exist.

Provider model names, access, SDK compatibility, actual native export details, camera/depth behavior, merchant reachability, asset conversion and operational cost require the concrete checks specified above. These are implementation facts to verify, not permission to change scope or silently weaken verification.

If real evidence invalidates a requirement, record the exact failure and its effect. Preserve saved valid state and return an honest recoverable outcome rather than guessing an alternative contract or fabricating a successful design.

### Architectural rationale

- **Measured context before questions, processing after selection:** the user can express priorities from native capture while the initial controller stays sequential. Product-verified choices remain distinct from final layout validity.
- **Verified dimensions before choice and placement:** estimated Products would make fit and saved geometry unstable. Retain rejected evidence instead of filling missing axes.
- **Immutable versions with a persisted active pointer:** Undo, regeneration and branches remain consistent across reopening; external catalog updates cannot rewrite history.
- **Partial action success with one valid commit:** useful independent changes survive an infeasible action, while one complete validated child and explicit warnings keep the result understandable and reversible.
- **Durable steps beyond request lifetime:** provider calls and human answers exceed one HTTP request. Persist state, release idle workers, deduplicate continuation and never treat total elapsed time as a failure deadline.
- **Separate observed Objects, placed Items and purchased units:** scan geometry, arrangement identity and whole-pack cost have different meanings. Their explicit relationships prevent duplicate identities, unsupported placements and incorrect totals.
