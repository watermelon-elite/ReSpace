import SwiftUI
import RoomPlan
import AVFoundation

struct ContentView: View {
    @State private var app = AppModel()
    @State private var setup = false
    @State private var scanSetup = false
    @State private var capture: CaptureController?
    @State private var permissionDenied = false
    @State private var recoveries: [CaptureArchive] = []
    @State private var discardArchive: CaptureArchive?
    @State private var showShoppingLists = false
    private var captureSupported: Bool { UIDevice.current.userInterfaceIdiom == .phone && RoomCaptureSession.isSupported }
    private var librarySupported: Bool {
        #if DEBUG && targetEnvironment(simulator)
        true
        #else
        captureSupported
        #endif
    }
    var body: some View {
        NavigationStack {
            if !librarySupported {
                RSPage(title: "A LiDAR iPhone\nis needed.", topTitle: "ReSpace", showsBack: false) {
                    RSSymbol(name: "camera")
                    Text("ReSpace uses the depth scanner on supported Pro iPhones to measure your room.").foregroundStyle(ReSpaceStyle.secondary)
                    VStack(spacing: 0) {
                        RSKeyValue(title: "Device", value: "LiDAR iPhone")
                        RSKeyValue(title: "Software", value: "iOS 18 or later")
                    }
                } footer: { EmptyView() }
            } else {
                RSPage(title: app.rooms.isEmpty && ImportedRoomView.modelURL == nil ? "Your first room" : "Your rooms", topTitle: "ReSpace", showsBack: false,
                       trailingSymbol: "gearshape", trailingLabel: "Connection settings", trailing: { setup = true }) {
                    if app.rooms.isEmpty && ImportedRoomView.modelURL == nil {
                        Image("RoomInspiration").resizable().scaledToFill().frame(height: 300).clipped().clipShape(RoundedRectangle(cornerRadius: 28))
                            .accessibilityLabel("Room inspiration")
                    }
                    ForEach(Array(app.rooms.filter { $0["source_scene_sha256"] == .null }.enumerated()), id: \.element) { index, room in
                        NavigationLink { RoomReview(app: app, roomID: room["room_id"].text) } label: { roomCard(room, hero: index == 0) }.buttonStyle(.plain)
                    }
                    if ImportedRoomView.modelURL != nil {
                        NavigationLink { ImportedRoomView(app: app) } label: {
                            RSRow(title: "Kitchenette", subtitle: "Your reconstructed room", symbol: "cube.transparent")
                        }.buttonStyle(.plain)
                    }
                    if app.shoppingLists != nil {
                        Button { showShoppingLists = true } label: {
                            RSRow(title: "Saved shopping lists", subtitle: "Your Product links, ready to share", symbol: "bag")
                        }.buttonStyle(.plain)
                    }
                    if let error = app.error {
                        RSNotice(message: error, isError: true)
                        Button("Refresh") { Task { await app.refresh() } }.buttonStyle(RSButtonStyle(kind: .secondary))
                    }
                    if app.client == nil {
                        Button { setup = true } label: { RSRow(title: "Connect ReSpace", subtitle: "Set up your connection to open your rooms", symbol: "network") }.buttonStyle(.plain)
                    }
                    if !captureSupported { Text("New scans require a LiDAR iPhone. Saved Rooms are available for local testing.").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary) }
                    ForEach(recoveries, id: \.captureID) { archive in
                        VStack(alignment: .leading, spacing: 12) {
                            Text(archive.phase == "upload_pending" ? "Your scan is safe." : "Let’s scan again.").font(ReSpaceStyle.font(22, weight: .semibold))
                            Text(archive.phase == "upload_pending" ? "It’s on your phone. Reconnect to finish saving it." : "The scan was interrupted before it finished.").foregroundStyle(ReSpaceStyle.secondary)
                            if archive.phase == "upload_pending" {
                                Button("Try saving again") { if let client = app.client { capture = CaptureController(archive: archive, app: app, client: client) } }.buttonStyle(RSButtonStyle()).disabled(app.client == nil)
                            } else {
                                Button("Discard interrupted scan") { discardArchive = archive }.buttonStyle(RSButtonStyle(kind: .secondary))
                            }
                        }.padding(20).background(ReSpaceStyle.canvas, in: RoundedRectangle(cornerRadius: 20))
                    }
                    ForEach(app.pending, id: \.operationID) { request in
                        VStack(alignment: .leading, spacing: 12) {
                            Text(request.method == "DELETE" ? "Deletion pending" : "Let’s reconnect.").font(ReSpaceStyle.font(22, weight: .semibold))
                            Text("We couldn’t confirm the request. Check it before trying again.").foregroundStyle(ReSpaceStyle.secondary)
                            Button("Check request") { Task { do { _ = try await app.reconcile(request); await app.refresh() } catch { app.error = error.localizedDescription } } }.buttonStyle(RSButtonStyle(kind: .secondary))
                        }
                    }
                } footer: {
                    Button(app.rooms.isEmpty ? "Scan your room" : "Scan a new room") { scanSetup = true }
                        .buttonStyle(RSButtonStyle()).disabled(!captureSupported || app.client == nil || app.busy)
                }
                .refreshable { await app.refresh(); recoveries = CaptureArchive.recoverable() }
                .task { await app.recoverPending(); await app.refresh(); recoveries = CaptureArchive.recoverable() }
            }
        }
        .sheet(isPresented: $setup) { backendSettings }
        .sheet(isPresented: $showShoppingLists) {
            if let store = app.shoppingLists { SavedShoppingListsView(store: store) }
        }
        .sheet(isPresented: $scanSetup) {
            RSPage(title: "Scan your room.", back: { scanSetup = false }) {
                Image("RoomInspiration").resizable().scaledToFill().frame(height: 300).clipped().clipShape(RoundedRectangle(cornerRadius: 28)).accessibilityLabel("Example room to scan")
                Text("Move slowly around the room. Include the walls and larger Objects.").foregroundStyle(ReSpaceStyle.secondary)
                DisclosureGroup("Ready to scan") { Text("ReSpace checks camera access, the connection and space to save your scan before starting.").padding(.top, 8) }.font(ReSpaceStyle.font(13))
            } footer: {
                Button("Start scan") { scanSetup = false; Task { await start() } }.buttonStyle(RSButtonStyle()).disabled(app.busy)
            }
        }
        .sheet(isPresented: $permissionDenied) {
            RSPage(title: "Allow camera access.", back: { permissionDenied = false }) {
                RSSymbol(name: "camera")
                Text("Your camera is needed to scan and measure the room.")
                Text("Enable Camera for ReSpace in Settings, then return here.").font(ReSpaceStyle.font(14)).foregroundStyle(ReSpaceStyle.secondary)
            } footer: {
                Button("Open Settings") { if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) } }.buttonStyle(RSButtonStyle())
                Button("My Rooms") { permissionDenied = false }.buttonStyle(RSButtonStyle(kind: .quiet))
            }
        }
        .confirmationDialog("Discard the interrupted scan and its uploaded photos?", isPresented: Binding(get: { discardArchive != nil }, set: { if !$0 { discardArchive = nil } }), titleVisibility: .visible) {
            Button("Discard Scan", role: .destructive) { if let archive = discardArchive, let client = app.client { Task { let controller = CaptureController(archive: archive, app: app, client: client); await controller.abandon(); recoveries = CaptureArchive.recoverable() }; discardArchive = nil } }
        }
        .fullScreenCover(item: $capture, onDismiss: { Task { await app.refresh(); recoveries = CaptureArchive.recoverable() } }) { CaptureScreen(controller: $0) }
    }
    private var backendSettings: some View {
        RSPage(title: "Connect ReSpace", back: { setup = false }) {
            VStack(alignment: .leading, spacing: 12) {
                Text("Backend URL").font(ReSpaceStyle.font(14, weight: .medium))
                TextField("https://your-backend.example", text: $app.backend).textContentType(.URL).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled().rsInput()
                Text("This installation ID groups your Rooms. It is not account authentication.").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
            }
        } footer: {
            Button("Save connection") { app.saveBackend(); setup = false; Task { await app.refresh() } }.buttonStyle(RSButtonStyle())
        }
    }
    private func roomCard(_ room: JSONValue, hero: Bool) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            if hero {
                roomImage(room).frame(height: 240).clipShape(RoundedRectangle(cornerRadius: 28))
            }
            HStack(spacing: 16) {
                if !hero { roomImage(room).frame(width: 64, height: 64).clipShape(RoundedRectangle(cornerRadius: 16)) }
                VStack(alignment: .leading, spacing: 5) {
                    Text(room["name"].text).font(ReSpaceStyle.font(18, weight: .semibold))
                    Text("Scanned \(displayDate(room["scan_at"].string ?? room["created_at"].text))").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
                    if let state = room["current_operation_state"].string {
                        Text(state.replacingOccurrences(of: "_", with: " ").capitalized).font(ReSpaceStyle.font(12, weight: .medium)).foregroundStyle(ReSpaceStyle.purple)
                    } else if room["capture_state"].text != "complete" {
                        Text(room["capture_state"].text.replacingOccurrences(of: "_", with: " ")).font(ReSpaceStyle.font(12))
                    }
                }
                Spacer()
                Image(systemName: "arrow.right").font(.system(size: 16))
            }.padding(.vertical, 8)
        }.foregroundStyle(ReSpaceStyle.ink)
    }
    private func roomImage(_ room: JSONValue) -> some View {
        Group {
            if let path = room["thumbnail_url"].string { PrivateCapturePhoto(app: app, path: path, fill: true) }
            else { ZStack { ReSpaceStyle.canvas; Image(systemName: "cube.transparent").font(.system(size: 48, weight: .ultraLight)).foregroundStyle(ReSpaceStyle.purple) } }
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
