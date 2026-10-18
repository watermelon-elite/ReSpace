# ReSpace design profile for AI agents

**Purpose:** build new screens and audit existing screens against the same product, information architecture and DreamSeal visual direction.

**Evidence snapshot:** 18 October 2026, from the current working tree, the approved layout gallery, the original DreamSeal references and limited native runtime inspection. This is a design guide, not a claim that every requirement is implemented or device-tested.

Start here. Read the branch-specific references below before designing or changing the corresponding interface.

## 1. Read order and authority

| Your task | Required reading | Completion criterion |
|---|---|---|
| Any screen, navigation or presentation change | This profile, [SPEC](../../SPEC.md), [domain glossary](../../CONTEXT.md) | You can state the user's task, the governing behavior and which state the screen presents. |
| Colors, typography, spacing, imagery, reusable components, animation or accessibility | [Visual and interaction system](SYSTEM.md) | Every visible element has a semantic role and an existing component or justified extension. |
| A particular flow, page, panel, question or error state | Relevant family in [Screen contracts](SCREENS.md) | Entry, visible information, actions, persistence and all applicable failure states are specified. |
| Reviewing the app or verifying an implementation | [Audit playbook and current findings](AUDIT.md) | Findings have source/runtime evidence, user impact, severity and a reproducible acceptance check. |
| Native preview or screenshot work | [UI studio](../ui-studio.md) | You know whether you are observing real data, an in-memory fixture or a browser mockup. |
| Capture, measurement, perception, placement or shopping behavior | The relevant SPEC section and research pointer in [AGENTS](../../AGENTS.md) | You preserve the existing domain contract; visual changes do not invent new backend behavior. |

### 1.1 Resolve conflicts in this order

1. Current explicit user instructions for the task, subject to higher-priority instructions.
2. The governing SPEC for product behavior, API, persistence and domain constraints; CONTEXT for terminology.
3. The user's approved design direction, operationalized by this profile.
4. Shared native presentation components for implementation consistency.
5. Current individual screens as evidence of implementation.
6. Historical mockups, screenshots and older specification drafts as references.

A screenshot is evidence of appearance, not authorization to recreate every control it contains. Existing code can contain a defect. A design recommendation is not permission to change the product contract. When sources conflict, identify the exact conflict and keep unaffected work moving. Never silently update SPEC to make a visual proposal appear already approved.

### 1.2 Evidence labels used throughout this profile

- **Contract:** required by the current SPEC or domain glossary.
- **Direction:** the user's established layout/brand intent, translated into operational design rules.
- **Observed:** present in inspected source or explicitly identified runtime evidence.
- **Recommendation:** a proposed improvement within the existing product. It is not an assertion that the change already exists.
- **Unverified:** a runtime or integration property that still needs testing.

The numerical design values in SYSTEM are a dated snapshot of shared components, with recommendations labeled separately. Read the implementation again before changing a token. The findings in AUDIT are a dated worklist, not a permanent indictment of a file.

## 2. The intended experience

ReSpace helps a person change a real room. The room is the primary object of attention. The interface should let the person scan, describe a change, answer a useful question when necessary, inspect the resulting room and act on a specific Product without first learning a planning system.

The user's central layout instruction is: **one clear thing to do on the screen**. Apply this to cognitive demand, not to a literal count of buttons. A question can have several answer choices. A room can have camera controls and a composer. An approval can have approve and decline. These still serve one task when the hierarchy is unambiguous.

The feeling is calm, direct and personal: generous white space, confident black text, real room imagery, deep purple selections and purposeful purple/gold actions. Warmth comes from the subject matter, spacing and measured use of color. Trust comes from visible consequences and truthful evidence.

### 2.1 Five questions an agent must answer before rendering a screen

1. **What is the person trying to accomplish now?** Write one sentence beginning with a verb: inspect the room, answer the budget question, compare a lamp, recover a saved scan.
2. **What information changes that action?** Keep that information visible. Examples: the current/new spending limit, the selected Item, the precise failure, the fact that fit is still pending.
3. **What can wait until requested?** Sources, extended rationale, instruction history, individual merchant evidence and secondary room controls often belong one level deeper.
4. **What is the one dominant next action?** It may be Send, an answer selection, Scan your room, Explore your room or simply manipulating the room canvas.
5. **What state must survive leaving?** Identify the draft, question identity, operation, selected committed version or local saved list. Navigation must not redefine backend state.

If the first answer needs “and then,” consider separating states. If the second answer contains only decoration, remove it. If the third answer contains a price consequence, permission or hard constraint needed for the current decision, bring it back into view.

## 3. The current journey and superseded concepts

### 3.1 Current journey

~~~text
Supported device
  → My Rooms
  → scan setup and permission
  → native room capture
  → durable finalization / upload recovery
  → measured Room review with a floating composer
  → natural-language request
  → only the clarifications actually needed
  → finalized Product selection
  → room processing, layout and validation
  → committed Design with composer and closed Items panel
  → inspect / edit / compare / buy / save a shopping list
~~~

This is a conditional journey. A Room with an active Design can reopen it. A missing budget produces a clarification before discovery. A no-purchases request can result in a zero-purchase design. A protected requirement can require another decision. An imported reconstructed Room without sufficient placement evidence can produce a Product plan with fit pending, not an applied layout.

### 3.2 Preserve the layout principle while updating the mechanism

| Historical reference | Current interpretation |
|---|---|
| Separate scope, style, budget and optional-notes wizard | Scope and style inferred from the user's request; only missing/ambiguous information is asked. No required mode picker, style form or invented default budget. |
| Always start with priority choice cards | Ordinary planning questions use natural-language replies. The one-question hierarchy survives; preset cards are reserved for justified structured decisions. |
| Three planning questions | Roughly three useful questions is a soft target. Known answers are skipped. It is neither a quota nor a cap. |
| Positive budget required | Explicit $0/no purchases is valid. Missing budget and zero budget are different states. |
| Add 1–5 and redesign 5–20 purchases | Maximums remain 5/20 new Items; neither scope has a purchase minimum. These are backend limits, not a mandatory consumer mode selector. |
| Always-visible Items/Assistant sheet | Items opens on request and starts closed. Design has no Assistant tab or transcript screen. Conversation still persists internally. |
| Selecting a model expands the panel | Selection highlights the model and adds command context. It only reveals a card if the Items panel is already open. |
| Three draggable panel heights | Historical exploration, not the current required interaction. Prefer the current compact toggle panel unless a new decision explicitly changes it. |
| Zoom buttons / Cutaway switch | Native orbit, pan, pinch and Reset View. No zoom-button or Cutaway controls. |
| Solid-purple gallery primary button with gold arrow | Useful historical appearance; native shared primary actions currently use the DreamSeal purple-to-gold/orange gradient with dark text. Follow the shared native component for new native pages. |
| 55 gallery screens | A review inventory of states. It does not require 55 routes, 55 Swift files or a fixed linear funnel. |

This table is a migration guardrail. Do not reconstruct old steps because they are easy to copy from the gallery.

## 4. Information architecture rules

### CORE-01 — One dominant task

Each state must have one concise task statement and one dominant action family. Navigation, dismissal and necessary alternatives may remain, but should not compete visually with the task.

**Pass:** a budget approval shows old limit, proposed limit, resulting total and explicit approval/decline. **Fail:** it also asks style, room purpose and preferred store.

For the room canvas, the dominant task is seeing and changing the room. Items, Undo and Reset View are lightweight tools supporting it. A persistent composer serves that task without turning the screen into a chat feed.

### CORE-02 — Disclose by consequence

Use three levels:

| Level | Purpose | Typical content |
|---|---|---|
| Immediate | Needed to understand or act now | Question; selected target; price; approval consequence; active failure; preview label; pending-fit warning |
| On request | Needed to evaluate or inspect | Product evidence, alternatives, full purchase list, photos, view options, operation details |
| Diagnostic | Needed to troubleshoot implementation | Revision IDs, raw provider messages, capture counters, internal scores/identifiers |

Diagnostic material is not default consumer copy. Retain genuinely useful evidence such as a source URL or a checked date. Remove implementation details that do not improve the user's decision. Do not bury financial or destructive consequences inside a diagnostic disclosure.

### CORE-03 — Give each sentence a job

A visible sentence must identify the task, explain a consequence, report real state or enable recovery. Delete generic welcome copy, duplicate summaries and motivational filler. Titles and labels should carry the interface before helper prose is added.

Use a short title or question, a compact answer/input area and only necessary supporting content. Empty space is acceptable when the task is complete and obvious. If blank space is caused by a fixed-height container that clips essential content elsewhere, it is a layout defect.

### CORE-04 — Preserve the room as context

The native scene occupies the available room-view area. A composer floats above the safe-area bottom and keyboard, without an opaque footer slab. Objects/Items access sits above the scene and opens its contents only when requested.

Product selection, question details and modal evidence may temporarily narrow attention. Return to the same Room and meaningful presentation state. Do not introduce persistent dashboards, metrics, feeds or navigation destinations that distract from the room.

### CORE-05 — Distinguish intent, choice, preview and commitment

Use explicit language and state treatment:

- A planning instruction changes what a future design may do.
- An answer changes a decision revision.
- A Product option is eligible for consideration, not already purchased or placed.
- A Swap preview is temporary.
- A committed Design is an immutable saved result.
- A local shopping list is a saved purchase snapshot.
- A share preview is an export, not a public post.

These distinctions must remain visible at the moment they affect action. A pleasant animation or green check cannot substitute for backend confirmation.

### CORE-06 — Make exits safe and understandable

Back returns within navigation. Leave for now dismisses the screen while preserving a pending operation/question. Cancel operation is an explicit durable action. Discard scan and Delete room are separate destructive actions with their own scopes.

Never make an X button silently answer a question, approve spending or cancel ongoing work. Label icon-only exits for accessibility. Where two exits do the same thing, simplify them without removing a necessary safe path.

### CORE-07 — Keep effort proportional

Ask only for unresolved information that can change the result. Use natural language for ordinary planning. Use structured comparison when exact evidence, consequences or approval make it useful.

Do not force an existing Room through onboarding again. Do not require the person to classify every Object before requesting a design. “Let the design decide” is the default planning instruction.

### CORE-08 — Preserve truthful limitations

Use actual progress, real source/check times and explicit missing evidence. Show fewer eligible options rather than padding a grid. Preserve saved price snapshots. A generic model is representative geometry. A reconstructed scene is not proof of measurement or fit. A placeholder share image is not a render of the user's design.

Treat unsupported certainty as a functional defect, even when the screen looks polished.

## 5. Domain guardrails for design agents

These are UI consequences of the governing contract; consult SPEC for full behavior.

| Concept | Required presentation consequence |
|---|---|
| Object / Item / Product | An Object was observed in the original room. An Item is a design entry. A Product is a purchasable furnishing. Show shopping fields only where applicable. Use familiar labels in consumer copy without merging identities in code. |
| Kept / Fixed | Keep protects position and presence until explicit unlock. Permanent fixtures and other placement constraints are not user Keep preferences. |
| Remove from design | Preserve the original scan. Removed original Objects may become Ghosts; removed new Products disappear. Room deletion is a different operation. |
| Hard requirement | Must-haves, approved spending and spatial constraints cannot be waived by Skip, silence, delegation or an attractive alternative. |
| Budget | USD whole-room purchase ceiling, explicitly supplied/approved. Zero is valid. Show total and tax/shipping exclusions. |
| PurchaseLine | Purchased pack count and supplied units differ from placed Items. Paid surplus remains paid. Read server totals rather than estimating savings in the UI. |
| Exact variant | Image, dimensions, selected offer and link must describe the same physical variant. Merchant duplicates are offers beneath a choice, not extra choices. |
| Verified dimensions | Label fit-critical axes and source. Disclose assumptions. Rug thickness may be unpublished while the published footprint is sufficient; do not invent thickness or claim all axes were verified. |
| Product-verified / placement-validated | Listing evidence makes a Product eligible. Spatial validation establishes placement validity for a particular saved result. Keep the distinction visible. |
| Partial success | Save the valid subset as one child with explicit failed-action warnings. Do not label the entire result failed or imply all requested changes succeeded. |
| Undo | Restores the exact parent through the active pointer. One Undo reverses the entire committed result, including a partial-success command. Camera reset is unrelated. |
| In-flight operation | Lock competing mutations and Undo; retain camera navigation. Losing a response does not prove failure. Reconcile the same identity. |
| Local saved shopping list | One snapshot per Room, replacing only after a successful write. Readable offline, without promising offline design edits or cross-device synchronization. |
| Imported Product plan | Without adequate native placement evidence, show fit pending and layout not applied. Do not render a fabricated committed arrangement. |

## 6. Brand translation

DreamSeal contributes Inter, bright neutral surfaces, deep purple, warm gold, fluid rounded controls and confident typography. ReSpace contributes room photography, measured geometry, practical decisions and Product evidence.

Use these traits together:

| Trait | Observable design decision |
|---|---|
| Calm | One task, limited simultaneous controls, stable layout, predictable exits |
| Personal | The user's Room name and selected Object provide context; copy speaks directly |
| Clear | Black headings, readable secondary text, named dimensions, explicit prices |
| Warm | Room imagery and gold accents, not verbose friendliness |
| Trustworthy | Evidence available one level deeper; uncertainty stated next to the affected claim |
| Tactile | Large rounded actions, clear pressed/selected states, gentle directional transitions |
| Focused | Purple/gold concentrated on action and selection, not every surface |

The original DreamSeal marketing site includes large desktop headlines, decorative glows and promotional content. The internal DreamSeal workspace uses different surfaces. Neither is a template for ReSpace's native screen density. Import the consumer brand vocabulary, not unrelated medical, subscription, business or promotional content.

The user's preference for Inter and purple/gold takes precedence over generic style-catalog advice that bans a font or calls all gradients generic. Judge this product against its chosen system.

## 7. Building a new page: agent execution procedure

### Step 1 — Identify the existing behavior

Read the caller, the state owner, the submitted action and the relevant SPEC section. Record the authoritative data and presentation-only state. Do not infer persistence from a view's local variables.

**Done when:** every action is classified as navigation, presentation, local storage, backend mutation or external handoff.

### Step 2 — Write a screen contract

Use the template in SCREENS. Include entry, task, immediate content, disclosed content, primary action, safe exits, data provenance, states and persistence. Name the existing component family.

**Done when:** loading, empty, failure, interruption and keyboard states relevant to this page have explicit behavior; none is left as “handle later.”

### Step 3 — Simplify at wireframe level

Arrange content without decorative treatment. Give the task the first meaningful position. Move a separate decision to a separate state. Remove redundant prose. Keep material consequences next to their action.

**Done when:** a reviewer can explain what to do from the title, content and primary action alone.

### Step 4 — Apply the shared visual system

Reuse ReSpaceStyle and RS components; use the archetype's spacing and typography. Extend a shared component only when the new behavior belongs to that component and the existing interface cannot express it cleanly.

**Done when:** no local color, radius, button or title style contradicts the shared system without a recorded reason.

### Step 5 — Connect states without changing contracts

Preserve IDs, drafts, locks, payload meaning and authoritative results. Animation surrounds state changes; it does not determine whether an answer was accepted or a mutation committed.

**Done when:** navigation and repeated interaction cannot submit duplicate logical actions or produce a false success state.

### Step 6 — Inspect real output

Use the actual view in the UI studio or the relevant live flow. Inspect the complete screen, long content, errors, keyboard, narrow supported layout and platform accessibility behavior affected by the change. Use static analysis where runtime is unavailable and label it.

**Done when:** all applicable checks in AUDIT have evidence or a precisely stated verification gap. A browser mockup is not a native-device test.

### Step 7 — Report the result

State what changed for the user, what stayed contract-compatible, how it was verified and remaining limitations. Include a source or screenshot for material findings. Do not report a visual review as proof that live scanning, Product verification or persistence works.

## 8. Audit output contract

An audit must produce actionable findings, not a mood board or a generic list of design principles. Each finding contains:

1. Screen and state.
2. Evidence type: runtime, source, specification conflict or unverified risk.
3. Exact source locator or reproducible steps.
4. User consequence.
5. Violated contract/rule.
6. Smallest suitable correction.
7. Acceptance check.
8. Priority and confidence.

Use AUDIT's severity definitions. A low-information screen is not automatically good; it must still explain the decision and recover from failure. A high-information evidence page is not automatically bad; the user explicitly opened it to inspect evidence.

## 9. Scope boundaries

This profile authorizes no new backend capabilities. It guides layout, presentation, copy and behavior already covered by the task and SPEC.

Keep commerce external; keep capture hardware requirements; keep immutable versions and durable operations. Do not add accounts, social feeds, public design hosting, carts, checkout, manual furniture dragging, a history browser, custom voice recording or speculative generation branches as design embellishments.

Preserve normal platform accessibility. The accessibility checks here are ordinary interface quality checks and proposed acceptance guidance; they do not expand SPEC into a separate accessibility-feature project.

The private imported-room implementation and bundled reconstructed-room entry require careful scope review: SPEC allows constrained imported planning context but also excludes sample-room entry and several reconstruction experiences. Do not assume that a bundled demonstration route is approved production onboarding.

## 10. Source provenance and maintenance

### Repository sources

- [SPEC](../../SPEC.md), especially sections 2–6, dimensions in 7.2 and Out of Scope.
- [CONTEXT](../../CONTEXT.md).
- [DesignSystem.swift](../../ReSpace/DesignSystem.swift).
- [ContentView.swift](../../ReSpace/ContentView.swift), [Capture.swift](../../ReSpace/Capture.swift), [RoomViews.swift](../../ReSpace/RoomViews.swift).
- [IntentViews.swift](../../ReSpace/IntentViews.swift), [OperationViews.swift](../../ReSpace/OperationViews.swift), [DesignView.swift](../../ReSpace/DesignView.swift).
- [ProductViews.swift](../../ReSpace/ProductViews.swift), [ImportedRoomView.swift](../../ReSpace/ImportedRoomView.swift).
- [ShoppingList.swift](../../ReSpace/ShoppingList.swift), [ShoppingListViews.swift](../../ReSpace/ShoppingListViews.swift), [ShoppingShareView.swift](../../ReSpace/ShoppingShareView.swift).
- [RoomScene.swift](../../ReSpace/RoomScene.swift), [UI studio](../ui-studio.md), [UIDemo.swift](../../ReSpace/UIDemo.swift).

### Historical design references

The following are local provenance, not required dependencies of this guide:

- DreamSeal consumer brand: /Users/humaid/cpapworld/cpapWebsite/DESIGN.md.
- DreamSeal internal direction: /Users/humaid/DS_HQ/DREAMSEAL.md.
- Approved layout/mockup gallery: /Users/humaid/.codex/visualizations/2026/10/17/01a14bbc-d9b8-7ff1-aab1-f653ca64999c/respace-ui-mockups/.
- Within that gallery: DREAMSEAL_DIRECTION.md, DESIGN.md, onboarding.html, redesign.html, REDESIGN_SCREEN_MAP.md and redesign-screens/.
- The gallery was served at http://127.0.0.1:58051/. A local server address is temporary and is not the durable design specification.

### Updating this profile

When an approved decision changes, update its single governing description and affected screen contract. Update the superseded-concepts table when an old reference becomes dangerous to copy. Resolve or reclassify dated audit findings after inspecting the new source.

Keep design rules separate from product changes. If a proposed improvement changes authorization, persistence, purchases, placement or supported scope, describe the required product decision explicitly instead of labeling it a harmless UI cleanup.

When adding or moving profile documents, update the root AGENTS map in the same change.
