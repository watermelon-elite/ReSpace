import Foundation

enum ScanMeshError: Error, LocalizedError {
    case invalidGeometry

    var errorDescription: String? {
        "The captured surface mesh contains invalid geometry. Start a new scan."
    }
}

/// Metric geometry in the same ARKit world coordinates as FrameMetadata camera poses.
/// Anchor vertices stay local. The anchor-to-scan transform is applied exactly once at display time.
struct ScanMeshSnapshot: Codable, Sendable {
    var schemaVersion = 1
    var captureId: String
    var timestamp: Double
    var coordinateSystem = "arkit_scan_meters_y_up"
    var anchors: [ScanMeshAnchor]

    static let maximumVertices = 1_000_000
    static let maximumTriangles = 2_000_000

    func validate(for captureId: String) throws {
        guard schemaVersion == 1, self.captureId == captureId, timestamp.isFinite,
              coordinateSystem == "arkit_scan_meters_y_up", !anchors.isEmpty, anchors.count <= 4096,
              Set(anchors.map(\.id)).count == anchors.count else { throw ScanMeshError.invalidGeometry }
        var vertices = 0, triangles = 0
        for anchor in anchors {
            try anchor.validate()
            vertices += anchor.vertexCount; triangles += anchor.triangleCount
            guard vertices <= Self.maximumVertices, triangles <= Self.maximumTriangles else {
                throw ClientError.storage("This surface scan is too large. Scan a smaller room at a time.")
            }
        }
    }

    func encoded() throws -> Data {
        try validate(for: captureId)
        let encoder = PropertyListEncoder(); encoder.outputFormat = .binary
        return try encoder.encode(self)
    }

    static func decode(_ data: Data, captureId: String) throws -> Self {
        let mesh = try PropertyListDecoder().decode(Self.self, from: data)
        try mesh.validate(for: captureId)
        return mesh
    }
}

struct ScanMeshAnchor: Codable, Sendable {
    var id: String
    /// Column-major, rigid anchor-to-scan transform. No arbitrary fitting or normalization.
    var transform: [Float]
    var vertexCount: Int
    var triangleCount: Int
    /// Tightly packed float32 little-endian xyz, independent of ARKit's source buffer stride.
    var positions: Data
    var normals: Data
    /// Tightly packed uint32 little-endian triangle indices.
    var triangles: Data

    func validate() throws {
        try validateStructure()
        for i in 0..<(vertexCount * 3) {
            guard positions.scanFloat(at: i).isFinite, normals.scanFloat(at: i).isFinite else {
                throw ScanMeshError.invalidGeometry
            }
        }
    }

    private func validateStructure() throws {
        guard !id.isEmpty, vertexCount > 0, vertexCount <= ScanMeshSnapshot.maximumVertices,
              triangleCount > 0, triangleCount <= ScanMeshSnapshot.maximumTriangles,
              positions.count == vertexCount * 12, normals.count == vertexCount * 12,
              triangles.count == triangleCount * 12,
              transform.count == 16, transform.allSatisfy(\.isFinite),
              abs(transform[3]) < 0.001, abs(transform[7]) < 0.001,
              abs(transform[11]) < 0.001, abs(transform[15] - 1) < 0.001 else { throw ScanMeshError.invalidGeometry }
        let x = SIMD3(transform[0], transform[1], transform[2])
        let y = SIMD3(transform[4], transform[5], transform[6])
        let z = SIMD3(transform[8], transform[9], transform[10])
        func dot(_ a: SIMD3<Float>, _ b: SIMD3<Float>) -> Float { a.x*b.x + a.y*b.y + a.z*b.z }
        let determinant = x.x*(y.y*z.z-y.z*z.y) - y.x*(x.y*z.z-x.z*z.y) + z.x*(x.y*y.z-x.z*y.y)
        guard abs(dot(x,x)-1) < 0.01, abs(dot(y,y)-1) < 0.01, abs(dot(z,z)-1) < 0.01,
              abs(dot(x,y)) < 0.01, abs(dot(y,z)) < 0.01, abs(dot(x,z)) < 0.01,
              abs(determinant - 1) < 0.01 else { throw ScanMeshError.invalidGeometry }
        for i in 0..<(triangleCount * 3) where triangles.scanUInt32(at: i) >= UInt32(vertexCount) {
            throw ScanMeshError.invalidGeometry
        }
    }

    /// ARKit can leave undefined normals in slots that no triangle references.
    /// Compact those slots before persistence, preserving all face order, winding and coordinates.
    func removingUnreferencedVertices() throws -> Self {
        try validateStructure()
        var remap = [UInt32](repeating: .max, count: vertexCount)
        var referencedCount = 0
        for i in 0..<(triangleCount * 3) {
            let index = Int(triangles.scanUInt32(at: i))
            if remap[index] == .max { remap[index] = 0; referencedCount += 1 }
        }
        if referencedCount == vertexCount {
            try validate()
            return self
        }
        var compactPositions = Data(capacity: referencedCount * 12)
        var compactNormals = Data(capacity: referencedCount * 12)
        var nextIndex: UInt32 = 0
        positions.withUnsafeBytes { (sourcePositions: UnsafeRawBufferPointer) in
            normals.withUnsafeBytes { (sourceNormals: UnsafeRawBufferPointer) in
                for index in 0..<vertexCount where remap[index] != .max {
                    remap[index] = nextIndex; nextIndex += 1
                    compactPositions.append(sourcePositions.bindMemory(to: UInt8.self).baseAddress!.advanced(by: index * 12), count: 12)
                    compactNormals.append(sourceNormals.bindMemory(to: UInt8.self).baseAddress!.advanced(by: index * 12), count: 12)
                }
            }
        }
        var compactTriangles = Data(capacity: triangles.count)
        for i in 0..<(triangleCount * 3) {
            compactTriangles.appendScanUInt32(remap[Int(triangles.scanUInt32(at: i))])
        }
        var compact = self
        compact.vertexCount = referencedCount
        compact.positions = compactPositions; compact.normals = compactNormals
        compact.triangles = compactTriangles
        try compact.validate() // Invalid values on any referenced vertex still reject the scan.
        return compact
    }

    func worldPosition(at index: Int) -> SIMD3<Float> {
        let x = positions.scanFloat(at: index*3), y = positions.scanFloat(at: index*3+1), z = positions.scanFloat(at: index*3+2)
        return SIMD3(transform[0]*x + transform[4]*y + transform[8]*z + transform[12],
                     transform[1]*x + transform[5]*y + transform[9]*z + transform[13],
                     transform[2]*x + transform[6]*y + transform[10]*z + transform[14])
    }

    func worldNormal(at index: Int) -> SIMD3<Float> {
        let x = normals.scanFloat(at: index*3), y = normals.scanFloat(at: index*3+1), z = normals.scanFloat(at: index*3+2)
        let normal = SIMD3(transform[0]*x + transform[4]*y + transform[8]*z,
                           transform[1]*x + transform[5]*y + transform[9]*z,
                           transform[2]*x + transform[6]*y + transform[10]*z)
        let length = sqrt(normal.x*normal.x + normal.y*normal.y + normal.z*normal.z)
        return length > 0 ? normal / length : .zero
    }
}

extension Data {
    func scanUInt32(at index: Int) -> UInt32 {
        withUnsafeBytes { UInt32(littleEndian: $0.loadUnaligned(fromByteOffset: index * 4, as: UInt32.self)) }
    }
    func scanFloat(at index: Int) -> Float { Float(bitPattern: scanUInt32(at: index)) }
    mutating func appendScanUInt32(_ value: UInt32) {
        var little = value.littleEndian
        Swift.withUnsafeBytes(of: &little) { append(contentsOf: $0) }
    }
    mutating func appendScanFloat(_ value: Float) { appendScanUInt32(value.bitPattern) }
}

/// Native sceneDepth and RGB are registered in normalized sensor-image coordinates.
struct RegisteredScanDepth {
    let width: Int
    let height: Int
    let depth: Data
    let confidence: Data?
    let confidenceWidth: Int
    let confidenceHeight: Int

    init?(metadata: FrameMetadata, depth: Data, confidence: Data?) {
        guard metadata.depthFormat == "float16_le_meters", let w = metadata.depthWidth,
              let h = metadata.depthHeight, w > 0, h > 0, w <= 4096, h <= 4096,
              depth.count == w*h*2 else { return nil }
        width = w; height = h; self.depth = depth
        let cw = metadata.confidenceWidth ?? 0, ch = metadata.confidenceHeight ?? 0
        if let confidence, metadata.confidenceFormat == "uint8_arkit", cw > 0, ch > 0,
           cw <= 4096, ch <= 4096, confidence.count == cw*ch {
            self.confidence = confidence; confidenceWidth = cw; confidenceHeight = ch
        } else { self.confidence = nil; confidenceWidth = 0; confidenceHeight = 0 }
    }

    func seesSurface(u: Float, v: Float, cameraDepth: Float) -> Bool {
        guard u.isFinite, v.isFinite, cameraDepth.isFinite, u >= 0, u < 1, v >= 0, v < 1,
              cameraDepth > 0.1 else { return false }
        if let confidence {
            let offset = Int(v * Float(confidenceHeight)) * confidenceWidth + Int(u * Float(confidenceWidth))
            guard confidence[offset] >= 1 else { return false }
        }
        let offset = (Int(v * Float(height)) * width + Int(u * Float(width))) * 2
        let bits = depth.withUnsafeBytes { UInt16(littleEndian: $0.loadUnaligned(fromByteOffset: offset, as: UInt16.self)) }
        let observed = Float(Float16(bitPattern: bits))
        // Reject surfaces behind foreground objects and disocclusions/geometry disagreement.
        return observed.isFinite && observed > 0 && abs(observed - cameraDepth) <= max(0.05, cameraDepth * 0.025)
    }
}
