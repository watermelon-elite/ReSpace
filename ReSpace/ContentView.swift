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
    @State private var reconstructionAddress = ""
    @State private var checkingConnection = false
    @State private var connectionOK = false
    @State private var connectionMessage: String?
    @State private var scanSetup = false
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
                library
                    .refreshable { await refreshLibrary() }
                    .task { await refreshLibrary() }

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
                    Task { do { try await store.captures.removeCapture(id); await app.refreshScans() } catch { app.scanError = error.localizedDescription } }
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
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 28) {
                        Image(systemName: "viewfinder").font(.system(size: 48, weight: .light)).foregroundStyle(ReSpaceStyle.accent)
                        Text("Capture one room").font(ReSpaceStyle.font(28, weight: .semibold))
                        Text("Move slowly around the room. Photos and measurements are saved automatically.").foregroundStyle(ReSpaceStyle.secondary)
                        scanTip("lightbulb", "Turn on the lights", "Clear views help capture surfaces and furniture.")
                        scanTip("rectangle.portrait", "Keep the phone upright", "Include every wall, the floor and larger furniture.")
                        scanTip("checkmark.circle", "Finish when you’ve covered the room", "You’ll review the saved scan before building a model.")
                    }.padding(24)
                }
                .navigationTitle("New scan").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { scanSetup = false } } }
                .safeAreaInset(edge: .bottom) {
                    VStack(spacing: 12) {
                        if simulatedScan && !app.isUIDemo {
                            Text("Use a LiDAR iPhone to capture a room.").foregroundStyle(ReSpaceStyle.secondary)
                        } else {
                            Button("Start scanning") { scanSetup = false; Task { await start() } }.buttonStyle(RSButtonStyle())
                        }
                        Text("Your scan stays on this iPhone until you choose to build a model.").font(ReSpaceStyle.font(12)).foregroundStyle(ReSpaceStyle.secondary).multilineTextAlignment(.center)
                    }.padding(20).background(ReSpaceStyle.white)
                }
            }
        }
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
            await refreshLibrary()
        } catch { app.scanError = error.localizedDescription }
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
            await refreshLibrary()
        } catch { app.scanError = error.localizedDescription }
    }
    private var backendSettings: some View {
        NavigationStack {
            Form {
                Section("3D model service") {
                    Text("Your Mac builds the model. Keep both devices on the same Wi-Fi.").foregroundStyle(.secondary)
                    TextField("Service address", text: $reconstructionAddress).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Button(checkingConnection ? "Checking…" : "Save and check connection") { Task { await checkConnection() } }.disabled(checkingConnection)
                    if let connectionMessage { Label(connectionMessage, systemImage: connectionOK ? "checkmark.circle" : "exclamationmark.circle").foregroundStyle(connectionOK ? ReSpaceStyle.secondary : ReSpaceStyle.danger) }
                }
                if app.designFeaturesEnabled {
                    Section("Design service") {
                        TextField("Service address", text: $app.backend).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                        Button("Save connection") { app.saveBackend() }
                        Button("Shopping lists") { setup = false; showShoppingLists = true }
                    }
                }
                Section {
                    Text("Scans are saved on this iPhone. Building a 3D model sends the scan to your Mac and OpenAI, with a separate confirmation and a $10 limit per generation.")
                }
            }
            .navigationTitle("Settings").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { setup = false } } }
            .task { reconstructionAddress = (try? AppConfiguration.load().reconstructionURL?.absoluteString) ?? "" }
        }
    }
    private func checkConnection() async {
        checkingConnection = true; connectionMessage = nil; connectionOK = false
        defer { checkingConnection = false }
        do {
            let raw = reconstructionAddress.trimmingCharacters(in: .whitespacesAndNewlines)
            guard let url = URL(string: raw), ["http", "https"].contains(url.scheme ?? ""), url.host != nil, url.user == nil, url.password == nil, url.query == nil, url.fragment == nil else {
                throw ContractError.invalid("Enter a complete service address, such as http://your-mac.local:8008.")
            }
            let configuration = try AppConfiguration.load()
            let client = ReconstructionClient(baseURL: url, token: configuration.reconstructionToken)
            try await client.checkConnection()
            UserDefaults.standard.set(raw, forKey: "reconstructionURL")
            app.scanStore?.reconstruction = client
            connectionOK = true; connectionMessage = "Connected. Ready to build your model."
        } catch { connectionMessage = "Couldn’t connect. Check the address, Wi-Fi and that the service is running on your Mac. " + error.localizedDescription }
    }

    private var library: some View {
        List {
            if !app.scansLoaded && !app.isUIDemo { ProgressView("Opening your rooms…") }
            else if app.localRooms.isEmpty && app.rooms.isEmpty && app.scanRecoveries.isEmpty {
                VStack(spacing: 18) {
                    Image(systemName: "viewfinder").font(.system(size: 52, weight: .ultraLight)).foregroundStyle(ReSpaceStyle.accent)
                        .frame(width: 96, height: 96).background(ReSpaceStyle.wash, in: RoundedRectangle(cornerRadius: 24))
                    Text("Your room, in 3D").font(ReSpaceStyle.font(24, weight: .semibold))
                    Text("Scan a room, build its model, then explore it from inside.").foregroundStyle(ReSpaceStyle.secondary).multilineTextAlignment(.center)
                }.frame(maxWidth: .infinity).padding(.vertical, 50).listRowBackground(Color.clear).listRowSeparator(.hidden)
            }
            if let store = app.scanStore {
                ForEach(app.localRooms) { room in
                    NavigationLink { LocalRoomPreviewView(room: room, repository: store.captures, reconstruction: store.reconstruction, app: app) } label: {
                        HStack(spacing: 14) {
                            LocalScanThumbnail(roomID: room.id, repository: store.captures).frame(width: 68, height: 68).clipped().clipShape(RoundedRectangle(cornerRadius: 12))
                            VStack(alignment: .leading, spacing: 6) {
                                Text(room.displayName).font(ReSpaceStyle.font(17, weight: .semibold))
                                Text(room.createdAt.scanDateLabel).font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
                            }
                        }.padding(.vertical, 6)
                    }
                    .contextMenu {
                        Button("Rename", systemImage: "pencil") { renameScan = room; renameScanText = room.displayName }
                        Button("Delete room", systemImage: "trash", role: .destructive) { deleteScan = room }
                    }
                }
                if !app.scanRecoveries.isEmpty {
                    Section("Needs attention") {
                        ForEach(app.scanRecoveries, id: \.captureId) { manifest in
                            if manifest.state == "completed" {
                                Button("Finish saving scan") { scanRecoveryID = manifest.captureId; scanning = true }
                            } else {
                                VStack(alignment: .leading, spacing: 10) {
                                    Text("Interrupted scan").fontWeight(.medium)
                                    Text("This scan didn’t finish. Start a new scan when you’re ready.").font(.subheadline).foregroundStyle(.secondary)
                                    Button("Discard incomplete scan", role: .destructive) { discardScanID = manifest.captureId }
                                }.padding(.vertical, 6)
                            }
                        }
                    }
                }
            }
            if app.designFeaturesEnabled {
                ForEach(app.rooms.filter { room in room["source_scene_sha256"] == .null && !app.localRooms.contains { $0.backendRoomId == room["room_id"].text } }, id: \.self) { room in
                    NavigationLink { RoomReview(app: app, roomID: room["room_id"].text) } label: { roomCard(room, hero: false) }
                }
                if let error = app.error { Text(error).foregroundStyle(ReSpaceStyle.danger) }
            }
            if let error = app.scanError {
                Section { Text(error).foregroundStyle(ReSpaceStyle.danger); Button("Try again") { Task { await refreshLibrary() } } }
            }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(ReSpaceStyle.white)
        .navigationTitle("Rooms")
        .toolbar { ToolbarItem(placement: .topBarTrailing) { Button { setup = true } label: { Image(systemName: "gearshape") }.accessibilityLabel("Settings") } }
        .safeAreaInset(edge: .bottom) {
            Button { scanSetup = true } label: { Label("Scan room", systemImage: "plus") }
                .buttonStyle(RSButtonStyle()).disabled(!simulatedScan && (!captureSupported || app.scanStore == nil || app.busy))
                .padding(20).background(ReSpaceStyle.white)
        }
    }
    private func refreshLibrary() async {
        if !app.isUIDemo { await app.refreshScans() }
        if app.designFeaturesEnabled { await app.recoverPending(); await app.refresh() }
    }
    private func scanTip(_ symbol: String, _ title: String, _ detail: String) -> some View {
        HStack(alignment: .top, spacing: 16) {
            Image(systemName: symbol).frame(width: 24).foregroundStyle(ReSpaceStyle.accent)
            VStack(alignment: .leading, spacing: 5) { Text(title).fontWeight(.medium); Text(detail).font(.subheadline).foregroundStyle(.secondary) }
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

private struct LocalScanThumbnail: View {
    let roomID: String
    let repository: CaptureRepository
    @State private var image: UIImage?
    var body: some View {
        Group {
            if let image { Image(uiImage:image).resizable().scaledToFill() }
            else { ReSpaceStyle.wash.overlay { Image(systemName:"cube.transparent").foregroundStyle(ReSpaceStyle.accent) } }
        }.accessibilityHidden(true)
        .task(id:roomID) {
            guard let bytes=try? await repository.thumbnailBytes(roomID) else { return }
            image=UIImage(data:bytes)
        }
    }
}

#if DEBUG
#Preview("My Rooms") { UIDemoPreview(.rooms) }
#endif
