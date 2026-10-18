import Foundation

// Builder 1 transport types. Backend implementations remain owned by Builders 2/3.
struct RoomSummary: Codable, Identifiable, Sendable, Equatable {
    var id: String
    var name: String
    var metadataRevision: Int
    var scannedAt: String?
    var createdAt: String
    var thumbnailUrl: URL?
    var captureState: String
    var latestSnapshotId: String?
    var activeDesignId: String?
    var activeRevision: Int
    var currentOperationId: String?
    var currentOperationState: OperationState?
    var warnings: [String]
}

struct ScanRoomRecord: Codable, Sendable {
    var schemaVersion: Int
    var summary: RoomSummary
    var snapshot: RoomSnapshot?
    var planning: PlanningState
}

struct RoomSnapshot: Codable, Identifiable, Sendable, Equatable {
    var id: String
    var revision: Int
    var roomId: String
    var captureId: String
    var validity: RoomValidity
    var height: Float
    var floor: RoomFloor
    var walls: [RoomWall]
    var corners: [RoomCorner]
    var openings: [RoomOpening]
    var objects: [RoomObject]
    var wallFeatures: [WallFeature]
    var zones: [RoomZone]
    var styleHints: [String: String]
    var story: [String]
    var processing: ProcessingCounts
    var scanToRoomTransform: [Float]
    var objectAliases: [String: String]?
}

struct RoomValidity: Codable, Sendable, Equatable {
    var usable: Bool
    var reasons: [String]
    var warnings: [String]
}
struct RoomFloor: Codable, Sendable, Equatable {
    var polygon: [[Float]]
    var areaM2: Float
}
struct RoomWall: Codable, Identifiable, Sendable, Equatable {
    var id: String
    var a: [Float]
    var b: [Float]
    var height: Float
}
struct RoomCorner: Codable, Identifiable, Sendable, Equatable {
    var id: String
    var at: [Float]
    var walls: [String]
}
struct RoomOpening: Codable, Identifiable, Sendable, Equatable {
    var id: String
    var type: String
    var wallId: String
    var offset: Float
    var width: Float
    var bottom: Float
    var height: Float
}
struct RoomObject: Codable, Identifiable, Sendable, Equatable {
    var id: String
    var category: String
    var label: String
    var center: [Float]
    var baseElevation: Float
    var yaw: Float
    /// Width, depth, height (X, Z, Y), in meters.
    var size: [Float]
    var attrs: [String: String]
    var render: RenderDescriptor?
}
struct WallFeature: Codable, Identifiable, Sendable, Equatable {
    var id: String
    var type: String
    var wallId: String
    var offset: Float
    var height: Float
}
struct RoomZone: Codable, Identifiable, Sendable, Equatable {
    var id: String
    var type: String
    var reason: String
    var polygon: [[Float]]
}
struct ProcessingCounts: Codable, Sendable, Equatable {
    var pending: Int
    var completed: Int
    var failed: Int
    var distinctDetails: Int?
}
enum ItemInstruction: String, Codable, Sendable, CaseIterable {
    case keep, decide, remove
    var label: String {
        switch self {
        case .keep: "Keep in place"
        case .decide: "Let the design decide"
        case .remove: "Remove from design"
        }
    }
}
struct PlanningState: Codable, Sendable, Equatable {
    var roomId: String
    var revision: Int
    var instructions: [String: ItemInstruction]
}
struct RoomList: Codable, Sendable {
    var schemaVersion: Int
    var rooms: [RoomSummary]
    var nextCursor: String?
}
struct RenameRoomRequest: Codable, Sendable {
    var schemaVersion = 1
    var name: String
    var expectedMetadataRevision: Int
}
