import SwiftUI
import RoomPlan

struct ScanCaptureScreen: View {
    let store: WorkspaceStore
    let recoveryId: String?
    let completion: (String?) -> Void
    @State private var controller: ScanCaptureController
    @State private var confirmDiscard = false
    @Environment(\.scenePhase) private var scenePhase

    init(store: WorkspaceStore, recoveryId: String?, completion: @escaping (String?) -> Void) {
        self.store = store; self.recoveryId = recoveryId; self.completion = completion
        _controller = State(initialValue: ScanCaptureController(store: store))
    }
    var body: some View {
        ZStack {
            ReSpaceTheme.cream.ignoresSafeArea()
            if (controller.phase == .scanning || controller.phase == .finishing), let roomView = controller.roomView {
                ScanCaptureSurface(view: roomView).ignoresSafeArea()
                VStack {
                    HStack {
                        Button("Cancel scan") { confirmDiscard = true }.buttonStyle(.bordered).tint(.white)
                        Spacer()
                        Text(store.localCaptureEnabled ? "\(controller.elapsedSeconds / 60):\(String(format: "%02d", controller.elapsedSeconds % 60)) · \(controller.acceptedFrames) photos" : "\(controller.acceptedFrames)/40 photos")
                            .font(ReSpaceStyle.font(13)).padding(10).background(.regularMaterial, in: Capsule())
                    }
                    Spacer()
                    VStack(spacing: 10) {
                        Text(controller.guidance).font(ReSpaceStyle.font(18, weight: .semibold))
                        Text(store.localCaptureEnabled ? (controller.canFinish ? "Revisit gaps, furniture sides, and spaces underneath before finishing." : "Scan for at least 1 minute. Walk around furniture and capture surfaces from several angles.") : controller.detailText).font(ReSpaceStyle.font(13)).foregroundStyle(.secondary)
                        PrimaryAction(title: controller.phase == .finishing ? "Finishing scan…" : "Done", symbol: "checkmark",
                                      disabled: controller.phase == .finishing || !controller.canFinish) { controller.done() }
                    }.padding(18).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 24))
                }.padding(20)
            } else { stateView.padding(28) }
        }
        .task { await controller.prepare(recovering: recoveryId) }
        .onChange(of: controller.phase) { _, phase in if case .ready(let id) = phase { completion(id) } }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active { controller.appBecameInactive() }
            else if controller.phase == .permissionDenied {
                controller = ScanCaptureController(store: store)
                Task { await controller.prepare() }
            }
        }
        .alert("Discard this scan?", isPresented: $confirmDiscard) {
            Button("Keep scanning", role: .cancel) {}
            Button("Discard", role: .destructive) { Task { await controller.discard(); completion(nil) } }
        } message: { Text(store.localCaptureEnabled ? "This scan’s local data will be deleted. Your other saved rooms are kept." : "This incomplete scan and its uploaded artifacts will be deleted. Your saved rooms are kept.") }
    }
    @ViewBuilder private var stateView: some View {
        switch controller.phase {
        case .permissionDenied:
            VStack(alignment: .leading, spacing: 20) {
                Image(systemName: "camera").font(.largeTitle)
                Text("Let’s see your space.").font(ReSpaceStyle.font(34, weight: .semibold))
                Text("Allow camera access in Settings to scan your room.").foregroundStyle(.secondary)
                Button("Open Settings") { if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) } }
                Button("Back to My Rooms") { completion(nil) }
            }
        case .interrupted:
            VStack(alignment: .leading, spacing: 20) {
                Image(systemName: "viewfinder").font(.largeTitle)
                Text("Scan interrupted.").font(ReSpaceStyle.font(34, weight: .semibold))
                Text("Scan interrupted. Start again to capture this room.")
                if let error = controller.error { Text(error).font(ReSpaceStyle.font(13)).foregroundStyle(.secondary) }
                PrimaryAction(title: "Restart scan", symbol: "arrow.clockwise") {
                    Task { await controller.discard(); controller = ScanCaptureController(store: store); await controller.prepare() }
                }
                Button("Back to My Rooms") { Task { await controller.discard(); completion(nil) } }
            }
        case .failed:
            VStack(alignment: .leading, spacing: 20) {
                Text("Your scan needs attention.").font(ReSpaceStyle.font(34, weight: .semibold))
                StatusBanner(text: controller.error ?? "The scan could not finish.", isError: true)
                if controller.hasCompletedCapture {
                    Button(store.localCaptureEnabled ? "Retry saving scan" : "Retry finished upload") { Task { await controller.finalize() } }
                    Button("Back to My Rooms") { completion(nil) }
                } else {
                    Button("Restart scan") { Task { await controller.discard(); controller = ScanCaptureController(store: store); await controller.prepare() } }
                    Button("Back to My Rooms") { Task { await controller.discard(); completion(nil) } }
                }
                Button("Discard scan", role: .destructive) { confirmDiscard = true }
            }
        default:
            VStack(spacing: 20) {
                ProgressView()
                Text(controller.phase == .preparing ? "Preparing your scan…" : "Saving your room…").font(ReSpaceStyle.font(22, weight: .semibold))
                Text(store.localCaptureEnabled ? "Saving the room and its recorded data on this iPhone." : "Keep this scan’s recorded data until upload is confirmed.").font(ReSpaceStyle.font(15)).foregroundStyle(.secondary)
                if controller.phase == .recovering && !store.localCaptureEnabled { Button("Back to My Rooms") { completion(nil) } }
            }
        }
    }
}

private struct ScanCaptureSurface: UIViewRepresentable {
    let view: RoomCaptureView
    func makeUIView(context: Context) -> RoomCaptureView { view }
    func updateUIView(_ uiView: RoomCaptureView, context: Context) {}
}
