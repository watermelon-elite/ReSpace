# ReSpace

An iPhone app that scans a room (RoomPlan + LiDAR), detects small items (Perceptron Mk1.5), and redesigns the room with real products placed by a Python solver (Gemini plans, the solver places).

## Map

Keep this map current: when you add or move a doc, add or update its line here in the same change.

### Specs
- [`SPEC.md`](SPEC.md): the governing complete product specification. Read before implementing behavior, screens, capture, planning, perception, placement, shopping, rendering, APIs or persistence. It includes the resolved contracts and acceptance criteria; earlier drafts do not override it.
- [`CONTEXT.md`](CONTEXT.md): the canonical domain glossary. Use its distinctions between Objects, Items, Additions, Kept, Fixed, versions, Products and purchases in code, prompts and documentation.
- [`specs/merge-conflicts.md`](specs/merge-conflicts.md): resolved conflict register, source evidence and accepted decisions, including the user's partial-success edit rule. Historical rationale; normative behavior is in `SPEC.md`.
- [`specs/BUILDER_1_SPEC.md`](specs/BUILDER_1_SPEC.md): historical client/capture/rendering specification used in the consolidation; superseded by `SPEC.md`.
- [`specs/H2-perception-spatial.md`](specs/H2-perception-spatial.md): historical perception/geometry/solver specification used in the consolidation; its override table is no longer governing.
- [`specs/h3spec.md`](specs/h3spec.md): historical planning/products/backend specification used in the consolidation; superseded by `SPEC.md`.
- [`specs/room-reconstruction-json.md`](specs/room-reconstruction-json.md): proposal, not yet agreed. Problems found placing Products into the sample room reconstruction's JSON (no yaw, true size, surface heights, wall endpoints, openings; non-registry categories), and a proposed version 2 aligned with `SPEC.md` §12.5, which `backend/respace/reconstruction.py` reads. Read before changing the room export format or the Product placement pipeline that consumes it.
- [`userflow.md`](userflow.md): historical screen-flow sketch; use the complete screen and workflow requirements in `SPEC.md`.

### Research
Verified facts, each claim tagged confirmed or inferred with its source URL. Read the matching file before writing the code it covers.
- [`specs/layout-awareness-side-chat-summary.md`](specs/layout-awareness-side-chat-summary.md): room-layout research, evidence limits and proposed Gemini/H2 integration from the side chat. Read when evaluating layout-awareness changes; proposals are not approved requirements and `SPEC.md` remains governing.
- [`specs/H2-research/roomplan-arkit-facts.md`](specs/H2-research/roomplan-arkit-facts.md): Apple `CapturedRoom` JSON shape and enum/simd encoding, RoomPlan/ARKit coordinate frames, wall and object axes, `sceneDepth` availability during RoomPlan, intrinsics and the pixel-to-ray math. For any CapturedRoom parsing, camera or depth code.
- [`specs/H2-research/perceptron-facts.md`](specs/H2-research/perceptron-facts.md): Perceptron API and SDK, model IDs, `annotation_format`, the 0–1000 coordinate grid vs `/v1/detect` pixels, limits and pricing. For any Mk1 call or parsing.
- [`specs/launch-research/shortlist.md`](specs/launch-research/shortlist.md): twenty priority launch-film references and ReSpace applications. Read when planning the launch film; recommendations are creative inferences, with review coverage stated.
- [`specs/launch-research/candidates.md`](specs/launch-research/candidates.md): all 120 candidates, links, reach evidence and selection reasons; companion JSON preserves structured evidence.
- [`specs/launch-research/footage-previews.md`](specs/launch-research/footage-previews.md): eight automated audiovisual previews, clip limits and editorial corrections. Check before using a scene or timestamp.
- [`specs/launch-research/deep/index.md`](specs/launch-research/deep/index.md): twenty full-film audiovisual reviews, comparison and coverage summary; links each film's editorial analysis, model output (quotation redactions labeled where needed) and coverage record. Read editorial corrections before citing footage.
- [`specs/launch-research/deep/respace-direction.md`](specs/launch-research/deep/respace-direction.md): original ReSpace launch concept, reference mechanisms, proposed film spine and production decisions; creative inferences, not validated performance claims.
- [`specs/launch-research/respace-launch-script-storyboard.md`](specs/launch-research/respace-launch-script-storyboard.md): revised three-minute landscape film, 224-word core narration, 43 timed shots and imagined-future production plan; read when writing or filming the launch. [Critical review](specs/launch-research/respace-script-revision-review.md), [recording copy](specs/launch-research/respace-launch-voiceover.txt), [concept board](specs/launch-research/respace-storyboard-concepts.png) and [image prompt](specs/launch-research/respace-storyboard-image-prompt.txt) accompany it.
- [`specs/launch-research/spatial-discovery.md`](specs/launch-research/spatial-discovery.md), [`specs/launch-research/creative-discovery.md`](specs/launch-research/creative-discovery.md): supporting discovery sources; their preliminary rankings are superseded by the shortlist.

### Engineering conventions

- [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md):
  GitHub issue operations and publication conventions.
- [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md):
  Canonical triage roles and their tracker labels.
- [`docs/agents/domain.md`](docs/agents/domain.md):
  Rules for reading the glossary and architectural decisions.

### Prompts
- [`prompts/layout-reasoning.md`](prompts/layout-reasoning.md): research-backed layout principles, written as Gemini's system prompt for questions, Product choice, Anchor planning, repair and explanations. Edit it when changing how the agent reasons about layouts.

### Code
- [`script/README.md`](script/README.md): contained temporary DS_HQ Script-screen copy, ReSpace narration and visual tracks, local autosave and run instructions. Read when changing the launch-script prototype; independent of the iPhone app.
- [`ReSpace/`](ReSpace/), [`ReSpace.xcodeproj/`](ReSpace.xcodeproj/): the iOS capture, Room review, planning and immutable design client.
- [`ReSpace/DesignSystem.swift`](ReSpace/DesignSystem.swift), [`ReSpace/IntentViews.swift`](ReSpace/IntentViews.swift), [`ReSpace/OperationViews.swift`](ReSpace/OperationViews.swift), [`ReSpace/ProductViews.swift`](ReSpace/ProductViews.swift): DreamSeal presentation components, guided brief/questions and focused Product pages; bundled Inter retains its [license](ReSpace/Resources/Inter-LICENSE.txt).
- [`ReSpace/ShoppingList.swift`](ReSpace/ShoppingList.swift), [`ReSpace/ShoppingListViews.swift`](ReSpace/ShoppingListViews.swift), [`ReSpace/ShoppingShareView.swift`](ReSpace/ShoppingShareView.swift): saved per-Room purchase links, local persistence and native image/text sharing, including placeholder room posts with price labels for Messages and Instagram.
- [`backend/`](backend/): versioned API, durable state, Product verification, perception and deterministic placement; contract and behavior tests are under `backend/tests/`.
- [`backend/README.md`](backend/README.md): local runtime, opt-in model testing, startup instructions and test-data limits, and the room preview pipeline that reads a room reconstruction record, places Products and composes one USDZ (`reconstruction.py`, `composition.py`).
- [`assets/`](assets/): versioned render assets and offline conversion; [`Kenney license`](assets/sources/kenney/LICENSE.txt) records the retained source license.
- [`assets/README.md`](assets/README.md): which parts of `assets/` ship and which do not. Everything there is production except `spar3d/`, which is a laboratory whose output is never committed and never catalog-eligible. Read before treating any file under `assets/` as either shippable or scratch, and before promoting a reconstruction.
- [`assets/spar3d/README.md`](assets/spar3d/README.md): offline SPAR3D image-to-mesh runtime, a capability under evaluation rather than a current source of catalog assets, feeding `assets/prepare.py`. Records gated-weight access, the five upstream packaging workarounds, measured CPU and MPS timings, and why torch cannot be downgraded. Also carries the graded reconstruction quality across thirty products in seven categories — lamps and chairs usable, shelf units and plants not, tables and desks individually, upholstery front-facing only — the unreliable colour on dark and saturated finishes, the automatic orientation (`prepare.py --auto-orient`) that turns, straightens and levels every reconstruction, with the measurements behind it, the measurement showing reconstruction does not parallelize on this hardware, and the two separate virtualenvs. Read before running or changing reconstruction, or before deciding whether a category gets a reconstruction or a stand-in.

## Agent skills

### Issue tracker

Track issues and published specs in GitHub Issues for
`watermelon-elite/ReSpace`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five default triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

Use the root `CONTEXT.md` glossary and `docs/adr/` decisions.
See `docs/agents/domain.md`.
