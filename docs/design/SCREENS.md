# ReSpace screen and state contracts

Use [PROFILE](PROFILE.md) for authority and [SYSTEM](SYSTEM.md) for visual implementation. This reference specifies the information architecture of the whole app. A “screen” below can be a route, modal, panel or state of an existing view; it does not imply a new file or backend endpoint.

**Contract** means current SPEC behavior. Layout/copy prescriptions are the intended design direction unless marked as recommendations. Example copy describes a pattern; sample prices, objects and outcomes must never be passed off as live data.

## 1. Screen contract template

Before implementing a new state, fill in this compact contract:

~~~yaml
screen:
  name: human-readable state name
  task: one verb-led sentence
  entry: preceding state and required authoritative data
  archetype: focused-page | room-canvas | evidence | list | native-handoff
  immediate:
    - facts required for the current decision
  disclosed:
    - secondary details and how to reach them
  primary_action: action, eligibility, acknowledgement and destination
  secondary_actions: safe exits and necessary alternatives
  state_owner:
    presentation: selection / panel / camera / navigation
    durable: room / question / operation / committed version / saved list
  states: loading / ready / empty / busy / error / uncertain / terminal
  persistence: what survives leaving, failure and reopening
  verification: concrete assertions and fixture/runtime evidence
~~~

Do not list a state that cannot occur merely to fill the template. Do not omit one that can occur because the happy-path screenshot is simpler.

## 2. Whole-app map

| Family | Native implementation entry | Main task |
|---|---|---|
| Compatibility, library, setup, connection | [ContentView.swift](../../ReSpace/ContentView.swift) | Enter the supported product; find or scan a Room |
| Capture/finalization | [Capture.swift](../../ReSpace/Capture.swift) | Capture and durably retain one room |
| Native Room review and instructions | [RoomViews.swift](../../ReSpace/RoomViews.swift) | Understand the measured Room and express what may change |
| Initial request and ordinary reply | [IntentViews.swift](../../ReSpace/IntentViews.swift) | Describe the desired change in one composer |
| Questions, operation detail and outcomes | [OperationViews.swift](../../ReSpace/OperationViews.swift) | Resolve one decision or understand actual work |
| Committed Design, Items and edit tools | [DesignView.swift](../../ReSpace/DesignView.swift) | Inspect and refine a saved arrangement |
| Product evidence/options | [ProductViews.swift](../../ReSpace/ProductViews.swift) | Evaluate a specific Product and its alternatives |
| Imported reconstructed Room | [ImportedRoomView.swift](../../ReSpace/ImportedRoomView.swift) | Inspect reconstructed context and request a constrained Product plan |
| Local purchase lists | [ShoppingListViews.swift](../../ReSpace/ShoppingListViews.swift) | Revisit exact saved purchases |
| Share preview and native export | [ShoppingShareView.swift](../../ReSpace/ShoppingShareView.swift) | Review and export a shopping list |
| Development fixtures | [UIDemo.swift](../../ReSpace/UIDemo.swift), [UI studio](../ui-studio.md) | Inspect actual view layouts safely |

## 3. Entry and My Rooms

### SCREEN-01 — Device compatibility

**Task:** understand whether this device can scan and use the product.

Use a focused page with a direct compatibility title, one short explanation of the supported LiDAR iPhone requirement and an appropriate safe exit. Distinguish hardware incompatibility from camera-permission denial, backend connectivity and storage failure.

**Contract:** unsupported production devices show compatibility information; they do not enter a sample-room bypass. A debug UI studio is a separate development surface.

**Audit checks:**

- Hardware support failure does not invite repeated camera-permission retries.
- Permission denial on supported hardware does not say the device is unsupported.
- Production and debug entry conditions are inspected separately.
- No fictitious demo capability is presented as a recovery route.

### SCREEN-02 — My Rooms, empty

**Task:** start the first scan.

**Immediate content:** concise heading, one relevant room image if available, dominant Scan your room action. A small connection/recovery message can replace decorative content when prerequisites need attention.

The image establishes what the app is about; it is inspiration, not the user's captured room. Avoid additional cards for style, shopping, inspiration browsing or feature education.

**Actions:** Scan → setup/permission. A necessary connection/settings control can be quiet. No account creation step.

**States:** library loading must not briefly flash a false empty state; a load failure has Retry; a genuinely empty result presents the first-scan state.

**Verification:** one dominant action; image remains secondary; error and empty are distinct; narrow-height layouts preserve action reachability.

### SCREEN-03 — My Rooms, populated

**Task:** choose the Room to work on, or scan another.

**Immediate content per Room:** thumbnail, name, scan date and actual pending state when present. The first/featured room may use a larger image; additional rooms should remain easy to scan as rows.

**Actions:** open Room → review; New Scan creates a new Room. Saved shopping lists is a separate compact destination when available. Rename/delete belong to Room options, not competing large library actions.

The library header is just Your rooms and an accessible shopping-bag icon. Omit
the wordmark, mascot, tagline and lower shopping-list row. Debug Simulator scans
use a full-color, intentionally inert Scan your room button with no device-test
notice; physical-device scan gating stays in place.

**State rules:**

- Show persisted active work such as Generating or Awaiting answer.
- Opening the Room does not launch a second operation.
- New captures preserve completed Rooms.
- A Room awaiting deletion is identified as unavailable/pending until reconciliation.
- A failed thumbnail still shows name/date and a usable row.

**Do not imply:** newest saved version equals active version; Undo may have restored an older parent.

**Verification:** several Rooms with long names, missing images, one pending question, one active operation and a deletion recovery. A pending item should not consume the entire library.

### SCREEN-04 — Connection and development configuration

**Task:** recover the connection needed to proceed.

Current ContentView exposes backend URL and installation identity configuration. Treat this as an implementation/setup surface. It is not part of the consumer visual language or a reason to display API details across the app.

**Recommendation:** keep operational configuration clearly separated from the room workflow. Consumer-facing failure copy should state the action available now; diagnostics may retain technical detail.

Do not add authentication/accounts or remove the existing connection flow under the guise of polishing. A release presentation decision is separate from documenting the present implementation.

**Verification:** invalid URL, unreachable server, retained input and retry; no credential or private installation data leaks into screenshots, shared images or public links.

## 4. Scan and recovery

### SCREEN-05 — Scan setup

**Task:** prepare to capture this room.

**Immediate content:** one instruction, relevant camera/room visual if helpful, Start scan. Keep instructions short enough to recall while moving the phone.

**Disclosed:** readiness details explaining camera access, connection and storage. Show a failed prerequisite directly rather than hiding it inside a collapsed checklist.

**Contract (integration decision, 2026-10-18):** validate camera permission, mesh capture support and writable local storage before acquisition. Retain reconstruction evidence locally; connect to the planning backend when Plan changes is chosen. Request permission in the scan context.

**Failure branches:** camera denied → explanation and Settings route; planning/reconstruction connection failure → retain saved scan and reconnect/retry; insufficient writable storage → actionable storage explanation; unsupported hardware → compatibility state.

**Verification:** each prerequisite has a distinct message and recovery; restarting setup does not create duplicate logical captures.

### SCREEN-06 — Active capture

**Task:** follow the current native scan guidance.

The native camera/RoomPlan experience dominates. Place one current coaching instruction in a legible overlay. Finish scan is the principal explicit completion control; Cancel scan is secondary.

**Contract:** camera movement gathers observations; it does not design the room. Capture duration guidance is not an auto-finish timer. Frame sampling/upload counters describe artifacts, not unique Objects or completed perception.

**Observed:** current UI shows “Stored … · Pending …” over capture. **Recommendation:** keep user-relevant acquisition status prominent and move raw counters to a less prominent diagnostic treatment if they do not change the user's action.

**Failures:** transient tracking degradation may guide recovery within the same session. Backgrounding, origin loss, session failure or transport loss during acquisition require interruption/restart according to SPEC.

**Verification:** guidance remains readable over bright/dark camera content; Finish and Cancel have accessible targets; no decorative overlay covers important native coaching; scanning performance is not affected by continuous heavy layout animation.

### SCREEN-07 — Discard scan confirmation

**Task:** decide whether to discard this scan.

Show a short question and the exact loss: this scan and its photos will be discarded and a new scan will be needed. Keep scanning/Keep this scan is the safe action; Discard scan is explicit.

Do not call this “Delete room” if it only concerns the current incomplete capture. Previously completed Rooms remain intact.

**Verification:** Back returns without discarding; repeated activation does not repeat destructive work; the wording matches whether capture is still active or already saved locally.

### SCREEN-08 — Finalizing and saving

**Task:** understand whether the completed capture has been safely retained.

Show actual saving/upload state, optional measured-room preview and a clear path back when allowed. Details can include stored artifacts if they help explain recovery, but the first message should describe the consequence for the user.

**Contract:** a verified local save precedes the saved-scan screen. Plan changes transfers the calibrated subset and requires durable backend completion before native Room review. Reconstruction runs separately and publishes only a verified finished walkthrough. Deferred perception has not yet run; do not claim detected small objects or a finished design.

If the operation is still safely completing, leaving does not mean discard. If storage failed, do not use “Your scan is safe.”

**Verification:** pending finalization, local save failure, server response loss and durable completion produce distinct states; no invented percent; no rescan demand merely because a completed upload needs reconciliation.

### SCREEN-09 — Interrupted acquisition

**Task:** restart an invalidated scan.

Use the direct explanation “Scan interrupted. Start again to capture this room” or equivalent accurate copy. The primary action starts a fresh capture; the safe exit returns to My Rooms.

**Contract:** partial acquisition is not resumable. Do not offer Continue scan, Use partial room or a sample-room escape. Cleanup/retry details can be secondary while the restart action remains clear.

**Verification:** a fresh capture gets fresh identity/origin; completed Rooms remain accessible; pending cleanup is not presented as a completed deletion until confirmed.

### SCREEN-10 — Completed-upload recovery

**Task:** finish saving an already completed scan.

**Immediate content:** retained-state explanation, actual remaining work and Try saving again. A quiet return to My Rooms remains available where allowed.

**Contract:** retain finished artifacts; reconcile and retry with the same identities. This differs from interrupted acquisition and should not look like a generic “Scan failed” page.

**Verification:** reopening preserves recovery; retry does not duplicate Rooms; storage errors do not falsely promise retention; a user can explicitly discard with the appropriate scope.

## 5. Measured Room review

### SCREEN-11 — Review canvas

**Task:** inspect the measured Room and describe the desired change.

**Immediate layout:** compact Room name/navigation, Objects access and Reset View above a full available scene, persistent floating composer below. If an active Design exists, provide a compact Saved design/Reopen design route.

The initial view does not require a giant title or an Object-instruction checklist. Geometry and photos are native measured context before deferred processing.

**Disclosed:** Objects, Room options, photos, instructions and metadata. Existing instruction conversation may remain in its specific review surface; do not confuse it with the removed Design Assistant tab.

**Selection:** selecting an Object highlights it and supplies explicit command context. Camera gestures orbit/pan/zoom without changing object placement.

**Loading/error:** initial load shows progress; failure must replace indefinite progress with Retry and a safe exit. Preserve already loaded room context during a later refresh failure.

**Verification:** scene uses available space; composer above keyboard; selected Object context can clear independently of draft; a failed initial request has visible recovery. The current root review error treatment is a source finding in AUDIT.

### SCREEN-12 — Objects list and one Object's instruction

**Task:** decide what may happen to a particular observed Object.

List Objects with recognizable category/name and current instruction. Selecting one opens a focused Object state with measured context/preview and exactly the three mutually exclusive instructions:

- Keep in place.
- Let the design decide.
- Remove from design.

The first protects position and presence. The default is Let the design decide. Remove changes future design intent while preserving the original room.

**Layout:** one Object at a time, with a concise title and three choices. Label any displayed dimensions. The save action confirms the planning instruction; do not imply geometry moved immediately.

**Busy:** block competing instructions while the Room operation is locked. Preserve the selection/draft on failure.

**Verification:** unspecified instruction renders as default, Keep and Remove never appear simultaneously selected, saved instructions map to stable native identity, and failure does not jump to another Object.

### SCREEN-13 — Unlock a Kept Object

**Task:** explicitly permit a protected change.

Name the Object and explain what protection is being removed. Provide explicit Unlock and continue plus a safe return/Keep protected action.

An ordinary Remove selection must not implicitly unlock. The current implementation can route a removal command to backend clarification; verify the complete interaction before claiming a local screen alone enforces the rule.

**Contract:** permanent fixtures remain governed by their constraints even after a user planning preference changes.

**Verification:** both Keep→Decide and Keep→Remove paths require appropriate explicit authorization; Back leaves protection intact; approval targets the same Object and revision.

### SCREEN-14 — Photos and Room instructions

These are separate secondary tasks, not a single crowded “Room details” dashboard.

**Photos:** show one actual capture photo, clear position/count if useful, previous/next controls when multiple and a safe return. Preserve aspect and distinguish loading from unavailable media. A missing photo does not imply the Room itself disappeared.

**Instructions:** let the person explain planning constraints in text, with enough context to know this affects future planning. Persistent instruction conversation can support revisiting what was said. The Room-review command must not mutate measured geometry or an existing saved design.

**Verification:** private media uses the existing authorized media path; no raw capture media enters public exports; text survives failure; source IDs and internal request details are not presented as conversation content.

### SCREEN-15 — Room options, rename, deletion

Room options is a short list of distinct secondary actions. Each opens its own focused state.

**Rename:** one text field with current name, clear Save action and Back. Metadata revision is independent of design history. Preserve input after failure.

**Delete confirmation:** name the Room and the associated data affected: scan/photos, designs, conversation and relevant retained Room data. Current local shopping-list cleanup is also part of confirmed deletion. Explicit Delete room; safe cancel/back.

**Deletion pending:** show that confirmation is still awaited and provide reconciliation/retry. Do not remove evidence of pending work and claim success merely because the first request returned an error.

**Verification:** rename does not invalidate layout work; deletion prevents late operation resurrection; other Rooms remain usable; the local list is removed only through the defined confirmed cleanup flow.

## 6. Natural-language requests and questions

### SCREEN-16 — Initial request

**Task:** describe the room change.

Use the Room's floating composer. The initial request may combine activities, style, constraints and a budget naturally. Do not force the person through separate scope/style/budget pages.

**Data:** current Room/capture/revision identities, user's exact words, optional selected Object, automatic intent and USD currency. Keep identifiers out of consumer copy.

**Contract:** infer supported scope/style from the text. Extract only an explicit whole-room spending ceiling; ask when missing/ambiguous before Product discovery. An explicit no-purchases/$0 request is valid.

**Success acknowledgement:** show actual accepted operation state and keep the Room visible. Clear a submitted draft only after acceptance; preserve it after errors/unknown outcomes according to the existing request flow.

**Verification:** a fully specified request avoids redundant questions; a vague budget produces clarification; zero is not treated as blank; double Send/response loss does not duplicate generation.

### SCREEN-17 — Ordinary clarification

**Task:** answer one unresolved practical question.

Show one question and accept a natural-language response through the same composer model. Keep enough Room/selected-target context to interpret the question. Only the current question is active.

Good question topics are actual activities, usual occupants/guests and the desired improvement, when unanswered. The rough target of three useful questions does not justify asking known questions or stopping before a hard conflict is resolved.

**Disclosure:** operation details/options can contain Leave for now, permitted Skip, Decide for me, cancellation and answer revision. Avoid presenting all controls as equally prominent choices beside the answer.

**Motion:** use the vertical handoff in SYSTEM when the question changes. Preserve the answer when navigating back through a permitted revision path. Ordinary keyboard behavior remains native.

**Verification:** long question, multiline answer, empty/whitespace answer, keyboard appearance, server delay/error, navigation away/reopen and exact question restoration.

### SCREEN-18 — Structured Product comparison

**Task:** choose between eligible Products with a meaningful trade-off.

This is a justified exception to ordinary free-text clarification.

**Visible for each choice:** actual image or honest fallback, title/variant, merchant, checked price, labeled dimensions relevant to the choice and concise practical consequence. Show fit pending when placement has not been validated.

Use a small vertical set, usually up to three eligible choices including the current selection. Fewer is valid. Preserve card readability instead of fitting every attribute into a compressed tile.

**Disclosed:** full evidence, source/check details and optional explanation. The default card still needs enough evidence for the comparison; a low price alone is insufficient.

**Actions:** select one; use explicit completion for multi-selection if allowed. Consequential cost approval is separate from selecting an attractive Product. Add details can be optional.

**Verification:** exact-variant consistency, source image failure, long titles, named axes, prices/pack implications, selected accessibility state and no fake filler options.

### SCREEN-19 — Numeric or multi-selection clarification

**Task:** provide the particular structured value required by the pending question.

Only render this when the backend/question semantics require it. A count input should name what is being counted. A multi-select should explain the permitted range succinctly when it matters.

Use a stepper or appropriate numeric input for a bounded number; use selectable rows for distinct choices. Keep one question and one completion action.

**Verification:** min/max validation, zero where allowed, long option labels, all options reachable, and no automatic advance before a multi-selection is complete.

### SCREEN-20 — Budget clarification and spending increase

There are two different decisions:

**Missing budget:** ask the person for the whole-room USD ceiling in the ordinary composer flow. Do not prefill an invented amount. Explicit no purchases/$0 is a valid answer.

**Increase approval:** show the current approved limit, proposed limit, resulting purchase total and why the change is requested. State tax/shipping exclusions. Present an explicit approval action and an honest route to retain the current limit or revise the request, using supported question actions.

**Contract:** Skip, silence, closing, selecting a preference or Decide for me cannot approve additional spending.

**Recommendation:** a direct “Keep current limit” decision is clearer than requiring the user to discover rejection through generic options. If the current question protocol cannot represent it, record that gap; do not submit a fabricated approval/answer.

**Verification:** old/new amounts cannot be confused; approval label names the amount/action; decline preserves the ceiling; over-budget candidate never becomes a saved purchase through local UI optimism.

### SCREEN-21 — Protected constraint / infeasible request

**Task:** choose which specific constraint, if any, may change.

Name the conflict in practical terms: blocked access, unsupported placement, a protected Object, a must-have that cannot fit, or insufficient verified alternatives.

Show only the decisions needed to resolve that conflict. Distinguish a suggested optional substitution from a material change to a must-have.

**Actions:** permitted explicit choices, revise in text or leave/cancel as appropriate. Safe refusal must preserve the prior valid state.

**Verification:** Keep, must-have and approved budget are not silently relaxed; the question refers to current identities/evidence; a generic “Make it work” action cannot waive hard constraints.

### SCREEN-22 — Question options and answer revision

**Task:** control participation or leave the current operation.

Show a short list: permitted Skip, Decide for me, Leave for now, Cancel operation and relevant answer history/revision. Only show actions supported by the pending state.

**Semantics:**

- Skip records a skip where allowed.
- Decide for me delegates within approved constraints.
- Leave for now preserves the exact question.
- Cancel operation is explicit and preserves earlier committed results.
- Revision changes decision history through the supported revision flow; it does not race ongoing work.

**Verification:** labels map to distinct actions; backgrounding performs none of them; revision preserves history and valid identities; a question is never answered twice by returning to the page.

## 7. Operations and outcomes

### SCREEN-23 — Preparing / processing / validating

**Task:** understand the actual current phase and retain control over leaving.

Show the reported phase/progress message, concise context and a relevant Room preview when it helps. A spinner can indicate work without claiming a percentage. Details can explain completed/remaining phases only when known.

**Contract:** the pipeline is sequential. No search/spatial work advances behind an unanswered question. Capture completion is not perception completion. A design goal duration is not a failure deadline.

**Actions:** leave for now; explicit cancellation through options. Camera interaction can remain available on a canvas while mutation actions are locked.

**Verification:** queued/running/needs-answer/terminal states are distinct; polling does not steal focus or restart animation; client timeout becomes reconciliation rather than instant failure; earlier saved results remain intact.

### SCREEN-24 — Complete, partially complete, rejected, failed, cancelled

Use outcome-specific content rather than one generic success screen.

| Outcome | Immediate message | Primary next step |
|---|---|---|
| Valid committed Design | Room is ready, with material result context | Explore your room |
| Finalized Product plan only | Products are ready; layout not applied; fit pending | Review Products / return to reconstructed Room |
| Partial successful edit | What changed and what could not change | Return to updated Design; failures accessible |
| No eligible match / rejected request | Practical reason and preserved prior state | Revise request or choose supported recovery |
| Provider/worker failure | Accurate failure and what was retained | Retry/reconcile as supported |
| Cancelled operation | Cancellation confirmed; earlier saved result retained | Return to Room/Design |
| Unusable room boundary after recovery | Why generation cannot continue | Rescan, preserving unrelated completed Rooms |

Do not claim the entire request succeeded when only a subset did. Do not create a new Design for a direct failed Swap. Do not label a Product plan as “Your room is ready.”

**Verification:** the action destination matches the actual result kind; warnings remain visible/reachable; one Undo corresponds to one committed partial-success result; no invented geometry or false finality.

## 8. Committed Design

### SCREEN-25 — Design canvas, panel closed

**Task:** see and refine the saved arrangement.

**Layout:** full available Room canvas, compact Room title/navigation, top-right shopping bag, Items/Undo/Reset View and view options above the scene, floating composer with concise request status/context below.

Items starts closed. No Assistant tab, transcript screen, zoom buttons or Cutaway toggle. A canvas does not need a large page title repeating the Room name.

**Data:** displayed committed Design and its immutable Scene/purchases/evidence. Reopening normally resolves the Room's persisted active pointer, including an Undo-restored parent.

**Selection:** tap highlights the Item and shows selected context; the panel remains closed. Clear selection clears command context. Camera gestures move the view only.

**Busy:** camera remains available; competing edits, Swap/Remove and Undo are locked. Known valid geometry stays visible while work is pending. Adopt committed geometry immediately.

**Verification:** first entry closed; stable-ID selection; selected target after removal clears; keyboard does not hide input; full scene has useful space; bag saves the displayed committed state.

### SCREEN-26 — Items list and selected Item

**Task:** inspect one part of the design or choose an Item to inspect.

**List:** concise rows with recognizable identity, image/representative symbol and necessary status/price. Existing Objects do not receive fictional merchant fields.

**Selected detail:** name, relevant image, price/merchant for a Product, concise actions and disclosure for dimensions/evidence. Details, Swap and Remove are related Item actions; keep their visual hierarchy compact and reflow when needed.

All items returns to list. Close items returns attention to the canvas. Selecting a card highlights the corresponding Item. If a model is selected while the panel is open, reveal its card.

**Removed original Object:** use a clear removed/ghost state and supported Restore action. Removed new Products do not remain visible as purchasable scene entries.

**Verification:** panel scroll reaches every action, including at large text/keyboard sizes; long product names do not hide actions; purchase total is labeled and opens the same save-list flow as the bag.

### SCREEN-27 — Language edit and selected context

**Task:** request a change to the current saved arrangement.

The composer accepts the user's words and optional selected Item identity. The selected context is visible and dismissible, so “move this” has an understandable target.

**Contract:** ambiguous targets become clarifications. Language edits do not show speculative geometry. Current placements remain until an authoritative result; valid partial actions can commit together with failures explained.

**Pending question:** make the current question easy to answer. The composer-first direction should extend consistently to ordinary clarifications; structured/consequential decisions may open dedicated detail.

**Verification:** clearing context preserves text; a stale active revision triggers refresh/resubmission rather than silent application to a different layout; response loss reconciles the same request; rejected edits preserve prior geometry/purchases.

### SCREEN-28 — Undo and view options

These are separate actions with different effects.

**Undo:** available when there is a parent and no competing active mutation. Restores the exact parent, updates active state and remains persisted across reopening. It reverses the complete committed result, not an arbitrary last visual animation.

**Reset View:** changes camera framing only and stays usable while generation/edit operations run.

**View options:** Ghost visibility, design notes and concise gesture guidance. Ghost visibility changes presentation; it does not restore the Object or affect purchases.

**Verification:** repeated camera actions create no versions; Undo does not act while locked; reopening after Undo shows the active parent; no unsupported Redo/history browser appears.

## 9. Product evaluation and direct actions

### SCREEN-29 — Product detail

**Task:** decide whether this Product/offer is suitable.

**Immediate content:** real image/fallback, title, selected variant, checked price, merchant, concise recommendation reason and necessary fit/assumption caveats.

**Disclosed:** dimensions and evidence; alternative Products and merchant offers; full purchase consequences.

**Primary action:** Buy/open the exact selected merchant offer where valid. It is an external handoff, not in-app checkout. Alternate actions should not imply all browsing changes the saved Design.

**Verification:** image/title/dimensions/URL describe the same physical variant; unavailable URL does not become an unrelated search disguised as the selected offer; no price is invented when missing.

### SCREEN-30 — Dimensions and evidence

**Task:** inspect the evidence behind a Product recommendation.

Display labeled Width/Depth/Height or category-appropriate footprint, source link, checked time, original measurement labels/units where helpful, exact-offer details, warnings and pending-fit distinction.

For an unpublished noncritical axis, show “Not published” and the representative-geometry assumption where relevant. For missing critical information, do not imply eligibility. Scores/reasons are ranking judgments; explain uncertainty when comparison evidence is insufficient.

Keep exact variant/offer relationships internally, but raw UUIDs are usually not consumer evidence. A recognizable size/color/model label is more useful.

**Verification:** rug thickness is not presented as published; package measurements are not substituted; opening evidence does not mutate a saved snapshot; long URLs and labels wrap.

### SCREEN-31 — Alternatives and Find more

**Task:** compare eligible alternatives without losing the current selection.

Show the current choice and up to the initial eligible alternatives. Group merchant offers beneath an exact variant rather than duplicating cards. Optional cheaper/style labels must be supported by evidence.

Find more requests new eligible options, preserves old choices and selection, and appends up to the permitted number of unseen results. A smaller/empty result is honest.

**States:** loading, error with retry, eligible options, none found, options stale relative to the current design. A search result is not a committed swap.

**Verification:** selecting for preview is explicit; no candidate replaces the saved Product through search alone; insufficient results do not introduce rejected/unverified placeholders.

### SCREEN-32 — Temporary Swap preview

**Task:** inspect and confirm a specific replacement.

Label Preview/Not saved yet prominently. Show the candidate identity, price consequences and current eligibility/validation state. The preview uses the candidate's verified dimensions at the existing position/orientation.

**Actions:** Use this Product/confirm and Keep saved Product/cancel. While submission is uncertain, reconcile the same request and retain the mutation lock.

**Contract:** the preview does not change active Design, purchases or Undo. Success adopts the authoritative child. Failure/cancellation restores saved geometry. Surrounding furniture is not silently moved to make the preview fit.

**Verification:** save-list bag during a preview still saves the committed version; switching/closing does not create a child; rejected fit preserves saved purchase data; preview text remains visible above the keyboard/panel boundary.

### SCREEN-33 — Remove / Restore

**Task:** decide whether this Item should be removed from the arrangement, or restore a removed original Object through supported behavior.

Name/show the Item and describe the consequence. A kept Object requires explicit unlock. Dependents may need reconsideration; do not promise unsupported objects will remain floating.

**Purchase consequence:** the backend recomputes totals and pack requirements. Do not promise savings equal to a unit price when a pack may still be needed.

**Success:** removed original Object becomes a Ghost where enabled; removed new Product disappears. Clear stale selected context.

**Verification:** safe dismissal preserves state; failed removal retains current placement; result and total update together; restore follows the existing operation/validation rules.

## 10. Saved purchases and sharing

### SCREEN-34 — Save and open shopping list

**Task:** retain the purchases for the displayed committed design.

The bag and purchase total use the same flow. Save one local snapshot for this Room, replacing the older one only after a successful write. Then open the list.

**Allowed source:** committed Design PurchaseSummary, or a finalized imported-room SelectionSnapshot with explicit pending-fit caveat. An incomplete interview, candidate pool or temporary Swap is not a complete list.

**Failure:** show save failure and retry; retain the previous saved list. Do not open a partial snapshot and claim it was saved.

**Verification:** no design version/Undo change; correct displayed version, not merely latest version; invalid purchase data rejected; storage-write failure preserves the old snapshot.

### SCREEN-35 — Shopping list and saved-list index

**List task:** inspect the exact saved purchases.

Show Room name, saved time, purchase lines and overall total. Each line includes Product name, merchant/exact link, purchased pack count, supplied units and paid surplus where applicable, with authoritative saved USD line total. Show approved ceiling and tax/shipping exclusions.

The default view is a compact linked Product row (name, merchant, price), total,
tax/shipping note and Share list. Put the saved timestamp, approved ceiling and
full pack accounting under Details. Show multi-pack quantities and paid extras
in the row when they change what is being purchased. Use a short pending-fit note
instead of a large status banner. Saved-list rows show Room, Product count and
total; timestamps remain available inside each list.

Room fit pending remains visible for a Product-plan list. Saved-price/availability caveats explain the snapshot; do not silently refresh saved amounts.

**Empty:** “Nothing to buy” is a valid result. Existing Objects do not appear as fictional purchases. Do not force sharing of a blank purchase set.

**Saved-list index task:** select a Room's locally saved list. Compact row: Room and count/total. Readable offline without fetching the Room.

**Verification:** app relaunch/offline read, several lists, long purchase titles, paid surplus, zero purchases and saved vs current-version distinction. No offline design editing or sync promise.

### SCREEN-36 — Share preview

**Task:** review what will be exported before invoking a native share destination.

Show the export image, page navigation/count when multiple, essential placeholder/illustrative-position disclosure and the total. Keep full caption/links available in a disclosure.

**Contract:** 1080 × 1350 JPEG, bundled room placeholder, up to four PurchaseLines per image, pagination without dropped purchases, numbered title/pack-count/line-price labels, overall total and tax/shipping exclusions. Pending-fit caveat survives where applicable.

The preview may use fixed graphic typography because it produces a raster artifact; separately verify readability at actual shared-image viewing sizes. The interactive preview controls still follow native text/target rules.

**Recommendation:** keep platform-specific Instagram instructions in a relevant secondary state/disclosure so the first preview screen has a clear export task.

**Verification:** 1, 4, 5 and more purchases; every line exported exactly once in the image set; complete text contains every exact link; labels not represented as actual spatial placements; no private scan photo/geometry/conversation/credentials included.

### SCREEN-37 — Share images & links / Instagram / copy caption

**Share images & links:** opens the native share sheet with images plus the complete shopping text. The user chooses recipient and sends.

**Instagram post:** native image-only share path. Explain that caption transfer may require explicit Copy caption & links. If the extension is unavailable, saving images through the share sheet is the supported fallback.

**Copy caption:** copies only when explicitly activated. Give concise acknowledgement without implying the content was posted.

**Contract:** no automatic send/post, no Meta API requirement, no new public hosted design page. Native sharing/saving remains a real external action even in the UI studio.

**Verification:** inspect prepared payloads without sending to people; cancellation returns to preview; temporary files remain valid during the native handoff and clean up appropriately afterward; exported text retains price/availability/exclusion/pending-fit caveats.

## 11. Reconstructed Room and development surfaces

### SCREEN-38 — Imported reconstructed Room

**Task:** inspect reconstructed context and request the supported planning result.

Use the same room-first shell: scene, Objects access, Reset View, details, floating composer and bag. Label reconstructed provenance and approximate/coarse geometry in relevant details.

**Contract boundary:** original capture/hash/Object bounds can inform planning. Without original native geometry, support and calibration evidence, only a verified Product plan is saved; fit remains pending and layout has not been applied.

The bag is useful after a finalized plan, but an unfinished interview is not a completed shopping list. If unavailable, explain why rather than implying a list was saved.

**Scope caution:** the current bundled Kitchenette entry must be assessed against the production no-sample-room rule. The existence of an imported-context backend path does not automatically authorize a public sample-gallery onboarding feature.

**Verification:** local model remains viewable when backend is unavailable; send failure is actionable; pending-fit language persists into shopping/export; no synthetic placement success appears.

### SCREEN-39 — UI studio and review gallery

**Task:** inspect actual UI states for implementation/review.

The UI studio uses real views with in-memory data and simulated operation outcomes. The browser gallery uses separate mockup code and illustrative data. Label both contexts clearly in review material.

Do not let sample shortcuts define production behavior: fixture Undo is not a test of durable immutable history; sample questions are not proof of adaptive planning; placeholder products are not verified live offers.

The browser gallery's screen picker, board, motion-speed control and preview framing are review tools outside the product viewport. They must not appear in the consumer app.

**Verification:** state inventory covers current behavior, obsolete wizard/Assistant screens are marked historical, and no native share/publish action is exercised accidentally during visual review.

## 12. Shared state transitions

### 12.1 Persistence and authority matrix

| Interaction | Presentation effect | Durable effect | Failure behavior |
|---|---|---|---|
| Orbit/pan/pinch/Reset View | Camera only | None | Preserve current Design |
| Open/close Items, toggle Ghosts | Panel/visibility only | No Design version | Keep room usable |
| Select/clear Item | Highlight/command context | No Design version | Clear stale selection when authoritative removal occurs |
| Type request/answer | Draft | Draft persistence as implemented; no answer until accepted | Retain input |
| Submit answer | Busy then next question/result | Exact operation/question/reply/revision action | Reconcile; do not duplicate |
| Skip/delegate | Question advances when accepted | Explicit recorded action within constraints | Current question remains until resolved |
| Leave/back/close app | Navigation | No implicit answer/cancel/approval | Restore pending work on return |
| Commit edit | New scene displayed immediately | One immutable child and active-pointer update | Preserve valid parent if no commit |
| Partial successful edit | Updated scene plus warnings | One child for valid subset | Explain each failed action |
| Swap preview | Temporary scene | None | Restore committed state |
| Undo | Parent scene | Active-pointer change | Preserve current state until authoritative result |
| Rename Room | Name | Metadata only | Keep draft and existing history |
| Save shopping list | List opens | One local snapshot per Room | Preserve prior snapshot |
| Share preview/cancel | Export UI | No Design/Undo change | Return to local list |
| Confirm Room deletion | Pending then removed | Room cleanup plus local-list cleanup | Visible retryable pending state |

### 12.2 State-completeness checklist

For each changed screen, test the applicable conditions:

- Initial data unavailable.
- Valid populated state.
- Valid empty state.
- Missing optional media/evidence.
- Long text and large values.
- Keyboard open.
- Larger text size.
- Loading that takes long enough to be noticed.
- A request accepted but response lost.
- A known terminal failure.
- A pending question across leaving/reopening.
- Competing operation lock.
- Stale revision/selection.
- Reduced Motion.
- External handoff cancelled.

Use this checklist to choose meaningful fixtures and runtime checks. It is not permission to implement backend behavior that does not exist.

## Integrated reconstruction screens (2026-10-18)

Saved scan has one primary reconstruction action and a secondary Plan changes route into the existing Room review. Actual upload/progress/error state persists; prior successful walkthroughs remain available. Use Inter, RS actions/notices, bright surfaces and purple/gold emphasis from SYSTEM. Keep regenerate/share operations in secondary controls. A new paid generation retains the explicit $10 limit confirmation.

The walkthrough presents the original room, navigation, Reset View, object selection and optional image generation. It exposes no local editing or Undo controls and ignores old local edit files. Design changes open the existing backend flow. The image action is a generated rendition, not a committed Design.
