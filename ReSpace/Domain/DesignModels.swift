import Foundation

struct DesignVersion: Codable, Identifiable, Sendable, Equatable {
    var schemaVersion: Int
    var id: String
    var parentId: String?
    var roomId: String
    var roomSnapshotId: String
    var planning: PlanningState
    var inputs: GenerationInputs
    var summary: String
    var warnings: [String]
    var items: [SceneItem]
    var monetary: MonetaryPresentation?
    var createdAt: String
}
struct SceneItem: Codable, Identifiable, Sendable, Equatable {
    var id: String
    var originalObjectId: String?
    var origin: ItemOrigin
    var status: ItemStatus
    var category: String
    var label: String
    var position: [Float]
    var yaw: Float
    var size: [Float]
    var planningState: ItemInstruction
    var original: ScanPlacement?
    var lastValid: ScanPlacement?
    var render: RenderDescriptor
    var product: ProductPresentation?
    var reason: String?

    var isGhost: Bool { origin == .existing && status == .removed }
    var isVisible: Bool { origin == .existing || status != .removed }
}
enum ItemOrigin: String, Codable, Sendable { case existing, new }
enum ItemStatus: String, Codable, Sendable { case existing, moved, removed, new }
struct ScanPlacement: Codable, Sendable, Equatable {
    var position: [Float]
    var yaw: Float
    var size: [Float]
}
struct RenderDescriptor: Codable, Sendable, Equatable {
    var kind: String
    var category: String
    var tint: String?
    var asset: ScanRenderAsset?
}
struct ScanRenderAsset: Codable, Sendable, Equatable {
    var id: String
    var revision: String
    var url: URL
    var authoredBounds: [Float]
    var units: String
    var pivot: String
    var forward: String
    var normalized: Bool
}
struct ProductPresentation: Codable, Identifiable, Sendable, Equatable {
    var id: String
    var title: String
    var store: String
    var priceText: String?
    var imageUrl: URL?
    var isDemo: Bool
    var alternatives: [ProductAlternative]
}
struct ProductAlternative: Codable, Identifiable, Sendable, Equatable {
    var id: String
    var title: String
    var store: String
    var priceText: String?
    var imageUrl: URL?
}
struct MonetaryPresentation: Codable, Sendable, Equatable {
    /// Server-supplied formatted text, never recomputed by the client.
    var text: String
    var designId: String
    var isDemo: Bool
}

extension RoomSnapshot {
    func reviewItems(planning: PlanningState) -> [SceneItem] {
        objects.map { object in
            SceneItem(id: object.id, originalObjectId: object.id, origin: .existing,
                      status: .existing, category: object.category, label: object.label,
                      position: [object.center[0], object.baseElevation, object.center[1]],
                      yaw: object.yaw, size: object.size,
                      planningState: planning.instructions[object.id] ?? .decide,
                      render: object.render ?? RenderDescriptor(kind: "standin", category: object.category,
                                                               tint: nil, asset: nil))
        }
    }
}
