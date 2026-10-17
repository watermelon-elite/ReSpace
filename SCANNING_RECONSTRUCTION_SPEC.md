# ReSpace: Room Scanning and Reconstruction Specification

## 1. Objective and scope

Build an iPhone app that turns **one continuous walk around a furnished room into a textured 3D reconstruction**.

The reconstruction should preserve the room’s recognizable appearance, major dimensions, layout, and visible furniture geometry. Visual fidelity is the priority: a plain mesh or a collection of panoramic photographs does not satisfy the deliverable.

**Target environment:** iPhone 15 Pro Max, three developers with Swift, backend, and ML experience, and a 24-hour development window.

This specification covers capture, reconstruction, local persistence, and validation. A minimal reconstruction preview is included for inspection. Shopping, Gemini, redesign, furniture movement, backend upload, and the complete exploration interface are excluded. The saved data must permit those features later.

## 2. User experience

### Start a scan

The app explains that the user should:

- Scan one room at a time.
- Walk slowly around accessible areas while pointing the camera at walls and furniture.
- Observe important furniture from different angles during the same recording.
- Keep furniture and lighting reasonably unchanged during capture.
- Revisit areas with incomplete coverage before finishing.

Request camera permission when starting capture. Check support for the required LiDAR, scene reconstruction, and depth capabilities. Explain missing permissions or unsupported hardware before entering the scanner.

The baseline deployment target is iOS 18 or later, with validation on the team’s physical iPhone.

### Record continuously

A single **Start Scan** action begins one continuous AR session. There are no separate photograph or panorama capture steps.

During scanning, display:

- Live camera imagery.
- Observed surface coverage.
- Elapsed capture time.
- Tracking and capture guidance.
- A **Finish Scan** action.

Coverage represents surfaces actually observed. It must not imply that hidden areas have been captured.

Users can walk back to missed areas within the same session. Camera images and geometry are collected automatically.

### Finish and process

Finishing stops acquisition and begins local processing. Display named stages rather than an invented percentage:

1. Finalizing geometry.
2. Selecting camera views.
3. Applying photographic textures.
4. Completing structural gaps.
5. Saving the room.

Processing must not block UI interaction. Cancellation preserves the raw capture as an incomplete local package that can be processed again.

### Inspect the result

Provide a minimal 3D preview for assessing reconstruction quality, including an overhead view and recorded-camera viewpoints.

The preview must use the reconstructed geometry. It must not silently substitute a photograph or panorama for the model.

Clearly identify partial reconstructions and inferred regions. Preserve a diagnostic mode that shows geometry without photographic textures.

## 3. Capture architecture

### One shared coordinate system

Use a single AR session shared with RoomPlan:

- **RoomPlan:** structural surfaces, openings, room dimensions, and approximate furniture classifications and bounds.
- **ARKit scene reconstruction:** observed surface geometry.
- **Camera frames:** photographic appearance.
- **Camera poses and intrinsics:** image-to-geometry alignment.
- **Depth and confidence:** observation quality and visibility checks.

Apple documents shared RoomPlan/ARKit sessions, but the required configuration must be verified on the physical device during the initial feasibility test. [Apple’s RoomPlan enhancements](https://developer.apple.com/videos/play/wwdc2023/10192/)

All geometry, camera poses, and semantic objects must use the same scan-local coordinate frame, with distances expressed in meters. Persist explicit transforms whenever an exported representation uses a different frame.

Do not run independent camera sessions or assume separately acquired scans align automatically.

### Camera sampling

Do not retain every video frame.

Select keyframes based on:

- Normal tracking.
- Sufficient camera translation or rotation since the previous keyframe.
- Image sharpness.
- New surface coverage.
- Adequate overlap with existing observations.

Store the image, timestamp, pose, intrinsics, image orientation, and available depth/confidence metadata together. Preserve calibration when resizing images.

Write accepted frames incrementally to disk. Bound in-memory queues and skip acquisition when processing falls behind; never allow an unbounded frame backlog.

Sampling thresholds and image resolution are implementation tuning parameters, calibrated during the first physical-device test.

### Mesh capture

Track AR mesh anchors by identifier. Replace their stored geometry when anchors update and remove superseded anchors when appropriate.

Do not append every historical mesh update into the final reconstruction: doing so would create duplicated surfaces and obsolete geometry.

Retain the latest usable observed mesh and a record of the source coordinate transforms.

### Tracking failure

When tracking becomes unreliable:

- Suspend acceptance of new geometry and keyframes.
- Keep the last valid capture.
- Ask the user to slow down or return toward a previously observed area.

Resume only after tracking recovers in the existing coordinate frame.

If recovery fails, allow the user to finish the valid partial capture or restart. Never merge geometry from an unrelated session origin without verified alignment.

An app interruption ends the current capture segment. Seamless cross-launch scanning is outside this build.

## 4. Reconstruction pipeline

### A. Finalize observed geometry

Build the output mesh from the latest valid anchor geometry.

Apply conservative cleanup:

- Remove invalid and degenerate triangles.
- Recompute or normalize normals where necessary.
- Remove clearly isolated noise.
- Preserve visible furniture shape and room dimensions.

Avoid aggressive smoothing or simplification that erases recognizable details.

RoomPlan supplies structural context and semantic metadata; its approximate furniture boxes must not replace observed furniture geometry in the default reconstruction.

### B. Generate photographic textures

ARKit provides mesh geometry, not a ready-made photographic texture atlas. Texture generation is an explicit part of this project. [Apple’s ARMeshGeometry documentation](https://developer.apple.com/documentation/arkit/armeshgeometry)

For each mesh region:

1. Find camera keyframes from which the surface is visible.
2. Reject observations outside the image or facing away from the camera.
3. Reject occluded projections using mesh visibility and available depth confidence.
4. Rank remaining observations by sharpness, viewing angle, and useful image resolution.
5. Project image colors into a UV texture atlas.

The baseline implementation uses triangle-based UV allocation and selects the best valid source frame per triangle. Group neighboring triangles onto the same source frame where practical to reduce seams. Add atlas padding to prevent texture bleeding.

Exposure balancing and seam blending are secondary improvements after correct projection and occlusion handling work.

Never project a foreground object’s image onto a surface behind it merely because their image coordinates overlap.

Surfaces without reliable image coverage receive a neutral material and an incomplete-appearance flag. Do not generate photographic details to conceal missing observations.

### C. Complete conservative structural gaps

Permit inferred geometry only where measured structure supports it:

- Extend a detected wall across an occluded region.
- Complete a floor region within established room boundaries.
- Preserve detected doors and windows.

Avoid inventing ceilings, openings, furniture backs, or hidden objects when evidence is insufficient.

Inferred geometry must have separate provenance and must not be included as measured surface coverage. Unobserved textures remain neutral.

### D. Associate semantic objects

Assign stable scan-local IDs to RoomPlan furniture observations and structural elements. Save their categories, bounds, dimensions, and transforms.

Where practical, record candidate relationships between semantic bounds and observed mesh regions. Mark these associations as approximate.

**An object ID does not mean its furniture has been cleanly segmented into an independently movable mesh.** Future editing will require segmentation or replacement with an editable asset.

### E. Preserve viewing positions

Save well-tracked positions along the recorded walking path as candidate inspection viewpoints.

Choose spatially distinct positions with useful observed coverage. Do not invent positions inside furniture or outside the reconstructed room.

These positions are reconstruction outputs for the future viewer; implementing complete Street View navigation is outside this specification.

## 5. Local room-package contract

Save a versioned, self-contained directory that can later be uploaded without changing its internal representation.

| Component | Required contents |
|---|---|
| Manifest | Schema version, room ID, timestamps, processing status, units, coordinate conventions, relative asset paths |
| Capture metadata | Device/capture configuration, interruptions, tracking-quality summary |
| Camera observations | Keyframe images, timestamps, intrinsics, camera-to-world transforms, orientation, available depth/confidence |
| Observed geometry | Final captured mesh, normals, indices, anchor/source transforms |
| Structural model | RoomPlan export and normalized walls, floors, openings, and furniture observations |
| Reconstruction | Textured mesh, materials, texture images, UV coordinates |
| Provenance | Observed/inferred classification and texture-coverage status |
| Viewpoints | Recorded poses selected for later inspection or navigation |
| Quality report | Coverage, processing duration, warnings, and measured validation results when available |

Use JSON for metadata and binary assets for geometry and imagery. Save the viewable reconstruction as USD/USDZ with photographic materials; retain source geometry and calibration separately rather than treating the export as the only source of truth.

Package states are:

`capturing → captured → processing → ready`

Also support `partial`, `failed`, and `cancelled`, with the last completed stage and a readable reason.

Write results to temporary paths and mark the package ready only after required assets are successfully saved. Raw capture must survive a reconstruction failure so processing can be retried.

No Gemini credentials, retailer schema, or backend-specific URLs belong in the core capture format.

## 6. Quality, performance, and failure behavior

The agreed acceptance targets apply to the team’s test room, not to arbitrary rooms:

| Criterion | Target |
|---|---|
| Capture duration | Approximately 3–5 minutes |
| Processing duration | Within five minutes after capture |
| Geometry | Genuine reconstructed room and visible furniture surfaces |
| Appearance | Recognizable colors and placement of major furniture |
| Dimension accuracy | Major room dimensions within 10 cm of manual references |
| Inspection positions | At least three usable recorded positions |
| Rendering | Target 30 FPS on iPhone 15 Pro Max |
| Persistence | Saved reconstruction reopens without a network connection |

Validate dimension accuracy using at least three independently measured room spans. Inspect texture alignment from the selected viewpoints and the overhead view.

Reflective, transparent, dark, thin, and unobserved surfaces are known limitations. Depth confidence must inform processing rather than assuming all measurements are equally reliable. [Apple’s depth-confidence documentation](https://developer.apple.com/documentation/arkit/ardepthdata/confidencemap)

Required failure cases:

- Camera permission denied.
- Unsupported capture configuration.
- Tracking loss and recovery.
- Interrupted recording.
- Low storage or failed writes.
- Processing failure followed by retry.
- Partial texture coverage.
- Missing or corrupted saved assets.

A plain mesh may be saved for diagnosis, but must not be reported as a successful textured reconstruction.

## 7. Twenty-four-hour implementation sequence

| Time | Deliverable |
|---|---|
| Hours 0–3 | Physical-device feasibility test: shared capture, aligned geometry/images, visible photographic texture on a real scanned surface |
| Hours 3–10 | Continuous capture, keyframe persistence, mesh finalization, baseline texture projection |
| Hours 10–17 | End-to-end room reconstruction, semantic metadata, package save/load, minimal inspection preview |
| Hours 17–21 | Tracking recovery, conservative structural completion, memory and performance tuning |
| Hours 21–24 | Test-room validation, defect fixes, and preparation of a clearly labeled saved reconstruction |

Suggested ownership:

- **Swift developer:** capture session, guidance UI, tracking lifecycle, preview.
- **ML developer:** keyframe selection, projection, visibility filtering, texture quality.
- **Backend developer:** local package contract, incremental persistence, processing orchestration, save/load validation.

The first three hours are a technical gate. If photographic projection is not working, investigate alignment and visibility before adding UI polish. Do not quietly downgrade the deliverable to a plain RoomPlan model or photo tour.

A saved reconstruction of the actual test room is an acceptable demonstration fallback, clearly identified as previously captured.

This specification makes no claim that captured furniture is immediately editable. It preserves the geometry, imagery, calibration, identities, and provenance needed to integrate that work later.
