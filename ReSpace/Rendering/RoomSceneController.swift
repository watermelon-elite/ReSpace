import RealityKit
import SwiftUI
import UIKit

@MainActor @Observable
final class RoomSceneController {
    let root = Entity()
    let camera = PerspectiveCamera()
    private let structure = Entity()
    private let furniture = Entity()
    private var snapshot: RoomSnapshot?
    private var rendered: [String: SceneItem] = [:]
    private var entities: [String: Entity] = [:]
    private var walls: [(Entity, SIMD3<Float>)] = []
    private var assetTasks: [String: Task<Void, Never>] = [:]
    private var yaw: Float = .pi / 5
    private var pitch: Float = .pi / 3
    private var radius: Float = 8
    private var target = SIMD3<Float>(repeating: 0)
    private var selectedId: String?
    private var showGhosts = true
    var assetWarnings: Set<String> = []

    init() {
        root.addChild(structure); root.addChild(furniture); root.addChild(camera)
        let key = DirectionalLight()
        key.light.intensity = 1800
        key.light.color = .white
        key.shadow = DirectionalLightComponent.Shadow(maximumDistance: 30, depthBias: 1)
        key.look(at: .zero, from: SIMD3(3, 8, 4), relativeTo: nil)
        root.addChild(key)
        let fill = PointLight()
        fill.light.intensity = 700
        fill.light.attenuationRadius = 30
        fill.position = [0, 5, 0]
        root.addChild(fill)
    }

    func update(snapshot: RoomSnapshot, items: [SceneItem], selectedId: String?, showGhosts: Bool) {
        if self.snapshot?.id != snapshot.id {
            let first = self.snapshot == nil
            self.snapshot = snapshot
            rebuildStructure(snapshot)
            if first { resetView() }
        }
        self.selectedId = selectedId; self.showGhosts = showGhosts
        let visible = items.filter(\.isVisible)
        let ids = Set(visible.map(\.id))
        for id in Array(entities.keys) where !ids.contains(id) {
            entities.removeValue(forKey: id)?.removeFromParent()
            rendered[id] = nil; assetTasks.removeValue(forKey: id)?.cancel()
        }
        for item in visible {
            if rendered[item.id] != item {
                assetTasks.removeValue(forKey: item.id)?.cancel()
                entities.removeValue(forKey: item.id)?.removeFromParent()
                let entity = makeItem(item)
                furniture.addChild(entity); entities[item.id] = entity; rendered[item.id] = item
                if let asset = item.render.asset { load(asset, for: item, entity: entity) }
            }
            updatePresentation(item.id)
        }
    }

    func itemId(for entity: Entity) -> String? {
        var current: Entity? = entity
        while let node = current {
            if entities[node.name] === node { return node.name }
            current = node.parent
        }
        return nil
    }

    func resetView() {
        guard let polygon = snapshot?.floor.polygon, !polygon.isEmpty else { return }
        let xs = polygon.map { $0[0] }, zs = polygon.map { $0[1] }
        let minX = xs.min() ?? 0, maxX = xs.max() ?? 4
        let minZ = zs.min() ?? 0, maxZ = zs.max() ?? 4
        target = [(minX + maxX) / 2, 0.45, (minZ + maxZ) / 2]
        radius = max(4, max(maxX - minX, maxZ - minZ) * 1.65)
        yaw = .pi / 5; pitch = .pi / 3
        updateCamera()
    }
    func orbit(dx: Float, dy: Float) {
        yaw -= dx * 0.008; pitch = max(0.22, min(1.48, pitch + dy * 0.006)); updateCamera()
    }
    func pan(dx: Float, dy: Float) {
        let factor = radius * 0.0015
        target.x += (-cos(yaw) * dx + sin(yaw) * dy) * factor
        target.z += (sin(yaw) * dx + cos(yaw) * dy) * factor
        updateCamera()
    }
    func zoom(factor: Float) { radius = max(2, min(30, radius / factor)); updateCamera() }
    private func updateCamera() {
        let offset = SIMD3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * radius
        camera.look(at: target, from: target + offset, relativeTo: nil)
        for (wall, center) in walls {
            let outward = center - target
            let toward = camera.position - target
            wall.components.set(OpacityComponent(opacity: simd_dot(outward, toward) > 0 ? 0.12 : 1))
        }
    }

    private func rebuildStructure(_ room: RoomSnapshot) {
        structure.children.removeAll(); walls = []
        var descriptor = MeshDescriptor(name: "floor")
        descriptor.positions = MeshBuffers.Positions(room.floor.polygon.map { SIMD3<Float>($0[0], -0.015, $0[1]) })
        descriptor.primitives = .triangles(PolygonTriangulation.indices(room.floor.polygon))
        if let mesh = try? MeshResource.generate(from: [descriptor]) {
            let concrete = room.styleHints["floor"]?.lowercased().contains("concrete") == true
            structure.addChild(ModelEntity(mesh: mesh, materials: [SimpleMaterial(color: concrete ? UIColor(white: 0.7, alpha: 1) : UIColor(red: 0.72, green: 0.61, blue: 0.46, alpha: 1), roughness: 0.9, isMetallic: false)]))
        }
        for wall in room.walls {
            let group = Entity()
            let a = SIMD3<Float>(wall.a[0], 0, wall.a[1]), b = SIMD3<Float>(wall.b[0], 0, wall.b[1])
            let length = simd_distance(a, b)
            group.position = a
            group.orientation = simd_quatf(angle: -atan2(b.z - a.z, b.x - a.x), axis: [0, 1, 0])
            let openings = room.openings.filter { $0.wallId == wall.id }.sorted { $0.offset < $1.offset }
            var cursor: Float = 0
            for opening in openings {
                let start = min(length, max(cursor, opening.offset))
                let end = min(length, opening.offset + opening.width)
                addWallBox(to: group, from: cursor, to: start, bottom: 0, top: wall.height)
                addWallBox(to: group, from: start, to: end, bottom: 0, top: opening.bottom)
                addWallBox(to: group, from: start, to: end, bottom: opening.bottom + opening.height, top: wall.height)
                if end > start {
                    let panel = box(size: [end - start, opening.height, 0.025], color: opening.type == "window" ? .systemTeal.withAlphaComponent(0.35) : UIColor(red: 0.35, green: 0.28, blue: 0.21, alpha: 0.8))
                    panel.position = [(start + end) / 2, opening.bottom + opening.height / 2, 0]
                    group.addChild(panel)
                }
                cursor = max(cursor, end)
            }
            addWallBox(to: group, from: cursor, to: length, bottom: 0, top: wall.height)
            structure.addChild(group); walls.append((group, (a + b) / 2))
        }
        if let window = room.openings.first(where: { $0.type == "window" }),
           let wall = room.walls.first(where: { $0.id == window.wallId }) {
            let light = PointLight(); light.light.intensity = 350
            light.light.color = UIColor(red: 1, green: 0.96, blue: 0.87, alpha: 1)
            light.light.attenuationRadius = 10
            light.position = [(wall.a[0] + wall.b[0]) / 2, window.bottom + window.height / 2, (wall.a[1] + wall.b[1]) / 2]
            structure.addChild(light)
        }
        updateCamera()
    }
    private func addWallBox(to parent: Entity, from: Float, to: Float, bottom: Float, top: Float) {
        guard to - from > 0.001, top - bottom > 0.001 else { return }
        let panel = box(size: [to - from, top - bottom, 0.08], color: UIColor(red: 0.93, green: 0.91, blue: 0.86, alpha: 1))
        panel.position = [(to + from) / 2, (top + bottom) / 2, 0]
        parent.addChild(panel)
    }
    private func box(size: SIMD3<Float>, color: UIColor) -> ModelEntity {
        ModelEntity(mesh: .generateBox(size: size), materials: [SimpleMaterial(color: color, roughness: 0.8, isMetallic: false)])
    }
    private func makeItem(_ item: SceneItem) -> Entity {
        let root = Entity(); root.name = item.id
        let placement = item.isGhost ? item.lastValid : nil
        let position = placement?.position ?? item.position
        let dimensions = placement?.size ?? item.size
        root.position = [position[0], position[1], position[2]]
        root.orientation = simd_quatf(angle: placement?.yaw ?? item.yaw, axis: [0, 1, 0])
        let container = StandinFactory.make(category: item.category, size: dimensions, tint: item.render.tint)
        container.name = "visual"; root.addChild(container)
        let selection = box(size: [dimensions[0] + 0.03, dimensions[2] + 0.03, dimensions[1] + 0.03], color: .systemYellow.withAlphaComponent(0.18))
        selection.name = "selection"; selection.position.y = dimensions[2] / 2
        selection.isEnabled = false; root.addChild(selection)
        let text = "\(item.label) · \(String(format: "%.1f", dimensions[0])) m"
        let mesh = MeshResource.generateText(text, extrusionDepth: 0.001, font: .systemFont(ofSize: 0.11), containerFrame: .zero, alignment: .center, lineBreakMode: .byTruncatingTail)
        let label = ModelEntity(mesh: mesh, materials: [UnlitMaterial(color: UIColor.darkGray)])
        label.name = "label"; label.position = [-dimensions[0] / 2, dimensions[2] + 0.12, 0]
        root.addChild(label)
        root.components.set(InputTargetComponent())
        root.components.set(CollisionComponent(shapes: [.generateBox(size: [dimensions[0], dimensions[2], dimensions[1]]).offsetBy(translation: [0, dimensions[2] / 2, 0])], mode: .default, filter: .sensor))
        return root
    }
    private func updatePresentation(_ id: String) {
        guard let item = rendered[id], let entity = entities[id] else { return }
        entity.isEnabled = !item.isGhost || showGhosts
        entity.components.set(OpacityComponent(opacity: item.isGhost ? 0.2 : 1))
        entity.findEntity(named: "selection")?.isEnabled = selectedId == id
    }
    private func load(_ asset: ScanRenderAsset, for item: SceneItem, entity: Entity) {
        assetTasks[item.id] = Task { [weak self, weak entity] in
            do {
                let url = try await AssetCache.shared.file(for: asset)
                let model = try await Entity(contentsOf: url)
                try Task.checkCancellation()
                guard let self, let entity, self.entities[item.id] === entity else { return }
                let bounds = model.visualBounds(relativeTo: model)
                let desired = SIMD3<Float>(item.size[0], item.size[2], item.size[1])
                guard bounds.extents.x > 0, bounds.extents.y > 0, bounds.extents.z > 0 else { throw ClientError.invalidGeometry }
                if asset.normalized { model.scale = desired / bounds.extents }
                else {
                    guard simd_length(bounds.extents - desired) < 0.03 else { throw ClientError.invalidGeometry }
                }
                // Bounds establish the authored bottom-center; apply a single pivot adjustment.
                model.position = -SIMD3(bounds.center.x, bounds.min.y, bounds.center.z) * model.scale
                entity.findEntity(named: "visual")?.removeFromParent()
                model.name = "visual"; entity.addChild(model)
                self.assetWarnings.remove(item.id)
            } catch is CancellationError {} catch { self?.assetWarnings.insert(item.id) }
        }
    }
}
