// Adapted from Wes Bos's ScanView.swift at 31b2dc9 (MIT).
// Single fresh Room: excludes the multi-session ghost/relocalization UI.
import ARKit
import ImageIO
import RoomPlan
import SceneKit

/// The scanning view: camera feed with ARKit's LiDAR mesh drawn over it, each
/// surface tinted by how well the photos cover it, plus RoomPlan's live walls,
/// doors and windows as outlines. Renders whatever configuration the session runs.
@MainActor
final class SourceScanView: NSObject, ARSCNViewDelegate {
  let view: ARSCNView
  let engine: CoverageEngine
  var onSessionFailure: (([String]) -> Void)?
  var onSessionEvent: ((String) -> Void)?
  private var nodes: [UUID: SCNNode] = [:]
  /// meshes that arrived before their node was registered
  private var waiting: [UUID: CoverageEngine.AnchorMesh] = [:]
  private let outline = SCNNode()
  private var lastOutline: CFTimeInterval = 0

  /// Red facets need photos; green facets have good photo coverage.
  /// Keep the camera visible through the fill and trace the actual LiDAR triangles on top.
  private let materials: [SCNMaterial] = [
    (0xFF3939, 0.28), (0xF94B4B, 0.23), (0xE82B2B, 0.25),
    (0xFF3939, 0.28), (0xF94B4B, 0.23), (0xE82B2B, 0.25),
    (0x39ED75, 0.24), (0x51F589, 0.22), (0x26D966, 0.23),
    (0xFFFFFF, 0.0), (0xFFFFFF, 0.0), (0xFFFFFF, 0.0),
  ].map { hex, alpha in
    let m = SCNMaterial()
    m.lightingModel = .constant
    m.diffuse.contents = UIColor(red: CGFloat((hex >> 16) & 255) / 255,
                                green: CGFloat((hex >> 8) & 255) / 255,
                                blue: CGFloat(hex & 255) / 255, alpha: 1)
    m.transparency = alpha
    m.blendMode = .alpha
    m.isDoubleSided = false
    m.writesToDepthBuffer = true
    m.readsFromDepthBuffer = true
    return m
  }
  private let triangleLine: SCNMaterial = {
    let m = SCNMaterial()
    m.lightingModel = .constant
    m.diffuse.contents = UIColor.white
    m.transparency = 0.42
    m.fillMode = .lines
    m.blendMode = .alpha
    m.isDoubleSided = false
    m.readsFromDepthBuffer = true
    m.writesToDepthBuffer = false
    return m
  }()
  private let wallLine: SCNMaterial = {
    let m = SCNMaterial()
    m.lightingModel = .constant
    m.diffuse.contents = UIColor.white
    m.transparency = 0.9
    m.readsFromDepthBuffer = false // always visible, like RoomPlan's own outlines
    return m
  }()
  private let openingLine: SCNMaterial = {
    let m = SCNMaterial()
    m.lightingModel = .constant
    m.diffuse.contents = UIColor.cyan
    m.readsFromDepthBuffer = false
    return m
  }()

  /// Whether live mesh anchors go to the coverage engine. Off while relocalizing (the world
  /// isn't the zone's yet, and the engine keeps every anchor it's given) and while paused.
  /// Read on SceneKit's render thread.
  nonisolated let feed = FeedGate()
  init(session: ARSession, engine: CoverageEngine) {
    view = ARSCNView(frame: .zero)
    self.engine = engine
    super.init()
    view.session = session
    view.delegate = self
    view.automaticallyUpdatesLighting = false
    view.rendersCameraGrain = false
    view.rendersMotionBlur = false
    view.antialiasingMode = .multisampling4X
    view.scene = SCNScene()
    outline.renderingOrder = 10
    view.scene.rootNode.addChildNode(outline)
    engine.onMeshes = { [weak self] meshes in self?.apply(meshes) }
  }

  /// Hand every live mesh anchor to the engine again (after it wasn't fed for a while).
  /// Copying the buffers is heavy, so it happens off main; holding the anchors keeps them valid.
  func refeedEngine(from session: ARSession) {
    let anchors = session.currentFrame?.anchors.compactMap { $0 as? ARMeshAnchor } ?? []
    let engine = engine
    DispatchQueue.global(qos: .userInitiated).async {
      for a in anchors { engine.update(a) }
    }
  }

  /// RoomPlan's current walls (white) and doors/windows/openings (cyan), as outlines
  func showRoom(_ room: CapturedRoom?) {
    let now = CACurrentMediaTime()
    guard room == nil || now - lastOutline > 0.4 else { return } // RoomPlan updates a lot
    lastOutline = now
    outline.childNodes.forEach { $0.removeFromParentNode() }
    guard let room else { return }
    for w in room.walls { outline.addChildNode(rectangle(w.transform, w.dimensions, wallLine, inset: 0)) }
    for o in room.doors + room.windows + room.openings { outline.addChildNode(rectangle(o.transform, o.dimensions, openingLine, inset: 0.01)) }
  }

  private func rectangle(_ t: simd_float4x4, _ d: SIMD3<Float>, _ material: SCNMaterial, inset: Float) -> SCNNode {
    let hw = d.x / 2 - inset, hh = d.y / 2 - inset
    let pts = [SIMD3<Float>(-hw, -hh, 0.005), SIMD3(hw, -hh, 0.005), SIMD3(hw, hh, 0.005), SIMD3(-hw, hh, 0.005)]
    let src = SCNGeometrySource(vertices: pts.map { SCNVector3($0.x, $0.y, $0.z) })
    let idx: [UInt16] = [0, 1, 1, 2, 2, 3, 3, 0]
    let el = SCNGeometryElement(indices: idx, primitiveType: .line)
    let g = SCNGeometry(sources: [src], elements: [el])
    g.materials = [material]
    let node = SCNNode(geometry: g)
    node.simdTransform = t
    node.renderingOrder = 10
    return node
  }

  // MARK: ARSCNViewDelegate (render thread)

  /// Clip anything within 30 cm of the lens: it only blocks the view, and it's too close
  /// to photograph usefully anyway
  nonisolated func renderer(_ renderer: SCNSceneRenderer, updateAtTime time: TimeInterval) {
    if let cam = renderer.pointOfView?.camera, cam.zNear != 0.3 { cam.zNear = 0.3 }
  }

  /// Relocalize after an interruption (a phone call, the app in the background) instead of
  /// starting a new world
  nonisolated func sessionShouldAttemptRelocalization(_ session: ARSession) -> Bool { true }

  // Observe through ARSCNView, without replacing RoomPlan's ARSession delegate.
  nonisolated func session(_ session: ARSession, didFailWithError error: Error) {
    let chain = [error.localizedDescription]
    Task { @MainActor in self.onSessionFailure?(chain) }
  }

  nonisolated func sessionWasInterrupted(_ session: ARSession) {
    Task { @MainActor in self.onSessionEvent?("ARKit session interrupted") }
  }

  nonisolated func sessionInterruptionEnded(_ session: ARSession) {
    Task { @MainActor in self.onSessionEvent?("ARKit session interruption ended") }
  }


  nonisolated func renderer(_ renderer: SCNSceneRenderer, nodeFor anchor: ARAnchor) -> SCNNode? {
    guard let mesh = anchor as? ARMeshAnchor else { return nil }
    if feed.isOn { engine.update(mesh) }
    let node = SCNNode()
    let id = mesh.identifier
    Task { @MainActor in
      self.nodes[id] = node
      if let m = self.waiting.removeValue(forKey: id) { self.apply([m]) }
    }
    return node
  }

  nonisolated func renderer(_ renderer: SCNSceneRenderer, didUpdate node: SCNNode, for anchor: ARAnchor) {
    guard let mesh = anchor as? ARMeshAnchor, feed.isOn else { return }
    engine.update(mesh)
  }

  nonisolated func renderer(_ renderer: SCNSceneRenderer, didRemove node: SCNNode, for anchor: ARAnchor) {
    guard anchor is ARMeshAnchor else { return }
    let id = anchor.identifier
    engine.remove(id)
    Task { @MainActor in
      self.nodes[id] = nil
      self.waiting[id] = nil
    }
  }

  // MARK: geometry

  private func apply(_ meshes: [CoverageEngine.AnchorMesh]) {
    for m in meshes {
      guard m.vertexCount > 0, m.bandCounts.reduce(0, +) > 0 else { continue }
      guard let node = nodes[m.id] else {
        waiting[m.id] = m
        continue
      }
      // SIMD3<Float> is padded to 16 bytes in Swift arrays
      let stride = MemoryLayout<SIMD3<Float>>.stride
      let vertices = SCNGeometrySource(
        data: m.positions, semantic: .vertex, vectorCount: m.vertexCount,
        usesFloatComponents: true, componentsPerVector: 3, bytesPerComponent: 4, dataOffset: 0, dataStride: stride)
      let normals = SCNGeometrySource(
        data: m.normals, semantic: .normal, vectorCount: m.vertexCount,
        usesFloatComponents: true, componentsPerVector: 3, bytesPerComponent: 4, dataOffset: 0, dataStride: stride)
      var elements: [SCNGeometryElement] = []
      var mats: [SCNMaterial] = []
      var lineIndices = Data()
      var triangleCount = 0
      for (band, data) in m.bands.enumerated() where m.bandCounts[band] > 0 && materials[band].transparency > 0 {
        elements.append(SCNGeometryElement(data: data, primitiveType: .triangles, primitiveCount: m.bandCounts[band], bytesPerIndex: 4))
        mats.append(materials[band])
        lineIndices.append(data)
        triangleCount += m.bandCounts[band]
      }
      guard !elements.isEmpty else {
        node.geometry = nil
        node.childNode(withName: "scan-triangles", recursively: false)?.removeFromParentNode()
        continue
      }
      let geometry = SCNGeometry(sources: [vertices, normals], elements: elements)
      geometry.materials = mats
      let isNew = node.geometry == nil
      node.geometry = geometry
      let edges = node.childNode(withName: "scan-triangles", recursively: false) ?? SCNNode()
      edges.name = "scan-triangles"
      let lines = SCNGeometry(sources: [vertices], elements: [
        SCNGeometryElement(data: lineIndices, primitiveType: .triangles,
                           primitiveCount: triangleCount, bytesPerIndex: 4)
      ])
      lines.materials = [triangleLine]
      edges.geometry = lines
      edges.renderingOrder = 1
      if edges.parent == nil { node.addChildNode(edges) }
      if isNew && !UIAccessibility.isReduceMotionEnabled {
        node.opacity = 0.15
        let reveal = SCNAction.fadeIn(duration: 0.65)
        reveal.timingMode = .easeOut
        node.runAction(reveal, forKey: "scan-reveal")
      }
    }
  }
}

/// A thread-safe on/off switch
final class FeedGate: @unchecked Sendable {
  private let lock = NSLock()
  private var on = true
  var isOn: Bool {
    get { lock.withLock { on } }
    set { lock.withLock { on = newValue } }
  }
}
