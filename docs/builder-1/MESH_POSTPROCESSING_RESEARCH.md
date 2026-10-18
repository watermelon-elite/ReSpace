# Postprocessing ARKit mesh, LiDAR and photos

Research date: October 17, 2026. Primary documentation and source reviewed; no application code changed.

## Conclusion

Yes: use a reconstruction pipeline rather than expecting one ARKit-specific “smooth and complete” API. **OpenMVS is the closest fit for photo-guided refinement of an existing mesh; Open3D is the straightforward foundation for fusing saved RGB-D frames; CGAL supplies explicit small-hole repair.** These are different operations, and the combined result needs an adapter and a quality evaluation on actual scans.

## Practical options

| Tool | Appropriate job | Important limit / deployment |
| --- | --- | --- |
| **OpenMVS** | Its `RefineMesh` stage accepts an existing mesh and calibrated images, refines geometry against the photos, and `TextureMesh` produces photo textures. Its densification stage can consume existing depth maps converted into `.dmap` files. Current documentation also supports imported ARKit camera poses and intrinsics. | Closest multimodal building blocks, but not a direct `ARMeshAnchor + ARFrame` Swift API. Convert mesh, camera axes/calibration, imagery and depth into its scene formats. Official binaries cover Windows, Ubuntu and macOS arm64; evaluate as desktop/backend processing. [Usage](https://github.com/cdcseacave/openMVS/wiki/Usage), [refinement pipeline](https://github.com/cdcseacave/openMVS/blob/develop/docs/pipelines.md) |
| **Open3D** | TSDF fusion integrates multiple noisy depth maps with known camera poses, yielding smoother geometry. Color integration can attach RGB. Its mesh filters include Taubin smoothing, which addresses shrinkage associated with simple Laplacian smoothing. | RGB integration colors the reconstruction; it does not establish photo-derived geometry in a missing-depth region. Use Open3D on a Mac or backend; official Python/C++ distribution platforms are desktop OSes. [TSDF integration](https://open3d.org/docs/release/tutorial/t_reconstruction_system/integration.html), [RGB-D integration](https://www.open3d.org/docs/latest/tutorial/pipelines/rgbd_integration.html), [mesh filters](https://www.open3d.org/docs/release/tutorial/geometry/mesh.html), [platforms](https://www.open3d.org/docs/latest/getting_started.html) |
| **CGAL** | `triangulate_refine_and_fair_hole` fills a bounded mesh opening with a triangulated, refined, smoothed patch; additional smoothing/remeshing tools are available. | Geometry-based interpolation, without interpreting photos. Constrain hole size and validate patches; the manual notes possible self-intersections for complicated boundaries. C++ integration is possible in principle; an iOS wrapper/build is separate engineering. [Polygon Mesh Processing manual](https://doc.cgal.org/6.1/Polygon_mesh_processing/index.html) |
| **COLMAP** | Photogrammetric sparse/dense reconstruction from overlapping photos; known camera poses can initialize a reconstruction. It can feed calibrated imagery to OpenMVS. | Adds reconstruction/calibration tools rather than repairing an ARKit mesh automatically. Retaining ARKit pose estimates does not remove the need for correctly formatted cameras and image data. [Known-pose reconstruction](https://colmap.github.io/faq.html#reconstruct-sparse-dense-model-from-known-camera-poses), [dense reconstruction](https://github.com/colmap/colmap/blob/main/doc/tutorial.rst) |
| **Apple Object Capture** | Native photogrammetry for objects; available on supported iOS and macOS configurations. `PhotogrammetrySample.depthDataMap` accepts image depth and can help recover physical scale. | A reconstruction workflow from photographs, rather than a documented arbitrary ARKit-mesh refinement endpoint. Room-scale suitability and detail require testing. [Object Capture](https://developer.apple.com/documentation/realitykit/realitykit-object-capture), [sample depth](https://developer.apple.com/documentation/realitykit/photogrammetrysample/depthdatamap) |
| **Apple RoomPlan** | Produces clean, semantic, parametric room structure using camera and LiDAR, with component dimensions and furniture categories. | Useful for regularizing walls/floors/openings and arranging representative objects; its floor-plan representation does not establish exact missing furniture surfaces. [RoomPlan overview](https://developer.apple.com/augmented-reality/roomplan/), [Apple research](https://machinelearning.apple.com/research/roomplan) |

## What “fill in gaps” means

1. **Observed in another depth frame:** fuse the observations. TSDF integration is a good baseline.
2. **Visible in several overlapping photos but absent from LiDAR:** image-guided stereo/refinement can potentially recover geometry. OpenMVS is the most direct candidate above. Success depends on texture, overlap, exposure, calibration and camera motion; the library's existence is not a quality guarantee.
3. **A small opening surrounded by measured geometry:** interpolate a patch using CGAL, with a conservative size limit.
4. **Never observed by depth or camera:** an inferred surface is an assumption. A geometric patch or learned completion can make a model closed or plausible; it cannot turn unseen content into a measurement. Keep such geometry identifiable if dimensions or object identity matter.

These distinctions follow from the documented inputs and algorithms above. Do not equate RGB texturing with RGB-driven depth estimation, or a watertight output with a faithful reconstruction.

## Suggested ReSpace experiment

Start with an offline Mac/backend comparison on several representative rooms:

1. Existing ARKit mesh + mild Taubin smoothing + conservatively limited CGAL repair.
2. Saved depth frames + intrinsics + poses → Open3D TSDF → same repair.
3. Best initial mesh + calibrated photos → OpenMVS `RefineMesh` → `TextureMesh`; separately evaluate its imported depth-map route.

This is an engineering proposal based on the tool interfaces, not a tested recommendation that one will consistently beat ARKit. Compare missing-surface area, wall planarity, retained thin furniture details, texture appearance and deviation from high-confidence depth. Protect doors/windows and genuine openings from blanket hole filling.

The current capture pipeline already retains JPEG keyframes, calibrated camera-to-scan transforms, optional depth/confidence and final mesh anchors (parent-agent source inspection). Its 40-frame cap, 1280-pixel JPEG maximum edge and quality 0.7 should be treated as an unvalidated reconstruction dataset. More coverage and higher-quality imagery may matter more than swapping smoothing filters. Before building a converter, verify depth/RGB alignment at their respective resolutions, intrinsic scaling, meter units, camera-axis conversion, timestamp correspondence, and whether pose drift needs correction.

ARKit's `smoothedSceneDepth` averages depth over time; it can reduce frame-to-frame variation but is not a final scene completion operation. [Apple documentation](https://developer.apple.com/documentation/arkit/arframe/smoothedscenedepth)

For a product integration, inspect the selected versions' licenses and transitive dependencies before committing to distribution or hosting: [OpenMVS license](https://github.com/cdcseacave/openMVS/blob/develop/LICENSE), [CGAL licensing](https://doc.cgal.org/latest/Manual/license.html).
