# Photo-texturing ReSpace geometry: CPAP reuse and implementation analysis

Investigated 2026-10-18. **Research and a proposed experiment, not a change to the governing product specification.**

Evidence labels: **[CONFIRMED-CODE]** means inspected source; **[CONFIRMED-ARTIFACT]** means inspected saved output; **[CHECKED]** means a numerical check performed in this investigation; **[CONFIRMED-SOURCE]** means linked primary documentation/research; **[INFERRED]** means an engineering conclusion; **[PROPOSED]** means unimplemented work. Labels apply to the paragraph or table introduced by them.

## Recommendation

**[INFERRED] Yes: the calibrated projection principle transfers from the CPAP TrueDepth work to LiDAR rooms. ReSpace already has the relevant forward projection on its reconstruction branch.** Once a surface position and source camera are known, the depth-sensor technology does not enter the image lookup equation. The important new work is selecting trustworthy image regions, checking visibility, baking into stable texture coordinates, and separating plausible surface finish from baked lighting.

**[PROPOSED] Use a hybrid: retained room geometry + ordinary PBR materials for broad finishes + selective image-to-texture baking for distinctive detail.** First target the kitchenette's cabinet fronts, backsplash, floor and walls. Correct the sink opening/basin before texturing it. Preserve stainless steel, glazing and reflections through renderer materials. A fully projected generated image is useful as an experimental comparison, but is a weaker default for free movement and subsequent redesign.

## 1. Which project state was actually inspected

**[CONFIRMED-CODE] Three different states must not be conflated:**

| State | Verified revision | What exists |
|---|---|---|
| Current ReSpace checkout, `humaidjaffery` | `3353be1` | RoomPlan capture, calibrated RGB/optional depth, semantic geometry, observed RGB sampling, RealityKit orbit rendering, prepared catalog assets. |
| ReSpace reconstruction branch, local `origin/OpenAI-3dmodelgen` | `e84a1c50be0d04429bac506160019557788376b0` | ARKit mesh/depth evidence, RoomPlan shell, Astra-generated contents, original-photo projection, OBJ/MTL assets and a SceneKit walkthrough. |
| CPAP/DreamSeal checkout | `2da7def` | Recorded synchronized TrueDepth evidence, offline reconstruction, dual-pass trajectory consensus, 2D-to-3D facial landmarks and point-cloud output. |

This investigation did not fetch remote updates or switch branches. The reconstruction code discussed below is at the pinned local remote-tracking revision, not a claim about the latest remote state. Its four core projection source snapshots from the previous analysis were compared byte-for-byte with Git and match.

**[CONFIRMED-CODE]** Current [`SPEC.md`](../../SPEC.md) §11 specifies RealityKit, category stand-ins and prepared Product assets. Its Out of Scope section excludes textured room reconstruction, Gaussian splats and photoreal room rebuilding. This request authorizes researching that extension; these notes do not silently amend the specification. The separate walkthrough branch already explores a different scope.

**[CONFIRMED-CODE]** The current checkout already preserves useful inputs in [`Capture.swift`](../../ReSpace/Capture.swift:175): sensor-orientation JPEG, scaled intrinsics, camera transform, timestamp and optional depth/confidence. [`lifting.py`](../../backend/respace/lifting.py:29) applies `room_from_world` before interpreting cameras in normalized room coordinates. [`colors.py`](../../backend/respace/colors.py:16) performs coarse visibility-aware RGB sampling and reduces evidence to an observed Object color. It is not a texture atlas generator. [`RoomScene.swift`](../../ReSpace/RoomScene.swift:216) supports textured panels and loaded assets, but does not currently bake whole-room appearance.

**[CONFIRMED-CODE]** Capture formats also differ: the current app stores Float32 depth (`float32_le_m`); the reconstruction branch's [FrameEncoder](https://github.com/watermelon-elite/ReSpace/blob/e84a1c50be0d04429bac506160019557788376b0/ReSpace/Capture/FrameEncoder.swift) packs Float16 (`float16_le_meters`). Metadata shape differs too. Reusing algorithms does not make those artifact formats interchangeable.

## 2. What CPAP actually does, and what is reusable

### Active scanner

**[CONFIRMED-CODE]** The [record-before-reconstructing decision](/Users/humaid/cpap/docs/adr/0001-record-before-reconstructing.md) separates synchronized evidence from derived geometry. [ScanRecordingWriter](/Users/humaid/cpap/cpapfrontend/CPAPScanner/CPAPScanner/Scanning/Recording/ScanRecordingWriter.swift:102) records source RGB/depth timestamps, camera calibration and frame identity, saves lossless depth Fusion Frames, and preserves RGB in timed HEVC. This provenance discipline is directly relevant: a beautiful image with the wrong camera or frame association produces incorrect texture mapping.

**[CONFIRMED-CODE]** [OfflineReconstructionCoordinator](/Users/humaid/cpap/cpapfrontend/CPAPScanner/CPAPScanner/Scanning/Recording/OfflineReconstructionCoordinator.swift:96) currently runs primary and strict reconstruction probes, selects frames through trajectory consensus, then performs final fusion. Accepted frame metadata associates poses with their originating observations. This is implementation evidence, not a fresh measurement that consensus improves every scan.

**[CONFIRMED-CODE]** Its [landmark projection](/Users/humaid/cpap/cpapfrontend/CPAPScanner/CPAPScanner/Scanning/Recording/OfflineReconstructionCoordinator.swift:258) expands Vision face-relative coordinates, converts their orientation, samples median valid depth, unprojects through calibration, and applies the frame-associated reconstruction transform. It operates over 0.12–0.70 m. Its camera point is explicitly arranged as `(cameraY, -cameraX, z)`. That orientation logic is specific to this capture path.

**[CONFIRMED-CODE]** [CameraModelSnapshot](/Users/humaid/cpap/cpapfrontend/CPAPScanner/CPAPScanner/Scanning/Recording/ScanRecording.swift:57) retains nominal/effective intrinsics, extrinsics, distortion tables and a StandardCyborg focal-length factor of `1.019`. Those constants must not be transplanted into ARKit room calibration. The active landmark function uses nominal intrinsics; merely finding effective calibration in the recording does not prove every consumer uses it.

**[CONFIRMED-CODE]** Current fusion output is a point cloud, not a photo-textured mesh. Depth-only Fusion Frames receive synthetic neutral-gray colors when read by [PointCloudIO_PLY.mm](/Users/humaid/cpap/StandardCyborgCocoa/StandardCyborgFusion/Sources/StandardCyborgFusion/IO/PointCloudIO_PLY.mm:264). The app's saved Scan exports PLY. No call to `SCMeshTexturing`, `MetalTextureProjection` or `saveColorBufferForReconstruction` was found in the current CPAP app's Swift source. Retaining RGB video makes future texture work possible; it does not establish that photo baking is already in the active app.

**[CONFIRMED-CODE]** The earlier [TrueDepthFusionExplained.txt](/Users/humaid/cpap/TrueDepthFusionExplained.txt) describes live fusion of colored surfels and output point colors. That describes an earlier pipeline. **[INFERRED]** Even when actual RGB colors are attached to points, surface detail remains tied to point/vertex sampling; that is different from a high-resolution image atlas on a modest triangle mesh.

### Bundled texturing implementation

**[CONFIRMED-CODE]** The currently inspected Xcode project references the full `StandardCyborgFusion` package, despite a sibling `StandardCyborgFusion_NoMesh` directory. The full SDK contains a much closer precedent for the requested feature:

- [SCMeshTexturing.mm](/Users/humaid/cpap/StandardCyborgCocoa/StandardCyborgFusion/Sources/StandardCyborgFusion/Public/SCMeshTexturing.mm): captures RGB with view/projection matrices; builds a mesh, unwraps UVs, and invokes texture projection.
- [MeshUvMap.cpp](/Users/humaid/cpap/StandardCyborgCocoa/StandardCyborgFusion/Sources/StandardCyborgFusion/Algorithm/MeshUvMap.cpp): surface parameterization and atlas layout.
- [MetalTextureProjection.mm](/Users/humaid/cpap/StandardCyborgCocoa/StandardCyborgFusion/Sources/StandardCyborgFusion/Algorithm/MetalTextureProjection.mm:242): renders visible mesh UV coordinates from a source camera, then accumulates image colors into the atlas; later normalizes weights, fills holes and pads texture edges.
- [RenderUvs.mm](/Users/humaid/cpap/StandardCyborgCocoa/StandardCyborgFusion/Sources/StandardCyborgFusion/MetalDepthProcessor/RenderUvs.mm:109): enables depth testing and depth writes.
- [RenderUvs.metal](/Users/humaid/cpap/StandardCyborgCocoa/StandardCyborgFusion/Sources/StandardCyborgFusion/MetalDepthProcessor/RenderUvs.metal): projection, lens correction and normal-facing weight.

**[INFERRED]** Borrow that decomposition: geometry → stable UV atlas → source-camera visibility → image samples → coverage/seam handling. Do not import the entire face reconstruction system into the Python room pipeline. ARKit already supplies camera tracking, and we already have geometry to texture.

**[CONFIRMED-CODE + INFERRED]** The legacy SDK is a reference, not a verified drop-in room baker. For example, [UvToColor.metal](/Users/humaid/cpap/StandardCyborgCocoa/StandardCyborgFusion/Sources/StandardCyborgFusion/MetalDepthProcessor/UvToColor.metal:17) uses a non-atomic read/add/write when source pixels scatter to atlas texels; concurrent collisions warrant review. Its UV-render vertex shader divides by clip `w` before passing position to rasterization, warranting a perspective-interpolation check on large room triangles. These are source-level concerns, not observed failures in a new GPU run. A target-texel gather implementation avoids the scatter-write problem and is easier to verify. Copying code would also require reviewing the applicable subdirectory licenses.

**[INFERRED] Reuse assessment:**

| CPAP element | Room application | Decision |
|---|---|---|
| Frame identity, synchronized calibration/pose/evidence | Correct source-camera association and reproducible bakes | Reuse the design; ReSpace already implements much of it |
| Pinhole unprojection/projection | Same camera/surface mathematics | Reuse concept, use ReSpace's coordinate adapter |
| UV atlas, rendered visibility, angle weighting | Image appearance on existing triangles | Strong architectural inspiration |
| Validity/coverage and durable outputs | Preserve good results and report holes | Adapt to room surfaces and immutable design assets |
| Face orientations, `1.019` factor, 12–70 cm limits | Wrong assumptions for room cameras | Do not copy |
| Face landmarks, face phases, CPAP mask logic | No role in surface texturing | Do not copy |
| ICP, dual-pass face fusion, Poisson reconstruction | Rebuilds geometry/poses we already possess | Unnecessary for this feature |

## 3. Exact projection relationship

**[CONFIRMED-SOURCE]** For a point in a camera frame with positive forward depth, the pinhole model is `u = fx*x/z + cx`, `v = fy*y/z + cy`; focal lengths and principal point are in source-image pixels. Intrinsics must follow image resizing. [OpenCV calibration documentation](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html). ARKit image dimensions describe native sensor orientation, not portrait UI orientation. [Apple imageResolution](https://developer.apple.com/documentation/arkit/arcamera/imageresolution).

**[CONFIRMED-CODE]** The reconstruction branch already implements this in [instances.project](https://github.com/watermelon-elite/ReSpace/blob/e84a1c50be0d04429bac506160019557788376b0/services/reconstruction/respace_reconstruction/instances.py#L79), using [camera_to_cv_world](https://github.com/watermelon-elite/ReSpace/blob/e84a1c50be0d04429bac506160019557788376b0/services/reconstruction/respace_reconstruction/geometry.py#L11).

Let:

- `T` map ARKit camera coordinates to the scan world.
- `F = diag(1, -1, -1, 1)` convert positive-forward, image-down camera coordinates to ARKit camera coordinates.
- `P` be a homogeneous surface point in the same scan world.

Then the branch computes:

```text
q = inverse(T * F) * P
u = fx * q.x / q.z + cx
v = fy * q.y / q.z + cy
valid requires q.z > 0
```

The corresponding depth-assisted reverse operation is:

```text
q = [(u - cx) * d / fx, (v - cy) * d / fy, d, 1]
P = T * F * q
```

Here `d` is optical-axis depth, not distance along the slanted ray. In the current normalized-room backend, use `T_room_camera = room_from_world * T_world_camera`; do not mix normalized room points with raw scan poses. In an Object-local atlas, transform the Object's local point into the source scene before projection. Keep normals in the same frame, with the appropriate normal transform when scaling is involved.

**[INFERRED]** CPAP most visibly uses the reverse direction: 2D landmark + depth → 3D point. Texturing primarily uses the forward direction: known 3D point → corresponding image pixel. A depth measurement is not needed to locate an already-known mesh point. It is needed, or substituted with rendered visibility, to decide whether that point was actually visible.

**[PROPOSED]** For a virtual source camera, save its exact view/projection matrices and viewport. Using the renderer's complete projection also supports off-center or orthographic cameras. Do not reconstruct calibration from an approximate screenshot or assume a field-of-view axis. For a crop starting at `(x0,y0)` followed by scale `(sx,sy)`, the simple pinhole case gives `fx'=sx*fx`, `fy'=sy*fy`, `cx'=sx*(cx-x0)`, `cy'=sy*(cy-y0)`. Rotation, mirroring and padding need their own explicit image transform. A generator's changed object layout is not repaired by resizing intrinsics.

### Numerical checks performed

**[CHECKED]** Extracted and executed the actual branch's `camera_to_cv_world` and `project` functions, with a translated, rotated camera, unequal focal lengths, three pixels and depths from 0.8 to 4.2 m. Unprojecting and projecting again produced a maximum error of `5.68e-14` pixels. This verifies the isolated convention and arithmetic; it does not validate device calibration or generated-image alignment.

**[CHECKED]** A synthetic slanted triangle with camera-space vertices `(0,0,1)`, `(2,0,2)`, `(0,1,1)` demonstrates a separate issue. Its 3D centroid projects to `(0.5,0.25)` in normalized image coordinates. Interpolating only its three already-divided vertex image coordinates gives `(1/3,1/3)`. At a synthetic focal length of 1,000 pixels, the lookup difference is approximately `(-166.7,+83.3)` pixels. This is a mathematical counterexample, not a measured error in the kitchen.

## 4. What the room branch already does, and why coverage is weak

**[CONFIRMED-CODE]** [astra_textures.texture_furnishings](https://github.com/watermelon-elite/ReSpace/blob/e84a1c50be0d04429bac506160019557788376b0/services/reconstruction/respace_reconstruction/astra_textures.py#L18) currently:

1. Loads each generated Object mesh and transforms its vertices into scan space.
2. Skips walls, floor, ceiling and mirrors; excludes material slots with metallic ≥ 0.7 or roughness ≤ 0.12.
3. Chooses a limited set of nearby source cameras, using centroid visibility, optional photo IDs and a 15 cm translation-diversity check.
4. Uses [PhotoBaker.sample](https://github.com/watermelon-elite/ReSpace/blob/e84a1c50be0d04429bac506160019557788376b0/services/reconstruction/respace_reconstruction/surfaces.py#L131) to compare projected optical depth with recorded LiDAR depth. Agreement must be within `max(0.035 m, 0.015*z)`; absent depth produces no valid samples.
5. Requires a visible face center, all three corners inside the image and at least two depth-visible corners. Ranks views using absolute normal-facing angle divided by distance squared.
6. Assigns one source image per accepted triangle, writes per-corner `vt` coordinates, references the source JPEG through `map_Kd`, and retains roughness/metallic settings. Unaccepted faces retain plain material.

**[CONFIRMED-ARTIFACT]** Recomputed from the saved [quality receipt](/Users/humaid/dh26/.local/imported-kitchenette-source/quality.json):

| Surface/Object | Recorded photo surface coverage |
|---|---:|
| Base cabinets | 0% |
| Upper cabinets | 0% |
| Sink | 0% |
| Main countertop | 0.7972% |
| Near refrigerator | 0.2129% |

There are 40 Object texture reports: 19 have less than 1% coverage and 10 have exactly zero. These fractions are geometric face-area coverage, not camera-screen coverage. Reflective-material exclusions deliberately reduce some fractions. The asset contains 3,142 triangles. Counts alone do not prove why an individual face failed.

**[INFERRED]** There are several specific improvement opportunities:

- Large cabinet triangles can have visible interiors even when corners fall outside a photo. Requiring all corners loses those regions. A synthetic partial-triangle check confirmed this rejection condition.
- Assigning already-projected photo UVs only at corners gives an affine mapping over the 3D triangle. It is not exact perspective projection over a slanted plane. Ordinary renderer perspective correction interpolates attributes for the viewing camera; it does not reconstruct the missing source-projector division. Use a projective shader or bake per texel. Subdividing triangles only approximates the correction.
- Generated geometry can disagree with real LiDAR enough to fail a sound depth test. Loosening the tolerance globally can paint a foreground appliance onto a cabinet behind it. Diagnose rejection reasons and geometry first.
- Nearest-camera and translation-only diversity can miss a good view. Prefer projected useful surface coverage, angle, resolution, blur and source alignment.
- Absolute normal-facing scores allow both face orientations. For outward-oriented opaque meshes, use signed facing plus whole-scene visibility; handle genuinely two-sided surfaces explicitly.
- A single whole-photo source per triangle produces seams and over-retains image data. Patch-consistent selection and compact atlases are better long-term assets.

**[CONFIRMED-CODE]** There is already a better starting point for broad planes: [PhotoBaker.plane](https://github.com/watermelon-elite/ReSpace/blob/e84a1c50be0d04429bac506160019557788376b0/services/reconstruction/respace_reconstruction/surfaces.py#L155) enumerates surface texture pixels, recovers their 3D positions and selects photo samples per pixel. It defaults to 256 pixels/metre with a 2,048-pixel dimension cap. The active Astra furnishing pass does not use it for the shell. Its nearest-color/smoothing hole fill is not recovered wood grain or learned material completion.

**[CONFIRMED-CODE]** The [walkthrough loader](https://github.com/watermelon-elite/ReSpace/blob/e84a1c50be0d04429bac506160019557788376b0/ReSpace/Rendering/WalkthroughView.swift#L8) uses physically based lighting for Astra scenes and preserves roughness/metallic. Putting already-lit photos into those base-color slots can compound their baked illumination.

## 5. Original photos and generated images require different trust checks

**[INFERRED]** These inputs can share a baker, but they cannot share an unconditional claim of calibration:

| Source image | Known relationship | Appropriate visibility/evidence |
|---|---|---|
| Original synchronized RGB | Calibrated camera observed a physical scene | Camera calibration, sensor depth/confidence when available, target-mesh visibility, masks for unmodeled occluders |
| Unmodified virtual render | Exact camera rendered the target geometry | Whole-scene rendered depth, triangle/Object/material IDs |
| Generated edit of that render | Intended relationship to the render | Same render buffers **plus a correspondence check on the generated content** |
| Independent generated perspective | Camera and internal geometry may be inconsistent | Recover/validate correspondence first, or extract only material swatches |

**[INFERRED]** A rendered depth buffer answers “which target surface occupies this pixel?” It does not answer “did the generator keep the same cabinet there?” Feeding synthetic depth into the current real-photo path would remove one rejection mechanism without certifying image alignment. Even depth-conditioned generation can invent handles, grooves and openings that need geometry or local masking.

**[CONFIRMED-ARTIFACT]** The earlier experiment's [baseline render](/Users/humaid/.codex/visualizations/2026/10/18/01a14e79-4a10-7880-9914-7d046f9eb84f/room-analysis/scene-baseline.png) is 1440×1000. Its [generated edit](/Users/humaid/.codex/visualizations/2026/10/18/01a14e79-4a10-7880-9914-7d046f9eb84f/room-analysis/image-c-render-guided.png) is 1505×1045. Direct inspection shows much richer grain, cabinet hardware, backsplash and lighting, while the countertop remains solid under the faucets. These are rendered/generated images, not independently measured materials. The [render script](/Users/humaid/.codex/visualizations/2026/10/18/01a14e79-4a10-7880-9914-7d046f9eb84f/room-analysis/render_scene.swift) preserves camera position, look-at target and 72° field of view; it did not save a complete depth/ID/projection bundle.

**[PROPOSED]** Re-render and record that bundle. Match output scale/crop explicitly. Check major silhouettes and cabinet/counter/window boundaries, then accept individual surface regions. For this first room, manual approval masks are cheaper and easier to diagnose than a new general alignment model. Small plane-specific alignment corrections can use a homography; a single room-wide homography cannot align multiple depth planes or compensate for changed object geometry. Reject ambiguous regions rather than warping measured geometry to fit the generated picture.

**[CONFIRMED-ARTIFACT]** The imported kitchenette folder contains exported scene data, appearance files and quality/provenance, but no original calibrated capture manifest and depth package. It is sufficient for virtual-render projection work. Faithfully repeating the original LiDAR/photo bake requires recovering the original capture package.

## 6. Smallest useful implementation

All work in this section is **[PROPOSED]**. Start in an isolated experiment against the reconstruction branch's assets. Do not merge its capture protocol and SceneKit walkthrough wholesale into the main app just to prove texturing.

### Geometry and material preparation

Keep stable Object/Item identity, units and placement. Use a countertop cutout and real sink basin; small bevels, panel separations and important handles improve silhouette and shading. A normal map can suggest fine grooves, but cannot create an opening or correct a silhouette. Do not spend model calls regenerating known geometry simply to add a finish.

Use local planar or box UVs on cabinet fronts/sides, floor, walls and countertop. Physical material scale and grain direction matter: a wood pattern should not grow with the object's bounding box. Use an atlas only where a surface needs unique content. General UV unwrapping is unnecessary for the first planar experiment; introduce it for irregular surfaces when needed.

### One deep appearance-baking module

Keep a small interface: target geometry and UVs, source views with camera transforms, source-kind/validity evidence, and fallback materials → baked textures, material bindings and coverage diagnostics. The useful seam is around the complete bake, not separate public interfaces for every rasterizer/helper.

Internally, the existing real-photo source and a new rendered-view source can supply different visibility evidence. Keep their semantics explicit; do not masquerade generated RGB as a synchronized sensor observation. Reuse `project`, coordinate conversion, stable IDs, hashes and existing asset assembly. Extend/adapt the planar bake before adding a generic mesh baker. No new face-fusion dependency or microservice is needed.

For each target texture pixel:

```text
Locate its triangle in UV space.
Recover the 3D point from the triangle's barycentric coordinates.
Transform the point and normal into the source scene.
For each candidate source camera:
    Project the 3D point into the source image.
    Reject behind-camera, outside-image and grazing samples.
    Check whole-scene depth and surface identity.
    For original photos, additionally use available sensor-depth evidence.
    Require an accepted generated-image alignment mask when applicable.
    Sample valid RGB with proper image filtering.
Choose a consistent best source or blend compatible low-frequency regions.
Write to the target atlas; retain fallback material where no source qualifies.
```

For virtual views, render optical depth or compare correctly linearized depth; hardware z-buffer values are generally not metres. Render all relevant occluding Objects together, even when baking one Object. Preserve real openings. Keep source-camera coordinates distinct from destination atlas coordinates. Use bilinear/footprint-aware sampling, atlas gutters and mipmaps to avoid magnification blur and edge bleed.

Start with one best source per coherent surface patch. Blend compatible finish regions after exposure normalization in linear color, with narrow transitions at seams. Do not average displaced handles or cabinet lines; it creates double features. Extend detail into an unseen side with a compatible material, not a stretched frontal image. The classical view-selection/seam problem is documented in [Waechter et al.](https://download.hrz.tu-darmstadt.de/pub/FB20/GCC/paper/Waechter-2014-LTB.pdf) and the [authors' mvs-texturing implementation](https://github.com/nmoehrle/mvs-texturing).

### Appearance choices for this room

| Surface | First implementation | Reason/tradeoff |
|---|---|---|
| Walls and ceiling | Neutral paint/PBR material | Stable as camera and lighting change; low benefit from full-frame photo transfer |
| Floor | Physically scaled tileable material; project distinctive detail only if needed | Covers disocclusions cleanly; may not reproduce exact real wear |
| Cabinet fronts | Wood material plus accepted projected panel/detail regions | Good visual payoff; hardware needing parallax remains geometry |
| Cabinet sides/backs | Same material family and grain convention | Plausible unseen appearance without pretending it was observed |
| Backsplash | Tile material with subtle normal/roughness variation | Avoids freezing undercabinet lighting in the base color |
| Countertop | Neutral stone/laminate material, real thickness and sink cutout | Prevents highlight/shadow doubling; texture cannot supply basin geometry |
| Stainless appliances | Metal/roughness material, selected nonreflective decals/details | A captured reflection should not remain glued to a moving refrigerator |
| Glass/mirrors | Renderer material/reflection treatment | Photo projection stores the reflected room as if painted on glass |
| Catalog Products | Existing verified/prepared asset, reviewed material | Generated room styling must not alter the advertised Product variant |

**[CONFIRMED-SOURCE]** PBR formats separate base color, roughness, metallic, normal and occlusion; a normal map changes shading rather than mesh shape. [Khronos PBR guide](https://www.khronos.org/gltf/pbr). **[INFERRED]** A directly projected RGB image is captured appearance, not reliably recovered base color. Unlit display can closely preserve it for fixed-light demos, while relighting requires cleaner material maps. Automated de-lighting is an additional inference problem. [Paint3D](https://paint3d.github.io/) explicitly treats baked illumination with trained refinement rather than assuming RGB projection solves it.

### Multiple views and persistent output

Choose additional interior camera positions by uncovered useful surface area and projected resolution. Three deliberately different views are a reasonable first experiment, not a guarantee of full-room coverage. Render the already-textured model into the next view, protect accepted areas, and generate/inpaint uncovered areas. Preserve shared material choices across the room. Six independently generated full-room images can disagree even if each looks excellent.

Bake each movable Object's appearance into its local UVs so it follows later placement. Do not paint an Object onto the wall behind it. Object removal exposes previously unseen wall/floor regions that need material fallback. Cast shadows baked into neighboring surfaces need invalidation when layout changes; this is a major reason to keep those surfaces material-based.

Save textures and material bindings by immutable revision, tied to geometry/UV hash and source-camera/image provenance. Reuse existing checksummed asset publication and atomic result assembly. Export through the branch's OBJ/MTL path for the first walkthrough, or the existing validated USDZ asset path for RealityKit integration. Normal/roughness/metallic image-map import requires explicit verification; current scalar support does not prove every texture map survives conversion. Preserve Units, Object/Item IDs, Product dimensions and saved Design versions independently of appearance generation.

Room-derived textures should inherit capture privacy, not be published as generic public catalog images. This is directly relevant because the existing approach can include a whole source photograph as a texture file; compact cropped/baked atlases reduce unrelated retained imagery as well as file overhead.

## 7. Alternatives and the best fit

All rankings are **[INFERRED]**, not benchmark results for this kitchen.

| Approach | Advantages | Main limitations | Recommended use |
|---|---|---|---|
| One-view image projection | Fast proof, detailed visible appearance, ordinary mesh output | Unseen areas, image drift, baked lighting, flat fake detail | Controlled experiment and selected accents |
| PBR materials + selective projection | Stable orbiting, editable Items, coherent hidden surfaces, predictable renderer | Material selection/scale needed; less exact unique surface detail | Best first room-wide implementation |
| Geometry-conditioned multi-view texture generation | Learns plausible unseen detail while using a target mesh | Cross-view inconsistency, model/runtime cost, object-centric training | Later offline comparison after baking is verified |
| Photogrammetry | Real observed appearance and improved geometry | Requires overlapping images and cleanup; weak on reflective/textureless surfaces; semantic separation remains | When fidelity to the original room is the main goal and proxy geometry is insufficient |
| NeRF/Gaussian splatting | Convincing photographed novel views, view-dependent appearance | Different representation/rendering; editing, per-Item identity and relighting require extra work | Separate original-room walkthrough experiment |
| Generate a new 3D room from a picture | Can infer unseen appearance and geometry | Changes the measured scene and dimensions; compounds uncertainty | Poor fit for keeping this existing model authoritative |

**[CONFIRMED-SOURCE]** [Text2Tex](https://daveredrum.github.io/Text2Tex/) directly demonstrates known mesh → rendered depth → generated view → texture backprojection → further-view refinement. [TEXTure](https://texturepaper.github.io/TEXTurePaper/) uses iterative views and region states. [MVPaint](https://mvpaint.github.io/) adds synchronized multiview generation, 3D-aware completion and seam handling, with object benchmarks. **[INFERRED]** Their transferable lesson is shared appearance and explicit coverage. They do not establish that a room full of occluding Objects works as a drop-in object-turntable task.

**[CONFIRMED-SOURCE]** [Hunyuan3D 2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1) exposes a texture pipeline accepting mesh plus reference image and states 21 GB VRAM for texture generation. **[INFERRED]** It is an optional asset-level benchmark, not the lowest-risk first implementation or demonstrated iPhone/whole-room solution. No remote GPU or paid inference was provisioned for this investigation.

**[CONFIRMED-SOURCE]** [COLMAP's capture/reconstruction guidance](https://colmap.github.io/tutorial.html) emphasizes overlapping images, texture and capture conditions. [NeRF](https://www.matthewtancik.com/nerf) models density and view-dependent radiance; [3D Gaussian Splatting](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/) uses optimized Gaussians and its own rasterization. **[INFERRED]** These are valuable when reconstructing the photographed scene is the goal. They do not automatically produce PBR textures attached to our independently editable Items.

**[CONFIRMED-ARTIFACT]** ReSpace's own [SPAR3D evaluation](../../assets/spar3d/README.md) already documents the relevant warning: shelf interiors can be painted onto solid slabs, upholstery may be hollow from hidden angles, and color can be wrong despite good geometry. **[INFERRED]** Generating another mesh should not be the default fix for an appearance problem in known geometry. Always inspect clay geometry and translated viewpoints.

## 8. Concrete experiment and acceptance evidence

Everything here is **[PROPOSED]**; no end-to-end bake was implemented during this analysis.

1. **Prove the baker without generation.** Select a cabinet plane, a floor patch and an occluding Object. Render a known checker/ID pattern with saved camera/depth/IDs, bake it, and re-render. Verify camera axes, crop/resize, oblique triangles, partially visible triangles, occlusion and UV orientation. Expect source reprojection agreement within sampling/antialiasing error; use a roughly one-pixel interior target as an initial diagnostic goal, not an asserted current result.
2. **Correct the kitchen's visibly wrong geometry.** Add the sink cutout/basin and necessary cabinet relief. Inspect untextured views before appearance work.
3. **Compare three appearances on identical geometry/cameras.** Plain PBR baseline; direct generated-image projection; PBR plus accepted projected regions. This isolates which appearance strategy helps, instead of simultaneously changing geometry and generation.
4. **Test movement, not only rotation at one point.** Inspect original view, left/right translated views, close-ups, a reverse view and a path through the room. Identify double handles, false cavities, seams, grain stretching, hidden surfaces and fixed highlights.
5. **Add two useful views.** Carry accepted texture forward and fill newly exposed regions. Measure area coverage separately for observed, generated and fallback regions, plus coverage weighted by intended viewing paths. Log rejection causes, not just one final percentage.
6. **Verify edits and delivery.** Move/remove one Object, inspect the wall/floor behind it, reopen an earlier Design version, and confirm textures remain bound to the right assets. Verify on-device load time, peak texture memory and navigation frame rate.

**[CHECKED arithmetic / PROPOSED budgeting]** A single 2048² RGBA8 texture is 16 MiB before mipmaps, approximately 21.3 MiB with a full chain. A 4096² map is 64 MiB, approximately 85.3 MiB with mipmaps. Base color plus several material maps multiply that cost; small JPEG file size does not imply small decoded GPU memory. Start with shared tileable materials and a small number of 1K/2K unique atlases, then measure. These figures are format arithmetic, not measured RealityKit allocation.

**[INFERRED]** The first success criterion should be a visibly better cabinet/wall/floor result from several translated views with unchanged room measurements. Do not define success as a beautiful single image or “100% coverage” obtained by spreading uncertain pixels everywhere.

## Evidence limits and change record

The investigation read current code, the pinned reconstruction branch, CPAP architecture/source, the saved kitchenette quality receipt, earlier rendered/generated images, and primary research. It executed isolated projection arithmetic and counterexamples. It did not inspect private facial captures, replay a CPAP scan, run a new LiDAR capture, benchmark the SDK on a GPU, generate new images, train/run texture models or produce a finished textured room. Generation alignment and all-angle visual quality remain experimental.

Only this research note and its entry in the root documentation map were added. No application behavior, dependency, capture contract, product requirement or external issue was changed.
