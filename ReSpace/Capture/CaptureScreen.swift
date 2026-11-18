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
            if (controller.phase == .scanning || controller.phase == .finishing), let view = controller.sourceView ?? controller.roomView {
                ScanCaptureSurface(view: view).ignoresSafeArea()
                VStack(spacing: 16) {
                    HStack {
                        Button { confirmDiscard = true } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }
                            .accessibilityLabel("Cancel scan")
                        Spacer()
                        Text("Scan room").font(ReSpaceStyle.font(17, weight: .semibold))
                        Spacer()
                        Menu {
                            Toggle("High-resolution photos", isOn: $controller.highResolutionPhotos)
                            Text("\(controller.acceptedFrames) photos saved")
                            Text(controller.detailText)
                        } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
                        .accessibilityLabel("Capture options")
                    }.foregroundStyle(.white).padding(.horizontal, 8).background(.black.opacity(0.65), in: RoundedRectangle(cornerRadius: 16))
                    Spacer()
                    VStack(spacing: 16) {
                        if controller.phase == .finishing {
                            ProgressView("Saving your scan…")
                            Text("Keep ReSpace open while your room is saved.").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
                        } else {
                            Text(controller.guidance).font(ReSpaceStyle.font(17, weight: .semibold)).multilineTextAlignment(.center)
                            HStack(spacing: 12) {
                                Button { controller.takeDetailPhoto() } label: { Image(systemName: "camera").frame(width: 52, height: 52).background(ReSpaceStyle.wash, in: RoundedRectangle(cornerRadius: 14)) }
                                    .disabled(!controller.canTakeDetailPhoto).accessibilityLabel("Take an extra detail photo")
                                Button("Finish scan") { controller.done() }.buttonStyle(RSButtonStyle()).disabled(!controller.canFinish)
                            }
                        }
                    }.padding(20).background(ReSpaceStyle.white, in: RoundedRectangle(cornerRadius: 24))
                }.padding(16)

            } else { stateView.padding(28) }
        }
        .onAppear { UIApplication.shared.isIdleTimerDisabled = true }
        .onDisappear { UIApplication.shared.isIdleTimerDisabled = false }
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
    let view: UIView
    func makeUIView(context: Context) -> UIView { view }
    func updateUIView(_ uiView: UIView, context: Context) {}
}
