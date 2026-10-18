# ReSpace design audit playbook and current findings

Read [PROFILE](PROFILE.md) for authority, [SYSTEM](SYSTEM.md) for design rules and [SCREENS](SCREENS.md) for the affected state. This document provides a repeatable audit process and a dated assessment of the inspected app.

**Snapshot:** 18 October 2026. Repository base HEAD was 3353be181838559d46c5cb0a5f1e3197de3af1d0, with substantial existing working-tree changes. This is not an audit of that clean commit. Re-read files before acting on a finding.

## 1. Audit procedure for an AI agent

### Step 1 — Establish the current product contract

Read the relevant SPEC section, the screen contract and the code that owns its state/action. Check for a later user-approved change. Identify old mockup assumptions before evaluating the current screen.

**Complete when:** you have a one-sentence task, an authoritative data source and an explicit list of mutations versus presentation actions.

### Step 2 — Inventory states, not just routes

List the visible states reachable from the changed screen: normal, empty, loading, failure, busy, selected, pending question, preview, partial success, destructive confirmation and external handoff as applicable.

**Complete when:** each applicable state has either a fixture/reproduction path or an explicit verification gap. A file with one View can contain many meaningful screens.

### Step 3 — Inspect source before interaction

Follow actions into the existing request/persistence boundary. Check payload identity, selected-target mapping, operation locks and returned state. Read conditional branches for loading and error rendering.

**Complete when:** you know which screen interactions could alter real data, save media, open a merchant or invoke native sharing. Use fixtures for visual work where suitable; do not send/post merely to inspect the share UI.

### Step 4 — Inspect actual rendered output

Use the native UI studio for real SwiftUI layout, and the actual supported-device flow for capture/keyboard/gesture behavior when needed. Use browser mockups to review layout direction only.

Record screen/state, device/window size, text-size/appearance/motion settings if known, fixture/live status and screenshot timestamp. Do not invent missing environment details.

**Complete when:** the main task, last content row, primary action and recovery are actually visible/reachable, or their failure is documented.

### Step 5 — Run the invariant gates

An attractive screen fails if it changes meaning or authority. Evaluate the gate table below before grading aesthetic quality.

**Complete when:** every applicable gate is Pass, Fail or Not verified, with evidence. “Probably” is not Pass.

### Step 6 — Audit information and visual hierarchy

Remove each sentence/control mentally and ask whether the user loses task context, decision evidence, a necessary alternative or recovery. If not, it is a candidate for removal/disclosure.

Then inspect typography, spacing, state indication, image behavior, contrast, keyboard and text scaling. Use SYSTEM's semantic values instead of personal preference.

**Complete when:** every proposed change has a user consequence and fits the existing product scope.

### Step 7 — Prioritize and specify corrections

Use severity and confidence independently. A severe possible risk needs validation; a verified small inconsistency remains small. Separate confirmed source defects from runtime hypotheses and optional refinements.

**Complete when:** each finding includes the smallest correction and a measurable acceptance check.

### Step 8 — Verify the changed area and report limits

After implementation, rerun checks affected by the change, including adjacent states that reuse the component. Use existing tests where behavior changes; avoid a new test framework solely for a cosmetic adjustment.

**Complete when:** the report distinguishes what was fixed, what was tested and what remains unverified. Do not claim live API, RoomPlan, product-evidence or persistence success from fixture screenshots.

## 2. Invariant gates

| Gate | Pass condition | Examples of failure |
|---|---|---|
| G01 — Spending authority | Ceiling is explicit, zero valid, increases explicitly approved | Default budget invented; Skip treated as approval |
| G02 — Protected requirements | Keep/must-have/spatial constraints remain enforced | Generic preference overrides Keep; infeasible requirement silently dropped |
| G03 — Saved truth | Saved, preview, option and plan-only states are distinct | Candidate displayed as committed; placeholder presented as actual room |
| G04 — Operation identity | Repeated delivery/reopening reconciles the same logical action | Double answer; second generation after response loss |
| G05 — Navigation meaning | Leaving preserves work unless explicit cancellation | X cancels; backgrounding skips a question |
| G06 — Version integrity | Edits/Undo follow authoritative immutable version state | Camera reset creates a version; stale edit applies to another parent |
| G07 — Product evidence | Exact variant, source, fit-critical dimensions and offer are consistent | Unlabeled/misleading dimensions; representative mesh treated as proof |
| G08 — Purchase integrity | Server totals, packs and surplus retained | UI subtracts one unit price without pack recomputation |
| G09 — Capture integrity | Interrupted acquisition restarts; completed upload recovers | Continue partial acquisition; unnecessary rescan after completed upload loss |
| G10 — Privacy and external action | Share payload is scoped and user sends | Private scan media or credentials exported; automatic post/send |
| G11 — Supported scope | Production entry/capabilities follow current SPEC | Sample bypass, manual furniture dragging, invented checkout |
| G12 — Recoverability | Failure has an accurate next step and retains valid state | Infinite loading after known error; draft erased on rejection |

These gates summarize UI consequences; SPEC remains the detailed contract. A gate can fail due to misleading presentation even when the backend prevents the actual prohibited mutation.

## 3. Severity and evidence

### Severity

| Priority | Meaning | Response |
|---|---|---|
| P0 — Critical | Unauthorized action, private-data exposure, destructive ambiguity or materially false saved/purchase state | Stop release of the affected path; preserve valid state and fix the cause |
| P1 — High | Core task blocked, governing behavior contradicted, essential evidence/consequence unavailable | Correct before calling the affected flow complete |
| P2 — Medium | Confusion, unnecessary effort, inconsistent state treatment or accessibility/layout weakness | Fix in the relevant interface pass; verify affected states |
| P3 — Low | Cosmetic inconsistency with little task impact | Address with nearby work; do not trigger a broad rewrite |

### Evidence types

- **Runtime confirmed:** reproduced in the actual rendered app with steps and environment.
- **Source confirmed:** directly visible control flow/value in inspected code; runtime manifestation may still need a test.
- **Contract discrepancy:** current source/reference conflicts with governing requirements.
- **Risk to verify:** plausible issue identified from structure, not reproduced.
- **Design recommendation:** a proposed improvement, not a defect claim.

An audit should not turn every recommendation into a P1 bug. It should not downgrade a real authority or data-integrity problem because the screen looks simple.

## 4. Finding template

~~~text
Title: concise user-visible problem
Priority / confidence:
Screen and state:
Evidence type:
Source locator or reproduction:
Observed behavior:
Expected behavior and rule:
User consequence:
Smallest suitable correction:
Acceptance check:
Limitations / dependencies:
~~~

For source locators, prefer file plus symbol and a quoted expression; line numbers drift quickly in this working tree. Include runtime evidence when claiming clipping, gesture failure, incorrect focus or a measured hit-target problem.

## 5. Current assessment

### 5.1 What is already aligned

Preserve these strengths while making improvements:

- Shared DreamSeal colors, Inter, rounded primary actions and focused-page components exist in DesignSystem.
- The primary gradient uses dark labels; replacing them with white would weaken contrast.
- RoomRequestBar supports natural-language automatic-intent requests and pending text-compatible replies.
- DesignView starts with Items closed and does not automatically open it when a model is selected.
- The Design Assistant tab/transcript has been removed, while internal conversation persists.
- Camera tools are separate from edit actions; Undo and mutations have locking paths.
- OperationPanel has an asymmetric vertical transition and a Reduce Motion path.
- ProductDetail exposes dimensions, source/check evidence, uncertainty and pending-fit information in deeper views.
- ProductImage has an unavailable-media fallback.
- Shopping-list and sharing views distinguish saved snapshots, placeholder imagery and native handoff.
- UI studio fixtures render actual native views and separate preview behavior from live backend work.

These observations are not claims that every branch works end to end. They identify existing structure to reuse.

### 5.2 Current findings

#### FIND-01 — Initial Room-review failures can remain invisible

**P1 · High confidence · Source confirmed**

**Source:** [RoomViews.swift](../../ReSpace/RoomViews.swift), RoomReview.body and load().

When page is review and detail is null, the root view shows “Opening your room…”. load() stores failures in error. The visible RSNotice for error is in the non-review RSPage branch. The root canvas does not render that error or an initial-load retry.

**Consequence:** an initial fetch failure can look like endless opening, with no clear recovery on the screen the user entered.

**Correction:** give the review canvas explicit loading, loaded-with-refresh-error and initial-error states. Preserve already loaded geometry on refresh failure; offer Retry and Back for initial failure.

**Acceptance:** fail the first Room fetch and verify error/retry are visible; succeed on retry; fail a later refresh and verify the existing Room remains visible. Do not make the user open options to discover the failure.

#### FIND-02 — The Design scene renderer is constrained to a square

**P1 · High confidence about source; runtime impact needs inspection · Contract discrepancy**

**Source:** [DesignView.swift](../../ReSpace/DesignView.swift), the RoomScene frame uses height min(geometry.size.width, geometry.size.height), followed by a larger outer frame.

**Consequence:** the actual renderer can occupy only a square inside a taller scene region. A broad gray region may look like a full canvas while gesture/geometry space is smaller. This needs runtime confirmation across panel and keyboard states.

**Expected:** SPEC's room-first full available canvas, with scene framing adapted by camera rather than an arbitrary width-based height cap.

**Correction:** evaluate a renderer sized to the available region, retaining camera framing, overlays and safe-area behavior.

**Acceptance:** compare panel closed/open and keyboard states on a tall supported iPhone; verify geometry remains well framed and gestures work throughout the intended scene surface. Do not “fix” this by enlarging furniture or changing saved transforms.

#### FIND-03 — Product-question image failures have no distinct fallback

**P2 · High confidence · Source confirmed**

**Source:** [OperationViews.swift](../../ReSpace/OperationViews.swift), image choice AsyncImage uses the content/placeholder initializer with ProgressView as placeholder. It does not switch over failure state.

**Consequence:** an unavailable image can remain visually indistinguishable from loading. The user is asked to compare a Product without knowing whether the image will arrive.

**Correction:** use a phase-aware fallback, consistent with ProductImage, while retaining title, price and evidence. Do not mark the Product out of stock because its image failed.

**Acceptance:** valid URL, failed URL and missing URL all produce stable readable choices; selected state and answer action remain usable.

#### FIND-04 — Several compact dimension displays omit axis labels

**P1 for evidence used to choose a Product; P2 for secondary summaries · High confidence · Source confirmed**

**Sources:** [OperationViews.swift](../../ReSpace/OperationViews.swift) choice metadata, [ProductViews.swift](../../ReSpace/ProductViews.swift) alternatives, [RoomViews.swift](../../ReSpace/RoomViews.swift) Object summary and [DesignView.swift](../../ReSpace/DesignView.swift) Item details.

Several summaries join dimensions with multiplication signs without naming width/depth/height. ProductEvidence already supplies named axes and handles unpublished assumptions more carefully.

**Consequence:** a compact comparison can be read in the wrong order even though the expanded evidence is accurate.

**Correction:** use a shared concise axis-labeled presentation, preserving units and assumed/unpublished axes. A footprint-only category should not acquire a falsely verified height.

**Acceptance:** furniture and rug fixtures show understandable axes in both compact and expanded views; the same variant/data is used in each.

#### FIND-05 — Design-edit clarification uses a different input path

**P2 · High confidence about structure; flow parity needs validation · Contract discrepancy to review**

**Sources:** [IntentViews.swift](../../ReSpace/IntentViews.swift), RoomRequestBar.canReply; [DesignView.swift](../../ReSpace/DesignView.swift), composer and locked.

RoomRequestBar can send text-compatible replies to a pending question. DesignView disables its composer while locked and sends the user through OperationPanel via “Answer a question to continue.”

**Consequence:** initial planning and later edit clarification may feel like different products, and the floating composer cannot always perform the ordinary reply the current direction calls for.

**Correction:** assess reuse of the existing pending-reply behavior for ordinary Design clarifications, while preserving mutation locks and structured approval screens. Do not simply enable a second chat mutation during an active operation.

**Acceptance:** an edit that needs an ordinary clarification accepts the reply against the exact pending question; no competing operation is created. Budget/protected decisions retain explicit controls.

#### FIND-06 — Fixed Items-panel heights need text-size and keyboard validation

**P2 · Medium confidence · Risk to verify**

**Source:** [DesignView.swift](../../ReSpace/DesignView.swift), 270/330 pt panel baselines, 80% geometry cap and clipped parent.

**Consequence:** larger text and a keyboard may leave little room for the panel body, selected actions or composer. Source structure alone does not prove clipping.

**Correction if reproduced:** let content and available height drive the panel constraint, preserve a scrollable body and reflow action groups. Keep the normal state compact.

**Acceptance:** every selected Item action and the composer remain reachable with large text and keyboard visible; no zero-height body or nested-scroll trap.

#### FIND-07 — A spending increase lacks a direct visible “keep current limit” path

**P2 · High confidence about current controls · Design recommendation**

**Source:** [OperationViews.swift](../../ReSpace/OperationViews.swift), budget question footer.

The primary action is approval, with generic Skip only when permitted and other controls in question options. There is no dedicated current-limit choice in this view.

**Consequence:** a person who declines extra spending may need to infer which secondary action preserves the current budget.

**Correction:** expose a clear supported decline/revise path. First verify the question action contract can represent it; do not invent a backend answer or use Skip to approve anything.

**Acceptance:** both approval and refusal have understandable consequences; leaving is still distinct from answering; refusal never raises the stored ceiling.

#### FIND-08 — Product image choices need explicit selected semantics

**P2 · Medium confidence · Source gap; runtime verification required**

**Source:** [OperationViews.swift](../../ReSpace/OperationViews.swift), custom image-choice buttons, compared with RSChoice in [DesignSystem.swift](../../ReSpace/DesignSystem.swift).

The image branch shows a checkmark when selected but does not explicitly apply the selected accessibility trait used by RSChoice.

**Consequence:** accessible selection feedback may be inconsistent between text and image choices.

**Correction:** give both variants equivalent selection semantics and a coherent card label/value.

**Acceptance:** VoiceOver/accessible inspection communicates which image choice is selected without reading decorative duplicate content. Verify actual behavior before declaring a runtime failure.

#### FIND-09 — Full-page question animation needs focus and input-lock verification

**P2 · Medium confidence · Risk to verify**

**Source:** [OperationViews.swift](../../ReSpace/OperationViews.swift), formIdentity transition on the RSPage, and [DesignSystem.swift](../../ReSpace/DesignSystem.swift), title focus on appearance.

The full page transitions, including navigation/footer, and uses one duration for incoming/outgoing content. Busy guards concern submission, but animation overlap/focus behavior was not demonstrated.

**Consequence:** navigation chrome may move unnecessarily; outgoing controls could remain accessible during transition; focus could fail to reach the new question or interrupt composer continuity.

**Correction if reproduced:** stabilize persistent chrome, ensure only the current question is interactive/accessibility-visible and coordinate focus after identity changes. Preserve Reduce Motion.

**Acceptance:** repeated fast answers, Back/revision, slow response and reduced motion produce one active question and one submission; screen-reader focus reaches the intended new content.

#### FIND-10 — Share preview presents several destination-specific instructions at once

**P2 · High confidence about content · Design recommendation**

**Source:** [ShoppingShareView.swift](../../ReSpace/ShoppingShareView.swift), preview content and three footer actions.

The image preview, caption disclosure, placeholder explanation, Instagram instructions and Share/Instagram/Copy actions are all part of the initial page.

**Consequence:** this late-stage task becomes denser than the rest of the one-task flow.

**Correction:** retain the essential placeholder/pending-fit explanation, make Share images & links dominant, and disclose destination-specific guidance when relevant. Keep the existing export functionality.

**Acceptance:** a person can identify the ordinary share action immediately; Instagram fallback and explicit copy remain discoverable; no required export caveat is hidden from the review.

#### FIND-11 — Internal diagnostics leak into consumer-facing surfaces

**P2 · High confidence · Source confirmed; presentation recommendation**

**Sources:** capture Stored/Pending counters in [Capture.swift](../../ReSpace/Capture.swift); raw selected-variant identifier in [ProductViews.swift](../../ReSpace/ProductViews.swift); backend configuration in [ContentView.swift](../../ReSpace/ContentView.swift).

Some details are useful for development but add little to the consumer's current decision.

**Correction:** retain useful sources, dates and measured facts; place opaque IDs and implementation diagnostics in an appropriate troubleshooting context. Review release setup separately rather than deleting a required connection capability.

**Acceptance:** the default flow uses task language; diagnostic access remains available where required; exact-variant identity continues to exist internally.

#### FIND-12 — Imported-room production entry needs an explicit scope check

**P1 scope review · High confidence about source condition · Contract discrepancy**

**Sources:** [ContentView.swift](../../ReSpace/ContentView.swift), bundled ImportedRoomView.modelURL entry outside the demo path; [ImportedRoomView.swift](../../ReSpace/ImportedRoomView.swift); SPEC 2.4 and Out of Scope.

Current SPEC permits private imported reconstructed context with constrained Product-plan output, but excludes sample-room entry and broad reconstruction features. The bundled Kitchenette route may be available in a non-demo build when the asset exists.

**Consequence:** a development/test asset could become a production onboarding path that appears more generally supported than the contract permits.

**Correction:** establish the intended release exposure and label/gate the route accordingly. Preserve the approved imported-plan evidence restrictions. Do not remove the capability solely because the older gallery lacked it.

**Acceptance:** build configuration and runtime entry match the approved scope; plan-only results never claim applied layout; unsupported devices do not gain an unintended sample bypass.

#### FIND-13 — Historical gallery is now behaviorally stale

**P1 for future implementation guidance · High confidence · Reference discrepancy**

The 55-state gallery still includes the explicit scope/style/budget wizard, mandatory positive budget assumptions, an Assistant tab and old panel/camera controls.

**Consequence:** an agent copying the gallery can regress current approved behavior while believing it is following the design.

**Correction:** treat PROFILE's superseded-concepts table and current SPEC as authoritative. On the next gallery update, visibly mark historical states and add current composer/panel/list/share coverage.

**Acceptance:** new pages follow current behavior while retaining the approved information rhythm; a review board never presents obsolete states as the required production journey.

#### FIND-14 — Small shared-control inconsistencies remain

**P3 · High confidence about source; target size requires measurement**

- The shopping-bag gradient direction differs from SPEC's gold-to-purple wording.
- The compact Saved design navigation link in RoomReview does not explicitly establish the shared 44 pt minimum hit area.
- OperationPanel text validation uses nonempty text; the shared composer trims whitespace for send eligibility.

**Correction:** resolve the bag-specific direction consistently, measure/adjust the Saved design target and align whitespace eligibility without changing answer semantics.

**Acceptance:** bag treatment matches the approved direction; the link has a usable target; whitespace-only text cannot trigger an avoidable invalid submission.

## 6. Recommended correction sequence

1. Resolve the source-confirmed initial-load recovery issue and verify the full scene area.
2. Clarify active-question reply paths, labeled measurements and Product image failure states.
3. Validate keyboard/text-size/focus behavior on the actual native views.
4. Refine budget refusal and share-preview disclosure within existing contracts.
5. Confirm production exposure of the reconstructed-room route.
6. Update historical gallery guidance and address small shared-control inconsistencies.

This is an audit recommendation, not an implementation plan already executed. No app/backend fixes were made while writing this profile.

## 7. Verification matrix

Use the rows relevant to the change. A full app audit should cover all applicable families.

| Scenario | Expected invariant | Best evidence |
|---|---|---|
| Empty library / fetch error | Empty and error distinct; scan/retry clear | Native fixture + injected API failure |
| Camera denied / unsupported | Different explanation and recovery | Supported device + permission state; gate fixture |
| Interrupted acquisition | Fresh scan required | Physical supported device |
| Completed upload response lost | Same completed capture recovers | Existing recovery integration tests + device |
| Complete initial request | No redundant wizard | API/operation fixture + native UI |
| Missing budget / $0 request | Clarify missing; accept explicit zero | Contract tests + UI |
| One question / long question | One active decision; full text reachable | Native fixture |
| Text/image/multi/numeric answer | Appropriate control and valid submission | Fixtures + action assertions |
| Budget approval/refusal | Explicit authority preserved | Payload/operation assertions + UI |
| Leave/reopen question | Exact identity restored | Persistence/integration check |
| Response loss/retry | No duplicate logical action | Existing idempotency tests |
| Panel closed/select model | Context appears; panel stays closed | Native UI |
| Panel open/select card | Scene and card share stable Item ID | Native UI + source |
| Keyboard and large text | Composer/actions accessible | Native runtime |
| Reduced Motion | No large spatial transition | Native runtime |
| Image failure | Honest stable fallback | Failed-media fixture |
| Partial successful edit | One child, explicit failures, one Undo | Backend tests + native result |
| Failed direct Swap | Saved state unchanged; no child | Backend tests + preview UI |
| Save list during preview | Committed version saved | Local storage/payload test |
| Paid surplus / zero purchases | Correct authoritative totals/empty state | Purchase fixtures |
| Five or more export lines | Pagination drops none | Rendered JPEGs + text inspection |
| Share cancellation | No send/post; return safe | Native share preview, without sending |
| Imported plan-only result | Fit pending through list/export | Fixture + operation contract |
| Delete pending | Visible retry, no late resurrection | Existing deletion tests + UI |

Do not add brittle screenshot tests for every reversible spacing change. Test state transitions and invariants when code changes them; inspect visual output for layout. Reuse existing test/preview infrastructure.

## 8. Optional quality scoring

Scoring can help compare revisions, but cannot override a failed invariant gate.

Rate each applicable axis 0–3 with one sentence of evidence:

- **Task clarity:** can the next useful action be identified?
- **Information hierarchy:** is essential context visible and secondary detail disclosed?
- **Visual consistency:** do shared tokens/components form a coherent page?
- **Interaction continuity:** do input, motion, navigation and selection preserve context?
- **State completeness:** do busy, error, empty and uncertain states remain usable?
- **Evidence honesty:** are saved/preview/verified/pending distinctions accurate?
- **Platform behavior:** are text, focus, touch, keyboard and reduced motion preserved?

0 = absent/broken; 1 = substantial friction; 2 = usable with local issues; 3 = clear and verified for the inspected state. Mark untested axes Not verified rather than assigning a flattering average.

## 9. Evidence coverage and limits of this profile

### Inspected

- Current governing SPEC sections for navigation, requests, questions, design, operations, products, sharing, dimensions and scope.
- Canonical domain terminology.
- Current native presentation source across the screen families in SCREENS, including shared components, composer, operation panel, Design, Product evidence, capture UI, reconstructed-room view, shopping and share preview.
- UI studio source/documentation to distinguish fixture behavior from production.
- Original DreamSeal consumer/internal direction and local gallery documentation.
- Historical gallery images for the empty-room and priority-question compositions.
- A native simulator Ready-state screenshot showing the shared title, white space, purple/gold primary action and safe return. Simulator window identified iPhone 17 Pro / iOS 26.1. The displayed outcome was preview content, not a verified live generated room.
- Source-derived rounded color contrast calculations.

### Not demonstrated by this work

- A complete click-through of every native state or the current browser gallery.
- Fresh physical-device capture, backend generation, live Product verification or solver outcomes.
- VoiceOver, larger text, reduced-motion runtime behavior, every keyboard state or measured touch bounds.
- Persistence/idempotency, upload recovery, deletion, purchase correctness or real external sharing end to end.
- Dark-mode or iPad acceptance.

The audit findings explicitly distinguish source evidence from these runtime gaps. The existing browser verification files concern the historical mockup, not the native implementation.

### Source fingerprints

These SHA-256 prefixes identify the inspected bytes for important files. They are traceability markers, not version-control replacements.

| File | SHA-256 prefix |
|---|---|
| SPEC.md | fe9cc2947606cd35 |
| ReSpace/DesignSystem.swift | 1d157408e133dd3e |
| ReSpace/IntentViews.swift | 7896a8a663f3eb40 |
| ReSpace/OperationViews.swift | a006d874e34ccd6e |
| ReSpace/DesignView.swift | 9c94ace16431d37b |
| ReSpace/ProductViews.swift | 232073a07f1e38ce |
| ReSpace/RoomViews.swift | 0978d5d648251bc7 |
| ReSpace/ShoppingShareView.swift | 4f7417c99b3330a5 |

If a fingerprint differs, inspect the new source before carrying a finding forward. Update this dated section when conducting a new audit; keep enduring design rules in PROFILE/SYSTEM/SCREENS.
