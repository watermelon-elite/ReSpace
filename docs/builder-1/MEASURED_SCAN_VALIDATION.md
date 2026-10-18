# Measured room surface capture

Implemented October 17, 2026. Physical room accuracy has not yet been measured.

## What this version does

New local room scans use one ARSession for RoomPlan, RGB photos, depth and ARKit `.mesh` scene reconstruction. The custom session runs before RoomCaptureView is initialized, following [Apple’s documented setup](https://developer.apple.com/documentation/roomplan/roomcaptureview/init(frame:arsession:)). The app requests native scene depth when supported and does not enable additional plane-detection flattening.

When Done is tapped, capture requires normal tracking and nonempty mesh geometry. A single final ARFrame supplies the complete current mesh anchor set; the app copies the current vertex, normal and triangle buffers and each anchor’s rigid transform. It does not accumulate older versions of the same anchor. This avoids installing another ARSession delegate alongside RoomPlan.

The mesh remains in meters in the same scan coordinates as camera poses. Vertices are not fitted to RoomPlan boxes, rescaled, smoothed or moved to beautify furniture. New local RoomPlan processing also disables chair-arrangement beautification. The derived RoomPlan USDZ is retained, while the local viewer displays the measured mesh alone.

Saved geometry uses a versioned binary snapshot with capture identity, coordinate convention, anchor transforms, packed float32 positions/normals and uint32 triangle indices. Validation rejects malformed buffers, nonfinite coordinates, out-of-range indices, scale/reflection in transforms, duplicate anchors and excessive geometry. The snapshot is hashed with the existing artifact storage and survives save/reopen. Scans exceeding the resource budget fail explicitly rather than being silently reduced.

Tracking loss, relocalization, stale camera frames and abrupt sampled pose changes interrupt capture. No reset or re-centering is applied within a scan. These checks reduce known coordinate problems; they do not establish ground-truth room accuracy or eliminate gradual tracking drift.

## Color and viewing

The 3D-only viewer loads measured surfaces directly. It samples colors per vertex from the retained ARKit photos. Matching native depth rejects foreground occlusion and geometric disagreement, while available confidence excludes low-confidence depth samples. Surface orientation and distance weight the remaining colors. Processing decodes one photo/depth pair at a time.

Vertices without an accepted photo sample remain neutral gray. Unseen surfaces remain missing. There is no automatic filling, furniture asset substitution or detailed photographic texture atlas.

The ruler button measures straight-line distances between two selected mesh surface points, in meters. Measurement markers do not intercept subsequent surface selections. This provides an in-app way to compare the captured model with a physical measurement.

Older scans remain viewable and are identified as simplified scans. They need a new scan to obtain measured surface detail. Backend/service rendering is not switched to this local mesh format in this first version; the new mesh artifact is emitted only in local capture mode.

## Verification completed

- iOS Simulator build: passed.
- Core suite: 32 tests passed, including metric transform/round-trip, invalid geometry rejection, depth/confidence visibility, mesh persistence/integrity and legacy manifest compatibility.
- Native synthetic SceneKit check: passed for local vertex preservation, exactly-once translated anchor placement, translated camera alignment, top/bottom RGB orientation, and depth-occluded surfaces retaining neutral color.
- Whitespace/diff checks: passed.

These checks validate data handling, coordinates and rendering logic. They do not measure real LiDAR accuracy, completeness, camera/mesh calibration on a device, sustained performance or thin furniture geometry. Physical device discovery found no available device for that validation.

## Physical validation before relying on measurements

1. Scan a well-lit, static room with a chair, a table and an unobstructed wall. Move slowly around each object and include sides, corners, the floor and visible areas beneath furniture.
2. Measure room width/depth and a table’s width/height with a tape or laser. Record those values independently of the app. Use the viewer’s ruler on corresponding captured surfaces, repeat each selection, and record absolute and percentage errors. Define an acceptable product tolerance before evaluating the results; this implementation claims no measured tolerance.
3. Compare visual alignment of tabletops, chair backs/legs, wall corners and floor intersections. Check for double surfaces, holes, missing thin parts and colors crossing object edges. Use multiple scans and compare repeatability rather than accepting one favorable result.
4. Save, terminate the app and reopen the room. Repeat measurements to verify persistence. Exercise interruption, backgrounding, restart and save recovery; verify there is no mixed-origin geometry.
5. Check peak memory, opening time, frame rate and sustained capture temperature on the intended iPhone. Inspect sparse/long scans: the geometry continues beyond the existing 40-photo color-sampling budget, so later or hidden surfaces may remain uncolored.

Apple describes scene reconstruction as an approximation of the physical environment. Thin, hidden or poorly observed parts must be assessed on the intended device; a passing software test cannot guarantee they are captured. [ARKit scene reconstruction](https://developer.apple.com/documentation/arkit/arworldtrackingconfiguration/scenereconstruction)

## Scan startup regression fixed

The physical iPhone startup probe reproduced the immediate “Surface capture stopped” interruption twice. RoomPlan enabled reconstruction option value 25, which still contains the mesh bit (1). The controller incorrectly required exact equality with `.mesh`; it now checks that the active options include the mesh capability. Disabled or absent reconstruction still interrupts capture. The shared-session identities matched, and mode 25 persisted throughout the successful test, ruling out a different session or a brief startup transition as the cause.

A regression using the recorded flags failed before the fix and passed afterward; the full core suite now passes 34 tests. The same on-device startup loop stayed scanning for 35 observations over about seven seconds and delivered 22 mesh anchors. The normal fixed app was installed and launched after removing the temporary probe from its build. Production sources contain no probe instrumentation. This verifies startup and delivery of real mesh geometry; physical dimensional accuracy still requires the room measurement procedure above.

## Scan save regression fixed

The connected iPhone reproduced the exact “The room service returned incomplete geometry. Refresh the room or rescan.” error after Done, despite delivering 21 mesh anchors. Temporary diagnostics traced rejection to the mesh snapshot's finite-value validation, not a service response. A follow-up scan found 1,219 nonfinite normal vectors, all on vertex slots that no triangle referenced; no captured position or referenced normal was nonfinite. These observations identify the failing condition on this device, without asserting why ARKit retains those unused slots internally.

The exporter now removes unreferenced vertex slots and remaps triangle indices before persistence. Every triangle, its order and winding, and its referenced position/normal values are preserved exactly; anchor transforms remain unchanged. No captured surface is deleted, rescaled or fitted. Structural validation runs before compaction, and the compact snapshot still rejects nonfinite referenced values, invalid indices, malformed buffers and nonrigid transforms. Persisted snapshots remain strict. Local mesh failures now report a surface-mesh error instead of attributing the problem to the room service.

This follows the indexed geometry relationship in [Apple's ARMeshGeometry.faces documentation](https://developer.apple.com/documentation/arkit/armeshgeometry/faces): face indices identify vertices in the vertex buffer. Removing slots unused by every face does not alter the represented triangles.

The regression fixture, including interleaved unused NaN normals, failed before the fix. It now verifies the exact world position and normal at every triangle corner, winding/order, save/decode round trip, and continued rejection of invalid referenced geometry. All 35 portable core tests pass. The original 15-second capture/Done loop then reached the saved/ready state with 23 mesh anchors and no error on the physical iPhone. The normal fixed app was rebuilt, installed and launched after removing the temporary probe UI; production sources contain no diagnostic instrumentation.

This verifies the save failure is fixed and that compaction preserves captured geometry. Physical dimensional accuracy still requires comparison with independent room measurements.
