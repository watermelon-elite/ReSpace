import ARKit
import Metal

/// Copies one final ARFrame's current mesh anchors. This includes current transforms and
/// naturally excludes removed anchors, without retaining an unbounded history of AR buffers.
actor SceneMeshEncoder {
    func encode(_ anchors: [ARMeshAnchor], captureId: String, timestamp: Double) throws -> Data {
        guard !anchors.isEmpty else { throw ClientError.storage("No surfaces were captured. Move around the room and try again.") }
        var snapshots: [ScanMeshAnchor] = []
        var vertexCount = 0, triangleCount = 0
        for anchor in anchors.sorted(by: { $0.identifier.uuidString < $1.identifier.uuidString }) {
            try Task.checkCancellation()
            let geometry = anchor.geometry
            guard geometry.vertices.count > 0, geometry.faces.count > 0 else { continue }
            vertexCount += geometry.vertices.count; triangleCount += geometry.faces.count
            guard vertexCount <= ScanMeshSnapshot.maximumVertices,
                  triangleCount <= ScanMeshSnapshot.maximumTriangles else {
                throw ClientError.storage("This surface scan is too large. Scan a smaller room at a time.")
            }
            let positions = try copy(geometry.vertices)
            let normals = try copy(geometry.normals)
            let faces = geometry.faces
            guard faces.primitiveType == .triangle, faces.indexCountPerPrimitive == 3,
                  faces.bytesPerIndex == 2 || faces.bytesPerIndex == 4,
                  faces.count * 3 * faces.bytesPerIndex <= faces.buffer.length else { throw ScanMeshError.invalidGeometry }
            var triangles = Data(capacity: faces.count * 12)
            let base = faces.buffer.contents()
            for i in 0..<(faces.count * 3) {
                let pointer = base.advanced(by: i * faces.bytesPerIndex)
                let value = faces.bytesPerIndex == 4 ? pointer.loadUnaligned(as: UInt32.self) : UInt32(pointer.loadUnaligned(as: UInt16.self))
                triangles.appendScanUInt32(value)
            }
            let matrix = anchor.transform
            snapshots.append(try ScanMeshAnchor(id: anchor.identifier.uuidString,
                transform: (0..<4).flatMap { column in (0..<4).map { row in matrix[column][row] } },
                vertexCount: geometry.vertices.count, triangleCount: faces.count,
                positions: positions, normals: normals, triangles: triangles).removingUnreferencedVertices())
        }
        return try ScanMeshSnapshot(captureId: captureId, timestamp: timestamp, anchors: snapshots).encoded()
    }

    private func copy(_ source: ARGeometrySource) throws -> Data {
        guard source.format == .float3, source.componentsPerVector == 3, source.stride >= 12,
              source.count > 0, source.offset >= 0,
              source.offset + (source.count - 1) * source.stride + 12 <= source.buffer.length else {
            throw ScanMeshError.invalidGeometry
        }
        var data = Data(capacity: source.count * 12)
        let base = source.buffer.contents().advanced(by: source.offset)
        for i in 0..<source.count {
            let vertex = base.advanced(by: i * source.stride)
            for component in 0..<3 { data.appendScanFloat(vertex.loadUnaligned(fromByteOffset: component * 4, as: Float.self)) }
        }
        return data
    }
}
