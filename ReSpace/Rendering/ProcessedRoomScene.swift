import ModelIO
import SceneKit
import SceneKit.ModelIO
import UIKit

/// Parse derived assets off the main actor. Assets retain the scan's meter units
/// and world transform; this loader never centers, fits or rescales the room.
actor ProcessedRoomScene {
    func load(_ url: URL, highlightRepairs: Bool) throws -> SCNScene {
        let asset = MDLAsset(url: url)
        asset.loadTextures()
        let scene = SCNScene(mdlAsset: asset)
        var geometryCount = 0
        scene.rootNode.enumerateChildNodes { node, _ in
            if let geometry = node.geometry, !geometry.sources(for: .vertex).isEmpty {
                geometryCount += 1
                geometry.materials.forEach { $0.isDoubleSided = true }
            }
        }
        guard geometryCount > 0 else { throw ClientError.invalidGeometry }
        if highlightRepairs {
            let patchURL = url.deletingLastPathComponent().appendingPathComponent("inferred.obj")
            if FileManager.default.fileExists(atPath: patchURL.path) {
                let patches = SCNScene(mdlAsset: MDLAsset(url: patchURL))
                for child in patches.rootNode.childNodes {
                    child.enumerateHierarchy { node, _ in
                        if let geometry = node.geometry {
                            let material = SCNMaterial()
                            material.diffuse.contents = UIColor.systemOrange
                            material.lightingModel = .constant; material.isDoubleSided = true
                            material.readsFromDepthBuffer = false
                            geometry.materials = [material]; node.renderingOrder = 10
                        }
                    }
                    scene.rootNode.addChildNode(child)
                }
            }
        }
        return scene
    }
}
