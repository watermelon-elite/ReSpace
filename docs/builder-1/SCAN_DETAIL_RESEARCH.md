# Making ReSpace room scans recognizable

Research date: October 17, 2026. Research and implementation proposal only; application code was not changed for this investigation.

## Recommendation

Start by rendering recognizable furniture models from the categories and attributes that RoomPlan already detects. Keep RoomPlan’s measured placement and dimensions, the existing sampled colors, and the 3D-only viewer. A detected chair should have a seat, legs and back; a table should have a top and base. Apple provides `CapturedRoom.ModelProvider` specifically to replace object bounding boxes with category/attribute-matched models. The application must supply the model assets. These models represent the detected furniture type; they do not establish the exact shape of the original furniture. [Apple: ModelProvider](https://developer.apple.com/documentation/roomplan/capturedroom/modelprovider)

If the requirement later becomes preserving the actual furniture’s shape, investigate ARKit mesh capture as a separate second phase. Photogrammetry is another option for selected objects or areas, with a more demanding capture and processing workflow.

## What the current app saves and displays

These findings come from the current ReSpace source, rather than assumptions about Apple’s sample apps:

| Code evidence | Current behavior and consequence |
| --- | --- |
| [FrameEncoder.swift](/Users/kdieguez/Documents/Projects/ReSpace/ReSpace/Capture/FrameEncoder.swift:74) | Local preview export uses `.parametric`. Furniture is displayed through the simplified RoomPlan export. |
| [CaptureController.swift](/Users/kdieguez/Documents/Projects/ReSpace/ReSpace/Capture/CaptureController.swift:165) | `RoomBuilder(options: [.beautifyObjects])` is already enabled. Enabling this option again will not add detailed furniture geometry. |
| [FrameEncoder.swift](/Users/kdieguez/Documents/Projects/ReSpace/ReSpace/Capture/FrameEncoder.swift:11) | The app saves RGB JPEGs, matching camera calibration and poses, and optional depth. JPEGs have a maximum edge of 1280 pixels and quality 0.7. |
| [SamplingPolicy.swift](/Users/kdieguez/Documents/Projects/ReSpace/ReSpace/Domain/SamplingPolicy.swift:18) | At most 40 keyframes are retained. This is a bounded observation pipeline, not a dedicated photogrammetry capture workflow. |
| [CaptureController.swift](/Users/kdieguez/Documents/Projects/ReSpace/ReSpace/Capture/CaptureController.swift:16) | Capture uses the default RoomCaptureView/session. No explicit mesh reconstruction configuration or mesh-anchor persistence is implemented. |
| [RoomColorizer.swift](/Users/kdieguez/Documents/Projects/ReSpace/ReSpace/Rendering/RoomColorizer.swift:15) | The viewer estimates diffuse colors for existing geometry. It does not add geometry, texture detail, or object identification. |
| [StandinFactory.swift](/Users/kdieguez/Documents/Projects/ReSpace/ReSpace/Rendering/StandinFactory.swift:5) and [RoomSceneController.swift](/Users/kdieguez/Documents/Projects/ReSpace/ReSpace/Rendering/RoomSceneController.swift:163) | The backend review/design renderer already has simple recognizable category models. The local saved-room viewer does not use this rendering path. |
| [FrameEncoder.swift](/Users/kdieguez/Documents/Projects/ReSpace/ReSpace/Capture/FrameEncoder.swift:72) | Processed `CapturedRoom` JSON is retained. The original opaque `CapturedRoomData` is not persisted. A new export can use saved categories/attributes, but cannot recover discarded detailed surface measurements. |

No bundled USDZ furniture model library was found in the repository. Adding a model library, or authoring suitable procedural assets, is part of implementation.

## What Apple’s APIs can provide

### RoomPlan: recognized furniture and better exported representation

RoomPlan objects expose category, dimensions, transform, identifier, confidence and attributes. Attributes describe distinctions such as chair type, chair legs/back/arms, sofa type, and table type/shape. They can drive more specific model selection. For example, the supported table-shape values include rectangular, circular/elliptical and L-shaped. Classification can still be unidentified or incorrect; the interface should allow a user to inspect and correct a label. [Apple: Captured object attributes](https://developer.apple.com/documentation/roomplan/captured-object-attributes), [table shapes](https://developer.apple.com/documentation/roomplan/tableshapetype)

The export options have different purposes:

| Export option | Relevant result |
| --- | --- |
| `.parametric` | Editable parametric representation. |
| `.mesh` | Mesh representation of RoomPlan’s surfaces/objects, including polygonal walls, cut openings and certain recesses. |
| `.model` | Supports supplied ModelProvider furniture models, alongside the richer room-surface representation. |

Changing `.parametric` to `.mesh` alone does not capture a detailed LiDAR replica of furniture. The export-format table and the separate ModelProvider mechanism establish that these are distinct capabilities. [Apple: USDExportOptions](https://developer.apple.com/documentation/roomplan/capturedroom/usdexportoptions)

`beautifyObjects` realigns groups of chairs around a table and can unify their attributes. It is an arrangement/appearance adjustment, not a switch for higher-resolution scanning. Because ReSpace already uses it, compare its effect on positional fidelity before changing it. The original unprocessed capture is not currently retained for later rebuilding. [Apple: beautifyObjects](https://developer.apple.com/documentation/roomplan/roombuilder/configurationoptions/beautifyobjects)

RoomPlan can also export a metadata mapping from USDZ node names to CapturedRoom element UUIDs. This supports reliable object selection, category labels and applying the correct sampled color after replacing a box with a model. Apple demonstrates metadata mapping and model export in its RoomPlan session. [Apple: Explore enhancements to RoomPlan, export discussion](https://developer.apple.com/videos/play/wwdc2023/10192/?time=951)

### ARKit: measured surface geometry

ARKit scene reconstruction provides a polygonal approximation of the environment. Its mesh exposes vertices, normals, faces and optional face classifications. It does not expose a ready-made textured-room asset through ARMeshGeometry; sampling camera colors or building UV textures is additional application work. This last point follows from the documented geometry API surface. [Apple: sceneReconstruction](https://developer.apple.com/documentation/arkit/arworldtrackingconfiguration/scenereconstruction), [ARMeshGeometry](https://developer.apple.com/documentation/arkit/armeshgeometry)

The iOS `ARMeshClassification` API identifies faces as wall, floor, ceiling, table, seat, window, door or none. These are face labels, not persistent identities for separate chairs or tables. Associating the mesh with editable furniture objects would require additional logic, preferably using RoomPlan’s object records. Do not confuse this API with newer visionOS/C classification APIs that expose other categories. [Apple: ARMeshClassification](https://developer.apple.com/documentation/arkit/armeshclassification)

RoomPlan supports a custom ARSession. Apple requires the app to run it with ARWorldTrackingConfiguration before passing it to `RoomCaptureView(frame:arSession:)`, and documents that the settings are preserved. This makes a shared RoomPlan/ARKit capture architecture supported. Actual mesh quality and resource use still need a device trial. [Apple: custom ARSession initializer](https://developer.apple.com/documentation/roomplan/roomcaptureview/init(frame:arsession:))

### Object Capture: actual appearance with a separate capture workflow

RealityKit Object Capture reconstructs objects from overlapping photographs. Both image capture and reconstruction are available on supported iOS devices; reconstruction is not exclusively a Mac feature. Check the relevant `isSupported` properties at runtime. [Apple: ObjectCaptureSession](https://developer.apple.com/documentation/realitykit/objectcapturesession)

Area mode, introduced in iOS 18, supports surfaces and subjects that cannot be walked around completely. Apple warns that areas larger than six feet may lose mesh/texture quality unless reconstructed at a higher detail level on Mac. Area mode is a valid experiment for room sections, but this evidence does not establish that a quick whole-room pass will yield crisp furniture throughout the room. [Apple: Discover area mode for Object Capture](https://developer.apple.com/videos/play/wwdc2024/10107/)

Apple currently documents only `.reduced` reconstruction detail on iOS; higher detail options are available on macOS. That affects how much detail can be distributed across a room-sized result. [Apple: PhotogrammetrySession.Request.Detail](https://developer.apple.com/documentation/realitykit/photogrammetrysession/request/detail)

Apple recommends high-resolution photographs, substantial angle coverage and roughly 70% overlap between adjacent images. Thin, shiny, transparent and featureless subjects can be difficult. Our inference: the present 40 downsampled observation frames should not be treated as a validated photogrammetry dataset. A dedicated capture pass would need coverage guidance and quality feedback. [Apple: Capturing photographs for Object Capture](https://developer.apple.com/documentation/realitykit/capturing-photographs-for-realitykit-object-capture)

## Proposed implementation

### First delivery: recognizable furniture in existing scans

1. **Supply a small furniture library.** Start with dining/office chairs, stools, rectangular/round tables, straight/L-shaped sofas, beds and storage. Use authored or appropriately licensed assets, with bounds, axes and units validated against RoomPlan export. Apple’s catalog sample prefers `.usdc` source files; the assembled room can be exported as USDZ. [Apple: custom model sample](https://developer.apple.com/documentation/roomplan/providing-custom-models-for-captured-rooms-and-structure-exports) The exact asset conventions and exporter scaling must be tested rather than assumed.
2. **Choose models from detected semantics.** Use category and supported attribute combinations, with category-only and labeled-box fallbacks. Keep unknown/low-confidence cases distinguishable. The existing StandinFactory can guide a procedural fallback but currently covers fewer variants and belongs to another rendering path.
3. **Export with ModelProvider and `.model`.** Add `metadataURL` mapping for object UUIDs. Preserve the existing saved preview until the new export succeeds. Version the derived preview so an updated asset library can regenerate old local scans from retained CapturedRoom JSON.
4. **Apply color by object identity.** Estimate sampled colors against the original scan representation first, then transfer the result to the corresponding model through its UUID. Sampling photos against invented replacement geometry could introduce color errors. Preserve intentional model material differences where useful.
5. **Add tap identification.** Show category, measured dimensions and confidence for the selected object. Visual recognition and an explicit label should reinforce each other.
6. **Keep model detail separate from measured evidence.** Record which geometry is a representative asset and which properties came from the scan. Do not treat modeled chair legs or a selected chair style as new measurements.

This phase can improve already saved local scans without a new scan, provided their processed RoomPlan JSON is intact. It does not require a new backend or a second camera session. This is the recommended first delivery for the stated goal of telling chairs and tables apart.

### Second delivery: evaluate actual surface capture

Use one shared ARSession configured for supported `.meshWithClassification`, then pass it to RoomCaptureView in Apple’s documented order. Persist bounded copies of current mesh-anchor buffers and transforms, handle updates/removals, and keep them in the same scan coordinate system as RoomPlan and RGB frames. Treat origin loss/interruption as an explicit capture boundary.

Render a measured mesh in the existing 3D-only viewer, with sampled vertex/surface colors. Evaluate mesh density, holes, thin chair legs, table edges and alignment before committing to textured mesh export. Avoid replacing all editable semantic furniture objects with one inseparable room mesh. These are proposed engineering steps, not claims that this capture has been implemented or validated.

For higher visual fidelity on selected furniture or room sections, evaluate a separate Object Capture flow and optionally Mac reconstruction. It adds capture time, processing and alignment work, and should remain a separate product decision.

## Validation before shipping

Use a physical LiDAR iPhone to scan a dining chair, office chair, stool, round table and rectangular table, plus cluttered/partly hidden arrangements. Compare the current and proposed previews from the same viewpoints.

Check category and attribute correctness, recognizable silhouette, correct object UUID on tap, dimensions/orientation, sampled color, missing-asset fallback, save/reopen and old-scan regeneration. Measure frame rate, peak memory, export/load time and sustained capture temperature; no performance results are claimed by this research.

For the mesh experiment, separately verify shared-session behavior, anchor persistence, coordinate alignment, interruption handling and actual improvement to thin geometry. Keep AR as capture infrastructure; the saved-room viewer remains 3D-only.
