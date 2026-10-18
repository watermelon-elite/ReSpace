import Foundation
import RealityKit

@MainActor public enum RealityAssetLoader {
    public static func install(_ model: Entity, in container: Entity, replacing fallbacks: [Entity]) {
        fallbacks.forEach { $0.removeFromParent() }
        container.addChild(model)
    }
    public static func texture(from url: URL) async -> TextureResource? { try? await TextureResource(contentsOf: url) }
    public static func load(_ asset: RenderAsset, from url: URL, savedSize: [Double]) async throws -> Entity {
        let scale = try asset.scale(for: savedSize)
        let model = try await Entity(contentsOf: url)
        let bounds = model.visualBounds(relativeTo: nil)
        guard asset.validatesLoadedBounds(minimum: [Double(bounds.min.x), Double(bounds.min.y), Double(bounds.min.z)], maximum: [Double(bounds.max.x), Double(bounds.max.y), Double(bounds.max.z)]) else { throw ContractError.invalid("Loaded model violates its authored bounds or bottom-center pivot.") }
        model.scale *= SIMD3<Float>(Float(scale[0]), Float(scale[1]), Float(scale[2]))
        return model
    }
}
