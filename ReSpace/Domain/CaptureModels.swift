import Foundation

struct ArtifactRecord: Codable, Identifiable, Sendable, Equatable {
    var id: String
    var type: String
    var filename: String
    var byteLength: Int
    var sha256: String
}
struct ArtifactAcknowledgment: Codable, Sendable {
    var artifactId: String
    var byteLength: Int
    var sha256: String
    var durable: Bool
}
struct FrameMetadata: Codable, Sendable {
    var schemaVersion = 1
    var id: String
    var captureId: String
    var timestamp: Double
    var width: Int
    var height: Int
    var orientation: String = "sensor"
    var intrinsics: [Float]
    var cameraToScanTransform: [Float]
    var depthWidth: Int?
    var depthHeight: Int?
    var depthFormat: String?
    var confidenceWidth: Int?
    var confidenceHeight: Int?
    var confidenceFormat: String?
}
struct CaptureFrame: Codable, Identifiable, Sendable {
    var id: String
    var metadata: FrameMetadata
    var artifacts: [ArtifactRecord]
}
struct CaptureManifest: Codable, Sendable {
    var schemaVersion = 1
    var roomId: String
    var captureId: String
    var creationId: String
    var finalizeId: String
    var createdAt: String
    var state: String
    var frames: [CaptureFrame]
    var roomExport: ArtifactRecord?
    var thumbnail: ArtifactRecord?
    var acknowledgments: [ArtifactAcknowledgment]
    /// Provided by Builder 2 after normalization; never guessed by the client.
    var scanToRoomTransform: [Float]?

    var allArtifacts: [ArtifactRecord] {
        frames.flatMap(\.artifacts) + [roomExport, thumbnail].compactMap { $0 }
    }
    var canEvictRawFiles: Bool {
        state == "finalized" && roomExport != nil && allArtifacts.allSatisfy { artifact in
            acknowledgments.contains { $0.artifactId == artifact.id && $0.durable &&
                $0.byteLength == artifact.byteLength && $0.sha256 == artifact.sha256 }
        }
    }
}
struct FrameUploadResult: Codable, Sendable {
    var schemaVersion: Int
    var acknowledgments: [ArtifactAcknowledgment]
    var perceptionState: String
    var distinctDetails: Int?
}
struct DraftRoomResult: Codable, Sendable {
    var schemaVersion: Int
    var summary: RoomSummary
    var captureId: String
}
struct DraftRoomRequest: Codable, Sendable {
    var schemaVersion = 1
    var operationId: String
    var captureId: String
    var mode = "home"
    var name: String
}
struct FinalizeRequest: Codable, Sendable {
    var schemaVersion = 1
    var operationId: String
    var manifest: CaptureManifest
    var capturedRoom: Data
    var thumbnail: Data?
}
struct FinalizeResult: Codable, Sendable {
    var schemaVersion: Int
    var room: RoomRecord?
    var operation: RoomOperation?
    var acknowledgments: [ArtifactAcknowledgment]
}
struct DeletionResult: Codable, Sendable {
    var schemaVersion: Int
    var deleted: Bool
}
