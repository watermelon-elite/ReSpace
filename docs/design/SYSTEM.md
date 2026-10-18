# ReSpace visual and interaction system

Read [PROFILE](PROFILE.md) first for authority, current product direction and superseded mockups. This reference defines how the interface should look, move, read and respond. Read [SCREENS](SCREENS.md) for where these components belong.

Values marked **Observed** describe the inspected native implementation on 18 October 2026. **Direction** describes the intended design. **Recommendation** identifies an improvement or acceptance target, not an already implemented feature.

## 1. Visual composition

### VIS-01 — Bright, quiet base

Use white for focused task pages and Product surfaces. Use a near-white lavender canvas around room controls and quiet supporting regions. The 3D renderer currently uses a neutral gray background; treat this separately from page chrome.

Allow black text and the Room/Product image to establish hierarchy before adding color. Reserve larger colored areas for primary actions, selected choices and relevant notices. Large brand gradients behind forms or room geometry would obscure the task.

An ordinary page should read in this order:

1. Navigation/context.
2. Task title or question.
3. The content needed for that task.
4. Primary action.
5. Optional or secondary actions.

The room canvas has a different hierarchy: Room, selected context/status, composer, then compact tools. Do not force a large page title or hero card above a canvas that already communicates the task.

### VIS-02 — Use white space to separate decisions

Whitespace is an information boundary. A clear gap between a heading and its answers makes the question easier to parse. Space between sections should exceed space within a section.

Do not fill unused space with slogans, decorative statistics, repeated instructions, branded badges or large icons simply to balance a screenshot. Conversely, avoid centering all content vertically by default: the user should find the title and actions in predictable locations.

On compact or keyboard-visible screens, yield decorative space first. Preserve readable text, controls, the active question and relevant consequences.

## 2. Semantic color registry

**Observed source:** [ReSpaceStyle in DesignSystem.swift](../../ReSpace/DesignSystem.swift). Hex values below are rounded equivalents of the source RGB values; the source values remain authoritative.

| Role / current symbol | Approximate color | Intended use | Misuse to reject |
|---|---|---|---|
| ink | #1A1A1A | Titles, primary body text, important values | Pure-black text plus many competing accent colors |
| secondary | #615B69 | Explanations, merchant, dates, supporting labels | Treating essential consequences as faint decoration |
| purple | #6A0DAD | Selected state, accent icons, secondary actions, links | Coloring every paragraph purple |
| gold | #E6C46A | Small warm accent, brand detail | Small gold text on white |
| actionInk | #120C17 | Text/icons over the action gradient | Replacing with white without measuring contrast |
| actionGradient start | #8B5CF6 | Bright violet end of primary action | Using it alone as a small-text color on white |
| actionGradient end | #F59E0B | Warm gold/orange end of primary action | Treating it as warning status |
| wash | #F3EBFA | Selected option fill, selected-target context | Large blocks of low-contrast purple text |
| canvas | #FAF8FC | Quiet page/support surface | Assuming it is the 3D renderer background |
| line | #E7E0EB | Decorative dividers and quiet grouping borders | Sole indicator of an essential control boundary/state |
| danger | #A12D46 | Destructive action, error text/icon | Decorative emphasis unrelated to error/destruction |
| white | #FFFFFF | Focused page and content surfaces | White body text over the full action gradient |

**Observed gradient:** top-leading to bottom-trailing, from bright violet to warm gold/orange. Primary buttons, send controls and prominent icon buttons share it.

**Contract exception:** SPEC describes the shopping-bag treatment as gold-to-purple. The shared component currently uses purple-to-gold. Track this as a small directional discrepancy; a page agent should not silently reverse every primary button to resolve a bag-specific requirement.

### 2.1 Contrast evidence

The following calculations use rounded sRGB hex values, the standard relative-luminance formula and opaque backgrounds. They are local calculations, not screenshot measurements or a full accessibility certification.

| Pair | Approximate contrast | Design consequence |
|---|---:|---|
| ink on white | 17.40:1 | Strong text baseline |
| secondary on white | 6.55:1 | Suitable supporting text baseline |
| purple on white | 9.24:1 | Strong accent text |
| purple on wash | 7.95:1 | Suitable selected-state text |
| danger on white | 7.05:1 | Strong error/destructive text |
| actionInk on violet gradient endpoint | 4.55:1 | Narrow normal-text margin; preserve the dark label |
| actionInk on warm gradient endpoint | 8.96:1 | Strong label contrast |
| white on violet gradient endpoint | 4.23:1 | Below the normal-text threshold |
| white on warm gradient endpoint | 2.15:1 | Insufficient for normal or large text |
| gold on white | 1.68:1 | Decorative accent only in this pairing |
| line on white | 1.29:1 | Quiet separator, not sufficient sole control-state signal |
| older DreamSeal #8A8A8A muted text on white | 3.45:1 | Do not copy into normal small body copy |

A 1,001-sample linear sRGB interpolation of the rounded gradient had minimum actionInk contrast approximately 4.55:1. Actual rendering, transparency, pressed states and overlays still need inspection. Avoid reducing enabled label opacity or lightening actionInk; the violet end has little spare margin.

For audit thresholds, use at least 4.5:1 for ordinary text and 3:1 for large text under WCAG's definition; placeholder text is text, too. These thresholds come from [W3C's text-contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

Required control graphics and state indicators need sufficient contrast with adjacent colors; use 3:1 as the audit threshold where applicable. A decorative divider is not automatically an essential boundary. See [W3C's non-text contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html).

### VIS-03 — Encode state with more than hue

Selected choices use a checkmark and selection semantics in addition to purple fill/border. Errors name the failure and offer recovery. Temporary previews carry the word “Preview.” Disabled actions expose their disabled state; when the reason is not obvious, place a short explanation nearby.

Gold is a brand accent, not “success.” Purple is a brand/selection color, not proof of a valid result. Do not create status semantics by hue alone.

### 2.2 Appearance modes

The inspected design and UI studio are light-first. This guide does not claim a completed dark-mode system. For a task that must support another appearance, define semantic surface/text pairs and verify them deliberately. Do not mix automatically inverted system colors with hardcoded white controls and assume the result is complete.

## 3. Typography

### 3.1 Family and scale

**Observed:** bundled InterVariable, registered through CoreText, with SwiftUI custom fonts using relative text styles. Preserve [the bundled font license](../../ReSpace/Resources/Inter-LICENSE.txt).

| Role | Current size / weight | Usage |
|---|---|---|
| Focused page title, RSTitle | 34 pt semibold; tracking -1.4; relative largeTitle | One task or question, leading aligned |
| Selected Item title | 22 pt semibold | Item panel detail heading |
| Product price | 24 pt in Product detail | Price close to merchant/variant |
| Shopping purchase title | 18 pt semibold | Purchase-line identification |
| Primary choice/row title | 16 pt medium | Answer and navigation labels |
| Standard prose | Approximately 16 pt baseline | Short explanatory text |
| Action label | 15 pt semibold | Primary/secondary button |
| Message/body detail | 15 pt | Compact response or message |
| Top bar title | 14 pt semibold | Persistent context, normally one line |
| Notice / key-value / composer text | 14 pt | Supporting information and input |
| Subtitle / merchant / date / context | 13 pt | Secondary identification |
| Compact feedback / evidence time | 12 pt in some current views | Audit carefully; important warnings need readable prominence |

These are current native values, not a mandate to shrink all new body text to fit. Reuse the appropriate semantic role. If a role consistently requires larger text for readability, improve the shared role instead of adding unrelated sizes to individual pages.

### TYPE-01 — Preserve hierarchy under wrapping

Use sentence case, a clear weight difference and consistent alignment. A short title may occupy two lines. A long server question must remain readable rather than shrink to one line.

Keep product names and user-entered Room names intact where the decision depends on them. A compact top bar can truncate a long Room name if its full value is available in an appropriate detail view; a confirmation must identify the target sufficiently.

Avoid all-caps paragraphs, wide letter spacing, decorative serif substitutions and gradient-filled headings. The visual identity comes from Inter, scale and composition.

### TYPE-02 — Scale text through layout

Support normal platform text scaling. Use minimum heights, flexible vertical stacks and scrolling. At larger sizes, allow rows to become taller, key-value values to wrap and action groups to stack vertically.

Do not reduce font size, cap Dynamic Type or clip a question to preserve the exact screenshot height. Display titles can lose some negative tracking at large accessibility sizes if testing shows collisions. This is a recommendation for adaptive refinement, not a currently centralized implementation.

For numbers, retain meaningful precision: prices follow authoritative money formatting; measurements retain meaningful units/axes; counts distinguish packs, supplied units and placements. Do not turn missing values into zero.

## 4. Spatial rhythm and geometry

### 4.1 Current baseline

| Element | Observed baseline |
|---|---|
| Focused page horizontal content/footer gutters | 24 pt |
| Top bar horizontal gutter | 16 pt |
| Top bar vertical padding | 8 pt |
| Top-bar action area | 44 × 44 pt |
| Standard page top padding | 16 pt |
| Question page top padding | 56 pt |
| Page content stack gap | 24 pt |
| Page bottom padding | 24 pt |
| Footer padding | 24 horizontal, 12 top, 16 bottom |
| Footer action gap | 8 pt |
| Choice internal padding | 18 pt |
| Choice gap / content group gap | Commonly 16 pt |
| Row vertical padding | 18 pt |
| Primary button minimum height | 56 pt |
| Compact/quiet action minimum height | 44 pt |
| Choice minimum height | 80 pt |
| Navigation row minimum height | 64 pt |
| Composer send action | 44 × 44 pt |

Spacing is currently expressed as repeated values, not a fully centralized spacing-token enum. Do not claim otherwise.

**Recommendation:** reason with semantic gaps: 4–8 within a small label/value group; 12–16 between related elements; 24 between sections; 40–56 for deliberate question breathing room when height permits. Reuse the existing component's value before introducing another. These are defaults, not a rigid grid that overrides readable content.

### 4.2 Radius vocabulary

| Shape | Current role |
|---|---|
| Capsule | Primary and secondary actions; compact scene tools |
| Circle | Icon button, send action, trailing primary arrow |
| 14–16 pt radius | Small Product media, notices, inputs, selected context |
| 20 pt radius | Choice cards, symbol tile, user message bubble |
| 24 pt radius | Compact Items panel |
| 28 pt radius | Larger imagery, room preview, composer outline |

Do not assign the same large radius to every rectangle. A card is a bounded selectable object; a simple informational list can use rows and dividers. Avoid nested rounded cards unless each boundary has a real interaction or grouping purpose.

### 4.3 Borders and elevation

Use light 1 pt separators for grouping. Selected choices use purple and a checkmark. RSChoice currently has a very soft purple shadow, approximately 4% opacity, radius 8 and y-offset 3.

Keep shadows subordinate to content. Avoid heavy drop shadows, glowing borders and frosted-glass stacks as a default. Platform material can be appropriate over active camera content when needed to preserve legibility, but a persistent opaque footer behind the Room composer conflicts with the current layout direction.

### LAYOUT-01 — Adapt to available space, not a single screenshot

Use available safe-area width and height. Layouts must accommodate the keyboard, long text and larger platform text sizes. At narrow widths, stack image/text choices if the text column becomes unreadable. Keep natural scrolling for long evidence.

Recommended review widths for browser artifacts are 320, 375, 390 and 414 CSS px; wider gallery layouts are review tooling, not proof of iPad support. For the native app, test actual supported iPhone layouts and simulator sizes applicable to the change. The product's unsupported-device gate is not permission for broken preview layouts.

### LAYOUT-02 — Use two footer models deliberately

**Focused task page:** an RSPage safe-area footer can hold a full-width dominant action, with a secondary/quiet alternative underneath. White backing is appropriate here so content cannot obscure the action.

**Room canvas:** the composer floats over the scene above the bottom safe area and keyboard. Its own rounded input surface provides legibility. Do not attach the focused-page white footer slab to the entire canvas bottom.

Always reserve enough content space or scrolling reach so the last item remains accessible above the footer. Avoid using a fixed device height.

## 5. Component contracts

### 5.1 RSPage and RSTopBar

**Purpose:** focused task/evidence/navigation pages.

- RSTopBar carries Back, optional context title and one trailing action. Icon controls have descriptive labels.
- RSTitle states the task. Question mode creates extra space above it at normal sizes.
- Content scrolls vertically; footer actions remain reachable.
- Native navigation chrome is hidden because the component supplies its own; this creates responsibility for equivalent Back/dismiss semantics.
- The title is marked as a heading and receives accessibility focus on page appearance.

**Audit:** duplicated Back and Close actions; a top title repeating the large title without adding context; fixed blank space that crowds inputs above the keyboard; focus not reaching a changed question; absent recovery in the root canvas branch.

**Extension rule:** add a semantic parameter only when multiple screens need the same behavior. Do not create a generic layout engine for one exceptional screen.

### 5.2 RSButtonStyle

**Primary:** gradient capsule, dark actionInk label, 56 pt minimum height, semibold 15 pt label, trailing arrow inside a pale circle. Full-width use is the standard focused-page action.

**Secondary:** white surface, purple label, quiet border. Use for a meaningful alternative within the same task.

**Quiet:** reduced visual weight, generally 44 pt minimum. Use for Skip, safe navigation or secondary tools.

**Danger:** danger background and white label for a deliberate destructive action when appropriate. Explain scope immediately above.

**Observed states:** pressed opacity approximately 0.72; disabled opacity approximately 0.45. The enabled and disabled semantics must match actual action availability.

**Rules:**

- One visually dominant primary per focused task; a necessary negative answer is still visible and reachable.
- Use an action label, not “Submit” when a more specific verb exists.
- Loading replaces/augments the action's state while keeping its dimensions stable.
- A tap is accepted once; disable repeated logical submission while awaiting acknowledgement.
- Long labels wrap or adapt; the arrow cannot cover text.
- Do not use the gradient for ordinary text links, every row or destructive emphasis.
- Explicit approval labels name the approved action or amount. A generic Continue is insufficient for a spending increase.

### 5.3 RSIconButton and scene tools

44 × 44 pt hit area, approximately 19 pt symbol. Prefer SF Symbols for native consistency; label the action semantically for assistive technology.

Reset View affects camera framing. Undo affects the active committed version. Bag saves/opens a purchase snapshot. These actions cannot share a generic label such as “More.”

Leave enough separation to prevent accidental adjacent taps. When a symbol is unfamiliar, provide a visible text label or a suitable explanatory context. The user should not need to infer Product purchase behavior from a decorative bag alone.

### 5.4 RSChoice

Use for a single structured selection, protected instruction or meaningful option. It is not the default replacement for every conversational answer.

Observed anatomy: optional 28 pt symbol slot, 16 pt medium title, optional 13 pt subtitle, selection indicator, 18 pt padding, 80 pt minimum height, 20 pt radius.

Keep the whole card tappable. Selected state uses purple/wash/checkmark and the selected accessibility trait. A subtitle explains a real distinction; omit it when the title is sufficient.

Single-choice selection may advance after visible acknowledgement for low-consequence questions. Multi-choice requires an explicit completion action. Budget increases, destructive operations and consequential consent require explicit action even when a choice has been selected.

When a Product image is involved, preserve title, merchant, exact variant and price implications. Use the dedicated Product comparison composition rather than forcing a long listing into an 80 pt generic card.

### 5.5 RSRow and RSKeyValue

RSRow is navigation or a compact entity entry: leading symbol/media, title, optional subtitle, trailing directional affordance and quiet divider. Plain information should not show an arrow implying an action.

RSKeyValue communicates a fact. Use readable labels such as Width, Depth, Height, Purchased packs, Supplied units and Paid surplus. At larger sizes, place value below label if necessary.

Avoid unlabeled measurement triples. “120 × 60 × 75 cm” is ambiguous unless the axis order is explicitly stated. Prefer “W 120 · D 60 · H 75 cm” in compact space and separate labeled rows in evidence.

### 5.6 RSNotice

Use for a current limitation, error or consequence. Pair a concise statement with the next available recovery when applicable. Keep essential notices beside the affected content/action.

Examples:

- “Room fit is still pending.”
- “Your scan is on this phone. Reconnect to finish saving it.”
- “The chair could not move without blocking the doorway.”

Do not stack success, info, warning and promotional notices above one task. Resolve redundant state messages into one accurate statement. Raw internal exceptions should be translated into actionable user language while diagnostic detail remains accessible where useful.

### 5.7 RSComposer and RoomRequestBar

Observed composer: rounded white input with a border, vertical text field spanning one to four lines, 44 pt gradient send control, optional selected-target context above with a clear action. It remains editable while Send may be disabled.

**Direction:**

- Initial request and ordinary clarification use the same interaction model.
- Keep the target explicit when a selected Object/Item changes what “this” means.
- Clear selection without deleting the draft.
- Preserve drafts across navigation and submission failure.
- Trim whitespace for send eligibility.
- Empty input does not show an active send affordance.
- Show concise actual progress, error or pending-question feedback above the composer.
- Keep relevant feedback legible; do not truncate the actionable part of a failure.
- Allow platform keyboard dictation; do not invent a microphone recording feature.
- The input remains above the keyboard. Context and question must not be hidden behind it.
- A busy operation can disable Send while preserving draft composition, except when the current operation explicitly accepts the pending reply.

RoomRequestBar already routes supported pending clarifications through the request composer. DesignView currently exposes pending-operation detail separately and disables its composer while locked; see AUDIT for the need to review parity with the current composer-first clarification direction.

### 5.8 Product media and Product cards

ProductImage already distinguishes loading, success and unavailable media. Reuse that behavior for other listing images. A spinner must eventually give way to a fallback on failure.

Use aspect-fit when cropping would hide dimensions or variant details. Maintain a stable media frame so text and tap targets do not jump during loading. A fallback should remain a valid selectable Product entry when its other evidence is sufficient; absence of a photo is not proof of unavailable stock.

Keep actual Product colors and materials. Do not tint Product photos purple/gold to match the UI. The selected border/label carries the brand.

### 5.9 Items panel

Starts closed on Design entry. Opens only through Items or the specific temporary Swap flow. Contains either the list or a selected Item detail, with a clear way back to All items and a close action.

Current fixed baseline heights are 270 pt for Swap preview, 330 pt for selected detail, and a list calculation capped at 330 pt; all are capped at 80% of the available geometry height. These are implementation observations, not ideal constraints at every text size.

**Recommendation:** preserve compactness at normal sizes but let content, keyboard and text scaling determine an accessible maximum. The panel body scrolls. The composer and panel controls remain reachable. Avoid nested gesture conflicts between scene movement, panel scroll and keyboard dismissal.

### 5.10 Evidence disclosures

Use evidence pages for sources, dates, measurements, merchant offers, assumptions, component scores and uncertainty. This is a deliberately deeper information surface.

The disclosure label should predict what it opens: “Dimensions and sources,” “Why this Product,” or “Purchase details.” Avoid technical IDs as visible proof. Show units, original measurement labels and source links where useful. Scores describe ranking judgments, not probabilities of fit or satisfaction.

## 6. Motion grammar

### MOTION-01 — A question hands attention to the next question

The user's approved gesture is vertical continuity: the answered question moves up and fades, while the new question rises from below, expands slightly and fades in.

Historical gallery reference:

| Phase | Reference treatment |
|---|---|
| Outgoing question | Translate y toward -145 px, scale toward 0.96, opacity toward 0; about 360 ms |
| Incoming question | Start y about +240 px, scale 0.94, opacity 0; arrive at y 0, scale 1, opacity 1; about 620 ms |
| Incoming delay | About 80 ms |
| Easing | Cubic Bézier (0.16, 1, 0.3, 1) |
| Back | Reverse the perceived direction and restore the previous response |
| Reduced motion | Immediate content replacement / no spatial transition |

These are animation reference values, not backend timings or a requirement to use the same displacement on every iPhone. Scale travel to the available presentation surface. Keep the reading position stable.

**Observed native:** OperationPanel uses the same approximate displacement/scale and curve, a shared 0.62-second animation, and no spatial transition with Reduce Motion. The implementation is not identical to the browser's distinct outgoing/incoming durations and delay.

### MOTION-02 — Keep animation separate from acknowledgement

1. User acts.
2. The local selection/input acknowledges the action.
3. Submission becomes busy and repeated activation is blocked.
4. The authoritative next question/result arrives, or an error preserves the current answer.
5. Attention transitions once to the new state.

Do not animate a fabricated next question while waiting for the backend. If the response is fast, the transition can be fluid. If it is slow, use truthful compact waiting feedback rather than extending an ornamental animation.

Only the current question is interactive and exposed to assistive technology. The outgoing view must not remain tappable or focusable while visually fading. Focus the new question heading after the transition; preserve an appropriate text-input focus for composer-based clarification.

An answer animation must not send the answer a second time through an appearance callback. Identify transitions by stable question/revision identity, not by an incrementing local slide number unrelated to the operation.

### MOTION-03 — Animate interface movement, preserve geometry truth

Use restrained transitions for panel opening, disclosure, selection feedback and navigation. The current Items panel uses about 250 ms ease-out and respects Reduce Motion.

Committed room geometry changes immediately. Do not tween a chair through a wall to its new saved position, animate an unsupported speculative language edit or create a dramatic morph that implies continuity the solver did not validate.

The Swap preview is the explicit exception for temporary candidate geometry, and must remain labeled. Camera gestures remain direct and responsive.

Nonessential interaction-triggered motion should be suppressible; this aligns with [W3C's animation-from-interactions guidance](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html). Applying this principle does not claim full WCAG conformance for the native app.

### MOTION-04 — Ollo stays secondary

`ReSpace/Ollo.swift` is the shared native companion in the main app and UI studio.
The home screen has no mascot or tagline. Other screens use the existing
transparent poses: a brief
asking pose per operation/question/revision, still listening on focus, still
thinking during real queued/running work, and one hop after an observed operation
commits a complete Design. History, plan-only results, warnings, partial success,
failure and cancellation do not celebrate. Returning to a screen or polling the
same question cannot restart a gesture.

Keep one character per visible screen. The 64-point composer character becomes
40 points when typing and hides at accessibility text sizes. Questions use the
existing top-bar space; terminal results use a 96-point illustration. The image
is decorative, noninteractive and hidden from VoiceOver. Image swaps cancel on
view/state changes or backgrounding; Reduce Motion uses the appropriate still
pose. Preserve existing readable questions, status, controls and room gestures.

## 7. Images, room rendering and illustration

### MEDIA-01 — Match visual authority to evidence

| Visual | Meaning the UI may communicate |
|---|---|
| Captured room photo | Private evidence from that Room/capture |
| Native measured geometry | Available native measurements; not completed deferred perception |
| Committed Scene | The authoritative saved arrangement and its retained evidence |
| Product photo | Listing appearance for the exact selected variant, subject to source accuracy |
| Generic model | Representative geometry with saved dimensions; not exact appearance |
| Reconstructed mesh | Reconstructed context with explicit uncertainty; not independently verified dimensions |
| Inspiration photo | An illustration of the experience, not the user's room or generated result |
| Shopping share placeholder | Illustrative backdrop and label positions, not projected Item locations |

Use one strong room image when it establishes context. Avoid decorative image mosaics on task screens. Preserve aspect ratio and intentional crop; do not crop evidence so the relevant object or measurement becomes unintelligible.

Room selection needs a perceivable highlight and corresponding text context. Keep material/product appearance realistic. If a selection outline needs brand alignment, use a dedicated selection treatment; do not recolor the whole room.

Images that convey information need meaningful accessibility descriptions. Decorative symbols should be hidden from the accessibility tree. Avoid repeating the exact same Product title multiple times in one accessible card when the image contributes no additional information.

## 8. Copy system

### COPY-01 — Name the task or consequence directly

| Situation | Preferred pattern | Avoid |
|---|---|---|
| Empty library | “Your first room” / “Scan your room” | Multi-paragraph onboarding pitch |
| Request placeholder | “Describe your new design…” | A dense example prompt with several requirements |
| Ordinary question | One practical question about the unresolved need | Several questions joined with “and” |
| Pending question | The question or “Answer a question to continue,” with access | Generic “Action required” without destination |
| Progress | Actual reported work in plain language | Fabricated percent, countdown or “almost done” |
| Completed design | “Your room is ready” plus material outcome | Unsupported superlatives or blanket success after partial failure |
| Preview | “Preview” / “Not saved yet” | “Updated” before commit |
| Spending approval | “Raise limit to $…” | “Continue” hiding increased spending |
| Product evidence missing | “Not published” / “Unavailable” with context | Zero values or invented certainty |
| Recoverable saved scan | “Your scan is safe” only when local retention is known | Claiming retention after a storage-write failure |
| No purchases | “Nothing to buy” | Empty error panel or compulsory Product recommendation |

Write at the user's task level. “Opening your room” is useful; internal IDs and provider names rarely are. Keep backend terminology in diagnostic details where it helps troubleshooting. Retain domain distinctions in the implementation.

### COPY-02 — Treat generated text as variable content

Server-provided questions, warnings and explanations can be long. Design for full sentences, multiple warnings, long Product titles and missing optional fields.

Do not silently cut a hard constraint or failure reason to maintain minimalism. Present a concise accurate summary with a clear path to the full material explanation. If no safe summary exists, let the content wrap and scroll.

Do not insert marketing claims, certainty or approval into a generated response. Display the authoritative meaning. Formatting a server error for readability must not turn a failed operation into a retryable one without evidence.

## 9. Accessibility and input checklist

This is standard interface quality guidance for existing controls, not a separate feature expansion.

- **Reading order:** task/context, content, consequence, action; focus follows actual navigation.
- **Labels:** every icon-only control has an action label. Close, Back, Reset View, Undo, Clear selection and Save shopping list are distinct.
- **Selection:** selected state is exposed semantically as well as visually.
- **Targets:** use the shared 44 pt minimum native control area; larger primary actions remain 56 pt minimum. A small glyph is allowed inside a larger target.
- **Text scaling:** long titles, choice labels, key-value facts and buttons can grow or reflow.
- **Keyboard:** input, target context and submission remain visible; no footer or panel traps the field.
- **Reduce Motion:** remove large spatial question transitions and panel motion; preserve the new state and focus.
- **Color:** maintain readable foreground/background pairs and non-color state cues.
- **Media:** informative descriptions; decorative elements hidden; failure fallback readable.
- **3D alternatives:** maintain the existing Objects/Items textual routes for inspection/selection. Do not claim the 3D surface itself is fully accessible without testing it.
- **Errors:** announce/show a meaningful error without erasing the draft; focus moves only when needed for recovery.
- **Gestures:** ordinary browsing and decisions have reachable controls; camera gestures never mutate furniture.
- **State changes:** do not repeatedly announce unchanged polling status or move focus every refresh.
- **External handoff:** a link or share action is identifiable before opening another application.

## 10. Implementation decision rules

1. Reuse a shared component when its semantics match. Similar shape alone is not sufficient.
2. Prefer a small extension to a shared component over a slightly different local copy.
3. Keep presentation state local where appropriate; authoritative operation, question and committed design identity stay in the existing domain layer.
4. Do not add a dependency for spacing, icons, animation or a simple disclosure already supported by SwiftUI.
5. Keep raw style literals out of new page code when an existing semantic token fits.
6. Do not rewrite unrelated screens merely to centralize every current spacing value.
7. If new layout changes which actions are available, inspect locking, confirmation and persistence behavior as part of the change.
8. Verify enabled, selected, pressed, loading, failure and disabled states, not only the pristine default.
9. Treat the largest plausible content as a design input rather than an exceptional bug.
10. If a browser prototype is built, use real semantic controls, keyboard focus and reduced-motion behavior; keep gallery chrome outside the product viewport.
