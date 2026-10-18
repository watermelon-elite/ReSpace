import CoreGraphics
import ImageIO
import SceneKit
import UIKit
import simd

/// Uses the RGB images and poses captured from RoomPlan's shared ARKit session.
/// Processes one photo at a time and uses the model itself to reject occluded surfaces.
actor RoomColorizer {
    struct Result {
        let scene: SCNScene
        let hasSampledColor: Bool
        var isMeasuredMesh = false
        var coloredFraction: Float = 0
    }

    func load(_ id: String, repository: CaptureRepository) async throws -> Result {
        let manifest = try await repository.load(id)
        if let artifact = manifest.sceneMesh {
            let bytes = try await repository.bytes(artifact, captureId: id)
            let mesh = try ScanMeshSnapshot.decode(bytes, captureId: id)
            return try await MeasuredRoomScene().build(mesh, frames: manifest.frames, repository: repository)
        }
        let frames = manifest.frames
        let url = await repository.localPreviewURL(id)
        let scene = try SCNScene(url: url)
        var nodes: [SCNNode] = []
        scene.rootNode.enumerateChildNodes { node, _ in
            if let geometry = node.geometry, !geometry.sources(for: .vertex).isEmpty {
                nodes.append(node)
            }
        }
        let targets = nodes.map { node -> [SIMD3<Float>] in
            let bounds = node.boundingBox
            let low = SIMD3<Float>(Float(bounds.min.x), Float(bounds.min.y), Float(bounds.min.z))
            let high = SIMD3<Float>(Float(bounds.max.x), Float(bounds.max.y), Float(bounds.max.z))
            var points: [SIMD3<Float>] = []
            // Inset grid rays target the interior as well as the edges of broad surfaces.
            let fractions: [Float] = [0.15, 0.5, 0.85]
            for x in fractions {
                for y in fractions {
                    for z in fractions {
                        let local = low + (high - low) * SIMD3(x, y, z)
                        points.append(node.simdConvertPosition(local, to: nil))
                    }
                }
            }
            return points
        }
        var samples = Array(repeating: [SIMD3<Float>](), count: nodes.count)
        for frame in frames {
            try Task.checkCancellation()
            let meta = frame.metadata
            guard meta.orientation == "sensor", meta.cameraToScanTransform.count == 16,
                  meta.intrinsics.count == 4, meta.width > 0, meta.height > 0,
                  let artifact = frame.artifacts.first(where: { $0.type == "jpeg" }) else { continue }
            guard let bytes = try? await repository.bytes(artifact, captureId: id),
                  let image = RGBImage(bytes) else { continue }
            let m = meta.cameraToScanTransform
            let pose = simd_float4x4(columns: (
                SIMD4(m[0], m[1], m[2], m[3]), SIMD4(m[4], m[5], m[6], m[7]),
                SIMD4(m[8], m[9], m[10], m[11]), SIMD4(m[12], m[13], m[14], m[15])))
            guard m.allSatisfy(\.isFinite), abs(simd_determinant(pose)) > 0.0001 else { continue }
            let origin = SIMD3(pose.columns.3.x, pose.columns.3.y, pose.columns.3.z)
            let inverse = pose.inverse
            for (index, node) in nodes.enumerated() {
                for target in targets[index] {
                    let targetInCamera = inverse * SIMD4(target.x, target.y, target.z, 1)
                    guard ScanColorProjection.pixel(cameraPoint: [targetInCamera.x, targetInCamera.y, targetInCamera.z],
                        intrinsics: meta.intrinsics, width: meta.width, height: meta.height) != nil else { continue }
                    let distance = simd_distance(origin, target)
                    guard distance > 0.1, distance < 8 else { continue }
                    // Cast beyond the target so thin surfaces and rounded furniture can intersect.
                    let end = origin + simd_normalize(target - origin) * (distance + 1)
                    guard let hit = scene.rootNode.hitTestWithSegment(from: SCNVector3(origin), to: SCNVector3(end),
                        options: [SCNHitTestOption.backFaceCulling.rawValue: false, SCNHitTestOption.searchMode.rawValue: SCNHitTestSearchMode.closest.rawValue]).first,
                          hit.node === node else { continue }
                    let world = hit.simdWorldCoordinates
                    let camera = inverse * SIMD4(world.x, world.y, world.z, 1)
                    guard let pixel = ScanColorProjection.pixel(cameraPoint: [camera.x, camera.y, camera.z],
                        intrinsics: meta.intrinsics, width: meta.width, height: meta.height),
                          let rgb = image.color(x: pixel[0] / Float(meta.width), y: pixel[1] / Float(meta.height)) else { continue }
                    samples[index].append(rgb)
                }
            }
            await Task.yield()
        }
        var colored = false
        for (index, node) in nodes.enumerated() where samples[index].count >= 3 {
            let colors = samples[index]
            // A median limits the influence of highlights, shadows and object edges.
            let middle = colors.count / 2
            let r = colors.map(\.x).sorted()[middle]
            let g = colors.map(\.y).sorted()[middle]
            let b = colors.map(\.z).sorted()[middle]
            let tint = UIColor(red: CGFloat(r), green: CGFloat(g), blue: CGFloat(b), alpha: 1)
            guard let geometry = node.geometry?.copy() as? SCNGeometry else { continue }
            let materials = geometry.materials.isEmpty ? [SCNMaterial()] : geometry.materials
            geometry.materials = materials.map { original in
                guard let material = original.copy() as? SCNMaterial else { return original }
                // Preserve authored textures if a future exporter provides them.
                let contents = material.diffuse.contents
                if contents == nil || contents is UIColor || contents.map({ CFGetTypeID($0 as CFTypeRef) == CGColor.typeID }) == true {
                    material.diffuse.contents = tint
                    colored = true
                }
                return material
            }
            node.geometry = geometry
        }
        return Result(scene: scene, hasSampledColor: colored)
    }
}

struct RGBImage {
    let width: Int
    let height: Int
    let pixels: [UInt8]

    init?(_ data: Data) {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { return nil }
        let width = image.width, height = image.height
        var buffer = [UInt8](repeating: 0, count: width * height * 4)
        let rendered = buffer.withUnsafeMutableBytes { bytes -> Bool in
            guard let context = CGContext(data: bytes.baseAddress, width: width, height: height,
                bitsPerComponent: 8, bytesPerRow: width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else { return false }
            context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        guard rendered else { return nil }
        self.width = width; self.height = height
        pixels = buffer
    }

    func color(x: Float, y: Float) -> SIMD3<Float>? {
        guard x.isFinite, y.isFinite, x >= 0, x < 1, y >= 0, y < 1 else { return nil }
        let offset = (Int(y * Float(height)) * width + Int(x * Float(width))) * 4
        return SIMD3(Float(pixels[offset]), Float(pixels[offset + 1]), Float(pixels[offset + 2])) / 255
    }
}
