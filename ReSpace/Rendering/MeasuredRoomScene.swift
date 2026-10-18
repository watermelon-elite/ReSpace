import SceneKit
import UIKit
import simd

/// Builds measured geometry without fitting, smoothing, moving furniture or filling unseen surfaces.
/// One worker decodes one registered RGB/depth frame at a time.
actor MeasuredRoomScene {
    func build(_ mesh: ScanMeshSnapshot, frames: [CaptureFrame], repository: CaptureRepository) async throws -> RoomColorizer.Result {
        let scene = SCNScene()
        let worldPositions = mesh.anchors.map { anchor in (0..<anchor.vertexCount).map { anchor.worldPosition(at: $0) } }
        let worldNormals = mesh.anchors.map { anchor in (0..<anchor.vertexCount).map { anchor.worldNormal(at: $0) } }
        var accumulated = mesh.anchors.map { [SIMD4<Float>](repeating: .zero, count: $0.vertexCount) }
        // The complete dataset goes to the Mac; keep on-device preview work bounded.
        let count = min(48, frames.count)
        let previewFrames = (0..<count).map { frames[$0 * max(0, frames.count - 1) / max(1, count - 1)] }
        for frame in previewFrames {
            try Task.checkCancellation()
            let meta = frame.metadata
            guard meta.orientation == "sensor", meta.width > 0, meta.height > 0,
                  meta.cameraToScanTransform.count == 16, meta.cameraToScanTransform.allSatisfy(\.isFinite),
                  let projection = ScanColorProjection(intrinsics: meta.intrinsics, width: meta.width, height: meta.height),
                  let photo = frame.artifacts.first(where: { $0.type == "jpeg" }),
                  let depthArtifact = frame.artifacts.first(where: { $0.type == "depth" }),
                  let depthBytes = try? await repository.bytes(depthArtifact, captureId: mesh.captureId),
                  let photoBytes = try? await repository.bytes(photo, captureId: mesh.captureId),
                  let image = RGBImage(photoBytes) else { continue }
            let confidenceArtifact = frame.artifacts.first(where: { $0.type == "confidence" })
            var confidence: Data?
            if let confidenceArtifact { confidence = try? await repository.bytes(confidenceArtifact, captureId: mesh.captureId) }
            guard let depth = RegisteredScanDepth(metadata: meta, depth: depthBytes, confidence: confidence) else { continue }
            let m = meta.cameraToScanTransform
            let pose = simd_float4x4(columns: (
                SIMD4(m[0],m[1],m[2],m[3]), SIMD4(m[4],m[5],m[6],m[7]),
                SIMD4(m[8],m[9],m[10],m[11]), SIMD4(m[12],m[13],m[14],m[15])))
            guard abs(simd_determinant(pose)) > 0.0001 else { continue }
            let inverse = pose.inverse
            let origin = SIMD3(pose.columns.3.x, pose.columns.3.y, pose.columns.3.z)
            for (anchorIndex, anchor) in mesh.anchors.enumerated() {
                try Task.checkCancellation()
                for index in 0..<anchor.vertexCount {
                    let point = worldPositions[anchorIndex][index]
                    let camera = inverse * SIMD4(point.x, point.y, point.z, 1)
                    guard let pixel = projection.pixel(cameraPoint: SIMD3(camera.x,camera.y,camera.z)) else { continue }
                    let u = pixel[0] / Float(meta.width), v = pixel[1] / Float(meta.height)
                    guard depth.seesSurface(u: u, v: v, cameraDepth: -camera.z) else { continue }
                    let delta = origin - point
                    let squaredDistance = simd_length_squared(delta)
                    guard squaredDistance > 0.01, squaredDistance < 25 else { continue }
                    let facing = simd_dot(worldNormals[anchorIndex][index], delta / sqrt(squaredDistance))
                    guard facing > 0.2, let rgb = image.color(x: u, y: v) else { continue }
                    let weight = facing * facing / max(0.25, squaredDistance)
                    accumulated[anchorIndex][index] += SIMD4(rgb.x * weight, rgb.y * weight, rgb.z * weight, weight)
                }
            }
            await Task.yield()
        }
        var coloredVertices = 0, vertexCount = 0
        for (anchorIndex, anchor) in mesh.anchors.enumerated() {
            try Task.checkCancellation()
            let positions = SCNGeometrySource(data: anchor.positions, semantic: .vertex, vectorCount: anchor.vertexCount,
                usesFloatComponents: true, componentsPerVector: 3, bytesPerComponent: 4, dataOffset: 0, dataStride: 12)
            let normals = SCNGeometrySource(data: anchor.normals, semantic: .normal, vectorCount: anchor.vertexCount,
                usesFloatComponents: true, componentsPerVector: 3, bytesPerComponent: 4, dataOffset: 0, dataStride: 12)
            var colors = Data(capacity: anchor.vertexCount * 16)
            for sample in accumulated[anchorIndex] {
                let rgb: SIMD3<Float>
                if sample.w > 0 {
                    rgb = SIMD3(sample.x, sample.y, sample.z) / sample.w; coloredVertices += 1
                } else { rgb = SIMD3(repeating: 0.65) }
                colors.appendScanFloat(rgb.x); colors.appendScanFloat(rgb.y)
                colors.appendScanFloat(rgb.z); colors.appendScanFloat(1)
            }
            let colorSource = SCNGeometrySource(data: colors, semantic: .color, vectorCount: anchor.vertexCount,
                usesFloatComponents: true, componentsPerVector: 4, bytesPerComponent: 4, dataOffset: 0, dataStride: 16)
            let element = SCNGeometryElement(data: anchor.triangles, primitiveType: .triangles,
                primitiveCount: anchor.triangleCount, bytesPerIndex: 4)
            let geometry = SCNGeometry(sources: [positions, normals, colorSource], elements: [element])
            let material = SCNMaterial()
            material.diffuse.contents = UIColor.white; material.lightingModel = .lambert
            material.isDoubleSided = true
            geometry.materials = [material]
            let node = SCNNode(geometry: geometry); node.name = anchor.id
            let m = anchor.transform
            node.simdTransform = simd_float4x4(columns: (
                SIMD4(m[0],m[1],m[2],m[3]), SIMD4(m[4],m[5],m[6],m[7]),
                SIMD4(m[8],m[9],m[10],m[11]), SIMD4(m[12],m[13],m[14],m[15])))
            scene.rootNode.addChildNode(node)
            vertexCount += anchor.vertexCount
        }
        return RoomColorizer.Result(scene: scene, hasSampledColor: coloredVertices > 0,
            isMeasuredMesh: true, coloredFraction: Float(coloredVertices) / Float(max(1, vertexCount)))
    }
}
