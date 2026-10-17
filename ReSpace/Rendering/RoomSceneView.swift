import RealityKit
import SwiftUI

struct RoomSceneView: View {
    var snapshot: RoomSnapshot
    var items: [SceneItem]
    @Binding var selectedId: String?
    var showGhosts = true
    var resetToken = 0
    @State private var scene = RoomSceneController()
    @State private var lastDrag = CGSize.zero
    @State private var lastMagnification: CGFloat = 1
    @State private var panMode = false

    var body: some View {
        RealityView { content in
            content.camera = .virtual
            content.add(scene.root)
            scene.update(snapshot: snapshot, items: items, selectedId: selectedId, showGhosts: showGhosts)
        } update: { _ in
            scene.update(snapshot: snapshot, items: items, selectedId: selectedId, showGhosts: showGhosts)
        }
        .realityViewCameraControls(.none)
        .gesture(SpatialTapGesture().targetedToAnyEntity().onEnded { value in
            selectedId = scene.itemId(for: value.entity)
        })
        .simultaneousGesture(DragGesture(minimumDistance: 8).onChanged { value in
            let dx = Float(value.translation.width - lastDrag.width)
            let dy = Float(value.translation.height - lastDrag.height)
            if panMode { scene.pan(dx: dx, dy: dy) } else { scene.orbit(dx: dx, dy: dy) }
            lastDrag = value.translation
        }.onEnded { _ in lastDrag = .zero })
        .simultaneousGesture(MagnifyGesture().onChanged { value in
            scene.zoom(factor: Float(value.magnification / lastMagnification))
            lastMagnification = value.magnification
        }.onEnded { _ in lastMagnification = 1 })
        .overlay(alignment: .topTrailing) {
            Button { panMode.toggle() } label: {
                Label(panMode ? "Pan" : "Orbit", systemImage: panMode ? "hand.draw" : "rotate.3d")
                    .font(.caption.weight(.medium)).padding(10).background(.regularMaterial, in: Capsule())
            }.padding().padding(.top, 60)
        }
        .overlay(alignment: .bottomLeading) {
            if !scene.assetWarnings.isEmpty {
                Text("Some models use measured stand-ins").font(.caption2).padding(8).background(.regularMaterial, in: Capsule()).padding()
            }
        }
        .onChange(of: resetToken) { scene.resetView() }
        .onDisappear { lastDrag = .zero; lastMagnification = 1 }
        .background(Color(red: 0.94, green: 0.93, blue: 0.89))
    }
}
