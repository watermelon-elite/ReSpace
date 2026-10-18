import SwiftUI
import RoomPlan
import AVFoundation

struct ContentView: View {
    @State private var app = AppModel()
    @State private var setup = false
    @State private var capture: CaptureController?
    @State private var permissionDenied = false
    @State private var recoveries: [CaptureArchive] = []
    @State private var discardArchive: CaptureArchive?
    private var captureSupported: Bool { UIDevice.current.userInterfaceIdiom == .phone && RoomCaptureSession.isSupported }
    private var librarySupported: Bool {
        #if DEBUG && targetEnvironment(simulator)
        true
        #else
        captureSupported
        #endif
    }
    var body: some View {
        Group {
            if !librarySupported {
                ContentUnavailableView("LiDAR iPhone required", systemImage: "iphone", description: Text("ReSpace requires iOS 18 or later and an iPhone that supports RoomPlan and LiDAR room capture."))
            } else {
                NavigationStack {
                    List {
                        if !captureSupported { Section("Room capture unavailable") { Text("New scans require a LiDAR iPhone. Saved Rooms are available for local testing.") } }
                        if app.client == nil { Section { Text("Connect to your ReSpace backend to open your Rooms."); Button("Configure Backend") { setup = true } } }
                        if let error = app.error { Section { Text(error).foregroundStyle(.red); Button("Refresh") { Task { await app.refresh() } } } }
                        if permissionDenied { Section("Camera access is off") { Button("Open Settings") { if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) } }; Button("Return to My Rooms") { permissionDenied = false } } }
                        if app.rooms.isEmpty { ContentUnavailableView("Your rooms, ready for a fresh start", systemImage: "square.stack.3d.up", description: Text("Scan a room to review its measurements and create a design.")) }
                        ForEach(app.rooms, id: \.self) { room in
                            NavigationLink { RoomReview(app: app, roomID: room["room_id"].text) } label: {
                                HStack {
                                    if let path = room["thumbnail_url"].string { PrivateCapturePhoto(app: app, path: path).frame(width: 64, height: 64).clipped() } else { Image(systemName: "cube").frame(width: 48) }
                                    VStack(alignment: .leading) {
                                        Text(room["name"].text).font(.headline)
                                        Text(room["scan_at"].string ?? room["created_at"].text).font(.caption).foregroundStyle(.secondary)
                                        if let state = room["current_operation_state"].string { Text(state.replacingOccurrences(of: "_", with: " ").capitalized).font(.caption).foregroundStyle(.orange) }
                                        else if room["capture_state"].text != "complete" { Text(room["capture_state"].text.replacingOccurrences(of: "_", with: " ")).font(.caption) }
                                    }
                                }
                            }
                        }
                        ForEach(recoveries, id: \.captureID) { archive in
                            Section("Retained scan") {
                                if archive.phase == "upload_pending" { Button("Recover completed scan") { if let client = app.client { capture = CaptureController(archive: archive, app: app, client: client) } } }
                                else { Text("Scan interrupted. Start again to capture this room."); Button("Discard interrupted scan", role: .destructive) { discardArchive = archive } }
                            }
                        }
                        ForEach(app.pending, id: \.operationID) { request in Section("Request awaiting confirmation") { Text(request.path); Button("Reconcile") { Task { do { _ = try await app.reconcile(request); await app.refresh() } catch { app.error = error.localizedDescription } } } } }
                    }
                    .navigationTitle("My Rooms")
                    .toolbar { ToolbarItem(placement: .topBarLeading) { Button("Backend", systemImage: "network") { setup = true } }; ToolbarItem(placement: .topBarTrailing) { Button("New Scan", systemImage: "plus") { Task { await start() } }.disabled(!captureSupported || app.client == nil || app.busy) } }
                    .refreshable { await app.refresh(); recoveries = CaptureArchive.recoverable() }
                    .task { await app.recoverPending(); await app.refresh(); recoveries = CaptureArchive.recoverable() }
                }
                .confirmationDialog("Discard the interrupted scan and its uploaded photos?", isPresented: Binding(get: { discardArchive != nil }, set: { if !$0 { discardArchive = nil } }), titleVisibility: .visible) {
                    Button("Discard Scan", role: .destructive) { if let archive = discardArchive, let client = app.client { Task { let controller = CaptureController(archive: archive, app: app, client: client); await controller.abandon(); recoveries = CaptureArchive.recoverable() }; discardArchive = nil } }
                }
                .sheet(isPresented: $setup) { NavigationStack { Form { TextField("https://your-backend.example", text: $app.backend).textContentType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled(); Text("This installation ID groups your Rooms. It is not account authentication.").font(.caption) }.navigationTitle("Backend").toolbar { Button("Save") { app.saveBackend(); setup = false; Task { await app.refresh() } } } } }
                .fullScreenCover(item: $capture, onDismiss: { Task { await app.refresh(); recoveries = CaptureArchive.recoverable() } }) { CaptureScreen(controller: $0) }
            }
        }
    }
    private func start() async {
        guard captureSupported, let client = app.client else { return }
        let allowed = AVCaptureDevice.authorizationStatus(for: .video) == .authorized ? true : await AVCaptureDevice.requestAccess(for: .video)
        guard allowed else { permissionDenied = true; return }
        app.busy = true; defer { app.busy = false }
        do {
            _ = try await client.request("health")
            let probe = app.disk.appendingPathComponent("write-probe"); try Data([1]).write(to: probe); try FileManager.default.removeItem(at: probe)
            let result = try await app.submit(PendingRequest(path: "rooms", roomID: nil, body: [:]))
            var archive = CaptureArchive(roomID: result["room"]["room_id"].text, captureID: result["capture_id"].text, startedAt: ISO8601DateFormatter().string(from: Date()))
            guard !archive.roomID.isEmpty, !archive.captureID.isEmpty else { throw ContractError.invalid("Backend did not create a draft capture.") }
            archive.phase = "capturing"; try archive.save()
            capture = CaptureController(archive: archive, app: app, client: client)
        } catch { app.error = error.localizedDescription }
    }
}
extension CaptureController: Identifiable { var id: String { archive.captureID } }
