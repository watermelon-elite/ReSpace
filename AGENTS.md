# ReSpace

An iPhone app that scans a room (RoomPlan + LiDAR), detects small items (Perceptron Mk1.5), and redesigns the room with real products placed by a Python solver (Gemini plans, the solver places). Hackathon MVP built by three people: H1 iOS & 3D, H2 Perception & Spatial, H3 AI, Products & Backend.

## Map

Keep this map current: when you add or move a doc, add or update its line here in the same change.

### Specs
- [`h3spec.md`](h3spec.md): H3's MVP sub-spec. Read before implementing the sequential Gemini agent, product discovery and verification, ranking, backend persistence or cloud deployment; its cross-builder impact section records required H1/H2 changes.
- [`SPEC.md`](SPEC.md): the governing MVP spec (architecture, user flow, contracts, API, DB, build plan). Frozen until the sub-spec merge; record changes in your own sub-spec under `specs/`.
- [`specs/H2-perception-spatial.md`](specs/H2-perception-spatial.md): H2's sub-spec for `detect`, `normalize_room`, `lift_keyframe`, `merge`, `solve` and `categories.json`. Read its **⚠️ Changes to SPEC.md** table first whenever you touch a contract, the keyframe upload, the RoomModel, DesignPlan or Scene; it overrides SPEC.md for H2's area. Its **Glossary** section holds H2's canonical domain terms (Object, Addition, Anchor, Item, Kept vs Fixed…): use those words in code, docs and prompts.
- [`BUILDER_1_SPEC.md`](BUILDER_1_SPEC.md): H1's sub-spec for the iOS client (capture, navigation, rendering, interactions, API integration), with its own glossary. Read it before changing anything the app sends or renders.
- [`userflow.md`](userflow.md): the original screen-by-screen user flow, a short form of SPEC.md §4.

### Research
Verified facts, each claim tagged confirmed or inferred with its source URL. Read the matching file before writing the code it covers.
- [`specs/H2-research/roomplan-arkit-facts.md`](specs/H2-research/roomplan-arkit-facts.md): Apple `CapturedRoom` JSON shape and enum/simd encoding, RoomPlan/ARKit coordinate frames, wall and object axes, `sceneDepth` availability during RoomPlan, intrinsics and the pixel-to-ray math. For any CapturedRoom parsing, camera or depth code.
- [`specs/H2-research/perceptron-facts.md`](specs/H2-research/perceptron-facts.md): Perceptron API and SDK, model IDs, `annotation_format`, the 0–1000 coordinate grid vs `/v1/detect` pixels, limits and pricing. For any Mk1 call or parsing.

### Code
- [`ReSpace/`](ReSpace/), [`ReSpace.xcodeproj/`](ReSpace.xcodeproj/): the iOS app (H1). Currently the Xcode template skeleton.
