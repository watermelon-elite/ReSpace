import SwiftUI
import RoomPlan
import AVFoundation

struct ContentView: View {
    @State private var app: AppModel
    init(app: AppModel? = nil) { _app = State(initialValue: app ?? AppModel()) }
    #if DEBUG
    @State private var showDemoRoom = false
    #endif
    @State private var scanRecoveryID: String?
    @State private var scanning = false
    @State private var scannedRoom: LocalSavedRoom?
    @State private var completedScanID: String?
    @State private var discardScanID: String?
    @State private var renameScan: LocalSavedRoom?
    @State private var renameScanText = ""
    @State private var deleteScan: LocalSavedRoom?
    @State private var setup = false
    @State private var scanSetup = false
    @State private var capture: CaptureController?
    @State private var permissionDenied = false
    @State private var recoveries: [CaptureArchive] = []
    @State private var discardArchive: CaptureArchive?
    @State private var showShoppingLists = false
    private var savedLists: [ShoppingList]? {
        #if DEBUG
        if let session = app.uiDemo { return [session.shoppingList] }
        #endif
        return app.shoppingLists?.lists
    }
    private var simulatedScan: Bool {
        #if DEBUG && targetEnvironment(simulator)
        true
        #else
        app.isUIDemo
        #endif
    }
    private var captureSupported: Bool { app.isUIDemo || (UIDevice.current.userInterfaceIdiom == .phone && RoomCaptureSession.isSupported) }
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
                RSPage(title: "Your rooms", showsBack: false, inlineTitle: true,
                       trailingSymbol: "bag", trailingLabel: "Shopping lists", trailing: { showShoppingLists = true }) {
                    if app.rooms.isEmpty && ImportedRoomView.modelURL == nil {
                        Image("RoomInspiration").resizable().scaledToFill().frame(height: 300).clipped().clipShape(RoundedRectangle(cornerRadius: 28))
                            .accessibilityLabel("Room inspiration")
                    }
                    ForEach(Array(app.rooms.filter { room in room["source_scene_sha256"] == .null && !app.localRooms.contains { $0.backendRoomId == room["room_id"].text } }.enumerated()), id: \.element) { index, room in
                        NavigationLink { RoomReview(app: app, roomID: room["room_id"].text) } label: { roomCard(room, hero: index == 0) }.buttonStyle(.plain)
                    }
                    if let store = app.scanStore {
                        ForEach(app.localRooms) { room in
                            NavigationLink { LocalRoomPreviewView(room: room, repository: store.captures, reconstruction: store.reconstruction, app: app) } label: {
                                RSRoomCard(title: app.rooms.first { $0["room_id"].text == room.backendRoomId }?["name"].string ?? room.name,
                                           subtitle: "Scanned \(room.createdAt.scanDateLabel)", hero: false) {
                                    ReSpaceStyle.canvas.overlay { Image(systemName: "cube.transparent").foregroundStyle(ReSpaceStyle.purple) }
                                }
                            }.buttonStyle(.plain)
                                .contextMenu {
                                    Button("Rename", systemImage: "pencil") { renameScan = room; renameScanText = room.name }
                                    Button("Delete room", systemImage: "trash", role: .destructive) { deleteScan = room }
                                }
                        }
                        ForEach(app.scanRecoveries, id: \.captureId) { manifest in
                            if manifest.state == "completed" {
                                Button("Finish saving your scan") { scanRecoveryID = manifest.captureId; scanning = true }
                                    .buttonStyle(RSButtonStyle(kind: .secondary))
                            } else {
                                RSNotice(message: "This scan was interrupted. Start a new scan to capture the room.")
                                Button("Discard interrupted scan") { discardScanID = manifest.captureId }
                                    .buttonStyle(RSButtonStyle(kind: .secondary))
                            }
                        }
                    }
                    if ImportedRoomView.modelURL != nil && !app.isUIDemo {
                        NavigationLink { ImportedRoomView(app: app) } label: {
                            RSRoomCard(title: "Kitchenette", subtitle: "Your reconstructed room",
                                       hero: app.rooms.allSatisfy { $0["source_scene_sha256"] != .null }) {
                                Image("KitchenettePreview").resizable().scaledToFill()
                                    .accessibilityLabel("Preview of your reconstructed kitchenette")
                            }
                        }.buttonStyle(.plain)
                    }
                    if let error = app.error {
                        RSNotice(message: error, isError: true)
                        Button("Refresh") { Task { await app.refresh() } }.buttonStyle(RSButtonStyle(kind: .secondary))
                    }
                    if app.client == nil {
                        Button { setup = true } label: { RSRow(title: "Connect ReSpace", subtitle: "Set up your connection to open your rooms", symbol: "network") }.buttonStyle(.plain)
                    }
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
                    Button("Scan your room") { if !simulatedScan { scanSetup = true } }
                        .buttonStyle(RSButtonStyle()).disabled(!simulatedScan && (!captureSupported || app.scanStore == nil || app.busy))
                }
                .refreshable { await app.refresh(); await app.refreshScans(); if !app.isUIDemo { recoveries = CaptureArchive.recoverable().filter { archive in !app.localRooms.contains { $0.backendRoomId == archive.roomID } } } }
                .task { await app.recoverPending(); await app.refresh(); await app.refreshScans(); if !app.isUIDemo { recoveries = CaptureArchive.recoverable().filter { archive in !app.localRooms.contains { $0.backendRoomId == archive.roomID } } } }
            }
        }
        .fullScreenCover(isPresented: $scanning, onDismiss: {
            Task {
                await app.refreshScans()
                if let id = completedScanID { completedScanID = nil; scannedRoom = app.localRooms.first { $0.id == id } }
            }
        }) {
            if let store = app.scanStore {
                ScanCaptureScreen(store: store, recoveryId: scanRecoveryID) { id in completedScanID = id; scanning = false }
            }
        }
        .sheet(item: $scannedRoom) { room in
            if let store = app.scanStore { LocalRoomPreviewView(room: room, repository: store.captures, reconstruction: store.reconstruction, app: app) }
        }
        .alert("Discard interrupted scan?", isPresented: Binding(get: { discardScanID != nil }, set: { if !$0 { discardScanID = nil } })) {
            Button("Cancel", role: .cancel) { discardScanID = nil }
            Button("Discard", role: .destructive) {
                if let id = discardScanID, let store = app.scanStore {
                    Task { do { try await store.captures.removeCapture(id); await app.refreshScans() } catch { app.error = error.localizedDescription } }
                }
                discardScanID = nil
            }
        } message: { Text("This incomplete scan and its local photos will be removed. Your other rooms are kept.") }
        .alert("Rename room", isPresented: Binding(get: { renameScan != nil }, set: { if !$0 { renameScan = nil } })) {
            TextField("Room name", text: $renameScanText)
            Button("Cancel", role: .cancel) { renameScan = nil }
            Button("Save") { if let room = renameScan { Task { await renameLocalRoom(room, name: renameScanText) } }; renameScan = nil }
        }
        .alert("Delete this room?", isPresented: Binding(get: { deleteScan != nil }, set: { if !$0 { deleteScan = nil } })) {
            Button("Cancel", role: .cancel) { deleteScan = nil }
            Button("Delete", role: .destructive) { if let room = deleteScan { Task { await removeLocalRoom(room) } }; deleteScan = nil }
        } message: { Text("Removes this iPhone’s scan and any linked planning room and designs. Copies on the reconstruction service remain there.") }
        .sheet(isPresented: $setup) { backendSettings }
        #if DEBUG
        .fullScreenCover(isPresented: $showDemoRoom) {
            NavigationStack { RoomReview(app: app, roomID: app.uiDemo!.roomID) }
        }
        #endif
        .sheet(isPresented: $showShoppingLists) {
            if let lists = savedLists { SavedShoppingListsView(lists: lists) }
            else {
                RSPage(title: "Shopping lists") {
                    Text("Shopping lists are unavailable. Reopen ReSpace to try again.")
                } footer: { EmptyView() }
            }
        }
        .sheet(isPresented: $scanSetup) {
            RSPage(title: "Scan your room.", back: { scanSetup = false }) {
                Image("RoomInspiration").resizable().scaledToFill().frame(height: 300).clipped().clipShape(RoundedRectangle(cornerRadius: 28)).accessibilityLabel("Example room to scan")
                OlloMessage(cue: .presenting) {
                    Text("Move slowly around the room. Include the walls and larger Objects.").foregroundStyle(ReSpaceStyle.secondary)
                }
                DisclosureGroup("Ready to scan") { Text("ReSpace checks camera access and space to save your scan. Your completed scan stays on this iPhone; connect to plan changes or create a walkthrough.").padding(.top, 8) }.font(ReSpaceStyle.font(13))
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
            Button("Discard Scan", role: .destructive) { if let archive = discardArchive, let client = app.client { Task { let controller = CaptureController(archive: archive, app: app, client: client); await controller.abandon(); recoveries = CaptureArchive.recoverable().filter { archive in !app.localRooms.contains { $0.backendRoomId == archive.roomID } } }; discardArchive = nil } }
        }
        .fullScreenCover(item: $capture, onDismiss: { Task { await app.refresh(); recoveries = CaptureArchive.recoverable().filter { archive in !app.localRooms.contains { $0.backendRoomId == archive.roomID } } } }) { CaptureScreen(controller: $0) }
    }
    private func renameLocalRoom(_ scan: LocalSavedRoom, name: String) async {
        guard let store = app.scanStore else { return }
        do {
            var scan = try await store.captures.localRoom(scan.id)
            if scan.backendCreationName != nil && scan.backendRoomId == nil {
                scan = try await app.linkScan(scan.id)
            }
            if let roomID = scan.backendRoomId, let client = app.client {
                let detail = try await client.request("rooms/\(roomID)")
                _ = try await app.submit(PendingRequest(path: "rooms/\(roomID)", method: "PATCH", roomID: roomID,
                    body: ["name": .string(name), "expected_metadata_revision": detail["room"]["metadata_revision"]]))
            } else if scan.backendRoomId != nil { throw ContractError.invalid("Connect ReSpace to rename this saved room.") }
            try await store.captures.renameLocalRoom(scan.id, name: name)
            await app.refreshScans(); await app.refresh()
        } catch { app.error = error.localizedDescription }
    }
    private func removeLocalRoom(_ scan: LocalSavedRoom) async {
        guard let store = app.scanStore else { return }
        do {
            var scan = try await store.captures.localRoom(scan.id)
            if scan.backendCreationName != nil && scan.backendRoomId == nil { scan = try await app.linkScan(scan.id) }
            if let roomID = scan.backendRoomId {
                let pending = app.pending.first { $0.roomID == roomID && $0.method == "DELETE" }
                let result = try await app.submit(pending ?? PendingRequest(path: "rooms/\(roomID)", method: "DELETE", roomID: roomID, body: [:]))
                guard result["deletion"]["state"].text == "deleted" else { throw ContractError.invalid("Deletion is pending. Check the request before retrying.") }
            } else { try await store.captures.removeCapture(scan.id) }
            await app.refreshScans(); await app.refresh()
        } catch { app.error = error.localizedDescription }
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
        RSRoomCard(title: room["name"].text,
                   subtitle: "Scanned \(displayDate(room["scan_at"].string ?? room["created_at"].text))",
                   status: (room["current_operation_state"].string ?? (room["capture_state"].text == "complete" ? nil : room["capture_state"].text))?.replacingOccurrences(of: "_", with: " ").capitalized,
                   hero: hero) { roomImage(room) }
    }
    private func roomImage(_ room: JSONValue) -> some View {
        Group {
            if let path = room["thumbnail_url"].string { PrivateCapturePhoto(app: app, path: path, fill: true) }
            else { ZStack { ReSpaceStyle.canvas; Image(systemName: "cube.transparent").font(.system(size: 48, weight: .ultraLight)).foregroundStyle(ReSpaceStyle.purple) } }
        }
    }
    private func start() async {
        #if DEBUG
        if app.isUIDemo { showDemoRoom = true; return }
        #endif
        guard captureSupported, app.scanStore != nil else { return }
        scanRecoveryID = nil
        scanning = true
    }
}
extension CaptureController: Identifiable { var id: String { archive.captureID } }

#if DEBUG
#Preview("My Rooms") { UIDemoPreview(.rooms) }
#endif
