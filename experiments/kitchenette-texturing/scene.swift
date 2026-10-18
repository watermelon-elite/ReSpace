import AppKit
import SceneKit
import simd

// The source camera matches the earlier kitchenette image experiment exactly.
let arguments = CommandLine.arguments
guard arguments.count == 4 else { fatalError("Usage: scene.swift MODEL.usdz OUTPUT_DIRECTORY capture|preview") }
let source = URL(fileURLWithPath: arguments[1])
let output = URL(fileURLWithPath: arguments[2], isDirectory: true)
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let scene = try SCNScene(url: source, options: nil)
scene.background.contents = NSColor(white: 0.93, alpha: 1)
let camera = SCNNode()
camera.camera = SCNCamera()
camera.camera!.fieldOfView = 72
camera.camera!.zNear = 0.03
camera.camera!.zFar = 40
camera.camera!.wantsHDR = true
camera.camera!.wantsExposureAdaptation = false
camera.camera!.exposureOffset = -1
scene.rootNode.addChildNode(camera)
let ambient = SCNNode()
ambient.light = SCNLight()
ambient.light!.type = .ambient
ambient.light!.intensity = 80
scene.rootNode.addChildNode(ambient)
let light = SCNNode()
light.light = SCNLight()
light.light!.type = .omni
light.light!.intensity = 120
light.position = SCNVector3(2, 2.8, 3)
scene.rootNode.addChildNode(light)
if arguments[3] != "capture" {
    // Soft inspection light avoids adding a point-light hotspot to baked RGB.
    ambient.light!.intensity = 1000
    light.light!.intensity = 0
    camera.camera!.wantsHDR = false
    camera.camera!.exposureOffset = 0
}
let renderer = SCNRenderer(device: nil, options: nil)
renderer.scene = scene
renderer.pointOfView = camera
let size = CGSize(width: 1440, height: 1000)
let views: [(String, SCNVector3, SCNVector3)] = arguments[3] == "capture"
    ? [("source", SCNVector3(1.35846, 1.6, 5.41760), SCNVector3(2.3, 1.3, 1.2))]
    : [("source", SCNVector3(1.35846, 1.6, 5.41760), SCNVector3(2.3, 1.3, 1.2)),
       ("left", SCNVector3(1.02, 1.6, 4.95), SCNVector3(2.3, 1.3, 1.2)),
       ("right", SCNVector3(1.78, 1.6, 5.05), SCNVector3(2.3, 1.3, 1.2)),
       ("reverse", SCNVector3(2.85, 1.6, 1.45), SCNVector3(1.45, 1.3, 5.2))]
func rows(_ matrix: simd_float4x4) -> [[Double]] {
    (0..<4).map { row in (0..<4).map { Double(matrix[$0][row]) } }
}
for (name, position, target) in views {
    camera.position = position
    camera.look(at: target)
    let snapshot = renderer.snapshot(atTime: 0, with: size, antialiasingMode: .multisampling4X)
    guard let tiff = snapshot.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff),
          let png = bitmap.representation(using: .png, properties: [:]) else { fatalError("Render failed") }
    try png.write(to: output.appendingPathComponent(name + ".png"))
    if arguments[3] == "capture" {
        let data: [String: Any] = [
            "width": Int(size.width), "height": Int(size.height),
            "world_to_camera": rows(simd_inverse(camera.simdWorldTransform)),
            "projection": rows(simd_float4x4(camera.camera!.projectionTransform(withViewportSize: size))),
            "convention": "row-major matrices; column vectors; camera looks down -Z; image origin top-left"
        ]
        try JSONSerialization.data(withJSONObject: data, options: [.prettyPrinted, .sortedKeys])
            .write(to: output.appendingPathComponent("camera.json"))
    }
    print("Rendered \(name)")
}
