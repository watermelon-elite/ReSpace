import SwiftUI

/// Temporary standalone RoomPlan testing. Does not create backend rooms or designs.
struct LocalRoomsView: View {
    let store: WorkspaceStore
    @State private var rooms: [LocalSavedRoom] = []
    @State private var recoveries: [CaptureManifest] = []
    @State private var scanning = false
    @State private var recoveryId: String?
    @State private var previewRoom: LocalSavedRoom?
    @State private var pendingPreviewId: String?
    @State private var renameRoom: LocalSavedRoom?
    @State private var renameText = ""
    @State private var deleteId: String?
    @State private var error: String?
    @State private var initialized = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Text("ReSpace").font(.system(.title2, design: .serif).weight(.semibold))
                    Text("My rooms").font(.system(size: 38, design: .serif)).padding(.top, 22)
                    StatusBanner(text: store.reconstruction == nil ? "Scans are saved on this iPhone. Configure your Mac service to improve a model." : "Scans are saved on this iPhone. Use Improve model to process a saved scan on your Mac.")
                    PrimaryAction(title: "New scan", symbol: "viewfinder") {
                        recoveryId = nil; scanning = true
                    }
                    if let error {
                        StatusBanner(text: error, isError: true)
                        Button("Retry") { Task { await reload() } }
                    }
                    ForEach(recoveries, id: \.captureId) { capture in
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Finish saving your scan").font(.headline)
                            Text("Your recorded room is retained on this phone.").font(.caption)
                            HStack {
                                Button("Retry save") { recoveryId = capture.captureId; scanning = true }
                                Spacer()
                                Button("Discard", role: .destructive) { deleteId = capture.captureId }
                            }
                        }.padding(18).background(ReSpaceTheme.surface, in: RoundedRectangle(cornerRadius: 20))
                    }
                    if rooms.isEmpty && recoveries.isEmpty {
                        ContentUnavailableView("Scan your first room", systemImage: "viewfinder",
                                               description: Text("Capture walls and furniture, then explore the room in 3D. No connection required."))
                    }
                    ForEach(rooms) { room in
                        Button {
                            previewRoom = room
                        } label: {
                            HStack(spacing: 16) {
                                Image(systemName: "cube.transparent").font(.largeTitle)
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(room.name).font(.system(.title3, design: .serif))
                                    Text("\(room.createdAt.scanDateLabel) · \(room.objectCount) items")
                                        .font(.caption).foregroundStyle(.secondary)
                                    Text("View 3D scan").font(.caption)
                                }
                                Spacer()
                                Image(systemName: "arrow.up.right")
                            }.padding(18).background(ReSpaceTheme.surface, in: RoundedRectangle(cornerRadius: 20))
                        }.buttonStyle(.plain)
                            .contextMenu {
                                Button("Rename", systemImage: "pencil") { renameRoom = room; renameText = room.name }
                                Button("Delete room", systemImage: "trash", role: .destructive) { deleteId = room.id }
                            }
                    }
                }.padding(24)
            }
            .background(ReSpaceTheme.cream)
            .toolbar(.hidden, for: .navigationBar)
            .refreshable { await reload() }
            .sheet(item: $previewRoom) { room in
                LocalRoomPreviewView(room: room, repository: store.captures, reconstruction: store.reconstruction)
            }
        }
        .task {
            if !initialized {
                do {
                    // Process death ends acquisition; completed captures remain retryable.
                    for manifest in try await store.captures.manifests()
                    where ["creating", "acquiring", "abandoned"].contains(manifest.state) {
                        try await store.captures.removeCapture(manifest.captureId)
                    }
                    initialized = true
                } catch { self.error = error.localizedDescription; return }
            }
            await reload()
        }
        .fullScreenCover(isPresented: $scanning, onDismiss: {
            Task {
                await reload()
                if let id = pendingPreviewId {
                    pendingPreviewId = nil
                    previewRoom = rooms.first { $0.id == id }
                }
            }
        }) {
            ScanCaptureScreen(store: store, recoveryId: recoveryId) { id in
                pendingPreviewId = id
                scanning = false
            }
        }
        .alert("Rename room", isPresented: Binding(get: { renameRoom != nil }, set: { if !$0 { renameRoom = nil } })) {
            TextField("Room name", text: $renameText)
            Button("Cancel", role: .cancel) { renameRoom = nil }
            Button("Save") {
                if let room = renameRoom {
                    let name = renameText
                    Task { await rename(room.id, name: name) }
                }
                renameRoom = nil
            }
        }
        .alert("Delete this local scan?", isPresented: Binding(get: { deleteId != nil }, set: { if !$0 { deleteId = nil } })) {
            Button("Cancel", role: .cancel) { deleteId = nil }
            Button("Delete", role: .destructive) {
                if let id = deleteId { Task { await remove(id) } }
                deleteId = nil
            }
        } message: { Text("This deletes the room model, photos, and depth saved on this iPhone.") }
    }

    private func reload() async {
        do {
            rooms = try await store.captures.localRooms()
            recoveries = try await store.captures.manifests().filter { $0.state == "completed" }
            error = nil
        } catch { self.error = error.localizedDescription }
    }
    private func rename(_ id: String, name: String) async {
        do { try await store.captures.renameLocalRoom(id, name: name); await reload() }
        catch { self.error = error.localizedDescription }
    }
    private func remove(_ id: String) async {
        do { try await store.captures.removeCapture(id); await reload() }
        catch { self.error = error.localizedDescription }
    }
}
