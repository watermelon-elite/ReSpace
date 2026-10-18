# Merge conflict register

## Three-branch integration — 2026-10-18

Sources: checkpoint `eb4d300` (all original local work), remote `humaidjaffery` at `5be3d9c`, and remote `OpenAI-3dmodelgen` at `383dc9f`. The user explicitly accepted the resolutions below. The first incoming branch had no textual conflicts; the second had four. A clean Git merge alone did not establish runtime compatibility.

| Conflict and evidence | Accepted resolution and implementation |
|---|---|
| `ContentView.swift`: AppModel rooms/planning/shopping versus WorkspaceStore’s separate local/remote app. Both branches also declare APIClient, JSONValue, CaptureController and other unrelated types. | Keep the current router and existing saved data. Retain the new capture/reconstruction implementation with distinct Scan-prefixed types. Show saved scans in the current Room library; Plan changes uses the existing backend. Reuse Inter, RS actions/notices and the DreamSeal palette. |
| Capture wire contracts: 900 reconstruction frames, 2560px JPEGs, Float16 depth, sensor orientation metadata, versus 40 planning frames, 1280px JPEGs and Float32 depth. Remote draft/acknowledgment envelopes also differ. | Preserve local reconstruction evidence. `CaptureTransfer` converts an evenly spaced subset with scaled intrinsics and original poses. `ScanIntegration` uses the current Room/keyframe/finalize protocol, persistent backend links and stable replay identities. Freeze the creation name so a rename cannot change a replay payload. The incoming remote API client remains isolated for its retained tests; it is not the production planning transport. |
| Rich exporter: inset sinks, logical counter runs, zero-headroom surfaces versus the restricted reader. | Defer richer planning support as requested. Use original native measurements for planning from integrated scans. Keep richer scene results for viewing. Reject unsupported groups rather than treating a logical counter as another solid physical object. |
| Door clearance: former swing-dependent depth/minimum 0.9m and 0.15m sides versus exporter 1.2m and 0.45m sides. | Adopt exporter clearance in the shared backend helper, clipped to the wall/floor; update the geometry fixture and governing spec. |
| Walkthrough Move/Hide/Paint/Tile/Wallpaper/Undo creates a separate local history without backend Keep/partial-success guarantees. | Viewing-only walkthrough. Remove local mutation methods and controls; preserve old local files without applying them. Existing immutable backend history owns all design edits. This supersedes the editable-view aspects of incoming ADR-0001/0002. |
| `.gitignore` add/add. | Union local configuration, caches, environments and reconstruction data exclusions. |
| `Package.swift` add/add: different source/test libraries. | Retain both disjoint library targets and test suites. Add transfer-calibration and retry-persistence coverage. |
| Xcode Info.plists/permissions/configuration and actor isolation. Incoming branch independently uses project version 110, unavailable in installed Xcode. Duplicate APIClient filenames also collide in generated strings output. | Use compatible project version 77 and explicit nonisolated default; combine camera/Photos/reconstruction settings. Debug retains local networking; Release requires HTTPS. Rename the incoming APIClient source and duplicate symbols; retain UI and normal shared schemes. |
| Swift compiler cannot type-check a chained matrix expression and the integrated preview body in reasonable time. | Split identical arithmetic into named terms and break the view body into smaller view expressions. Preserve rendering math and job lifecycle. |
| `furniture_assets.py` omits the new orientation option. | Pass `--auto-orient` for SPAR3D conversion; visual review remains required and pending assets are not promoted automatically. |
| Reconstruction reader indexes empty walls and accepts NaN/Infinity in comparison-based validation. | Fail closed on malformed or nonfinite evidence; retain specific validity reasons and regression tests. |
| A stationary kettle in `obstacles` is absent from editable Scene items, so removing its counter could strand it. | Shared scene validation blocks changing/removing its original support, including publication paths that bypass an edit helper. Preserve partial-success behavior for unrelated actions. |
| Six existing mypy errors in provider configuration and multipart parsing. | Use typed provider configuration and explicit string/UploadFile narrowing; backend type checking passes. |
| `sample_room_2`: wall attachment/protrusion is inconsistent and USDZ nodes remain in scan coordinates while JSON is in room coordinates. | Preserve source measurements and explicitly quarantine the pair with `planning_eligible: false`. Re-export both files from the original capture before clearing quarantine. |
| Duplicate proposal documents claim fields different from the implementation. | Put the restricted reader contract first in `specs/room-reconstruction-json.md`, retain the original proposal as history, point the root duplicate at it, and distinguish the richer exporter guide. |
| Different Python package requirements for backend, reconstruction and offline assets. | Keep their environments separate. Do not downgrade or replace the user's existing environments. |

The added transfer adapter, tests and documentation are integration work: the adapter preserves calibration and recovery across incompatible protocols; tests verify those boundaries; documentation records the user's decisions and prevents later reintroduction of incompatible contracts. No unrelated feature was added.

### Verification of the resolved merge

- Debug and Release iOS Simulator builds passed for the combined app. Both built Info.plists retain camera, Photos-sharing and reconstruction settings; only Debug permits local HTTP.
- Swift: 111 executed, 110 passed, one live-service check skipped. Includes real native import of the offline-generated room, transfer calibration/depth conversion, stable frame sampling, stored backend links and immutable creation-name replay.
- Planning backend: 416 passed; six opt-in live/provider checks skipped. Includes malformed geometry, richer-format rejection, stationary support protection and larger doorway clearance regressions.
- Reconstruction service: 249 passed; one live check skipped. Its Python environment was isolated from the backend and offline asset tools.
- Launch-script prototype: eight passed. Backend mypy: no issues in 34 source files with unavailable third-party stubs ignored.
- Actual Swift-converted JPEG/depth/confidence were accepted by the Python API; repeated creation, upload and finalization reused the same identities and yielded a readable native Room.
- An isolated iPhone Simulator exercised saved scan → Plan changes → upload/finalize → rendered native Room review. Installing the final build and reopening reused the same Room without another upload. The reconstruction entry screen was visually checked against the shared RS layout.
- Both remote tips were rechecked and remained at the source commits above. Staged whitespace/conflict-marker checks passed.

No paid provider calls or physical LiDAR capture were performed. Offline checks cannot establish arbitrary-room reconstruction quality, real-device performance or provider availability. Rich exporter-to-planner support remains intentionally deferred. Non-blocking diagnostics were Starlette’s test-client deprecation and Xcode’s skipped AppIntents metadata extraction (the app has no AppIntents dependency).

## Earlier H1/H2/H3 specification reconciliation


Status: resolved. The user accepted every Q1–Q9 recommendation, then explicitly chose partial success for multi-action edits. The user requested a complete product specification organized by functionality and system components, excluding builder labels, assignments, ownership tables, team handoffs and staffing plans. This register preserves reconciliation history; `../SPEC.md` is the consolidated product specification.

## Inputs and boundary

- [H1: iOS and 3D](BUILDER_1_SPEC.md).
- [H2: perception and spatial](H2-perception-spatial.md).
- [H3: agent, products and backend](h3spec.md).
- The pre-consolidation version of `SPEC.md` supplied the baseline for retained requirements. Its replacement, [the complete product specification](../SPEC.md), now governs implementation.

The source line numbers below refer to the working-tree documents at the start of reconciliation. The H1 and H3 files have already been moved into `specs/` by the user. The application is still a SwiftUI starter; implemented behavior does not settle these disputes.

Only incompatible requirements are questions. Compatible additional detail is merged. Recommendations below were accepted except for the explicitly overridden multi-action-edit recommendation. The compilation must preserve detailed contracts, algorithms, UI behavior, recovery and acceptance checks, while removing superseded alternatives and interview history from normative requirements. It must introduce no new feature scope.

## Decision tree

The first interview round covered Q1–Q9 below. Q2 contained four independent scope choices. All are resolved.

- Q1: shopping and direct actions → which shopping screens and acceptance paths survive.
- Q2a–d: business, Spot, samples and viewer/sharing scope → corresponding inputs, algorithms and acceptance obligations.
- Q3: perception timing → pre-generation review, native identity mapping, snapshot timing and progress.
- Q4: editable Items → the follow-up on failed multi-action commands below.
- Q5: hard requirements → permitted initial-generation omissions and repair outcomes.
- Q6: Keep semantics → unlock/remove enforcement and conversation outcomes.
- Q7: depth bytes → the same encoder/decoder contract for H1/H3/H2.
- Q8: placement ordering → which optional Additions consume space first.
- Q9: detection outcome → truthful failed/completed capture-processing state.

The user accepted the first-round recommendations and explicitly selected partial success in the dependent command-failure question. The later instruction to produce the final complete specification authorized consolidation of that shared understanding. This register retains the original proposals and their recorded outcomes; proposals cannot override the final decisions.

## First-round conflicts

### Q1. Live shopping and direct item actions

**H1:** shopping is display/navigation only; alternatives never replace products; Buy is unavailable; model edits use natural language. See H1 lines 36–43, 102–108 and 128–135.

**H3:** the live scan-to-design-to-Buy journey is required, with verified options, Find more, validated Swap/Remove actions, exact merchant links and local swap preview. See H3 lines 105, 164–166, 210–215, 236–238 and 257.

**Impact:** a functioning H3 product service cannot satisfy its acceptance journey through H1's specified placeholder UI.

**Recommendation:** adopt H3's live shopping/actions, including its swap-preview behavior; H3 computes product selection, validation and totals, and H1 presents results. Retain the shared exclusion of dragging, rotation and checkout. Natural-language commands still have no speculative preview. Alternative: retain H1's placeholder shopping and remove the conflicting live-shopping/client acceptance obligations from H3; language-driven real-product changes remain as H1 already permits.

**Decision:** accepted as recommended.

### Q2. Explicitly included versus excluded product surfaces

| Choice | H1 excludes | H2/H3 requires | Recommendation |
|---|---|---|---|
| Q2a: business mode | Mode selector, business labels and seat target; personal flow for everyone (H1 39, 50). | Home/business inputs, business questions and seating acceptance (H3 24, 33, 149, 155, 350); business zones and seating groups (H2 281–291, 419–428, 529). | H1's personal-only experience. |
| Q2b: Spot intent | Only Add and Full redesign (H1 38, 71). | Selected-spot input and `at_spot` placement (H3 140, 145, 155, 203; H2 528). | H1's two intents. Named wall/corner/object Anchors still work. |
| Q2c: samples | Unsupported devices cannot enter room/design flows; Rescan only for unusable geometry (H1 40, 49, 144). | Sample experience on unsupported devices and sample recovery (H3 25, 71, 201, 262). | H1's LiDAR-iPhone gate and Rescan recovery. Development fixtures remain valid. |
| Q2d: viewer/sharing | Before/After, walk mode, Day/Evening, sharing (H1 38, 244). | Those interfaces and their acceptance checks (H3 77–78, 90, 253, 257, 349–350). | H1's orbit/pan/zoom, neutral lighting and no sharing. Each excluded feature can be selected separately if desired. |

**Impact:** these are incompatible shipping and acceptance requirements, not a request to invent additional features. Narrower recommendations preserve H1's deliberate client boundary; they are not assumed to override H2/H3.

**Decisions:** Q2a–Q2d accepted as recommended; all four feature groups are excluded from this product scope.

### Q3. When perception and normalization run

**H1/H2:** detection runs with keyframe uploads; normalization/lifting/merge occur on finalization; review shows the processed room and incorporates late detections before generation. See H1 149–152, 185–186 and 229–233; H2 179–187.

**H3:** upload/finalize only store inputs; native capture/photos support review and the sequential interview; detection/normalization/lifting/merge start after choices and verified listings are finalized. No H2 work runs behind an unanswered question. See H3 124–145 and 275–278.

**Impact:** H1 expects a processed snapshot that H3 deliberately has not created; the same upload/finalize handlers cannot obey both schedules.

**Recommendation:** H3's deferred sequential workflow. H1 reviews native capture first, and H2 preserves/maps choices made against native identities. Freeze the processed room snapshot when it exists. Preserve H1's durable capture manifest and raw-data retention. Align review, validity timing, progress and acceptance checks with this order; remove the incompatible pre-generation late-detection branch. Retain H2's algorithms rather than changing them to implement orchestration.

**Decision:** accepted as recommended.

### Q4. Which existing Scene Items a chat edit can change

**H1/H3:** chat can move, remove, replace and restore Items; removal can require permitted changes to dependents. See H1 67, 95–108; H3 212–214.

**H2:** every Item in `base` is Fixed during re-solve (173, 545, 569). Moves/removes target only `object_id` (267–268), while previously added Products have `object_id: null` (300–302).

**Impact:** “move the lamp you added” is neither representable nor executable under the H2 contract. Removing a support cannot relocate its affected dependents.

**Recommendation:** hold unaffected Items fixed; allow explicit targets and permitted dependents to change, subject to Keep and permanent-fixture constraints. Use stable Scene Item identity for previously added products while preserving original Object mappings. This makes the already-required edit behavior executable.

**Decision:** accepted as recommended; the dependent failure policy is resolved below.

### Q5. Initial-generation repairs versus explicit requirements

**H2:** try another Anchor, drop a new Item if it cannot fit, and remove lowest-priority new Items for aisle repair, without a hard-requirement exception. See H2 556–566.

**H3:** explicit must-haves and choices cannot be silently dropped or materially changed; return unresolved conflicts after permitted repair so H3 can find an allowed equivalent or ask a targeted question. See H3 153, 205–206 and 294.

**Impact:** a solver Scene with only a warning can violate a user requirement that H3 promises to preserve.

**Recommendation:** H3's hard-constraint rule. Keep bounded repairs and explained optional omissions; return an unresolved conflict for a protected requirement. Distinguish hard requirements from soft Addition priority.

**Decision:** accepted as recommended.

### Q6. Removing a Kept Object

**H1:** movement/removal requires an explicit unlock, which may be part of the same command. See H1 92–96.

**H3:** explicit Remove itself overrides an earlier Keep. See H3 154 and 285.

**Impact:** the same “remove this kept sofa” command has opposite outcomes.

**Recommendation:** H1's explicit unlock rule; an explicit combined unlock-and-remove command can be one atomic change. Keep protects against both AI changes and accidental ordinary commands. Alternative: adopt H3's explicit Remove override and revise the lock semantics consistently. Permanent `fixed_in_place` fixtures remain protected either way.

**Decision:** accepted as recommended.

### Q7. Depth encoding

**H1:** proposed little-endian Float16 transport, explicitly subject to H2 agreement (210).

**H2:** little-endian row-major Float32 meters, optional UInt8 confidence and actual dimensions (329–331).

**Impact:** an unchanged encoder/decoder pair reads different byte lengths and values.

**Recommendation:** H2's Float32 contract, retaining optional depth/confidence and actual dimensions. H1 already records that the native depth buffer is Float32 (458). This is a handoff agreement, not another depth-acquisition feature.

**Decision:** accepted as recommended.

### Q8. Addition placement order

**H2:** Addition priority first, footprint as tie-breaker; reverse priority for permitted removals (108–110, 552–565).

**H3:** additions by footprint (204).

**Impact:** a large optional Addition can consume the space needed by a smaller, more important Addition under one ordering but not the other.

**Recommendation:** H2's priority-first rule. Product-ranking scores remain separate and unchanged; they choose Products, not placement order.

**Decision:** accepted as recommended.

### Q9. Successful empty detection versus detector failure

**H2:** `detect()` returns a list and returns `[]` on failure (148, 444).

**H1/H3:** distinguish failed optional processing from successful completion and record each detection outcome. See H1 222, 229; H3 201, 249 and 330.

**Impact:** the return contract erases the difference between “nothing found” and “detection failed,” so H3 cannot reliably supply the required status.

**Recommendation:** reserve `[]` for successful empty results; propagate failure separately to H3, for example with an exception it records as a failed attempt. Preserve the already-agreed nonblocking partial-detection fallback. The reporting change must not make detector failure fatal to an otherwise usable room.

**Decision:** accepted as recommended.

## Dependent conflict: failed multi-action edits

Resolved after Q4: the user selected “Save successful parts with warnings.”

**H1:** every requested operation in a design command succeeds or the active design stays unchanged; partial initial-generation output is explicitly different (102, 196).

**H2:** failed additions are dropped, failed moves return to original position, and the solver returns a Scene with warnings (560–566).

**Impact:** “move the sofa and add the lamp” can save only one requested change. For an already moved Object, restoring its scanned original position is also different from preserving the current saved placement.

**Recommendation:** use H1's all-or-nothing rule for design commands; validate the candidate before committing one child, and preserve the current active version on any failed requested operation. Initial generation can omit optional Additions under Q5's rule. H3's permitted dependent consequences belong in the same atomic child, not independent commits.

**Decision:** the recommendation above was overridden. Save successful parts with explicit warnings for unsuccessful parts. Validate the complete resulting scene; failed moves retain their current saved placement. A committed successful subset produces one immutable child and one Undo unit. No successful change means no child. Changes that depend on a failed operation cannot be reported as successful; safety, support, Keep and hard requirements remain enforced.

## Compatible requirements to compile without another product interview

- H1's at-most-four upload bound and H3's one upload are compatible: one satisfies both.
- H1 operation states and H3 detailed execution phases describe different levels of progress.
- H1's 60-second HTTP wait already requires operation reconciliation; it is compatible with H3's durable work and no total elapsed-time cutoff. The compiled specification defines distinct active-processing, user-wait, reusable-evidence and deferred-processing measurement boundaries; none is a runtime failure deadline.
- H1 says generation Cancel is not required, not forbidden. Retain H3's already-required explicit cancellation and its prevention of late publication.
- H1's active pointer, room rename/delete, conversation outcomes, planning revisions and permanent completed-capture retention add detail that H3 does not reject. Retain them.
- H1's proposed app-key header does not require H3 to implement app-key gating. Align transport with H3's explicit no-shared-key policy; omit the unused proposed header rather than adding an authentication project. Keep server-side credentials and private scan media.
- H3's eligibility gate excludes purchase Products with estimated or missing dimensions before H2 placement. H2's fallback sizing need not become permission to place unverified Products; scanned Object estimates remain distinct.
- Native capture IDs map to deterministic normalized IDs under the accepted deferred-processing sequence.
- H2's `qty` expands physical placed units; H3 separately owns whole-pack purchases, paid surplus and money. These are not competing counts.
- H3 can supply full product/alternative metadata from H2's references. H1's required elevation, rendering and snapshot details complete the shared schema; missing illustrative fields alone are not conflicts.
- H2's raycast-first, bounded depth-refinement algorithm supplies the precise implementation behind H1/H3's generic depth/fallback wording. Preserve the agreed size, frame, bottom-center pivot and yaw conventions.
- H2's overlap helper remains useful for server validation without reintroducing manual dragging. Test fixtures do not imply a shipping sample-room feature.
- The accepted deferred sequence uses actual-stage progress and supersedes the pre-interview story cycle. This follows the pipeline decision rather than introducing another scope choice.
- Initial invalid-plan-item filtering must not silently discard hard requirements. Partially successful design commands explicitly report each failed requested change; all committed changes and permitted dependent consequences form one valid child version.

## Compilation status

Completed: [SPEC.md](../SPEC.md) consolidates the accepted scope, all compatible source detail and the partial-edit override into a product/component structure. Source-to-draft reviews checked client workflows, perception/geometry, planning/products and their shared contracts. The final document contains 95 user stories and 130 acceptance criteria, with explicit schemas, API behavior, recovery, persistence and verification gates. The source documents remain historical inputs; no application implementation code was changed.

The complete specification is also published in [GitHub issue #1](https://github.com/watermelon-elite/ReSpace/issues/1), labeled `ready-for-agent`, with four consecutive indexed parts. Read-back verification confirmed that their combined normative text exactly matches `SPEC.md`.
