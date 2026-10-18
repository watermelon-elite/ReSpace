# H3 MVP: Sequential Room-Design Agent, Products and Cloud Backend

> Status: initial-version product and architecture decisions agreed through Q64. The user confirmed the testing boundary during synthesis. Runtime implementation has not started. Publication is pending project issue-tracker setup; the requested triage label is **ready-for-agent**.

## Problem Statement

A person redesigning a home or business room must reconcile how the space is used, existing furniture, physical dimensions, style and a limited budget. Shopping listings are inconsistent, stale prices distort decisions, and individually attractive products may not form a useful or feasible room. A static recommendation list cannot discover the user's priorities or explain whether a better couch is worth giving up extra seating.

The app needs to turn a captured room and a lightweight conversation into a clearly rendered, purchasable arrangement. Recommendations must use real room measurements and verified product specifications, respect explicit choices, and survive ordinary app/network interruptions. The first live beta must be practical to implement: one sequential agent workflow with deferred heavy spatial work, hosted independently of developer machines.

The repository currently contains a basic SwiftUI application. It has no implemented H3 backend, product pipeline, agent controller or automated test suite to extend.

## Solution

Build the H3 lane of a cloud-hosted iOS room-design MVP, with explicit H1 rendering/capture and H2 spatial handoffs. The user completes a scan, chooses an intent and answers a small adaptive set of easy questions. Before the first interactive Gemini turn, the backend supplies measured LiDAR/RoomPlan context and an initial batch of verified product specifications. Further answers can trigger fresh shopping and database searches, verification and reranking.

The agent asks about activities and priorities before concrete trade-offs, prefers reallocating the existing budget, and asks for extra money only when justified. It presents real listings and images. All work is sequential: a pending question pauses the workflow; heavy H2 processing starts only after answers and listings are finalized. Gemini then plans against the processed room, H2 validates placement, and the app displays a complete design with verified alternatives and Buy links.

Saved designs are immutable. Chat, swap and removal create child versions; Undo loads the parent. Persisted stages and evidence support reconnect, retry and explicit cancellation. A 90-second generation goal is never a failure deadline.

## User Stories

1. As a room owner, I want to scan and redesign a room without creating an account, so that I can start immediately.
2. As a room owner, I want to choose home or café/business mode, so that recommendations match the purpose of my space.
3. As a tester without a supported LiDAR device, I want to use a sample room, so that I can try the same design experience.
4. As a room owner, I want to finish capturing my room before recommendations begin, so that the agent uses the complete available capture.
5. As a room owner, I want to review native capture measurements and photos before heavy processing, so that I can begin describing my goals promptly.
6. As a room owner, I want to mark existing objects Keep or Remove, so that the design respects what I want to retain or change.
7. As a room owner, I want to retain the original scanned room, so that I can compare the redesign with the original.
8. As a room owner, I want to choose add, spot or full-redesign intent, so that the amount of change matches my request.
9. As a room owner, I want to describe a spot and desired item category, so that recommendations address a specific location.
10. As a room owner, I want to provide style preferences, a budget and optional instructions, so that the agent starts with my constraints.
11. As a business owner, I want to set a seating target, so that the design considers the number of people I need to accommodate.
12. As a room owner, I want to have the agent receive room measurements and verified listing specifications before its interview, so that size informs its questions and recommendations from the outset.
13. As a room owner, I want to have later product discoveries include verified dimensions before comparison, so that new recommendations remain grounded in physical evidence.
14. As a room owner, I want to answer initial questions about activities, occupancy and priorities, so that the agent understands how I actually use the room.
15. As a room owner, I want to avoid repeating answers already supplied in my initial request, so that the interview stays short and relevant.
16. As a room owner, I want to answer one easy question at a time using choices and images, so that I can give useful feedback with little effort.
17. As a room owner, I want to complete the interview without typing, so that free-text entry is never a barrier.
18. As a room owner, I want to optionally explain an answer in my own words, so that I can express a preference that the choices miss.
19. As a room owner, I want to skip a question or delegate remaining decisions, so that I retain control over how much input I give.
20. As a room owner, I want to resume an unanswered question after closing the app, so that I do not lose my place.
21. As a room owner, I want to revisit an answer between sequential steps, so that I can change my mind without losing the interaction history.
22. As a room owner, I want to distinguish flexible priorities from explicit must-haves and avoids, so that the agent knows which trade-offs are acceptable.
23. As a room owner, I want to see questions about meaningful practical priorities, so that I am not asked to choose repeatedly between arbitrary products.
24. As a room owner, I want to see whole-room trade-offs such as a better couch versus additional seating, so that I understand the consequence of reallocating my budget.
25. As a room owner, I want to have within-budget substitutions considered first, so that I am not routinely asked to spend more.
26. As a room owner, I want to explicitly approve any budget increase with the new total visible, so that my preference is not mistaken for permission to overspend.
27. As a room owner, I want to see real listing photos, specifications and price implications in product questions, so that I can judge the actual proposal.
28. As a room owner, I want to have the agent search again after an answer when useful, so that feedback changes the products it considers.
29. As a room owner, I want to have broad live discovery compared with previously discovered products every search, so that recommendations are not limited to a small cached selection.
30. As a room owner, I want to receive three suitable ranked choices per item when available, so that I have alternatives without an overwhelming initial list.
31. As a room owner, I want to see fewer than three choices when evidence is insufficient, so that the system does not fill the list with unsuitable products.
32. As a room owner, I want to see cheaper or style-match labels only when supported, so that categories are useful explanations rather than forced slots.
33. As a room owner, I want to see prices, measurements, ranking explanations and check times, so that I can understand and assess recommendations.
34. As a room owner, I want to have value reflect comparable products rather than raw cheapness, so that the agent can recognize an overpriced item or a worthwhile deal.
35. As a room owner, I want to see an insufficient-comparison notice when value evidence is sparse, so that the agent does not invent a normal market price.
36. As a room owner, I want to receive exact-variant dimensions supported by retailer or manufacturer evidence, so that product size is not guessed from a picture or title.
37. As a room owner, I want to avoid products with missing or ambiguous required dimensions, so that unverified items do not become selectable recommendations.
38. As a room owner, I want to have stale shortlisted prices and availability checked, so that the chosen offer is reasonably current.
39. As a room owner, I want to see one choice for the same product sold by multiple merchants, so that duplicate offers do not occupy all three alternatives.
40. As a room owner, I want to understand whole-pack quantities and unused purchased units, so that the purchase total reflects what I would actually have to buy.
41. As a room owner, I want to see a US-dollar purchase total with tax and shipping exclusions, so that I know what the displayed budget covers.
42. As a room owner, I want to tap Find more for additional unseen choices, so that I can explore without automatically replacing my selected item.
43. As a room owner, I want to keep my current selection while additional candidates are discovered, so that browsing does not silently change my design.
44. As a room owner, I want to have questions and searches run in a simple sequence, so that the initial prototype behaves predictably.
45. As a room owner, I want to have heavy spatial processing start after questions and listings are finalized, so that the initial workflow stays understandable and manageable.
46. As a room owner, I want to see preliminary size suitability distinguished from validated layout fit, so that I understand what has and has not been checked.
47. As a room owner, I want to have RoomPlan and Perceptron contribute complementary observations, so that the final room can include both large objects and smaller details.
48. As a room owner, I want to continue after a partial detection failure with an explanation recorded, so that one missed object does not stop the whole process.
49. As a room owner, I want to get recovery or a rescan/sample option if no usable room geometry exists, so that the app does not invent a valid room.
50. As a room owner, I want to receive a final layout with valid clearances and no prohibited overlaps, so that the rendered arrangement is physically plausible.
51. As a room owner, I want to have equivalent fit repairs attempted before being interrupted again, so that minor layout problems can be resolved efficiently.
52. As a room owner, I want to approve a repair that materially changes an explicit choice or must-have, so that spatial recovery does not quietly change my goals.
53. As a business owner, I want to see actual feasible seating and any shortfall, so that the app does not claim an impossible capacity.
54. As a room owner, I want to see the full room and selected products clearly in 3D, so that I can understand the proposed arrangement.
55. As a room owner, I want to use orbit and walk views with day/evening lighting, so that I can inspect the design from useful perspectives.
56. As a room owner, I want to compare Before and After, so that I can see how the proposal changes my original space.
57. As a room owner, I want to swap a product using a compatible verified alternative, so that I can change a choice without breaking the rest of the layout.
58. As a room owner, I want to remove an item and have its dependent placements reconsidered, so that the result does not leave objects unsupported or invalid.
59. As a room owner, I want to request edits through chat, so that I can refine the design without dragging furniture.
60. As a room owner, I want to clarify an ambiguous chat reference using item images, so that the agent changes the intended object.
61. As a room owner, I want to undo one completed chat edit, swap or removal, so that I can reverse a change reliably.
62. As a room owner, I want to branch from an earlier design without changing saved history, so that I can explore another direction safely.
63. As a room owner, I want to reopen a saved design with its original geometry and price snapshot, so that new catalog data does not silently rewrite it.
64. As a room owner, I want to see actual generation progress and reopen work after disconnecting, so that I can recover from app or network interruption.
65. As a room owner, I want to wait beyond the 90-second goal without an automatic failure, so that a slower valid search can still finish.
66. As a room owner, I want to explicitly cancel work while retaining my current room or design, so that I can stop without losing saved results.
67. As a room owner, I want to open the exact product offer through Buy, so that I can purchase the recommended item.
68. As a room owner, I want to share a screenshot and a shopping list grouped by store, so that I can discuss or act on the design.
69. As a beta tester, I want to use a cloud-hosted TestFlight experience, so that the app works without a developer keeping a laptop running.
70. As an H1 implementer, I want to receive stable room, question, option, asset and Scene contracts, so that I can build the iOS interaction and renderer against clear behavior.
71. As an H2 implementer, I want to receive finalized capture and selection inputs at the agreed stage, so that I can implement spatial processing without coordinating concurrent branches.
72. As an H3 implementer, I want to retain candidate failures, ranking evidence, questions, answers and stage outcomes, so that I can diagnose behavior and resume work without inventing missing state.
73. As an H3 implementer, I want to have retries apply each answer and result once, so that cloud redelivery does not duplicate designs, options or purchase quantities.
74. As an H3 implementer, I want to verify the workflow through the public API, so that tests protect externally visible behavior while allowing implementation changes.

## Implementation Decisions

### 1. Scope, authority and ownership

- Implement the initial version agreed in the conversation. All required H3 P0/P1 responsibilities remain in scope; optional P2 ideas are excluded. Build schedules and hackathon checkpoints impose no implementation deadlines.
- H3 owns Gemini planning and interaction, product discovery/verification/ranking, APIs, persistence, cloud deployment, catalog/assets and its shared integration contracts. H1 owns native capture, SwiftUI and RealityKit. H2 owns perception, normalization, lifting, merging, spatial placement and overlap checks. H3 invokes and validates these handoffs without taking over the H2 algorithms.
- Use the latest source specification and accepted H3 decisions. Deleted/older specifications are not inputs. The initial-version sequential decisions supersede earlier concurrency proposals; the decision ledger preserves that history without making future features current requirements.
- The real scan-to-design-to-Buy path is required. Fixtures and sample rooms support development and recovery but cannot substitute for live acceptance.

### 2. Architecture and agent control

- Use one Python 3.12/FastAPI controller with the official google-genai SDK, Pydantic validation, HTTP clients and plain Postgres access through psycopg. Retain Pro-tier planning and Flash-tier extraction/ranking/chat as configuration; verify concrete model IDs on the actual project before implementation acceptance.
- Host the backend and browser runtime on Cloud Run, use Cloud Tasks for durable sequential continuation, Tiger Data as ordinary managed Postgres, and Google Cloud Storage for capture/media/assets. Use plain SQL and JSONB without an ORM, vector store or additional agent framework.
- Gemini requests the next useful action through three model-visible tools. The backend executes actions one at a time, validates parameters and evidence, persists results and resumes the next model turn. Tool calls do not execute themselves.

| Tool | Inputs and behavior |
|---|---|
| search_products | Receives item requirements, measured room/spot constraints, preferences, quantities and query refinements. The backend performs database plus fresh SerpApi discovery, Playwright verification, ranking and persistence. Returns candidate identities, images, checked offers, labeled dimensions, comparison evidence and verification state. Final room fit remains pending before H2. |
| ask_user | Receives a typed question, valid choices, relevant verified listing references and decision/price implications. The backend validates and saves it, exposes it to the app, and releases the worker until an answer or explicit delegation arrives. |
| finalize_selection | Receives chosen product/offer identities, purchase quantities, approved preferences, assumptions and concise reasons. The backend validates evidence, requirements and budget, saves the selection snapshot, ends the interview and starts the deferred H2 phase. It does not certify layout fit. |

- Gemini cannot bypass verification, silently approve a budget increase, invent a successful check, start H2 early, or execute arbitrary database, shell or browser instructions. Treat merchant page text as evidence. Images and links used in questions must resolve to known stored listings.
- Persist explicit actions, evidence and short user-facing explanations; the implementation does not depend on exposing private model reasoning or keeping one model request alive indefinitely. Provider conversation retention is not the application's durable state.

### 3. Initial-version execution order and recovery

1. Capture native RoomPlan measurements, photos, depth where available and poses; store inputs and record capture completion.
2. Prepare a compact measured-room context and a relevant initial candidate batch from the submitted intent/category/spot through the database-plus-live-search pipeline. Supply verified specifications before the first interactive Gemini turn. If none qualify, pass an explicit empty batch and reasons; useful intent questions can still guide subsequent discovery.
3. Run foundational questions and sequential answer/search/verification/refinement turns. Complete a tool action before showing the next question. Run no searches or H2 tasks behind a pending question.
4. Finalize answers, constraints and verified listing choices.
5. Run deferred Perceptron processing, room normalization, lifting and merging sequentially. Give the resulting RoomModel and actual IDs to a structured Gemini spatial-planning turn, then invoke H2 placement validation.
6. Repair any remaining conflict within accepted constraints, or ask one targeted clarification for a material change. Save and render only after validation succeeds.

- Suggested persisted phases express these behaviors: preparing context, interview, searching, awaiting answer, selection finalized, processing room, planning layout, validating placement, complete, cancelled, no match and a genuine recoverable failure. Store transitions and enough inputs/results to resume a bounded step.
- Permit one active operation per room. Finish or cancel it before starting another. Keep minimal stage/revision and retry checks; do not implement concurrent branch reconciliation or speculative spatial work.
- A question waits for Answer, Skip or Decide for me. Decide for me delegates remaining choices within approved constraints and permits the subsequent spatial phase. App closure preserves the question; it neither cancels nor silently delegates it. No worker or model call remains open while awaiting input.
- Outside a user-input wait, persisted work can resume across app disconnection, request deadlines or worker restarts. Cloud task redelivery must not duplicate designs, options, answers or purchases. Persist completion before acknowledging it and recover dispatch failures without losing logical work.
- Cancel stops scheduling further work and prevents late publication. Retain candidate evidence and diagnostics, and preserve the existing room/design. Individual attempts have explicit timeouts and failure handling; total elapsed time alone never fails, truncates or cancels the generation.

### 4. Capture evidence and spatial context before the loop

- Capture must finish before recommendations. Native RoomPlan measurement already performed by the phone is available immediately; it is distinct from the deferred H2 reconstruction/lifting pipeline.
- Pass estimated room dimensions with their meaning, height, available walls/openings, measured existing objects/poses, stable capture IDs, Keep/Remove choices and spot reference. Include source, units, capture identity/time and reported uncertainty. Do not treat bounding extents as a rectangular floor plan or invent absent measurements/confidence.
- Pass each concrete product's exact-variant width, depth and height with axis labels, normalized units, published specifications, evidence source/time, checked offer and pack contents. Keep measured room context present across turns. Each newly discussed listing brings its verified measurements into the next reasoning turn.
- Use known dimensions to guide queries, reject obvious conflicts with explicit measured limits and explain preliminary suitability. User preferences cannot change an observed dimension. Product verification is distinct from final spatial eligibility: collision, support and clearance checks still follow H2 processing.
- H1 supplies captured JSON, JPEG keyframes, optional depth, camera intrinsics, orientation, dimensions, timestamps and camera-to-world poses. Preserve the capture frame and calibrate mappings with H2; use meters and a declared axis convention, with floor coordinates in x/z and y upward in the processed room.
- Retain the source capture baseline of up to 40 keyframes, sampled on roughly 1.5-second, 0.5-meter movement or 20-degree turn triggers when tracking/image quality permits. JPEGs are approximately 1280 pixels on the long edge with correctly rescaled intrinsics. One upload is in flight per room, with one retry; capture stays responsive. Upload and finalize handlers store inputs and do not invoke Mk1 or H2.
- Before processing, use native capture preview/photos and already captured object IDs for Keep/Remove and spot input. Do not show a fabricated fused room or pretend deferred detections already exist. Preserve/map native IDs when H2 normalizes the room. A later edit can reuse completed room geometry without repeating unchanged lifting.

### 5. Interview, intent and user constraints

- Begin with an adaptive soft target of about three quick questions: main activities, usual occupants/guests and the most important improvement. Adapt home/business choices and skip known answers. Three is neither a quota nor a cap.
- Present one question at a time. Favor single-choice cards, multi-select chips and short listing-image comparisons; numeric controls handle explicit budgets. Free text is optional and secondary. Most answers require a tap or a few taps, and the entire flow is possible without typing.
- Ask fundamental questions about use, experience and priorities more often than arbitrary product comparisons. Ask only when an answer could materially affect the plan. Once choices are resolved/delegated and validation passes, finish without filler questions.
- Store every question, choice set, answer, revision, skip, assumption and listing snapshot. Keep explicit answers distinct from inferred/default preferences. Reopen the exact pending interaction; answers can be revisited between sequential steps. Cross-room preference reuse is excluded.
- Ordinary preferences are flexible. Explicit must-have/avoid choices, Keep, approved budget and spatial requirements are hard constraints. Explain incompatible requirements and ask which can change; do not silently relax them.
- Keep preserves an existing object's position and presence during AI changes. An explicit user Remove can override a previous Keep choice. Remove excludes an object from the proposal while preserving the original capture. Keep and Remove identities cannot overlap in a request.
- Support add, spot and redesign intents. Add means one to five new items without AI-initiated moves/removals; spot means one requested item at the selected location; redesign permits five to twenty new items and appropriate moves/removals. Explicit user removals apply independently. Retain style chips, free-form initial instructions, budget and business seating targets.
- Gemini produces named anchors and valid existing IDs, never invented coordinates. Validate IDs, actions and constraints independently of model output. Invalid proposals cannot become committed actions. Retain the source rule of dropping/logging invalid planned items and retrying once when more than half are invalid; never silently discard a hard requirement under that rule. Actual provider failures get one retry then a recoverable result.

### 6. Discovery, retention and initial options

- Every new search, including Find more, explores both relevant database products and fresh Google Shopping results through SerpApi in US/USD. Suitable cached matches never eliminate live exploration. Query-response history cannot replace the live call; request fresh provider results.
- Each initial pass retrieves up to 50 relevant database candidates and runs three materially different relevant live queries, collecting available results before narrowing. These are work-defined passes, not time deadlines. Use fewer when sources are exhausted. Broad discovery must not stop merely because two or three attractive products were found.
- Use query variation for breadth; do not rely on ignored Shopping offset/page-size parameters. Validate provider behavior during integration. Curated catalog IDs are candidate seeds, not a preference override or verification bypass.
- Persist all discovered candidates, including rejected ones and missing fields. Retain up to ten ranked candidates per source, with query provenance, decision context, evidence, rejection reasons and outcomes. A provisional shortlist can contain internal candidates awaiting checks; those are not selectable options.
- Initially show up to three eligible choices including the main item. Keep rank separate from selected identity. Cheaper/style-match labels are optional explanations, not compulsory slots. Each choice includes product, offer, image, dimensions, evidence/check time, ranking explanation and rendering metadata.
- Show useful comparisons on cards; expandable detail contains component scores and evidence. Scores are judgments, not calibrated probabilities. “Best” means among the relevant eligible discoveries, not the whole market.
- Find more performs another broad database/live pass, stores its own shortlists and appends up to three unseen eligible options while preserving existing options/selection. Searching alone creates no design version. A later swap validates the chosen result against the current saved layout and budget.
- If no candidate qualifies, consider further relevant candidates and a verified catalog fallback, then explain an optional omission or return no match when nothing useful qualifies. Preserve the existing room/design. Never add an unverified candidate to fill a quota.

### 7. Product verification, identity and refresh

- Require actual product width, depth and height before concrete listing choices, design placement or alternatives. Require all axes even for thin items such as rugs. Allow exact unit conversions; reject package-only measurements, missing axes, ambiguous variants and invented category/image estimates.
- Use cloud-hosted Playwright to resolve the merchant/manufacturer product page. Prefer explicit structured measurement data, then visible specifications. Flash may extract stated labels/units and distinguish package from item dimensions; it may not manufacture values. Preserve source URL, variant identity, original labels/values/units, extraction time and normalized results.
- Exact-variant dimension evidence can be reused for seven days. Expiry causes re-verification, not product deletion. Catalog preparation uses the same eligibility policy.
- Keep a separate offer check timestamp. After provisional selection, verify selected database offers with Playwright when older than 24 hours or missing a timestamp. Check exact variant, price and availability. If invalid or over budget, rerank and try retained replacements. Combine dimensions and offer extraction in one visit when both need refresh.
- An inaccessible page means unverified, not proven out of stock. Retry a transient page/provider failure once, then retain its reason and continue. Do not repeatedly retry confirmed missing measurements or unavailable stock in the same search; later searches may reconsider them.
- For optional further database batches, require a provisional overall score more than five points above the weakest currently selected eligible choice on the same current comparison snapshot. With cutoff 80, skip 84/85 and check 86. Prefer already-fresh near-equivalent choices. This never skips mandatory checks on selected stale offers or useful fallback when fewer than three eligible choices exist.
- Stale prices make preliminary rankings uncertain, not mathematical upper bounds. Changed answers, prices or comparison evidence require reranking before applying the stopping rule. When no remaining database candidate clears it, stop optional database exploration and present fresh eligible results.
- Group reliably identified exact physical variants across merchants; title similarity alone is insufficient. Show one choice with multiple retained offers underneath, using the cheapest eligible offer for that variant. Different sizes/colors remain distinct variants.

### 8. Ranking and comparable value

- After applicable hard eligibility checks, use a shared 0–100 overall score: 60% practical/request fit, 30% style fit and 10% relative value. Rendering fidelity breaks otherwise equal scores. Keep components, reasons and scoring-rule version. No database/live source bias is allowed.
- Practical fit reflects stated activities and priorities. Relative value reflects a price advantage or premium against comparable products, not a reward merely for the lowest dollar amount. Absolute price remains relevant to budget eligibility, purchase allocation and later whole-room trade-offs; an explicit cheapest request guides feasible downstream selection without redefining the value component.
- Define comparison groups by type/function, approximate size/capacity, known material/features and condition. Use both discovery sources, do not group solely by price, and do not invent durability or comfort differences. Use the median of distinct comparable products with one representative valid offer per product. Normalize verified identical-unit packs for comparison only.
- Require at least three other comparable distinct products with usable recent price evidence before asserting unusual value/overpricing. Otherwise assign a neutral value component of 50 and show insufficient comparison evidence. Keep the candidate eligible if other rules pass. Preserve membership, inclusion reasons, sample count, prices/check times and uncertainty; a stale provisional comparison is not a verified bargain claim.
- With adequate evidence, calculate value as 50 plus 100 multiplied by one minus the candidate price divided by the comparable median, then bound the result from 0 to 100. At median $200, a $150 candidate scores 75, a $200 candidate 50 and a $250 candidate 25. Use valid positive comparable prices. This component contributes only 10% of overall rank.
- Freeze one comparison snapshot per completed discovery/ranking batch. New results or offer refreshes create another snapshot and rerank both sources together. Never compare scores from different benchmarks or rewrite saved historical explanations.

### 9. Purchase totals, packs and whole-room decisions

- Use US dollars and real offer prices. Purchase total is offer price multiplied by purchased quantity, including whole packs and paid surplus. Exclude existing furniture, removed purchase lines, tax and shipping. Never invent unknown prices.
- Distinguish product variant, merchant offer, purchased pack count, contents supplied, physical placed-unit identities and unused paid units. Verify pack contents and each item's dimensions. Reject ambiguous bundles from options but retain candidate records.
- Two $100 two-chair packs cost $200 and supply four chairs. Placing only three still costs $200 and must disclose the spare unit. Removing a placed unit does not automatically eliminate a still-required pack; recalculate whole purchases.
- Evaluate meaningful trade-offs as complete affected purchase sets: added/removed/downgraded items, total cost change, retained seating/use and the priority improved. Reallocate interim item budgets within the approved total. Do not optimize individual products at the expense of the room's purpose.
- Consider within-budget substitutions before requesting more money. A rare increase requires a concrete reason, checked product evidence, relevant quantities, resulting total and old/new ceiling. A $15 item upgrade that still fits the ceiling needs no ceiling increase. Preference, silence and Skip never approve more spending.
- Count retained existing seats and new physical seats, not packs. Report feasible seating and shortfall without exceeding budget or sacrificing clearance. Persist price/time snapshots in saved designs; later checks do not silently rewrite saved totals.

### 10. H2 handoff, geometry and final fit recovery

- H3 sequentially invokes H2 detection, normalization, lifting/merge, placement and overlap operations after listing finalization. Pass raw capture, keyframe evidence, stable-ID mapping context, current Keep/Remove choices, approved preferences and selected verified product dimensions/quantities.
- RoomPlan and Perceptron Mk1/Mk1.5 are complementary layers. During deferred processing, run stored frame detection sequentially and record every success, failure or timeout. Use available results after partial failure without a blocking error or user approval of fallback. If no usable boundary remains, try recovery, then offer rescan/sample-room recovery rather than inventing geometry.
- H2 uses depth where available and surface-ray fallback where appropriate, aligns native capture and keyframe coordinates, merges observations and preserves source/confidence. Original-room estimation for detected objects is distinct from the stricter actual-dimension requirement for purchasable products. Verify this distinction in shared contracts.
- After H2 returns a RoomModel, Gemini emits supported anchors against actual IDs: wall, corner, relative to an object, window, center, captured spot, wall-mounted, tabletop or business seating group. H2 computes metric coordinates/orientation deterministically.
- Preserve the source solver interface behavior: removals, moves and then additions by footprint; validate walls, existing/selected objects, door and keep-clear areas, with the agreed 5 cm footprint margin. Allow category-specific relationships such as rugs beneath furniture. Test a 0.9 m business aisle baseline and preserve applicable counter/register/door areas. Treat these as product geometry defaults, not a claim of regulatory certification.
- H2 may try bounded placement adjustments or a supported alternative anchor. If a layout still fails, first repair placement or try a retained, verified equivalent preserving approved requirements and budget, then revalidate sequentially. Ask one targeted question if repair materially changes an explicit choice or must-have. Explain optional omissions. Never publish a known-invalid layout or silently discard a hard requirement.
- Return structured conflicts before saving when unresolved. Reuse the interview history and valid room evidence during repair; do not restart the entire experience. Late inputs or worker retries cannot silently rewrite an already saved snapshot.

### 11. Versions, edits and dependent items

- Completed designs are immutable children of their selected parent. Each completed chat edit, swap or removal creates one child. Undo loads the parent; an edit after Undo creates another branch without changing old versions.
- Preserve the original capture, processed room snapshot, product dimensions, placement, purchases, totals, explanations and evidence/check times used by the saved design. Loading it does not resize furniture or refresh prices in place.
- Chat may replace, add, remove or move appropriate items using supported anchors. Use the selected item for an ambiguous reference when available; otherwise ask a short image/label clarification. Broad requests affect the plan under Keep, budget and must-have rules. Resolve only changed products, reuse unchanged geometry and hold unaffected placements fixed where appropriate.
- A swap alternative must fit the same position/orientation, preserve clearances and respect remaining budget. Revalidate when the layout changes. Supply complete alternative metadata for immediate local preview, but the saved child is authoritative. No direct furniture-position/rotation mutation endpoint is required.
- Removal re-evaluates dependent anchors/supports. Relocate dependents only when valid and permitted. Explain omission of an optional dependent; ask before changing a must-have. Save the removal and all necessary consequences as one child so one Undo restores it. Recalculate seating and whole-pack purchases.
- Find more results live in separate search records, not mutable saved Scenes. A selected new result is validated against the current intended parent and only then creates a child. Serial stage and retry checks prevent accidental double application.

### 12. Public API and shared contracts

- H3 owns Pydantic contracts and H1 owns corresponding Swift Codable models. Agree executable fixtures with H2 before integrating real capture or placement. Define complete schemas during implementation from these decisions; earlier illustrative JSON was not a complete schema.
- Key contracts cover capture receipts/status; measured-room context; design intent/Keep/Remove/spot; typed questions and answers; generation phases/results; candidate, variant and offer evidence; comparisons/ranks; purchase packs/placed units; RoomModel; anchor-based DesignPlan; validated Scene; and structured conflicts/warnings.
- A Scene supplies room geometry, original/current object identities and transforms, selected-product identity separate from rank, complete alternative/render metadata, quantities, purchases/surplus, total/currency/check times, feasible seats/shortfall, warnings and parent/version identity. It must be sufficient for the complete rendered room rather than just a list of new products.
- Question submission includes question/generation identity, relevant revision and retry identity, selected valid choices or optional text, and an explicit budget change where approved. Store the answer before continuation. Reject untrusted IDs or contradictory constraints at the boundary.

| Public operation | Required contract |
|---|---|
| Create/list rooms | Mode and device grouping; no sign-in. |
| Upload keyframes | Store JPEG, optional depth and metadata; return receipt without invoking H2. |
| Finalize capture | Record captured room and expected input outcomes; distinguish capture complete from processing complete. |
| Read room | Return stored capture/native summary/status and later RoomModel when available. |
| Start design | Accept initial intent after capture completes; return accepted generation identity promptly. |
| Read generation | Return durable phase, progress, pending question, diagnostics and result reference. |
| Answer question | Persist answer/delegation and resume the next sequential stage exactly once. |
| Cancel generation | Stop further scheduling/publication and preserve existing saved state/evidence. |
| Read design | Return the immutable complete Scene and its snapshots. |
| Chat edit | Start a serial generation against an explicit saved parent. |
| Swap/remove | Validate the action and save one child Scene or return the needed clarification. |
| Find more/read search | Persist search work and return additional eligible choices without changing selection. |
| Shopping list | Return products, purchased quantities, store groups, prices and exact offer links. |
| Catalog manifest/health | Expose versioned asset metadata and operational health. |

- Use the existing planned versioned HTTP API shape. The app sends answer requests and polls status; no persistent streaming connection is required. Keep response behavior consistent across immediate actions and resumable work.

### 13. Persistence and operational behavior

- Store rooms/capture summaries; keyframes with detection outcomes; immutable designs with parents and room/request/plan/Scene snapshots; persistent products and offers; seven-day query-response history; generation state with spatial evidence and all question/answer revisions; and product-search records containing source pools, top-ten rankings and displayed choices.
- JSONB is suitable for documents read/written together. Use plain SQL, a small SSL-enabled connection pool and indexes for room/device/design/product lookup. Product identity, offer identity and pack contents must be explicit enough to enforce deduplication and correct money; avoid adding unrelated data infrastructure.
- Query-history expiry does not delete products, failures or evidence required by saved designs. Retain all discovered candidates, rejected reasons and missing measurements. A new live search cannot be silently replaced by stored search results.
- Device identity organizes My spaces; it is not authentication. No shared application key or login project is required. Keep scan media private, product/model assets accessible for rendering, and provider credentials server-side. Validate external inputs and product URLs without introducing an account/permission system.
- Log stage outcomes, provider/extraction failures, rejected candidates, missing fields, model/schema failures, query counts, retries and usage. Preserve user-readable recovery explanations separately from diagnostic details. Bound individual external attempts while preserving logical work across cloud request limits.

### 14. H1 display and asset responsibilities supported by H3

- Supply H1's native capture review, Keep/Remove controls, intent/questions, generation progress, full RealityKit room, product cards, verified-dimension badge, purchase total, Buy links, Before/After, day/evening lighting, orbit/top-down and walk views. H1 implements these interfaces; H3 supplies the data/assets and validates contracts.
- Existing furniture uses category models scaled to measured size. Catalog products use validated USDZ assets; live discoveries use category stand-ins tinted from product imagery. Rugs/art/mirrors can use textured panels. Indicate representative rendering faithfully; generated geometry never establishes true physical dimensions.
- Prepare a broad category stand-in library, initially about twenty categories, with bottom-center origin, consistent facing and normalized scale. Prepare an initial curated catalog of roughly sixty verified products spanning home/business categories. These are coverage baselines, not permission to substitute a catalog-only demo for live discovery.
- Use the agreed Kenney kit basis for stand-ins and SPAR3D for offline catalog reconstruction, converting GLB to USDZ, checking textures/orientation/scale against verified dimensions and rejecting poor assets in favor of stand-ins. Aim for models under 3 MB. Confirm license/weight access and measure GPU/runtime requirements before bulk preparation; no live image-to-3D generation is required.
- Preserve original/current transforms for Before/After and removed-item representation. Support Buy to the exact verified offer and the source's secondary Amazon search-link behavior where an Associates tag is available; Amazon API/checkout are outside scope. Share screenshots and a shopping list grouped by merchant.

### 15. Deployment and acceptance boundaries

- Deploy backend, product database, extraction runtime and assets for real TestFlight use without a developer laptop. H1 owns compatible builds/distribution. H2 supplies geometry/perception integrations. H3 owns deployed APIs, credentials/configuration, catalog preparation and end-to-end verification.
- The iOS baseline is iOS 18 with supported LiDAR hardware (initial test devices from the Pro range), plus sample-room behavior on unsupported devices. Verify actual native capture/depth and RealityKit behavior on hardware; do not infer readiness from a mock.
- Measure the 90-second generation goal without enforcing a hard deadline. Retain local swap/removal preview responsiveness and the source target of at least 30 fps on an iPhone 13 Pro with up to forty items. Measure H2 processing from its deferred start; the earlier promise of lifted objects immediately after scanning is superseded.
- Test zero prohibited overlap/blocked doors and the source small-object positioning target of approximately 15 cm on representative physical captures. Treat real calibration and complete-room rendering as integration gates.
- Earlier demo-scale cost, credit-runway and per-search estimates are unvalidated for broad fresh discovery, browser extraction and interactive turns. Measure actual cloud/provider use and model availability; do not publish old pricing assumptions as the beta operating budget. Per-call limits do not become an overall generation cutoff.

### 16. Decisions that change other builders' implementation

This is the implementation-impact register for work outside H3. The comparison is against the current source specification, using its section and requirement numbers below. It records changes to H1's screens, interaction, rendering and distribution, and H2's spatial behavior. It does not transfer that work to H3. These are specification changes requiring implementation and owner verification, not claims that another builder's code has already changed.

#### H1: iOS, capture and RealityKit changes

| Area | Source behavior | Actual change H1 must implement | Agreed basis |
|---|---|---|---|
| Capture uploads and scan feedback | Source §4 Step 1 and §5.1 allow four simultaneous uploads; the scan counter reports Mk1 detections returned by uploads. | Use one upload in flight per room while keeping capture responsive. Show truthful capture/upload progress instead of an immediate detection count. Finish capture before recommendations. The existing sampling limits, native measurement capture and retry baseline remain. | Implementation Decisions 3–4; Q7, Q55, Q62. |
| Room review before the interview | Source §4 Step 2 renders the processed RoomModel and incrementally adds small objects after finalize; NFR-01 expects those objects immediately after scanning. | Review native capture/photos and available measured objects before server processing. Keep/Remove and spot selection must work against that available capture, without waiting for or displaying deferred Mk1 objects. Show the processed full room after the later spatial phase. This changes the preview and navigation implementation, not just its input schema. | Implementation Decisions 3–5, 15; Q55, Q62. |
| Adaptive question interface | Source §4 Steps 3–4 have a static intent sheet followed by a generating screen. | Add one active question at a time, with choice cards, multi-select chips, listing images and numeric controls. Support foundational use/occupancy/priority questions, optional text, Skip, Decide for me and revisiting answers between steps. Reuse this interaction for ambiguous chat references and material fit-repair questions. Completion must be possible without typing. | Implementation Decisions 5, 10–11; Q38–Q42, Q46–Q47, Q56, Q61, Q64. |
| Generation lifecycle and recovery screens | Source §4 Step 4 cycles through prewritten room story lines while waiting for a Scene, then returns a result or generic failure. | Render actual persisted stages, including awaiting an answer, searching and deferred room processing. Resume the exact pending interaction after reopening; provide explicit Cancel; preserve the existing room/design on cancellation or no match. Do not turn the 90-second goal into a UI timeout. Offer rescan/sample recovery when usable geometry cannot be recovered, and distinguish preliminary size suitability from validated final fit. | Implementation Decisions 3, 6, 10, 15; Q19, Q27, Q33–Q37, Q41, Q60–Q61. |
| Budget and practical trade-off presentation | Source §4 Step 3 collects a budget and seat target; item cards show price and a short reason. | Present the complete affected set of purchases, old/new cost, seating/use consequences and the priority improved. A proposed ceiling increase needs an explicit approval control showing the old/new ceiling and resulting total. Preference selection, Skip and app closure cannot act as approval. Show practical must-have conflicts through the question interface. | Implementation Decisions 5, 9; Q39, Q47, Q50. |
| Product choices and Find more | Source §4 says “3 alternatives,” while §5.5 and FR-09 specify a pick plus two alternatives; no Find more flow is defined. | Resolve that inconsistency as up to three initial choices **including** the main item. Add Find more, append up to three unseen eligible choices per completed search, and preserve the existing selection. Handle fewer choices/no match without displaying rejected candidates. Render one exact variant as one choice, with its retained merchant offers underneath. | Implementation Decisions 6–7; Q14, Q17–Q18, Q22, Q25, Q29–Q30. |
| Comparison and evidence details | Source §4 Step 5 displays photo, title, store, price, a reason and an optional verified badge. | Extend cards/details with checked measurements, check times, optional supported cheaper/style labels, ranking components and evidence. Show insufficient comparison evidence when applicable, and identify representative stand-ins faithfully. Labels are not mandatory alternative categories; “best” is scoped to the eligible discoveries. | Implementation Decisions 6–8, 14; Q16, Q24, Q29, Q31, Q41, Q49, Q53–Q54. |
| Pack quantities, totals and feasible seating | Source §4 presents a total/item count and a requested seat target, without pack/surplus presentation. | Distinguish purchased packs, physical units placed and paid surplus. Show the full purchase total in USD, tax/shipping exclusions, feasible seating and any shortfall. Refresh these displayed consequences after a completed edit without treating a removed unit as an automatically refunded whole pack. H3 computes money; H1 implements its intelligible presentation. | Implementation Decisions 9, 11; Q9–Q10, Q50–Q51, Q57. |
| Product scaling and saved rendering | Source §5.9 reloads a design with newly scraped dimensions and resizes the item. | Remove estimate-first/later-resize behavior for purchase items. Render verified sizes from the saved design snapshot; reopening must preserve its geometry, dimensions, prices and explanations. New offer checks must not silently change the displayed saved design. Existing scanned-object estimates remain a separate rendering case. | Implementation Decisions 7, 11, 14; Q13, Q26, Q54. |
| Direct furniture manipulation | Source §4 Step 5, §5.7 and FR-12 require floor/wall dragging, two-finger item rotation and an overlap highlight on release. | Remove direct furniture Move gestures and their release/save/error-highlight flow from the MVP. Retain item selection, camera navigation, Swap, Remove and chat-directed moves. This is a removal of H1 implementation work. | Implementation Decisions 11; Q11–Q12. |
| Swap, removal and Undo | Source §5.8 mutates the current version for manual swaps/removals; only chat creates a child. Source §5.5 treats swaps as client-side changes. | Preview a compatible alternative locally, then display the authoritative validated child. Every completed swap/removal is one undoable child; one Undo restores the whole action, including dependent items. Editing after Undo preserves the earlier branch. Keep Find more browsing separate from the saved design. Removal consequences and any required must-have clarification must be visible. Keep/Remove controls must also resolve an explicit Remove overriding a prior Keep. | Implementation Decisions 5, 11; Q8, Q11, Q22, Q25, Q40, Q57. |
| Exact offer navigation and sharing snapshots | Source §5.5 permits Buy to open a Google product page; saved item dimensions can subsequently change. | Open the selected verified merchant offer. Share the selected saved design's purchase quantities and price snapshot, including pack consequences, rather than substituting newly refreshed catalog values. The existing share sheet and secondary Amazon search feature remain. | Implementation Decisions 7, 9, 11, 14; Q16, Q26, Q30, Q51, Q54. |
| Live beta distribution and device acceptance | Source §10 makes TestFlight conditional; the source primarily targets an installed demo. | Prepare signing/distribution for real TestFlight beta use against deployed services. Verify the changed capture, question/resume/cancel, option, edit/Undo and recovery flows on hardware, alongside the existing RealityKit checks. A local demo or fixture-only walkthrough does not satisfy this acceptance target. | Implementation Decisions 15 and Testing Decisions; Q5, Q20, Q27. |

#### H2: perception and spatial implementation changes

| Area | Source behavior | Actual change H2 must implement | Agreed basis |
|---|---|---|---|
| Preserve decisions made against native capture | Source §4 reviews the normalized RoomModel before Keep/Remove or spot input; normalization can establish the IDs used thereafter. | Normalization must now preserve or map the native identities and spatial references already used for Keep/Remove and spot decisions. Verify that coordinate conversion and merging do not lose or redirect those choices. The changed work is the mapping behavior inside normalization/merge, beyond merely accepting another field. | Implementation Decisions 4–5, 10; Q55, Q62. |
| Hard requirements during placement repair | Source §5.6 drops an item that cannot fit and removes lowest-priority items until aisles connect. | Keep bounded placement repairs, but prevent those drop/remove paths from silently discarding an explicit must-have or materially changing an explicit choice. Preserve Keep and clearance requirements. Produce an unresolved conflict when permitted repair is exhausted so H3 can select a verified equivalent or ask the user. H3 owns product search/questions; H2 owns the changed solver decision and revalidation. | Implementation Decisions 5, 10; Q47, Q64. |
| Dependent anchors after removal | Source §5.6 applies removes before other operations, supports tabletop/relative anchors, and does not specify repair of their dependents. | Re-evaluate objects supported by or anchored to a removed item. Relocate only when permitted and geometrically valid; identify optional omissions or a hard conflict. Never leave an object floating on a removed support or referencing a missing anchor. Revalidate affected geometry while preserving unaffected placements. H3 groups the resulting consequences into one version. | Implementation Decisions 11; Q57. |
| Fit validation for swaps | Source §5.5 makes swap a client-side product change; §5.6 provides general placement and overlap checks. | Apply the selected alternative's actual dimensions at the existing position and orientation, including relevant support/clearance constraints. Reject an incompatible same-pose swap instead of relying on later resizing, silently moving surrounding furniture or accepting a visually plausible preview. Reuse existing geometry/checks where sufficient; this is an additional required validation path, not a new solver. H3 separately validates price and budget. | Implementation Decisions 7, 11; Q13, Q22. |
| Physical seating and incomplete feasible layouts | Source §5.6/FR-18 targets the requested seats, and its tests expect the target to be met; infeasible items may be dropped. | Evaluate retained existing seats plus newly placed physical units, independent of how many merchant packs were bought. Return the actual feasible seat count and a shortfall when the target cannot fit, while preserving clearance and explicit requirements. Unplaced paid surplus contributes no room capacity. Extend solver cases for shortfall and partial pack placement; purchasing arithmetic remains H3's work. | Implementation Decisions 9–11; Q10, Q51, Q57. |
| Unusable room geometry | Source NFR-07 already permits Mk1 failure to fall back to a RoomPlan-only room, but does not define the case where that room also has no usable boundary. | Distinguish a usable partial room from an unusable spatial result. Continue with valid available observations, but do not fabricate a valid boundary or successful Scene when normalization/recovery cannot establish one. H3 coordinates recovery and H1 offers rescan/sample; H2 must identify the genuine geometry failure. | Implementation Decisions 10; Q15, Q34, Q64. |
| Precomputed progress story | Source §11 assigns H2 the room-specific story lines generated during normalization for the prewritten generating-screen cycle. | That story-generation dependency is superseded by actual H3 stage progress. H2 no longer needs to create the pre-interview story sequence as a required deliverable. Its measured geometry and processing outcomes remain necessary. | Implementation Decisions 3, 15; Q55, Q60. |

#### Changes deliberately not counted as other-builder implementation work

- **Deferring and serializing H2 calls:** the initial version postpones detection/normalization/lifting/merge/placement until selection finalization. H3 owns that scheduling, upload/finalize handler changes, durable continuation and cancellation. This alone does not require H2 to rewrite its detection/lifting algorithms or build a job system. H1's preview/progress changes and H2's native-choice preservation are listed above because they do change those builders' work. Concurrent or speculative lifting remains future-only.
- **Contracts alone:** added question, candidate, evidence, generation and Scene fields, function signatures and status polling endpoints are shared integration work. The tables identify the actual screens and spatial behavior those contracts require; they do not count serialization or an H3-to-H2 call as a separate feature.
- **Existing requirements:** RoomPlan plus Mk1, RoomPlan-only fallback after Mk1 failure, native poses/intrinsics/depth capture, depth/ray lifting, basic Keep/Remove, clearances, full-room rendering, camera views, lighting, Before/After, no sign-in and the sample-room path already exist in the source. Only their specifically changed behavior above is a delta. Existing calibration, geometry accuracy and frame-rate checks still apply.
- **H3-owned changes:** Gemini orchestration, fresh database-plus-SerpApi discovery, Playwright extraction, ranking/value calculation, caching, cloud hosting, persistence, catalog/assets and offline SPAR3D preparation remain H3 work. They are not new H1/H2 responsibilities. No additional named builder's implementation ownership was established in this discussion.

## Testing Decisions

### Confirmed primary seam

The user explicitly approved the public backend API as the primary testing boundary. Drive capture submission, design start, questions/answers, search, finalized selection, deferred spatial work, saved designs and edits through that boundary. Use controlled Gemini, SerpApi, Playwright, storage/dispatch and H2 responses so tests are repeatable. Prefer observable responses, persisted/reopened state and external request evidence over private methods, module layout or exact model prose.

The repository has no backend tests or established test helpers. The only existing application is a SwiftUI starter, so there is no test-suite prior art to reuse. Introduce one API-level harness and shared representative room/provider fixtures rather than separate mocking conventions for every module. Test the controller, products, persistence and H2 handoff together at that seam. H2's own algorithm tests remain H2's responsibility; H3 checks the contract and complete results.

### API-level acceptance coverage

1. Capture receipts/finalization store inputs and expected outcomes without triggering Mk1, lifting, merging or placement. No recommendation starts during active capture.
2. The first interactive model request includes actual measured room context and initial verified listing specifications, or an explicit empty verified batch with reasons. Subsequent product turns preserve scan context and include new candidate dimensions before reasoning.
3. Questions use valid choices and known listing images, can be completed without typing, skip already known answers and preserve every answer/revision/assumption. A saved question survives reconnect and waits until Answer, Skip or Decide for me.
4. No search or H2 operation remains in flight while a question is pending. Search actions occur sequentially after answers; heavy H2 work starts only after selection finalization. Retry delivery cannot start a duplicate active operation.
5. Must-haves, Keep, explicit removals and the approved ceiling constrain all actions. Choosing a more expensive item, skipping or disconnecting does not approve a new budget. Explicit approval records the new ceiling and total.
6. An already useful database result still causes fresh live discovery. Exercise broad pools, separate retained top-ten lists, fewer-than-three outcomes, catalog eligibility, rejected-candidate retention and exclusion from selectable responses.
7. Reject absent axes, package dimensions, ambiguous variants, invented measurements and ambiguous packs. Exercise supported unit conversion, exact-variant evidence reuse, seven-day expiry and combined dimension/offer refresh.
8. Check selected stale offers after 24 hours or a missing timestamp. Exercise unavailable, changed-price, over-budget and inaccessible-page outcomes; inaccessible does not mean out of stock. Enforce one transient retry and retained diagnostics.
9. Exercise the optional refresh cutoff below, at and above five points, alongside mandatory selected-offer verification and insufficient-choice fallback. Compare only scores sharing the current benchmark and decision context.
10. Exercise comparable grouping, merchant deduplication, sparse-evidence neutrality, shared benchmark updates and relative value distinct from absolute affordability. Verify stored explanations and historical snapshots remain stable.
11. Exercise full-price whole-pack purchase totals and paid surplus, feasible seating based on physical units, removed purchase lines and budget changes caused by edits. Existing furniture/tax/shipping do not enter purchase totals.
12. Find more appends up to three unseen eligible options and keeps the selected item and saved version unchanged. Later selection validates against the intended parent/layout rather than trusting an obsolete search result.
13. Partial detection failures record diagnostics and continue with available observations. No usable room boundary produces recovery/rescan/sample behavior rather than an invented valid Scene.
14. Placement conflicts trigger sequential repair or an equivalent candidate. A material change to an explicit choice/must-have produces a targeted persisted question. Known invalid layouts are never saved as final designs.
15. Chat resolves selected-item references or asks a quick clarification. Swap fits the existing pose and budget. Removal re-evaluates support/anchor dependents, and the action plus necessary consequences forms one undoable child version.
16. Completed chat/swap/remove actions create immutable children; Undo and branching preserve earlier scenes, dimension/price snapshots and original scan references. Reopening does not auto-resize or silently refresh totals.
17. Duplicate answers, repeated worker deliveries, dispatch failure, process restart and connection loss produce the same logical outcome without duplicate designs/options/purchases. An actual recoverable failure retains the request and evidence.
18. Advancing beyond 90 seconds does not cause failure or publish unverified results. Cancel prevents further publication while retaining the previous design and candidate diagnostics. App closure alone does not cancel.
19. Complete Scene and shopping-list responses contain enough data for full room rendering, selected identity/rank, alternatives, purchases/surplus, warnings, seats, evidence/check times and exact Buy links.
20. Access through device grouping requires no sign-in. Server-side credentials and private capture storage do not become public response content.

### Focused calculation tests

Use small deterministic tests only where they add clarity beyond the API scenarios: decimal purchase arithmetic and whole-pack rounding; dimension unit/axis conversion; the 60/30/10 score; median-relative value with 75/50/25 examples and 0–100 bounds; neutral sparse evidence; and greater-than-five-point boundary behavior. These test domain outputs and invariants rather than mirroring helper implementations.

### Live integration and acceptance

- Validate actual Gemini tool/structured output against the allowed actions, IDs and schemas, with representative intents and malformed output. Verify concrete model IDs and provider access rather than relying on historical descriptions.
- Exercise representative real shopping queries and merchant pages through deployed Playwright. Verify exact-variant measurements, images, offer availability, source links and provider-cache behavior. Fixture success alone does not establish merchant coverage or live freshness.
- Validate Cloud Run browser dependencies and Cloud Tasks continuation/retry against real Postgres/storage. Close/reopen the app, restart a worker and confirm recovery; distinguish a user-input wait from background work.
- Have H1/H2 provide real native capture fixtures with poses, intrinsics, available depth and stable IDs. Verify coordinate alignment/calibration, partial detection recovery and placement on representative home/business rooms.
- Validate USDZ conversion, textures, origin/orientation and physical scaling in RealityKit, including fallback stand-ins and flat panels. Check full-room rendering, Before/After, navigation, lighting, frame rate and local preview responsiveness on the agreed hardware.
- Demonstrate live home redesign, a business seating/budget case, swap/remove/chat/Undo, Find more, Buy and share through a TestFlight-compatible build. Sample rooms and recordings are recovery aids; they do not replace this gate.
- Record generation latency, extraction success, query/browser/model usage and cloud cost. Do not treat the 90-second goal or old cost estimates as measured results.

## Out of Scope

- Concurrent H2 lifting/reconstruction/placement during questions, parallel speculative branches, overlapping per-room operations and future dependency-graph reconciliation. Serial durable cloud jobs remain in scope.
- Cross-room preference profiles/reuse and a previous-preferences UI. Questions, answers and histories for the current generation/room must still be stored.
- User accounts/login, a new authentication/authorization project, shared app-key gating and payment/checkout flows. Existing input validation, server-side secrets and private capture storage remain required.
- Direct furniture dragging or direct rotation. AI/chat-directed moves and camera navigation remain supported.
- Live camera AR placement, erasing real furniture from camera images, photorealistic room reconstruction, textured meshes/Gaussian splats and multi-room scanning.
- On-demand 3D generation for live shopping results, optional photoreal inspiration images and model-based review of rendered scenes. Offline catalog SPAR3D preparation remains in scope.
- Android, hosted public web sharing, Amazon product API integration and an added commerce backend.
- Additional agent frameworks, multi-agent runtime, microservices, Kubernetes, ORM/migration tooling, time-series/vector infrastructure or unsolicited abstractions.
- Implementation schedules, hackathon time plans, future-version grilling and assumptions from deleted historical documents.

## Further Notes

### Readiness and publication

Product and initial agent-architecture decisions are agreed. The primary API testing seam and focused calculation/live integration supplements were explicitly confirmed during this synthesis. No additional product interview is required to prepare this issue.

The repository is a starter, and the implementation, provider credentials, native capture handoffs, rendering and operating costs remain unverified. These are implementation/integration checks, not claims of completed work. Use the accepted behavior to finish concrete schemas and fixtures; ask only if new evidence exposes a material unresolved initial-version decision.

The requested triage label is **ready-for-agent**. No project issue-tracker/triage configuration was found in the available project instructions. The to-spec skill requires running **/setup-matt-pocock-skills** before publication when that configuration is missing. This document is the local issue-ready artifact; it must not be described as a published issue until creation is verified.

### Architectural rationale

- **Verify dimensions before choice/placement:** actual sizes determine useful recommendations and physical fit. Estimate-now/enrich-later would invalidate a selected product or saved layout. Retain rejected evidence rather than guessing dimensions.
- **Immutable design versions:** completed edits, swaps and removals create children so Undo has one consistent unit and historical rooms/products remain stable.
- **Persist work beyond HTTP lifetime:** live extraction and human answers exceed a single request's lifecycle. Store logical progress and execute bounded retryable cloud steps; 90 seconds is a goal, not a deadline.
- **Separate evolving interaction from saved results:** store questions, answers, selections and evidence independently of completed Scenes. The initial version runs sequentially with deferred H2; concurrency proposals remain future-only.

### Domain glossary

A room redesign combines an observed room with a proposed arrangement of existing furniture and real products.

**RoomPlan**:
The room-capture layer providing measured room structure and recognized large objects. It works alongside the separate Perceptron detection layer.

**Perceptron Mk1 detection**:
An additional observation of objects or room features from a scan image. These observations complement RoomPlan's recognized objects.

**Original room**:
The captured room and its existing objects before redesign choices are applied. It remains the reference for Before/After.

**Design**:
A proposed arrangement of existing furniture and selected products for a room.

**Design version**:
An immutable saved state of a design. A completed chat change, swap or removal produces a new version; Undo returns to the preceding version.
_Avoid_: Mutable snapshot

**Keep**:
A user choice requiring the AI to preserve an existing object's position and presence in the design. The user may explicitly change this choice.

**Remove**:
A user choice excluding an item from the proposed design. Removing an existing object preserves it in the original room.
_Avoid_: Delete detection

**Product candidate**:
A stored catalog or shopping result being considered for a design, including results with missing measurements. A retained candidate is not necessarily eligible to appear as an option.

**Candidate pool**:
The broader retrieved database or live-search results before ranking narrows them. Retain discovered candidates even when they do not make the shortlist.

**Source shortlist**:
Up to ten ranked candidates retained for each of database and live search, with search context, evidence, explanations and eligibility state. Provisional candidates are internal until verified.

**Offer check**:
Verification of a particular merchant's price and availability for an exact variant. It has a separate timestamp and 24-hour freshness window from seven-day dimension evidence.

**Generation**:
Persisted logical work producing a design or search result. It survives app disconnection and worker restarts and has no overall elapsed-time cutoff.

**Interactive planning loop**:
The repeated process of finding evidence, presenting meaningful decisions and incorporating answers. In this initial version it runs sequentially; H2 processing starts only after answers and listing selections are finalized.

**Room-use priorities**:
The user's activities, desired experience and relative importance of competing outcomes. They guide planning and trade-offs rather than limiting the interview to aesthetic style labels.

**Trade-off question**:
An easy-to-answer question clarifying a meaningful priority or practical consequence of a proposed arrangement. Concrete product trade-offs use verified listing evidence; most aim to work within the approved budget.

**Decision revision**:
The current set of planning choices and user answers. Dependent work identifies the revision it used; revising a decision does not mutate an already saved design version.

**Measured room context**:
The available spatial measurements already produced by the native room scan, including dimensions, measured features and their uncertainty. Gemini receives this before the interactive loop; it is distinct from the later fused RoomModel and validated layout.

**Product-verified choice**:
A listing with verified physical dimensions and an acceptable checked offer that can be discussed and selected during the interview. In the initial version, room fit remains pending until deferred spatial validation; this is not yet a placed design item.

**Eligible product**:
A candidate whose required actual dimensions, price and applicable design constraints have been satisfied. Only eligible products can enter a design or its selectable options.

**Rejected candidate**:
A stored candidate currently excluded from selectable options, with the missing measurements or other rejection reason recorded. Rejection does not delete the product record.

**Verified product dimensions**:
Actual product measurements supported by source information, rather than estimated from a title or image. Package measurements do not qualify as product dimensions.
_Avoid_: Estimated size, model-inferred dimensions

**Swap alternative**:
Another eligible product offered in place of a selected product. The initial ranked top three contains the main product and two alternatives, or fewer when suitable products are unavailable.

**Find more**:
An explicit request to search for additional eligible products for an item. Discovering options does not itself select a replacement.

**Relative value**:
A candidate's price advantage or premium compared with similar discovered listings, separate from its absolute cost and affordability within the room budget. The comparison evidence must be retained.

**Purchase offer**:
A merchant's purchasable listing for an exact product variant or verified pack, with a price and supplied contents.

**Placed unit**:
A physical item represented in the room. One purchased pack can supply multiple placed units; unplaced purchased units remain part of the cost and are shown as surplus.

**Purchase total**:
The sum of actual offer prices multiplied by purchased quantities for new products, including whole packs and paid surplus, in USD. It excludes existing furniture, removed purchase lines, tax and shipping; placed-unit count alone does not determine the bill.

**Seating target**:
The desired total number of seats, including retained existing seating. A design reports the feasible count and any shortfall while respecting the budget and spatial constraints.

### Accepted decision history

Later corrections take precedence. Superseded or deferred entries document the conversation; the Implementation Decisions above define this initial version.

| Question | State | Decision or remaining issue |
|---|---|---|
| Q1 H3 boundary | Settled | Full H3 lane plus its shared contracts and integration; H1/H2 retain their implementation ownership. |
| Q2 Source documents | Settled, updated | Use only the current source SPEC.md. All interview refinements and future questions are recorded in h3spec.md; ignore deleted specifications. |
| Q3 Completion scope | Settled | All H3 P0/P1 work and required integration; P2 remains optional. |
| Q4 Schedule | Settled | Ignore build time plans and focus on the coding project. |
| Q5 Live acceptance | Settled | Real end-to-end path required; fixtures and sample rooms support development and recovery. |
| Q6 Access | Settled | Anyone can scan and view results without sign-in; no authentication project. Device ID organizes My spaces. |
| Q7 Scan completion | Settled, version-adjusted by Q55 | Capture must finish first. In the initial version, questions/listing selection precede deferred H2 processing; partial detection failure remains nonblocking. Final room fit is checked before rendering. |
| Q8 Keep/Remove | Settled | Keep constrains AI changes. Remove excludes furniture from the design while preserving the original room. |
| Q9 Budget | Settled | US/USD, actual price × quantity, excluding existing furniture, tax and shipping; enforce the budget. |
| Q10 Seating | Settled | Return feasible seating including retained seats; explain shortfalls without relaxing constraints. |
| Q11 Undo | Settled, corrected | Chat, swap and removal each create a child version. Direct furniture dragging is removed. |
| Q12 Invalid dragging | Closed | Not applicable because direct furniture dragging/rotation is outside scope. |
| Q13 Dimensions | Settled, replaced | Actual dimensions must be verified before placement; live shopping candidates require Playwright extraction. No estimated placement followed by later resizing. |
| Q14 Alternatives | Settled, extended by Q22 | Initial ranked top three includes the selected product and two alternatives; fewer are allowed when insufficient eligible products exist. |
| Q15 Partial detection failure | Settled | RoomPlan and Perceptron Mk1 are complementary detection layers. Log failed detection work and continue with available data; no blocking error or confirmation. |
| Q16 Verification evidence | Settled | Retailer/manufacturer evidence for the exact selected variant; preserve source URL, identity, measurement labels and units. LLM extraction cannot invent values. |
| Q17 Missing dimensions | Settled | Reject products missing required physical dimensions from options, but retain candidates and log missing fields/reasons. |
| Q18 No verified match | Settled | Try further candidates, then suitable verified catalog fallback; omit with explanation or return no-match when nothing useful qualifies. Preserve the room/current design. |
| Q19 Live-search wait | Settled, corrected | 90 seconds is a performance goal only. No overall maximum duration or failure/error caused by exceeding it. |
| Q20 Cloud hosting | Settled | Host the live MVP in the cloud wherever feasible, including extraction, for distribution through TestFlight beta links. |
| Q21 Product cache | Settled, extended | Persist all discovered products/candidates; consult the database every search. Exact-variant dimensions stay fresh seven days. Q23 requires live exploration every time; Q26 sets separate 24-hour offer checks. |
| Q22 Ranked choices and more | Settled, extended | Initially show three eligible choices including the main item. Find more explores again. Alternatives must fit the current placement and budget. Q24–Q26 define broader search, retained rankings and refreshes. |
| Q23 Database versus live search | Settled, corrected | Always explore fresh live results and compare with suitable database matches, even when the database already has three good candidates. |
| Q24 Ranking | Settled, superseded in detail by Q49 | Hard eligibility filters; shared practical/style/relative-value score with retained comparisons. Q29 rejects mandatory cheaper/style slots. Absolute price is used for budget and downstream trade-offs, not raw-cheapness scoring. |
| Q25 Find more behavior | Settled, expanded | Gather broad pools, retain candidates and rankings, append up to three unseen eligible choices, preserve selection; create a design version only on swap. |
| Q26 Offer freshness | Settled, expanded | Store top ten per source after broad discovery, show three. Refresh shortlisted database offers older than one day using Playwright; replace failed choices and search further database batches only while competitive with fresh live results. Q45 sets the greater-than-five-point threshold for optional additional refreshes. Saved totals retain snapshot/check time. |
| Q27 Beta interruption recovery | Settled | Persist generation and let it finish/reopen after app/network interruption. Supersedes the no-background-jobs baseline. |
| Q28 Discovery breadth | Settled | Up to 50 relevant database candidates and three materially different live queries per item/pass; collect broadly before narrowing, use fewer when sources are exhausted. |
| Q29 Three displayed winners | Settled, corrected | Cheaper/style labels are recommendations when supported, never compulsory slots. Select the best eligible choices for current preferences; user correction labeled 28 applies to these categories. |
| Q30 Product versus merchant identity | Settled | One option per reliably identified exact physical variant, multiple merchant offers underneath, cheapest eligible offer; distinct sizes/colors remain variants. |
| Q31 Ranking details in the app | Settled | Concise comparisons on cards; expandable evidence/component scores labeled as judgments within this search. |
| Q32 Extraction retries | Settled | One retry for a transient failure, then retain/log and continue. No repeat retries for missing measurements/confirmed unavailable offers within a search; later searches may reconsider. |
| Q33 Cancellation | Settled | Explicit Cancel stops further work/publication; preserve existing design/data and ignore late publication. App closure does not cancel. |
| Q34 No usable geometry | Settled | Automatic recovery, then rescan/sample choice if geometry remains unusable. Partial detection failures still continue without blocking. |
| Q35 Cloud job dispatch | Settled | Cloud Tasks plus Cloud Run and durable Postgres state, idempotent checkpoints and no overall generation time cutoff. |
| Q36 Interaction start | Superseded for initial version by Q55 | Initial questions start after capture; H2 no longer runs concurrently. Product-verified choices may be discussed with room fit pending. |
| Q37 Participation/no answer | Settled via Q61 | Wait at the saved question for Answer, Skip or Decide for me; no independent work runs behind it. App closure preserves the question. |
| Q38 Question formats | Settled, refined | One active question; prioritize frictionless choice cards/chips/image comparisons and numeric budget controls. Free text is optional and secondary; no typing needed to finish. Revisit answers. |
| Q39 Understanding and budget trade-offs | Settled, expanded | Start with fundamental room-use/priority questions; favor practical within-budget reallocations over repeated product-choice prompts. Ask for a budget increase only when strongly justified, with explicit new ceiling/total approval. |
| Q40 Revised decisions | Settled, simplified for initial version | Store answer history; apply changes between serial steps, complete/cancel active work first, preserve retry/stage checks. Completed design changes create child versions. Parallel branch reconciliation is deferred. |
| Q41 Listing evidence in questions | Settled, version-adjusted | Dimensions and checked offers required; initial-version room fit is explicitly pending until H2. Budget proposals remain labeled/approval-gated. Unverified dimensions remain internal. |
| Q42 Loop completion | Settled | Finish automatically when preferences are resolved/delegated and products/placement are valid. No filler questions, fixed question count or duration cutoff. |
| Q43 Parallel branch work | Deferred; excluded from initial version | Earlier concurrent independent/two-branch preparation applies only to future development. No H2 tasks or speculative branches during initial-version questions. |
| Q44 Refresh cutoff | Settled via Q45 | Compare against weakest current eligible choice; optional extra database refresh requires a greater-than-five-point improvement. Never bypass selected-offer freshness checks; continue useful fallback when fewer than three choices exist. |
| Q45 Five-point inequality | Settled | On a shared 0–100 scale, an optional additional refresh needs >5 points of improvement. At cutoff 80, skip 84/85, check 86. Mandatory selected-offer checks still apply. |
| Q46 Opening questions | Settled | Adaptive soft target of three activity/occupancy/priority questions; skip known answers and adapt to home/business. No fixed quota or cap. |
| Q47 Preference versus constraint | Settled | Soft priorities by default; explicit must-have/avoid answers become hard constraints. Ask to resolve incompatible requirements rather than silently relaxing them. |
| Q48 Preference reuse | Excluded for this version | No cross-room reuse/profile flow. Persist all questions, answers, revisions and related context for current-room generation/history. |
| Q49 Shared score | Settled, corrected | 60% practical/request fit, 30% style, 10% relative value against similar discovered listings. Rendering breaks ties. Absolute price drives budget eligibility and later trade-offs, not a raw-cheapest value score. Q52–Q54 define comparison evidence and Q63 defines the value mapping. |
| Q50 Whole-room trade-offs | Settled | Compare complete affected purchase sets, costs and use/seating consequences; reallocate item budgets within the approved total. |
| Q51 Packs and quantities | Settled | Purchase whole packs and count full cost; verify contents and component dimensions, disclose surplus and retain rejected ambiguous bundles. |
| Q52 Comparable products | Settled | Groups based on function/size/known features/condition, both sources, deduplicated median and verified per-unit normalization. Retain evidence; no price-only grouping. |
| Q53 Sparse value evidence | Settled | Three other distinct comparable products with recent usable prices; otherwise neutral 50/100 and an insufficient-evidence label. Stale-price comparisons remain provisional. |
| Q54 Comparison snapshots | Settled | One benchmark snapshot per completed ranking batch; rerank both sources together when evidence changes. Do not compare different snapshots or rewrite saved history. |
| Q55 Initial versus future orchestration | Settled, scope correction | Initial version uses serial question/answer/search steps; finalize listings then perform H2 processing/spatial validation. No concurrent lifting, speculative branches or overlapping-task orchestration. Earlier overlapping-edit design is future-only. |
| Q56 Ambiguous chat references | Settled | Use selected item when available; otherwise quick image/label clarification. Broad requests affect the plan while preserving hard constraints. |
| Q57 Dependent removals | Settled | Revalidate affected anchors; valid relocation or explained optional omission, ask before changing must-haves. Save all consequences as one child version and recalculate packs/seating. |
| Q58 Initial agent runtime | Settled | Direct official Gemini SDK plus one serial Python/FastAPI controller and persisted stages; no additional orchestration service/framework required. |
| Q59 Model tools/backend authority | Settled | search_products, ask_user and finalize_selection; backend executes and validates. Supply measured scan context and verified listing specs before reasoning; deferred H2 runs after selection. |
| Q60 UI and durable execution | Settled | Answer POST/status polling, Postgres state and sequential Cloud Tasks continuation; release workers while waiting. |
| Q61 Serial unanswered behavior | Settled | Wait for Answer, Skip or Decide for me; app closure preserves the question and does not authorize spatial processing or extra spending. |
| Q62 Spatial evidence before the loop | Settled correction; residual recovery in Q64 | Native LiDAR/RoomPlan room measurements and verified listing specifications must be inputs before the interactive Gemini loop. Preserve scan context and add new verified listing dimensions before each product reasoning turn. Heavy H2 lifting remains deferred; Q64 defines residual failure recovery. |
| Q63 Relative-value mapping | Settled | value = clamp(50 + 100 × (1 − price/comparable_median), 0, 100), with neutral 50 for insufficient evidence; component weight 10%. |
| Q64 Residual fit recovery | Settled | Repair placement or try a verified equivalent preserving accepted requirements/budget, then revalidate sequentially. Ask a targeted question for material changes to explicit choices/must-haves. Never publish invalid fit. |
