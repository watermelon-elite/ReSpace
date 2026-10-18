import ARKit
import CoreImage
import ImageIO
import RoomPlan
import UniformTypeIdentifiers

/// Single worker; callers admit at most one frame so AR buffers never accumulate.
actor FrameEncoder {
    private let context = CIContext(options: [.cacheIntermediates: false])

    func encode(_ frame: ARFrame, captureId: String, repository: CaptureRepository, highQuality: Bool = false) async throws -> CaptureFrame {
        let id = UUID().uuidString
        let image = CIImage(cvPixelBuffer: frame.capturedImage)
        let scale = min(1, (highQuality ? 2560 : 1280) / max(image.extent.width, image.extent.height))
        let resized = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        guard let jpeg = context.jpegRepresentation(of: resized, colorSpace: CGColorSpaceCreateDeviceRGB(),
                                                    options: [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: highQuality ? 0.9 : 0.7]) else {
            throw ClientError.storage("The scan photo could not be encoded.")
        }
        guard let source = CGImageSourceCreateWithData(jpeg as CFData, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = properties[kCGImagePropertyPixelWidth] as? Int,
              let height = properties[kCGImagePropertyPixelHeight] as? Int else {
            throw ClientError.storage("The encoded scan photo has no dimensions.")
        }
        let intrinsics = frame.camera.intrinsics
        let sx = Float(width) / Float(CVPixelBufferGetWidth(frame.capturedImage))
        let sy = Float(height) / Float(CVPixelBufferGetHeight(frame.capturedImage))
        let pose = frame.camera.transform
        var metadata = FrameMetadata(id: id, captureId: captureId, timestamp: frame.timestamp,
                                     width: width, height: height,
                                     intrinsics: [intrinsics[0][0] * sx, intrinsics[1][1] * sy, intrinsics[2][0] * sx, intrinsics[2][1] * sy],
                                     cameraToScanTransform: (0..<4).flatMap { column in (0..<4).map { row in pose[column][row] } })
        var artifacts = [try await repository.writeArtifact(captureId: captureId, type: "jpeg", bytes: jpeg, extension: "jpg")]
        if let depth = frame.sceneDepth {
            let buffer = depth.depthMap
            CVPixelBufferLockBaseAddress(buffer, .readOnly)
            defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
            let depthWidth = CVPixelBufferGetWidth(buffer)
            let depthHeight = CVPixelBufferGetHeight(buffer)
            guard CVPixelBufferGetPixelFormatType(buffer) == kCVPixelFormatType_DepthFloat32,
                  let base = CVPixelBufferGetBaseAddress(buffer) else { throw ClientError.storage("The available depth format is unsupported.") }
            var packed = Data(capacity: depthWidth * depthHeight * 2)
            for row in 0..<depthHeight {
                let source = base.advanced(by: row * CVPixelBufferGetBytesPerRow(buffer)).assumingMemoryBound(to: Float.self)
                for column in 0..<depthWidth {
                    var bits = Float16(source[column]).bitPattern.littleEndian
                    withUnsafeBytes(of: &bits) { packed.append(contentsOf: $0) }
                }
            }
            metadata.depthWidth = depthWidth; metadata.depthHeight = depthHeight
            metadata.depthFormat = "float16_le_meters"
            artifacts.append(try await repository.writeArtifact(captureId: captureId, type: "depth", bytes: packed, extension: "bin"))
            if let confidence = depth.confidenceMap {
                CVPixelBufferLockBaseAddress(confidence, .readOnly)
                defer { CVPixelBufferUnlockBaseAddress(confidence, .readOnly) }
                if let base = CVPixelBufferGetBaseAddress(confidence) {
                    let w = CVPixelBufferGetWidth(confidence), h = CVPixelBufferGetHeight(confidence)
                    var packedConfidence = Data(capacity: w * h)
                    for row in 0..<h { packedConfidence.append(base.advanced(by: row * CVPixelBufferGetBytesPerRow(confidence)).assumingMemoryBound(to: UInt8.self), count: w) }
                    metadata.confidenceWidth = w; metadata.confidenceHeight = h; metadata.confidenceFormat = "uint8_arkit"
                    artifacts.append(try await repository.writeArtifact(captureId: captureId, type: "confidence", bytes: packedConfidence, extension: "bin"))
                }
            }
        }
        artifacts.append(try await repository.writeArtifact(captureId: captureId, type: "metadata", bytes: Wire.encoder().encode(metadata), extension: "json"))
        let result = CaptureFrame(id: id, metadata: metadata, artifacts: artifacts)
        try await repository.append(result, captureId: captureId)
        return result
    }

    func export(_ room: CapturedRoom) throws -> Data { try JSONEncoder().encode(room) }

    func exportLocalPreview(_ data: Data, to url: URL) throws -> Int {
        let room = try JSONDecoder().decode(CapturedRoom.self, from: data)
        if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
        try room.export(to: url, exportOptions: .parametric)
        return room.objects.count
    }
}
