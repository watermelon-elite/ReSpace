import SwiftUI
import RealityKit
import UIKit
import simd

struct RoomScene: UIViewRepresentable {
    let document: JSONValue
    let native: Bool
    @Binding var selectedID: String?
    let ghosts: Bool
    let resetToken: Int
    var assetBaseURL: URL? = nil
    var assetManifest: JSONValue = .null
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIView(context: Context) -> ARView {
        let view = ARView(frame: .zero, cameraMode: .nonAR, automaticallyConfigureSession: false)
        view.environment.background = .color(UIColor(white: 0.93, alpha: 1))
        context.coordinator.attach(view)
        return view
    }
    func updateUIView(_ view: ARView, context: Context) { context.coordinator.parent = self; context.coordinator.update() }
    @MainActor final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var parent: RoomScene
        weak var view: ARView?
        let root = AnchorEntity(world: .zero)
        let camera = PerspectiveCamera()
        var content = Entity()
        var last: JSONValue = .null
        var lastGhosts = true
        var lastReset = 0
        var center = SIMD3<Float>(0, 1, 0)
        var radius: Float = 7
        var azimuth: Float = .pi / 4
        var elevation: Float = .pi / 4
        var objects: [String: ModelEntity] = [:]
        var colors: [String: UIColor] = [:]
        var itemRoots: [String: Entity] = [:]
        var itemDocuments: [String: JSONValue] = [:]
        var highlights: [String: ModelEntity] = [:]
        var assetTasks: [String: Task<Void, Never>] = [:]
        var lastManifest: JSONValue = .null
        var wallEntities: [(Entity, SIMD3<Float>, SIMD3<Float>)] = []
        init(_ parent: RoomScene) { self.parent = parent }
        func attach(_ view: ARView) {
            self.view = view; view.scene.addAnchor(root); root.addChild(camera); root.addChild(content)
            let light = DirectionalLight(); light.light.intensity = 1800; light.look(at: .zero, from: [2, 6, 3], relativeTo: nil); root.addChild(light)
            view.environment.lighting.intensityExponent = 0.6
            let pan = UIPanGestureRecognizer(target: self, action: #selector(orbit(_:))); pan.maximumNumberOfTouches = 1
            let move = UIPanGestureRecognizer(target: self, action: #selector(pan(_:))); move.minimumNumberOfTouches = 2
            let pinch = UIPinchGestureRecognizer(target: self, action: #selector(zoom(_:)))
            let tap = UITapGestureRecognizer(target: self, action: #selector(select(_:)))
            for gesture in [pan, move, pinch, tap] { gesture.delegate = self; view.addGestureRecognizer(gesture) }
            update()
        }
        func update() {
            let changed = last != parent.document || lastGhosts != parent.ghosts || lastManifest != parent.assetManifest
            if changed {
                let first = last == .null
                if !parent.native, !first, last["room"] == parent.document["room"] {
                    if lastManifest != parent.assetManifest { itemDocuments.removeAll() }
                    reconcileItems(parent.document)
                } else {
                    assetTasks.values.forEach { $0.cancel() }; assetTasks.removeAll()
                    content.removeFromParent(); content = Entity(); root.addChild(content)
                    objects = [:]; colors = [:]; wallEntities = []; itemRoots = [:]; itemDocuments = [:]; highlights = [:]
                    if parent.native { buildNative(parent.document) } else { buildScene(parent.document) }
                }
                last = parent.document; lastGhosts = parent.ghosts; lastManifest = parent.assetManifest
                if first { reset() }
            }
            if lastReset != parent.resetToken { lastReset = parent.resetToken; reset() }
            for (id, entity) in objects { entity.model?.materials = [material(id == parent.selectedID ? .systemYellow : colors[id] ?? .systemGray, alpha: entity.name.hasPrefix("ghost:") ? 0.2 : 1)] }
            for (id, highlight) in highlights { highlight.isEnabled = id == parent.selectedID }
            positionCamera()
        }
        func material(_ color: UIColor, alpha: Float = 1) -> SimpleMaterial { SimpleMaterial(color: color.withAlphaComponent(CGFloat(alpha)), roughness: 0.8, isMetallic: false) }
        func box(size: SIMD3<Float>, at position: SIMD3<Float>, yaw: Float = 0, color: UIColor, id: String? = nil, alpha: Float = 1) -> ModelEntity {
            let entity = ModelEntity(mesh: .generateBox(size: simd_max(size, SIMD3(repeating: 0.005))), materials: [material(color, alpha: alpha)])
            entity.position = position; entity.orientation = simd_quatf(angle: yaw, axis: [0, 1, 0]); content.addChild(entity)
            if let id { entity.name = alpha < 1 ? "ghost:\(id)" : id; entity.generateCollisionShapes(recursive: false); objects[id] = entity; colors[id] = color }
            return entity
        }
        func tint(_ hex: String?) -> UIColor {
            guard let hex, hex.count == 7, hex.first == "#", let value = UInt32(hex.dropFirst(), radix: 16) else { return UIColor(red: 0.55, green: 0.61, blue: 0.58, alpha: 1) }
            return UIColor(red: CGFloat((value >> 16) & 255) / 255, green: CGFloat((value >> 8) & 255) / 255, blue: CGFloat(value & 255) / 255, alpha: 1)
        }
        func buildScene(_ scene: JSONValue) {
            let room = scene["room"] == .null ? scene["room_model"] : scene["room"]
            let polygon = room["floor"]["polygon"].array.map(\.numbers).filter { $0.count == 2 }
            floor(polygon, y: 0)
            for wall in room["walls"].array where wall["virtual"].bool != true {
                let a = wall["a"].numbers; let b = wall["b"].numbers
                guard a.count == 2, b.count == 2 else { continue }
                let start = SIMD3<Float>(Float(a[0]), 0, Float(a[1])); let end = SIMD3<Float>(Float(b[0]), 0, Float(b[1]))
                let length = simd_distance(start, end); guard length > 0 else { continue }
                let direction = (end - start) / length; let yaw = -atan2(direction.z, direction.x)
                let height = Float(room["height"].number ?? 0)
                let normal = wall["inward_normal"].numbers; let inward = SIMD3<Float>(Float(normal.first ?? 0), 0, Float(normal.last ?? 0))
                let openings = room["openings"].array.filter { $0["wall_id"].text == wall["id"].text }.sorted { ($0["offset"].number ?? 0) < ($1["offset"].number ?? 0) }
                var cursor: Float = 0
                func strip(_ from: Float, _ to: Float, _ bottom: Float, _ top: Float) {
                    guard to > from, top > bottom else { return }
                    let middle = start + direction * ((from + to) / 2) + SIMD3(0, (bottom + top) / 2, 0)
                    let entity = box(size: [to - from, top - bottom, 0.035], at: middle, yaw: yaw, color: UIColor(red: 0.89, green: 0.87, blue: 0.83, alpha: 1))
                    wallEntities.append((entity, middle, inward))
                }
                for opening in openings {
                    let left = max(0, Float(opening["offset"].number ?? 0))
                    let right = min(length, left + Float(opening["width"].number ?? 0))
                    let bottom = Float(opening["bottom"].number ?? 0); let top = min(height, bottom + Float(opening["height"].number ?? 0))
                    strip(cursor, left, 0, height); strip(left, right, 0, bottom); strip(left, right, top, height); cursor = max(cursor, right)
                    if opening["type"].text != "opening", right > left, top > bottom { _ = box(size: [right - left, top - bottom, 0.015], at: start + direction * ((left + right) / 2) + SIMD3(0, (bottom + top) / 2, 0), yaw: yaw, color: opening["type"].text == "window" ? .systemTeal : .brown, alpha: opening["type"].text == "window" ? 0.2 : 0.35) }
                }
                strip(cursor, length, 0, height)
            }
            reconcileItems(scene)
        }
        func reconcileItems(_ scene: JSONValue) {
            let visible = SceneItems.visible(in: scene, showGhosts: parent.ghosts)
            let ids = Set(visible.map { $0["id"].text })
            for id in Array(itemRoots.keys) where !ids.contains(id) {
                assetTasks.removeValue(forKey: id)?.cancel(); itemRoots.removeValue(forKey: id)?.removeFromParent()
                itemDocuments.removeValue(forKey: id); highlights.removeValue(forKey: id)
            }
            for item in visible {
                let id = item["id"].text
                guard itemDocuments[id] != item else { continue }
                assetTasks.removeValue(forKey: id)?.cancel(); itemRoots.removeValue(forKey: id)?.removeFromParent()
                let removed = item["status"].text == "removed"
                guard let placement = try? Placement(removed ? item["last_valid_placement"] : item["placement"]) else { continue }
                let size = SIMD3<Float>(Float(placement.size[0]), Float(placement.size[2]), Float(placement.size[1]))
                let container = Entity(); container.name = id
                container.position = SIMD3<Float>(Float(placement.position[0]), Float(placement.position[1]), Float(placement.position[2]))
                container.orientation = simd_quatf(angle: Float(placement.yaw), axis: [0, 1, 0])
                if removed { container.components.set(OpacityComponent(opacity: 0.2)) }
                content.addChild(container); itemRoots[id] = container; itemDocuments[id] = item
                let fallback = ModelEntity(mesh: .generateBox(size: size), materials: [material(tint(item["render"]["tint"].string))])
                fallback.position.y = size.y / 2; fallback.generateCollisionShapes(recursive: false); container.addChild(fallback)
                let label = ModelEntity(mesh: .generateText(item["label"].string ?? item["category"].text, extrusionDepth: 0.001, font: .systemFont(ofSize: 0.12)), materials: [UnlitMaterial(color: .darkGray)])
                label.position = [-size.x / 2, size.y + 0.03, 0]; container.addChild(label)
                let highlight = ModelEntity(mesh: .generateBox(size: size + SIMD3(repeating: 0.01)), materials: [material(.systemYellow, alpha: 0.16)])
                highlight.position.y = size.y / 2; highlight.isEnabled = id == parent.selectedID; container.addChild(highlight); highlights[id] = highlight
                assetTasks[id] = Task { [weak self, weak container] in
                    guard let self, let container else { return }
                    await self.upgrade(item, placement: placement, container: container, fallback: fallback, label: label)
                }
            }
        }
        func upgrade(_ item: JSONValue, placement: Placement, container: Entity, fallback: ModelEntity, label: ModelEntity) async {
            guard let baseURL = parent.assetBaseURL else { return }
            let descriptor = item["render"]
            let id = item["id"].text
            if descriptor["kind"].text == "panel" || ["rug", "wall_art", "mirror"].contains(item["category"].text) {
                if descriptor["texture_url"].string != nil {
                    do {
                        let url = try await RenderAssetCache.shared.texture(for: descriptor, baseURL: baseURL)
                        guard let texture = await RealityAssetLoader.texture(from: url) else { return }
                        guard !Task.isCancelled, itemRoots[id] === container else { return }
                        var surface = SimpleMaterial(color: .white, roughness: 0.8, isMetallic: false)
                        surface.color = .init(tint: .white, texture: .init(texture))
                        fallback.model?.materials = [surface]; label.removeFromParent()
                    } catch { /* Neutral correctly sized panel remains visible. */ }
                }
                return
            }
            var requested = descriptor.object
            let assets = parent.assetManifest["assets"].array
            if let exact = assets.first(where: { $0["asset_id"] == descriptor["asset_id"] && $0["revision"] == descriptor["asset_revision"] }) {
                requested["sha256"] = exact["sha256"]; requested["byte_count"] = exact["byte_count"]
                if requested["asset_url"] == nil || requested["asset_url"] == .null { requested["asset_url"] = exact["url"] }
            }
            var candidates: [JSONValue] = [.object(requested)]
            if let standin = assets.first(where: { $0["kind"].text == "standin" && $0["category"].text == item["category"].text && $0["asset_id"] != descriptor["asset_id"] }) { candidates.append(standin) }
            for candidate in candidates {
                do {
                    let asset = try RenderAsset(candidate)
                    let url = try await RenderAssetCache.shared.file(for: asset, baseURL: baseURL)
                    let model = try await RealityAssetLoader.load(asset, from: url, savedSize: placement.size)
                    guard !Task.isCancelled, itemRoots[id] === container else { return }
                    model.generateCollisionShapes(recursive: true)
                    RealityAssetLoader.install(model, in: container, replacing: [fallback, label])
                    return
                } catch { if Task.isCancelled { return } }
            }
        }
        func buildNative(_ room: JSONValue) {
            var nativeCenter = SIMD3<Float>.zero
            var wallCount: Float = 0
            for wall in room["walls"].array {
                let values = wall["transform"].numbers
                if values.count == 16 { nativeCenter += SIMD3<Float>(Float(values[12]), Float(values[13]), Float(values[14])); wallCount += 1 }
            }
            if wallCount > 0 { nativeCenter /= wallCount }
            for item in room["objects"].array {
                let transform = item["transform"].numbers; let size = item["dimensions"].numbers
                guard transform.count == 16, size.count == 3, size.allSatisfy({ $0 > 0 }) else { continue }
                _ = box(size: [Float(size[0]), Float(size[1]), Float(size[2])], at: [Float(transform[12]), Float(transform[13]), Float(transform[14])], yaw: Float(atan2(transform[8], transform[0])), color: tint(nil), id: item["identifier"].string)
            }
            for wall in room["walls"].array {
                let t = wall["transform"].numbers; let d = wall["dimensions"].numbers
                guard t.count == 16, d.count >= 2 else { continue }
                let position = SIMD3<Float>(Float(t[12]), Float(t[13]), Float(t[14]))
                let direction = SIMD3<Float>(Float(t[0]), Float(t[1]), Float(t[2]))
                let bottom = position.y - Float(d[1]) / 2
                let yaw = Float(atan2(t[8], t[0])); let width = Float(d[0]); let height = Float(d[1])
                let start = position - direction * width / 2
                let openings = ["doors", "windows", "openings"].flatMap { kind in room[kind].array.map { (kind, $0) } }.filter { $0.1["parentIdentifier"].text == wall["identifier"].text }.compactMap { kind, surface -> (String, Float, Float, Float, Float)? in
                    let transform = surface["transform"].numbers; let dimensions = surface["dimensions"].numbers
                    guard transform.count == 16, dimensions.count == 3 else { return nil }
                    let center = SIMD3<Float>(Float(transform[12]), Float(transform[13]), Float(transform[14]))
                    let left = max(0, simd_dot(center - start, direction) - Float(dimensions[0]) / 2)
                    return (kind, left, min(width, left + Float(dimensions[0])), center.y - Float(dimensions[1]) / 2 - bottom, Float(dimensions[1]))
                }.sorted { $0.1 < $1.1 }
                func strip(_ from: Float, _ to: Float, _ low: Float, _ high: Float) {
                    guard to > from, high > low else { return }
                    let center = start + direction * ((from + to) / 2) + SIMD3(0, bottom + (low + high) / 2 - position.y, 0)
                    let entity = box(size: [to - from, high - low, 0.025], at: center, yaw: yaw, color: .lightGray, alpha: 0.4)
                    let normal = SIMD3<Float>(Float(t[8]), 0, Float(t[10])); wallEntities.append((entity, center, simd_dot(nativeCenter - position, normal) < 0 ? -normal : normal))
                }
                var cursor: Float = 0
                for (kind, left, right, low, openingHeight) in openings {
                    strip(cursor, left, 0, height); strip(left, right, 0, max(0, low)); strip(left, right, min(height, low + openingHeight), height); cursor = max(cursor, right)
                    if kind != "openings", right > left { _ = box(size: [right - left, openingHeight, 0.012], at: start + direction * ((left + right) / 2) + SIMD3(0, bottom + low + openingHeight / 2 - position.y, 0), yaw: yaw, color: kind == "windows" ? .systemTeal : .brown, alpha: 0.25) }
                }
                strip(cursor, width, 0, height)
            }
            for surface in room["floors"].array {
                let t = surface["transform"].numbers; guard t.count == 16 else { continue }
                let points = surface["polygonCorners"].array.compactMap { corner -> [Double]? in
                    let p = corner.numbers; guard p.count == 3 else { return nil }
                    return [t[0]*p[0]+t[4]*p[1]+t[8]*p[2]+t[12], t[2]*p[0]+t[6]*p[1]+t[10]*p[2]+t[14]]
                }
                floor(points, y: Float(t[13]))
            }
        }
        func floor(_ polygon: [[Double]], y: Float) {
            guard polygon.count >= 3 else { return }
            let vertices = polygon.map { SIMD3<Float>(Float($0[0]), y, Float($0[1])) }
            var remaining = Array(vertices.indices); var indices: [UInt32] = []
            let signedArea = polygon.indices.reduce(0.0) { sum, i in let j = (i + 1) % polygon.count; return sum + polygon[i][0] * polygon[j][1] - polygon[j][0] * polygon[i][1] }
            if signedArea < 0 { remaining.reverse() }
            func cross(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ c: SIMD3<Float>) -> Float { (b.x-a.x)*(c.z-a.z)-(b.z-a.z)*(c.x-a.x) }
            while remaining.count > 3 {
                var cut = false
                for i in remaining.indices {
                    let a = remaining[(i + remaining.count - 1) % remaining.count], b = remaining[i], c = remaining[(i + 1) % remaining.count]
                    guard cross(vertices[a], vertices[b], vertices[c]) > 0.000001 else { continue }
                    let contains = remaining.contains { p in p != a && p != b && p != c && cross(vertices[a], vertices[b], vertices[p]) >= 0 && cross(vertices[b], vertices[c], vertices[p]) >= 0 && cross(vertices[c], vertices[a], vertices[p]) >= 0 }
                    if contains { continue }
                    indices += [UInt32(c), UInt32(b), UInt32(a)]; remaining.remove(at: i); cut = true; break
                }
                if !cut { return }
            }
            indices += remaining.reversed().map(UInt32.init)
            var descriptor = MeshDescriptor(name: "Measured floor"); descriptor.positions = MeshBuffers.Positions(vertices); descriptor.primitives = .triangles(indices)
            if let mesh = try? MeshResource.generate(from: [descriptor]) { content.addChild(ModelEntity(mesh: mesh, materials: [material(UIColor(red: 0.69, green: 0.61, blue: 0.49, alpha: 1))])) }
        }
        func reset() {
            let bounds = content.visualBounds(relativeTo: root)
            if bounds.extents.x.isFinite, simd_length(bounds.extents) > 0 { center = bounds.center; radius = max(2, simd_length(bounds.extents) * 1.1) }
            azimuth = .pi / 4; elevation = .pi / 4; positionCamera()
        }
        func positionCamera() {
            let position = center + SIMD3<Float>(radius * cos(elevation) * sin(azimuth), radius * sin(elevation), radius * cos(elevation) * cos(azimuth))
            camera.look(at: center, from: position, relativeTo: root)
            for (entity, wallCenter, inward) in wallEntities { entity.isEnabled = simd_dot(position - wallCenter, inward) >= -0.05 }
        }
        @objc func orbit(_ gesture: UIPanGestureRecognizer) { let delta = gesture.translation(in: view); gesture.setTranslation(.zero, in: view); azimuth -= Float(delta.x) * 0.007; elevation = min(1.45, max(0.08, elevation + Float(delta.y) * 0.007)); positionCamera() }
        @objc func pan(_ gesture: UIPanGestureRecognizer) { let d = gesture.translation(in: view); gesture.setTranslation(.zero, in: view); let right = SIMD3<Float>(cos(azimuth), 0, -sin(azimuth)); let forward = SIMD3<Float>(sin(azimuth), 0, cos(azimuth)); center -= right * Float(d.x) * radius * 0.0015; center -= forward * Float(d.y) * radius * 0.0015; positionCamera() }
        @objc func zoom(_ gesture: UIPinchGestureRecognizer) { radius = min(40, max(0.8, radius / Float(gesture.scale))); gesture.scale = 1; positionCamera() }
        @objc func select(_ gesture: UITapGestureRecognizer) {
            var candidate = view?.entity(at: gesture.location(in: view))
            while let entity = candidate {
                let id = entity.name.replacingOccurrences(of: "ghost:", with: "")
                if objects[id] != nil || itemRoots[id] != nil { parent.selectedID = id; return }
                candidate = entity.parent
            }
            parent.selectedID = nil
        }
    }
}
