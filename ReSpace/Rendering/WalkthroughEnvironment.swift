import SceneKit
import simd

/// A one-time reflection probe made from the delivered room itself.
/// This supplies missing PBR reflections, not captured fixture lighting.
enum WalkthroughEnvironment {
    static func apply(to scene: SCNScene, at position: SCNVector3) {
        let bounds = scene.rootNode.boundingBox
        func extent(_ low: SCNFloat, _ high: SCNFloat, _ center: SCNFloat) -> Float {
            Float(2 * max(abs(low-center), abs(high-center)) + 2)
        }
        let probe = SCNNode()
        probe.name = "respace-reflection-probe"
        probe.position = position
        probe.light = SCNLight()
        probe.light?.type = .probe
        probe.light?.probeType = .radiance
        probe.light?.probeUpdateType = .never
        probe.light?.intensity = 500
        probe.light?.probeExtents = SIMD3(extent(bounds.min.x, bounds.max.x, position.x),
            extent(bounds.min.y, bounds.max.y, position.y), extent(bounds.min.z, bounds.max.z, position.z))
        scene.rootNode.addChildNode(probe)
        let renderer = SCNRenderer(device: nil, options: nil)
        renderer.scene = scene
        renderer.autoenablesDefaultLighting = false
        renderer.updateProbes([probe], atTime: 0)
        // Reuse the baked cube as the global environment. Keeping a local
        // radiance probe across renderer handoff triggers a texture-array
        // copy failure in the iOS Simulator's Metal backend.
        scene.lightingEnvironment.contents = probe.light?.probeEnvironment?.contents
        scene.lightingEnvironment.intensity = 0.5
        probe.removeFromParentNode()
    }
}
