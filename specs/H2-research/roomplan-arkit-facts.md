# RoomPlan / ARKit facts for a Python CapturedRoom parser (iOS 17/18)

Researched 2026-10-17. Tags used below:
- **[CONFIRMED-DOC]**: Apple developer documentation (fetched from the DocC JSON at `developer.apple.com/tutorials/data/documentation/...`) or a WWDC transcript.
- **[CONFIRMED-SAMPLE]**: a real `JSONEncoder` output that someone posted.
- **[COMMUNITY]**: forum or GitHub reports, not from Apple.
- **[INFERRED]**: my reasoning from the sources above. Check it on a device.

The most useful advice: have the phone dump one real `JSONEncoder` output from an iOS 18 device, and build the parser against that file. No complete public iOS 17/18 sample exists. The only real sample found is a wall-only excerpt from the iOS 16 era.

---

## 1. CapturedRoom Codable JSON shape

### Swift API members (these become the JSON keys) [CONFIRMED-DOC]
`CapturedRoom` (https://developer.apple.com/documentation/roomplan/capturedroom) has:
- `identifier: UUID`
- `story: Int` (iOS 17)
- `version: Int`
- `walls`, `doors`, `windows`, `openings`, `floors` (iOS 17): each a `[CapturedRoom.Surface]`
- `objects: [CapturedRoom.Object]`
- `sections: [CapturedRoom.Section]` (iOS 17)

It conforms to Encodable and Decodable through custom `encode(to:)` and `init(from:)`, so Apple writes the encoder itself rather than relying on synthesized Codable.

`CapturedRoom.Surface` (https://developer.apple.com/documentation/roomplan/capturedroom/surface) has:
- `identifier: UUID`
- `parentIdentifier: UUID?` (iOS 17)
- `category: Surface.Category`
- `confidence: Confidence`
- `transform: simd_float4x4`
- `dimensions: simd_float3`
- `story: Int` (iOS 17)
- `completedEdges: Set<Surface.Edge>`
- `curve: Surface.Curve?`
- `polygonCorners: [simd_float3]` (iOS 17)

`CapturedRoom.Object` (https://developer.apple.com/documentation/roomplan/capturedroom/object) has:
- `identifier`, `parentIdentifier: UUID?` (iOS 17), `category: Object.Category`, `confidence`
- `transform: simd_float4x4`, `dimensions: simd_float3`, `story: Int` (iOS 17)
- `attributes: [any CapturedRoomAttribute]` (iOS 17). `CapturedRoom.AttributesCodableRepresentation` (iOS 17) is the serializable form.

`CapturedRoom.Section` (iOS 17) has `label: Section.Label`, `story: Int` and `center: simd_float3`.

`Surface.Curve` has `startAngle` and `endAngle` (`Measurement<UnitAngle>`), `radius: Float`, and `center: simd_float2` (iOS 17). The docs describe `center` as "Center of the curve, in local coordinates. Corresponds to xz center coordinates".

`Surface.Edge` has the cases `top`, `bottom`, `left` and `right`.

### Real sample (Qiita, kitanote; iOS 16 era; walls only, other keys removed by the author) [CONFIRMED-SAMPLE]
Source: https://qiita.com/kitanote/items/efcc3f03cf1a84703e6c (raw markdown: append `.md`). The author produced it with `JSONEncoder().encode(room)` and decoded it back with `JSONDecoder().decode(CapturedRoom.self, ...)`.
```json
"walls": [{
  "category":   { "wall": {} },
  "confidence": { "high": {} },
  "dimensions": [3.4638471603393555, 2.3485732078552246, 0],
  "completedEdges": [],
  "parentIdentifier": null,
  "identifier": "3EFAE2ED-4537-4E74-B9B8-50DA8645184A",
  "curve": null,
  "transform": [0.4371742904186249, 0, -0.8993767499923706, 0,
                0, 1, 0, 0,
                0.8993766903877258, 0, 0.4371742904186249, 0,
                -1.9961872100830078, -0.15500573813915253, 0.18577753007411957, 1]
}]
```
`parentIdentifier` already appears here, which suggests the key predates its public iOS 17 API. A forum post also says it was in the JSON "but not in the documentation".

### Other real keys seen
- **`coreModel`** [COMMUNITY, from real outputs]: each encoded room carries a large base64 string in `coreModel` (Apple-internal `RSFloorPlan`). One report measured 828 kB with it and 267 kB without it. The Python parser must ignore it and any other unknown keys.
  - https://developer.apple.com/forums/thread/732441 (excerpt: `{"rooms":[{"story":1,"floors":[...],"coreModel":"xPNhmdph..."`)
  - https://developer.apple.com/forums/thread/745735
- `CapturedStructure` JSON contains `rooms`, `story`, `floors` and `coreModel`, plus the documented `identifier`, `walls`, `doors`, `windows`, `openings`, `objects`, `sections` and `version`.

### Enum encoding
- **Surface category, object category, `Confidence` and `Edge`** are plain Swift enums without raw values. Apple's docs list only Codable, Equatable and Hashable (plus CaseIterable for Object.Category and Edge), not RawRepresentable.
  - They encode in Swift's synthesized enum style (SE-0295): `{"wall":{}}` and `{"high":{}}` [CONFIRMED-SAMPLE].
  - By the same rule: a door is `{"door":{"isOpen":true}}` or `{"door":{"isOpen":false}}`, a floor is `{"floor":{}}`, objects look like `{"storage":{}}` or `{"washerDryer":{}}`, and edges are `[{"top":{}},{"left":{}},...]` [INFERRED, high confidence; no posted door sample found].
  - Gist https://gist.github.com/Hadevs/2ece8bdc2b01be35da4c222711cb7099 decodes object `category` as `[String: EmptyStruct]` and matches on the `"storage"` key, which fits this format [COMMUNITY].
  - Parser advice: take the single key of the dict. For a door, read `.door.isOpen`, and default to `None` if it is missing.
- **`Section.Label`** and the attribute enums (`ChairType` and the rest) are RawRepresentable. `Section.Label` is also Codable, so it probably encodes as a bare raw-value string, for example `"livingRoom"` [INFERRED, medium; raw type not shown in the docs].
- **`attributes` encoding**: not found in any public sample [UNCONFIRMED]. Treat it as opaque, log it, and parse it leniently.
- **`confidence`** is `{"high":{}}`, `{"medium":{}}` or `{"low":{}}`. It means certainty in the classification, not geometric accuracy.
  - https://developer.apple.com/documentation/roomplan/capturedroom/confidence
- **`identifier`** is an uppercase UUID string. `story` and `version` are integers.

## 2. simd encoding
- **`simd_float3`** encodes as a JSON array of 3 numbers, not 4 despite the SIMD padding [CONFIRMED-SAMPLE: `"dimensions":[3.46,2.35,0]`]. The Swift standard library's SIMD Codable writes the scalars into an unkeyed container.
- **`simd_float4x4`** encodes as a **flat array of 16 numbers in column-major order** [CONFIRMED-SAMPLE].
  - Elements 12–14 hold the translation and element 15 is 1. Elements 3, 7 and 11 are 0.
  - Elements 0–3 are a unit horizontal vector, which is column 0 (the "right" axis).
  - The Hadevs gist also reads the position from `transform[12]` and `transform[13]`.
  - Python: `M = np.array(t, dtype=float).reshape(4, 4).T`, giving `M[:3,3]` = position, `M[:3,0]` = local x, `M[:3,1]` = local y, `M[:3,2]` = local z.
  - `simd_float4x4` has no stdlib Codable conformance. Third-party packages add it retroactively, and the compiler warns about that. So the 16-float layout comes from RoomPlan's own encoder [INFERRED].
  - A defensive parser should also accept a nested 4×4 array. One TypeScript RoomPlan parser accepts both: https://github.com/Begzod10/andoza_ai_mobile/pull/1 [COMMUNITY].
- **`polygonCorners`** is `[simd_float3]` and is expected to encode as `[[x,y,z], ...]` [INFERRED from the simd_float3 rule].
- **`Section.center`** is `[x,y,z]`. **`curve.center`** is `[x,z]`.
- The encoding of the `Measurement` values `startAngle` and `endAngle` is unconfirmed. Foundation's `Measurement` Codable usually produces `{"value":..,"unit":{"symbol":..,"converter":..}}` [INFERRED, low]. The parser should be lenient.

## 3. Coordinate conventions
- **World frame** [CONFIRMED-DOC]: ARKit world space is right-handed, y up (parallel to gravity), in meters.
  - With `.gravity` alignment, the **origin is the device's position when the session is first run**. -z is the initial camera heading projected onto the horizontal plane.
  - https://developer.apple.com/documentation/arkit/arconfiguration/worldalignment-swift.enum/gravity
  - https://developer.apple.com/documentation/arkit/arcamera/transform
- **The floor is NOT at y=0.**
  - In the Qiita sample, a 2.35 m tall wall has its center at y = -0.155, so the floor sits at about -1.33 m: roughly the phone's starting height below the origin [CONFIRMED-SAMPLE + INFERRED].
  - Compute the floor height from `floors[i].transform` translation y, or as wall center y minus `dimensions.y/2`.
  - The WWDC23 session says each room scan has "its own coordinate system, meaning the origin and orientation of the world coordinate is different for each room".
- **Wall and other surface local frame**:
  - Column 0 is "right", along the wall and horizontal. Column 1 is "up". Column 3 is the center position. This comes from an Apple WWDC22 Slack answer relayed in https://developer.apple.com/forums/thread/707998 [COMMUNITY relay of Apple].
  - Column 2 is the plane normal [INFERRED; consistent with the sample].
  - `dimensions = (width, height, 0)` [CONFIRMED-SAMPLE: z = 0 for walls; forum users also report z = 0 for doors].
  - Corners are `center ± right*w/2 ± up*h/2`.
- **Wall sidedness** [CONFIRMED by Apple DTS]: surfaces are estimated planes with no thickness. The API does not say which side is interior or exterior, and the sign of the normal is not documented.
  - https://developer.apple.com/forums/thread/837547
  - Infer the inside from the floor polygon or room centroid.
- **Object frame**: an oriented box centered at the translation, with yaw only in practice. `dimensions = (x: width, y: height, z: depth)` along the local axes, with y up.
  - [INFERRED, high] RoomPlan-2D draws the top-down rectangle with width = `dimensions.x` and depth = `dimensions.z`: https://github.com/denniswave/RoomPlan-2D (`Floor Plan/FloorPlanObject.swift`).
  - The docs only say "A bounding box sized to the object's extremities".
- **Doors and windows**:
  - The transform is a world-space transform like every other element [INFERRED, high]. The docs describe it as the "position and orientation in the scene", and the 2D floor-plan code in the forums draws doors and windows directly from it.
  - `parentIdentifier` (iOS 17+) links them to their wall [CONFIRMED-DOC]: "the parent of a window is the wall surface on which the window rests".
  - For objects, the parent can be another object, for example sink → storage.
  - Openings can have no parent. One importer assigns them to the nearest wall [COMMUNITY].
- **`polygonCorners`** [CONFIRMED-DOC]: "A 2D polygon that represents nonuniform wall heights and floor shapes … describes the polygon in local plane coordinates". It is in the surface's local frame, so world = `transform @ [x,y,z,1]`.
  - The axes used inside the floor's local frame are **undocumented**.
  - Forum users report that the floor transform has zero y and z Euler angles and that the polygon "seems to have a different orientation than the walls" [COMMUNITY, unresolved].
    - https://developer.apple.com/forums/thread/786887
    - https://developer.apple.com/forums/thread/713409
  - Determine empirically which component is near zero after applying the transform. The floor is a "rectangle during scanning and beautified as a polygon when scanning ends" (WWDC23).
  - `polygonCorners` can be an empty list for surfaces without a polygon [INFERRED].
- **Story bug** [COMMUNITY]: `floors[].story` was 0 everywhere in some iOS 17 exports. https://developer.apple.com/forums/thread/732424

## 4. Categories and attributes [CONFIRMED-DOC]
- **Object.Category** (iOS 16+, unchanged through the current docs) has 16 cases: `bathtub, bed, chair, dishwasher, fireplace, oven, refrigerator, sink, sofa, stairs, storage, stove, table, television, toilet, washerDryer`. https://developer.apple.com/documentation/roomplan/capturedroom/object/category-swift.enum
- **Surface.Category** cases: `wall, door(isOpen: Bool), window, opening, floor`.
- **Section.Label** (iOS 17) cases: `livingRoom, kitchen, diningRoom, bedroom, bathroom, unidentified`.
- **Attributes** (iOS 17, conforming to `CapturedRoomAttribute`). https://developer.apple.com/documentation/roomplan/captured-object-attributes
  - `ChairType`: dining, stool, swivel, unidentified
  - `ChairArmType`: existing, missing
  - `ChairBackType`: existing, missing
  - `ChairLegType`: four, star, unidentified
  - `SofaType`: rectangular, singleSeat, lShaped, lShapedExtension, unidentified
  - `StorageType`: cabinet, shelf
  - `TableType`: dining, coffee, unidentified
  - `TableShapeType`: rectangular, circularElliptic, lShaped, unidentified

## 5. Shared ARSession during RoomPlan
- **Same world frame** [INFERRED, high]:
  - `RoomCaptureSession.arSession` is the session RoomPlan runs on, and Apple says you may use it "to display your own AR experience".
  - WWDC22 sets `arView.session = captureSession.arSession` to overlay RoomPlan geometry.
  - Apple's multi-room guide requires each RoomCaptureSession to "share the same common coordinate space as the ARSession".
  - So `currentFrame.camera.transform` and the CapturedRoom transforms share one world frame.
  - https://developer.apple.com/documentation/roomplan/roomcapturesession/arsession
  - https://developer.apple.com/documentation/roomplan/scanning-the-rooms-of-a-single-structure
- **Caveat** [COMMUNITY]: one team reports the world origin is re-set each time `captureSession.run(configuration:)` is called, even with a reused ARSession and `stop(pauseARSession:false)`. https://developer.apple.com/forums/thread/763244
  - Collect keyframe poses only after `captureSession(_:didStartWith:)`, and only within the same run that produces the CapturedRoomData.
- **`sceneDepth` is not guaranteed** during RoomPlan [COMMUNITY, several reports]:
  - Apple's docs say `sceneDepth` and `smoothedSceneDepth` are nil unless the configuration's `frameSemantics` includes them [CONFIRMED-DOC]. https://developer.apple.com/documentation/arkit/arframe/scenedepth
  - Apr 2023: through `RoomCaptureView.captureSession`, `sceneDepth != nil` was true. With a standalone `RoomCaptureSession()` it was false. https://developer.apple.com/forums/thread/728601
  - The internal configuration lacked `.sceneDepth`. https://developer.apple.com/forums/thread/710134
  - With a custom ARSession (iOS 17 `init(arSession:)`), `sceneDepth` became nil once `RoomCaptureSession.run` started. The poster's accepted fix was to re-run a sceneDepth-enabled `ARWorldTrackingConfiguration` *after* the `didStart` delegate fires. https://developer.apple.com/forums/thread/763400
  - Dec 2025: both depth maps were still nil with a custom session (no answer). https://developer.apple.com/forums/thread/808834
  - Nobody reports whether that re-run degrades RoomPlan.
- **Safer re-run recipe** [INFERRED]:
  - Copy `session.configuration as? ARWorldTrackingConfiguration`, insert `.sceneDepth`, and call `run(config)` with no options.
  - Per ARKit docs, re-running with the same configuration type and no `.resetTracking` "resumes device position tracking from the last known state", so the world frame is kept. A *different* configuration type always resets tracking. https://developer.apple.com/documentation/arkit/arsession/run(_:options:)
  - Copying the config keeps whatever plane or scene-reconstruction settings RoomPlan set.
  - Verify at runtime (`frame.sceneDepth != nil`) and degrade gracefully.

## 6. ARFrame facts
- **`capturedImage`** [CONFIRMED-DOC]:
  - Full-range planar YCbCr 4:2:0 (BT.601), in the camera's **native sensor orientation**, which is always landscape. https://developer.apple.com/documentation/arkit/arcamera/imageresolution
  - The size is `camera.imageResolution`, commonly 1920×1440 by default on LiDAR iPhones and iPads [COMMUNITY; read it at runtime].
- **`camera.intrinsics`** [CONFIRMED-DOC + sample code]:
  - The pinhole K, with fx, fy, ox, oy in pixels and the principal point measured from the image's **top-left**. https://developer.apple.com/documentation/arkit/arcamera/intrinsics
  - It refers to the `capturedImage` / `imageResolution` pixel grid. Apple's point-cloud sample applies `camera.intrinsics.inverse` to points laid out over `camera.imageResolution`.
  - For depth pixels, scale fx, fy, cx and cy by `depthWidth / imageWidth` (for example 256/1920). The aspect ratio is the same; WWDC20 says the depth map is lower resolution "which still presents the same aspect ratio".
  - https://developer.apple.com/forums/thread/676368
- **`sceneDepth.depthMap`**:
  - Float32 meters (`kCVPixelFormatType_DepthFloat32`, 'fdep') per Apple's doc example [CONFIRMED-DOC, worded as "for example"; check the format at runtime].
  - 256×192 [COMMUNITY, widely reported; the resolution is not configurable per Apple DTS]. Updated at 60 Hz (WWDC20).
  - https://developer.apple.com/documentation/arkit/ardepthdata/depthmap
- **`confidenceMap`**: `kCVPixelFormatType_OneComponent8`, holding `ARConfidenceLevel` raw values 0 = low, 1 = medium, 2 = high [CONFIRMED-DOC]. https://developer.apple.com/documentation/arkit/ardepthdata/confidencemap
- **Depth is z-depth along the optical axis, not ray length** [CONFIRMED-DOC]: "distance from the plane of the camera" (ARDepthData docs and the WWDC20 10611 transcript).
- **Camera space** [CONFIRMED-DOC]:
  - +x runs along the device's long axis toward the Home-button side, which is image +u in native orientation.
  - +y is up, opposite to image v.
  - +z points out of the screen, so the camera **looks down -z**.
- **Pixel to ray** [CONFIRMED by the Apple sample]: the sample computes `local = K⁻¹·[u,v,1]·d` (an OpenCV-style frame) and then `world = camera.viewMatrix(.landscapeRight)⁻¹ · flipYZ · local`, where `flipYZ = diag(1,-1,-1,1)` and the display rotation for `.landscapeRight` is 0.
  - In Python, with native-orientation pixels and v growing downward:
    ```
    x_c = (u - cx)/fx * d
    y_c = -(v - cy)/fy * d
    z_c = -d
    p_world = camera.transform @ [x_c, y_c, z_c, 1]
    ```
  - Use `(u + 0.5, v + 0.5)` for pixel centers if needed.
  - Sample mirror: https://github.com/isakdiaz/arkit-scenedepth-pointcloud (`Shaders.metal` `worldPoint`, `Renderer.swift` `makeRotateToARCameraMatrix`).
  - DTS version: https://developer.apple.com/forums/thread/676368

## 7. RoomBuilder output frame vs. the live session
- No Apple statement says RoomBuilder re-origins or straightens the room [UNCONFIRMED].
- Evidence that it stays in the ARSession world frame [INFERRED, medium-high]:
  - Apple's multi-room workflow runs `RoomBuilder.capturedRoom(from:)` on each room and then merges the results with `StructureBuilder`. That merge only works because every processed room is in "the same 3D world coordinate" of the shared or relocalized ARSession (WWDC23 10192 and the structure-scanning guide).
  - WWDC23 also says RoomPlan results can be combined "without disrupting your existing ARAnchors".
  - The Qiita processed sample has an origin around phone height, not at a floor or room corner, which fits ARKit's session origin.
- Beautification (`.beautifyObjects`, polygonal floors, snapping) changes geometry *within* that frame. Expect centimetre-level differences between `didUpdate` snapshots and the final room, not a frame change [INFERRED].
- `RoomCaptureView` *displays* the final model re-centred and rotated, but that is view-only [INFERRED].
- **Recommendation:** verify on a device once by projecting final wall corners into a keyframe through its `camera.transform` and K. If they line up, store a 4×4 "session→room" transform field anyway (identity for now) so the server can handle a future mismatch.
