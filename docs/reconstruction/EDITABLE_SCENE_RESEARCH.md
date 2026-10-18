# Editable reconstructed scenes and Gemini editing

Research checked October 17, 2026 (America/Los_Angeles). This is a research recommendation. The user confirmed permanent single-room scope; preserving actual furniture and decor, explicitly posters, paintings, and whiteboards; movable furniture/decor only; fixed structure with texture/material finishes; seamless generated completion without estimated-region UI; and final-product-only presentation. Lighting and relighting do not matter for acceptance: earlier lighting research and the lighting gate below are excluded from current scope. Broken models lead to rescan, with no cleanup UI; earlier manual segmentation/cleanup review suggestions are superseded by automatic validation. The accepted ceiling is $5 per room and the target is 30 minutes; neither has been measured. Provenance and partial artifacts below are internal records. Remaining decisions are tracked in [the current pipeline](EDITABLE_WALKTHROUGH_PIPELINE.md). No tools below have been benchmarked against a ReSpace scan in this research pass.

## Recommendation and its limits

Use measured geometry, source photographs, and a semantic scene manifest to build **separate textured meshes for the architectural shell and each editable object**. Preserve observed furniture appearance wherever the capture supports it. Gemini proposes semantic edits to stable scene identities; an application-owned solver, geometry checks, and revision service execute them. A generated after-picture does not satisfy this requirement: walking around, reopening, exporting, and undoing must show the same changed geometry/materials.

An optional Gaussian splat can preserve a highly convincing original appearance, but it should not become the sole authority for editable surfaces, object dimensions, collisions, or materials. That is an architecture recommendation, not a claim that splats cannot be edited. Gaussian editing exists; relighting, removing cast shadows, reconstructing unseen surfaces, and compositing changed geometry remain distinct requirements.

The critical distinction is **observed appearance versus completed appearance**. A segmented sofa mesh preserves the scanned upholstery and shape; it may have no back, underside, or complete legs. Moving that mesh can expose missing object surfaces and missing room surfaces simultaneously. Furniture removal therefore requires both a detachable object and a clean room behind it. No single-image completion model establishes the actual unseen geometry.

## Repository evidence and what changes

The current repository already has useful pieces, but does not implement this complete scene:

| Existing file | Evidence | Consequence |
|---|---|---|
| `SPEC.md` §§0–1, 5 | Original MVP explicitly excludes textured meshes/photogrammetry/splats, uses generic furniture, and requires Gemini references plus a placement solver | The user's realistic walkthrough changes that original scope; preserve deterministic placement, revise the fidelity assumptions separately |
| `ReSpace/Rendering/ProcessedRoomScene.swift` | Loads an `MDLAsset` into `SCNScene`; marks all materials double-sided; optionally overlays `inferred.obj` | Useful inspection renderer, but no semantic object/material addressing or valid collision guarantee |
| `ReSpace/Rendering/RoomSceneController.swift` | RealityKit structure and furniture; `SceneItem.id` names entities; assets load asynchronously; virtual camera currently implements orbit/pan/zoom | Existing semantic renderer is a useful integration seam; source textures/scan surfaces are not yet connected to its entities |
| `ReSpace/Domain/DesignModels.swift` | `SceneItem.id`, `originalObjectId`, asset revision, placement, parented `DesignVersion` | Retain logical identities while updating mesh/texture asset revisions; extend material/surface state rather than using array offsets |
| `ReSpace/Domain/OperationModels.swift` | Operation IDs, selected object/item IDs, snapshot and planning revisions, expected active design/revision, undo and clarification types | Good basis for idempotent, grounded, concurrent edits; not evidence that the backing edit service exists |
| `ReSpace/Domain/ReconstructionModels.swift` | Current result requires an OBJ, coordinate system `arkit_scan_meters_y_up`, hashes and bounded asset sizes | Add a versioned scene manifest and mobile assets through a schema migration; do not silently reinterpret an OBJ result as a complete editable scene |
| `services/reconstruction/respace_reconstruction/models.py` | Capture includes calibrated images, poses, optional depth/confidence, scene mesh, RoomPlan export, artifact hashes | Enough data categories to attempt association, subject to coverage/calibration quality; no persisted source-to-entity correspondence yet |

The current `normalized` asset branch scales independent axes to a requested box. That can be useful for stand-ins, but must not distort measured furniture assets or vendor models. Adopt meter-authored geometry with a recorded rigid transform and explicit, bounded uniform-scale policy. A dimension mismatch should trigger review, not silent deformation.

Apple recommends RealityKit after SceneKit's deprecation. Treat a RealityKit migration as a proposed integration direction, keeping the existing SceneKit inspector useful during validation. [Apple migration session](https://developer.apple.com/videos/play/wwdc2025/288/)

## 1. Segmentation and object identity

### Available primary-source tools

| Tool | Verified capability and packaging | Appropriate role |
|---|---|---|
| SAM 2/2.1 | Prompted image masks and multi-object video mask propagation; code/checkpoints Apache 2.0, with separate notices for some optional components | Practical baseline when a detector, RoomPlan projection, or user tap supplies box/point prompts. [Official repository](https://github.com/facebookresearch/sam2) |
| SAM 3/3.1 | Text and visual prompts produce image/video instance masks and tracking; repository lists SAM 3.1 release on March 27, 2026. Gated checkpoint access; Python ≥3.12, PyTorch ≥2.7, CUDA ≥12.6 | Candidate text-driven proposals and tracking on GPU workers, benchmarked against SAM 2. Do not confuse with SAM 3D. [Official repository](https://github.com/facebookresearch/sam3) |
| SAM 3 license | Custom SAM License rather than Apache/MIT; redistribution, restricted-use, and other terms apply | Pin checkpoint/code/license versions before shipping. [Actual license](https://github.com/facebookresearch/sam3/blob/main/LICENSE) |
| OpenMask3D | 3D instance masks plus multi-view CLIP features; accepts point cloud and posed RGB-D frames. Repository code MIT; older environment and model/dependency licenses require separate checking | Research comparator or semantic retrieval layer; not a replacement for mesh extraction and completion. [Official implementation](https://github.com/OpenMask3D/openmask3d) |
| SAI3D | Superpoints and posed-image masks are merged into 3D instances | Evidence that geometry-aware multi-view association is a substantive stage. Repository licensing was not established in this pass; do not adopt by assuming permissive terms. [Paper](https://openaccess.thecvf.com/content/CVPR2024/papers/Yin_SAI3D_Segment_Any_Instance_in_3D_Scenes_CVPR_2024_paper.pdf), [code](https://github.com/yd-yin/SAI3D) |

### Proposed association algorithm

1. Allocate durable `entity_id` values for RoomPlan structures/objects and detected additional instances. Keep source RoomPlan IDs and observations as links, not universal identities. Different scans and processing runs may produce different source IDs.
2. Generate frame masks using calibrated projections of RoomPlan boxes and detector proposals; allow an interactive correction when two touching chairs merge. Track masks through adjacent frames where temporal coverage supports it.
3. Project reconstructed points/triangles into each calibrated image. Accept a mask vote only after image bounds, facing direction, depth visibility, and depth agreement tests. A pixel behind a foreground object is not evidence for the background triangle.
4. Weight votes by depth confidence, view angle, sharpness, mask confidence, and temporal duplication. Use 3D connectedness and measured object extent to associate cross-view instances. Do not merge every chair sharing a semantic category.
5. Resolve wall/furniture boundary ambiguity with small spatial regions/superpoints. Keep an explicit unresolved region where observations disagree. Track coverage by surface, not just count of masks.
6. Persist observation-to-instance and triangle/point-to-instance mappings. Remeshing changes triangle numbers: regenerate correspondence from source geometry instead of treating a face index as a durable user reference.
7. Review low-confidence removable objects. A positive text detection is not sufficient evidence that every object pixel, leg, shadow, and contact boundary is correctly isolated.

These are application algorithms and proposed checks, not capabilities supplied automatically by SAM. Sparse, widely separated keyframes do not behave like a continuous tracking video; geometry-based association must bridge gaps and re-identification.

## 2. Separate room and furniture without losing appearance

**Measured architectural shell.** Fit/retain walls, floors, ceilings, openings, trim, and permanent fixtures as separate identified surfaces. Use RoomPlan as a semantic/metric prior while retaining nonplanar observed geometry where valid. An editable wall face should be independently addressable from the same wall's door, window, skirting, and artwork.

**Observed furniture assets.** Cut confident furniture faces into object-local meshes, retaining source photographs, surface colors, metric bounds, and original pose. At shared boundaries, split triangles/duplicate boundary vertices as necessary; remove their source faces from the room layer. The system must not draw both the old scanned sofa and its moved replacement. Reconstruct uncertain thin legs and contact boundaries separately rather than dissolving them into the floor.

**Textures and material slots.** Preserve valid existing UV coordinates initially; UV seams and material boundaries need duplicate vertices. A shared image atlas can be retained read-only for several independently transformed meshes. Subsequent texture editing needs explicit texel ownership or a rebaked per-object/per-surface atlas so painting one wall cannot alter an unrelated island. Generate UV charts after the relevant topology is stable, bake only visible source observations with occlusion tests, and retain source-frame provenance. xatlas is an MIT-licensed UV library; it generates UV charts and may add vertices at seams, so maintain correspondence. [xatlas](https://github.com/jpcy/xatlas)

**Validation.** Reject non-finite vertices/transforms, invalid indices, zero-area faces, implausible extents, broken texture links, and inverted winding. Report nonmanifold edges, self-intersections, open boundaries, and connected components. Open3D documents topology tests and simplification/cleanup operations; these operations do not establish that a repaired object matches the original. Decorative room meshes may be open, so universal watertightness is an inappropriate acceptance rule; navigation and collision proxies need their own validity rules. [Open3D mesh documentation](https://www.open3d.org/docs/release/tutorial/geometry/mesh.html)

## 3. Removing and moving furniture reveals two kinds of unknowns

For an edit that exposes previously hidden areas, use this proposed order:

1. **Observed elsewhere:** reproject/reconstruct from another captured view where that wall/floor/object surface is visible.
2. **Targeted recapture:** ask for a short additional scan of the exposed area or the object's back when exact fidelity matters and access is possible.
3. **Constrained completion:** extend a measured floor/wall plane within justified boundaries and extrapolate a repeatable material. Never fill through an opening. Mark these geometry and texture regions inferred.
4. **Generative completion, if approved:** complete object backs or complex hidden content conditioned on masks, visible geometry, scale, and neighboring surfaces. Compare the generated visible parts with observations. Reject a candidate that changes the already measured shape to make the hidden part plausible.
5. **Replacement asset:** offer a clearly described catalog/proxy asset if an original object cannot be made convincingly movable. Do not silently substitute a generic sofa and call it the original.

Record separate provenance for geometry and appearance: an observed plane may legitimately have inferred texture; generated object geometry should not become a verified measurement. Inpainting one photograph only repairs one viewpoint. A usable completion must become a texture/geometry asset whose renders remain consistent across viewpoints.

SAM 3D Objects explicitly reconstructs full shape, texture, and layout from a single image and releases code/weights under the custom SAM License. It is a candidate **object completion/generation** stage, not proof that an unseen surface was measured or that the full room is recovered. Its output needs alignment to measured bounds, multi-view checks, and mobile export tests. [Official implementation](https://github.com/facebookresearch/sam-3d-objects), [license](https://github.com/facebookresearch/sam-3d-objects/blob/main/LICENSE)

SPAR3D remains another single-image object reconstruction candidate, including editable point-cloud conditioning; its Community License has commercial registration/attribution conditions and a revenue threshold requiring a separate license. It is not a complete indoor reconstruction pipeline. [Implementation](https://github.com/Stability-AI/stable-point-aware-3d), [actual terms](https://github.com/Stability-AI/stable-point-aware-3d/blob/main/LICENSE.md)

TRELLIS offers image/text-conditioned assets and multiple output representations. Its models and most code are MIT, but the authors identify differently licensed submodules; audit the exact mesh-generation execution path rather than treating every dependency as MIT. Generated assets still need metric/fidelity checks. [Official implementation and license section](https://github.com/microsoft/TRELLIS)

For new or replacement retail products, prefer licensed vendor-authored meshes with verified dimensions/materials. Store asset usage and redistribution rights independently from the product listing. A listing photo or purchase URL does not by itself establish rights to distribute a 3D model. Record any generated asset as an approximation rather than a geometrically exact SKU.

## 4. Photorealism, wall repainting, and changing light

Photo textures contain the photographed illumination, highlights, shadows, and sometimes reflections. A plain wall recolor can preserve the old sofa's shadow; moving a lamp can leave its old illumination painted into the wall. Distinguish an attractive view under captured lighting from physically responsive materials.

A proposed staged implementation is: preserve observed textures for the original appearance; use independently parameterized wall/floor materials for recoloring; fit simple lighting and neutralize obvious baked shadows locally; then investigate inverse rendering if realistic relighting becomes a hard requirement. Mark the relighting approximation in the capability/quality report. Never claim merely loading RGB textures into PBR materials separates reflectance from illumination.

IRIS is primary research demonstrating recovery of materials, spatially varying HDR lighting, and camera response from posed LDR images. It establishes the problem and a possible research direction; its paper results are not an implementation, latency, or robustness guarantee for ReSpace. [IRIS project](https://irisldr.github.io/), [CVPR paper](https://openaccess.thecvf.com/content/CVPR2025/papers/Lin_IRIS_Inverse_Rendering_of_Indoor_Scenes_from_Low_Dynamic_Range_CVPR_2025_paper.pdf)

RealityKit supports base color textures plus roughness, metallic, normal and other material properties. USDZ import creates PBR materials, and code can modify them at runtime. This provides a concrete target for approved wall/material edits; it does not supply inverse rendering. [Apple PBR material documentation](https://developer.apple.com/documentation/realitykit/physicallybasedmaterial), [material and lighting guide](https://developer.apple.com/documentation/realitykit/applying-realistic-material-and-lighting-effects-to-entities)

## 5. Data ownership and persistent edit contracts

Proposed service contracts, independent of renderer:

| Record | Owner and required contract |
|---|---|
| `CaptureBundle` | Immutable capture service output: capture ID, calibration/conventions, source artifact hashes, timestamps, sensor validity. User edits never overwrite this evidence |
| `ReconstructionRevision` | Worker-owned immutable revision: input hash, pipeline/model/checkpoint versions, aligned source transforms, quality report, dependency/license manifest, entity proposals, mappings, render/collision assets |
| `SceneEntity` | Scene service owns stable ID, semantic category/label, source object links, original pose, measured bounds, capabilities, geometry/appearance provenance and coverage. Asset versions may change without renaming the object |
| `SurfaceBinding` | Entity ID plus stable semantic surface/material-slot ID, immutable mesh and UV revision, editable material fields; explicit mapping to current export primitive/submesh. Face/texture index is revision-local |
| `SceneAsset` | Immutable content hash/revision, format, units, coordinate frame, pivot, authored bounds, texture/color-space metadata, LOD, source/license record. URLs are delivery locations, not identities |
| `SceneRevision` | Scene service owns parent revision, base reconstruction revision, active assets, transforms, material overrides, visibility, lights and navigation/collision revisions. Every approved edit has a complete replayable result |
| `EditOperation` | Operation service owns idempotency key, base/expected active revision, requester context, selected IDs, proposed semantic commands, solver output, validations, warnings, resulting revision and terminal state |

Reprocessing a capture creates a new reconstruction revision. It does not mutate an edited scene under the user: reconcile entities via evidence, preserve IDs for confirmed matches, tombstone removed IDs, and explicitly resolve ambiguous matches before replaying dependent edits. Keep `RoomSnapshot` evidence and `DesignVersion` intent distinct.

Authoring USD is a reasonable interchange option because its composition model supports references and non-destructive overrides. Keep the database scene manifest as application authority, and generate platform deliverables from it. USD explicitly does not supply persistent GUIDs; retain ReSpace IDs in metadata and the manifest. [OpenUSD introduction](https://openusd.org/release/intro.html), [referencing layers](https://openusd.org/release/tut_referencing_layers.html)

RealityKit loads USD/USDZ/Reality files and preserves the imported hierarchy. Do not assume GLB, OBJ, or Gaussian PLY can be fed directly to that loader with the same edit semantics. Generate and device-test USDZ and keep optional GLB as a separate exchange artifact. [Apple entity loading](https://developer.apple.com/documentation/realitykit/loading-entities-from-a-file)

## 6. Gemini proposes semantic commands; ReSpace commits revisions

Gemini's function calling returns function names/arguments; the application executes the function and returns its result. Structured output helps enforce JSON shape but Google explicitly requires validation of semantic values. A successful model response is therefore not a committed scene edit. [Function calling](https://ai.google.dev/gemini-api/docs/function-calling), [structured outputs and validation](https://ai.google.dev/gemini-api/docs/structured-output)

Send Gemini a compact current scene manifest, selected entity/surface IDs, named anchors, allowed operations, current capabilities, user constraints, and a few grounded renders/photos labeled with their revision. Resolve words such as “that,” “left,” and “behind” using selection and a recorded viewing camera. If “the chair” matches three plausible IDs, return the existing clarification shape rather than selecting a random chair.

Proposed command vocabulary, preserving `SPEC.md`'s no-coordinate rule:

```json
{
  "baseSceneRevision": "scene-r12",
  "commands": [
    {
      "type": "set_material",
      "targetEntityId": "wall-w3",
      "surfaceId": "interior-paint",
      "materialPresetId": "paint-sage-matte"
    },
    {
      "type": "move_object",
      "targetEntityId": "sofa-o7",
      "placement": {
        "relation": "against",
        "anchorId": "wall-w2",
        "alignment": "center"
      }
    }
  ]
}
```

Additional commands can include `remove_object`, `replace_object` using approved catalog IDs, `add_object`, `rotate_relative_to_anchor`, and `set_light_preset`. Define JSON Schema/Pydantic discriminated unions with enums, bounded counts, and strict extra-field rejection. Keep room/revision/idempotency fields in the authenticated application envelope rather than trusting model-generated replacements. The example is conceptual and needs versioned schemas and compatibility tests for the chosen Gemini endpoint/model.

Execution sequence:

1. Load and verify expected active revision; resolve IDs/capabilities/locks and entity existence against that revision.
2. Validate the proposed commands. Solver converts semantic references to exact metric transforms, using actual asset bounds and collision proxies.
3. Check containment, support, penetration, openings/door clearance, supplied aisle constraints, wall attachments, navigation connectivity and exposed-surface coverage. Planning clearances are product constraints, not certification of building-code compliance.
4. Rebuild dependent clean-background/material/light assets if required. A slow rebuild remains a running operation; the last good scene stays available.
5. Produce candidate render and navigation artifacts. Commit the whole command batch atomically to an immutable child revision only if validations succeed and the expected revision still matches.
6. Return actual execution outcome, warnings and resulting revision. Have Gemini describe that outcome; do not let its prose declare success before commit.
7. A retry with the same operation ID returns the same outcome. A stale base rejects or goes through an explicit rebase. Undo activates/creates a revision referencing the parent state, restoring geometry/material/lighting/visibility together; retain the event history.

Any 2D image generation should remain a labeled design preview until actual scene edits exist. Screenshots sent back to Gemini may help evaluate an edit, but they do not replace collision, identity, or measurement checks.

## 7. Splats as an optional delivery experiment

MetalSplatter provides a native Swift/Metal renderer for PLY/SPZ/.splat on iOS/macOS/visionOS and is MIT licensed. Its README describes a minimal sample and limited documentation; this is a renderer starting point, not a supported RealityKit drop-in. [Repository](https://github.com/scier/MetalSplatter), [license](https://github.com/scier/MetalSplatter/blob/main/LICENSE)

A mesh-plus-splat experiment must prove shared camera projection/depth, correct occlusion, picking IDs, per-object visibility/removal, old-shadow handling, and mobile resource usage. Otherwise selecting/moving a proxy leaves its scanned splat image behind. The original Graphdeco Gaussian Splatting implementation prohibits commercial use under its published default license; do not infer trainer licensing from an MIT viewer. [Graphdeco license](https://github.com/graphdeco-inria/gaussian-splatting/blob/main/LICENSE.md)

## 8. Prototype gates before promising the complete experience

These are proposed tests and example starting criteria, not achieved performance claims or accepted requirements:

| Gate | Test and pass evidence |
|---|---|
| Preserve the captured room | Scan at least three varied rooms; compare held-out camera renders and measured landmarks. Record depth residuals, visible coverage, texture seam/blur failures; separate inferred regions from evaluated observed ones |
| Detachable original furniture | Segment one sofa plus two touching chairs; rotate/translate each independently. No duplicate source object or surrounding wall/floor attached; original visible appearance remains recognizable |
| Hidden area validity | Remove the sofa and inspect exposed wall/floor from several heights/angles. Require continuous geometry and coherent texture, with provenance distinguishing observed, constrained, and generated regions |
| Material edit | Repaint one wall while leaving trim, openings, art, adjacent walls and unrelated atlas islands unchanged; inspect whether old furniture shadows persist |
| Placement | Execute anchored move/replacement commands; verify scale/pivots, supports, collision and doors using deterministic geometry, plus a walkthrough of the changed scene |
| Lighting | Only advertise realistic light edits after old baked light/shadows and newly cast shadows behave acceptably across views; otherwise expose a limited lighting capability |
| Persistent grounding | At least 20 mixed commands with selection/ambiguous names, invalid IDs, stale requests and duplicate operation IDs. Require no wrong-object commits, correct clarification, and reproducible reload/undo |
| Device delivery | Benchmark actual minimum-supported iPhone in Release for startup, peak memory, texture residency, frame-time percentiles and thermal degradation; provisional goal could be sustained ≥30 FPS, but choose budgets from measurements |
| Reprocessing | Improve the source reconstruction after several edits; demonstrate either evidence-backed ID reconciliation/replay or a clear conflict, never silent changes to the user's design |

Open evidence gaps: no ReSpace scan quality benchmark; no tested SAM 3/SAM 2 comparison on actual captures; incomplete object surface coverage unknown; no proven automatic clean-background pipeline; no measured inverse-rendering cost; no RealityKit textured-scene memory budget; and no completed asset/model license inventory. Resolve these with the smallest representative vertical slice before committing to quality or latency promises.

## 9. Preserve actual posters, paintings, and whiteboards

**Accepted scope:** retain source artwork, poster text, and written/printed whiteboard contents as captured pixels. Do not replace them with generated artwork, retyped OCR text, invented board contents, or generic wall-art assets. Lighting/shadow cleanup is outside acceptance. If capture quality prevents faithful preservation, fail the relevant capture validation and request rescan rather than adding an editing/cleanup UI. This subsection proposes the algorithm that implements those decisions; it does not claim the pipeline is already working.

RoomPlan's documented object categories do not include poster, painting, or whiteboard. Its wall surfaces are useful metric supports, but a RoomPlan-only export cannot be treated as a complete inventory of decor. Add a ReSpace wall-mounted entity category through image segmentation and cross-view association, using the SAM proposals discussed above. A low-relief paper poster may have no separately resolvable LiDAR surface at all. [Apple object categories](https://developer.apple.com/documentation/roomplan/capturedroom/object/category-swift.enum)

### Proposed capture-to-asset algorithm

1. **Propose the full instance and content boundary.** Detect/segment `poster`, `framed painting`, `wall art`, and `whiteboard`, including outer frame, inner artwork/board, and tray where visible. Keep outer silhouette and content rectangle separate. Do not require OCR to recognize all wording; it is appearance evidence, not reconstructed geometry. Preserve nonrectangular silhouettes as alpha masks or mesh outlines; do not crop everything to a bounding rectangle. Thick, tilted, or sculptural wall art needs observed 3D geometry rather than forced planar flattening.
2. **Ground the plane metrically.** For each observation, cast calibrated boundary rays onto the candidate measured wall, or onto a separately fitted decor plane when depth supports an offset/tilt. Store wall-local horizontal/vertical coordinates and the inward normal, metric width/height, and capture-to-wall transform. Reject wall associations that cross a corner, opening, or incompatible depth. Image homography alone does not supply meter scale; scale comes from the measured plane and calibrated camera geometry.
3. **Associate multiple views.** Reproject each candidate polygon into other frames, test visibility/depth agreement, and compare wall-local overlap, corners, size, and source appearance. Keep distinct IDs for two matching posters at different locations. Use feature correspondences plus robust `findHomography(..., RANSAC)` to verify textured artwork where available; whiteboards with little texture need pose/plane/corner evidence instead. OpenCV documents feature matching, robust homography estimation, inlier masks, and perspective projection for planar objects. [OpenCV feature matching and homography](https://docs.opencv.org/4.x/d1/de0/tutorial_py_feature_homography.html)
4. **Rectify actual source pixels.** Establish a canonical front rectangle at the measured aspect ratio and use the camera/plane mapping or corresponding corners to warp an accepted source crop into object-local texture space. OpenCV demonstrates planar perspective correction with `findHomography` and `warpPerspective`; the transform is valid for the same plane, not protruding frames or foreground occluders. [OpenCV homography tutorial](https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html)
5. **Select sharp evidence, without inventing detail.** Prefer a sharp, sufficiently frontal, fully visible frame for text/art. Use valid masks to exclude foreground occluders and invalid pixels. Select additional regions only when alignment is validated; indiscriminate averaging can double handwriting or blur fine print. Preserve an immutable source crop, orientation/color-space metadata, original resolution, per-region frame IDs and warp, and the derived texture hash. `warpPerspective` has explicit interpolation and border options; use a validity mask rather than treating extrapolated borders as observed content. [OpenCV geometric transforms](https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html)
6. **Do not fuse changing content.** A whiteboard that changes while scanning is not one stable multiview texture. Select a consistent capture time/frame set and preserve that state; disagreeing content must fail the automated consistency check. If small text cannot be recovered from captured resolution, rescan closer at adequate resolution. Generative upscaling and OCR rewriting are not valid ways to recover exact content.

### Independently editable geometry, support, and background

Create a logical decor entity with children for the front content plane, frame, and observed tray/edges as applicable. Preserve measured size and aspect ratio when moving. Thin planar assets are an appropriate representation for flat artwork; frame thickness/side/back geometry remains observed or internally recorded as inferred, never silently claimed as measured. RealityKit permits custom meshes assigned through `ModelComponent`; a textured `UnlitMaterial` is an optional way to display the captured face without an additional lighting requirement. Keep ordinary depth testing enabled so furniture correctly occludes decor. [Apple meshes](https://developer.apple.com/documentation/realitykit/meshresource), [Apple unlit material](https://developer.apple.com/documentation/realitykit/unlitmaterial)

Place the front surface a positive distance along the wall's inward normal, reflecting measured thickness where available; derive any minimum render separation from scene scale/depth precision and validate it on device. Do not render the decor and wall front as coplanar polygons, disable depth tests, or use an arbitrarily large offset: those cause flicker, wrong occlusion, or floating art. Give selection/collision geometry a thin finite volume separate from visual faces, and orient normals/UVs consistently so text is never mirrored after changing walls.

Remove decor appearance from the wall's own texture and any duplicate source geometry. Retain wall geometry behind the object; bake a separate clean underlying wall texture/material. Obtain that background from observed exposed wall evidence where possible; otherwise use the accepted seamless completion policy for the wall background, internally recording its provenance. A unique unseen mural/pattern cannot be recovered as fact; generated completion is a plausible substitute. This permission to complete hidden wall pixels does not permit replacing captured artwork or text. If the result fails automated visual/geometry checks, request rescan rather than displaying a broken model. Moving decor must neither leave its old image on the wall nor reveal a hole.

Make the artwork/board's `content` material slot and the wall's `interior-paint` slot different immutable owners. A wall recolor changes only wall material state. Shared atlases require explicit texel ownership or rebaking before changes; material edits cannot modify content texture pixels. Preserve the original source artwork and current derived texture across revisions and undo.

The scene contract needs `entityId`, `decorType`, `supportWallId`, wall-local polygon/center, wall-local orientation, `widthM`, `heightM`, thickness/provenance, source observations, `contentTextureAssetId`, frame submesh/material bindings, and underlying-wall asset/coverage reference. The current `WallFeature` in `ReSpace/Domain/RoomModels.swift` has only type, wall ID, offset, and height: extend the semantic entity model for this purpose rather than squeezing a textured, dimensioned object into a point feature.

For “move this poster to the opposite wall,” Gemini identifies the selected stable decor ID and semantic destination anchor. The deterministic solver picks a supported wall-local placement, retains size/texture, rotates the entity to that wall, and verifies that its entire polygon fits the available wall region without crossing openings or colliding with other mounted objects. Move frame/content/tray together; do not replace the image or scale it to make it fit. Reject an invalid destination or request clarification when “opposite wall” is ambiguous. Existing revision/operation rules apply atomically to the decor and the newly exposed wall background.

### Acceptance evidence

Use a room containing at least one text poster, a painting with a frame, and a whiteboard with fine handwriting. Require distinct persistent entities; compare rectified source crops with front and oblique device renders; verify no mirrored/cropped/replaced content or text ghosting; repaint the wall without changing decor pixels; move each item and inspect the old and new support area; reopen and undo to the same asset hashes and placement. Validate flicker/occlusion on the target phone. Record capture-resolution and glare/occlusion failures as rescan reasons, with no relighting/shadow cleanup gate. Measure the additional segmentation/rectification cost and latency inside the accepted $5/room ceiling and 30-minute target before claiming those budgets are achieved.
