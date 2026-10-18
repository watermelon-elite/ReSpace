import SwiftUI

enum AppRoute: Hashable { case room(String), design(String) }
private struct ScanRoute: Identifiable {
    let id = UUID()
    var recoveryId: String?
}

struct MyRoomsView: View {
    let store: WorkspaceStore
    @State private var path: [AppRoute] = []
    @State private var scanRoute: ScanRoute?
    @State private var renameRoom: RoomSummary?
    @State private var renameText = ""
    @State private var deleteRoom: RoomSummary?
    @State private var recoveries: [CaptureManifest] = []
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    header
                    PrimaryAction(title: "New scan", symbol: "viewfinder") { scanRoute = ScanRoute() }
                    if let error = store.listError {
                        StatusBanner(text: error, isError: true)
                        Button("Retry connection") { Task { await store.bootstrap(); await reloadRecoveries() } }
                    }
                    pendingDeletionRows
                    ForEach(recoveries, id: \.captureId) { capture in
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Finished scan needs upload recovery", systemImage: "icloud.and.arrow.up")
                                .font(.headline)
                            Text("Your recorded room is retained on this phone.").font(.caption).foregroundStyle(.secondary)
                            HStack {
                                Button("Retry upload") { scanRoute = ScanRoute(recoveryId: capture.captureId) }
                                Spacer()
                                Button("Discard", role: .destructive) {
                                    deleteRoom = RoomSummary(id: capture.roomId, name: "Recovered scan", metadataRevision: 0,
                                                             createdAt: "", captureState: "completed", activeRevision: 0, warnings: [])
                                }
                            }
                        }.padding(18).background(ReSpaceTheme.surface, in: RoundedRectangle(cornerRadius: 20))
                    }
                    if store.rooms.isEmpty && !store.loading && recoveries.isEmpty {
                        VStack(alignment: .leading, spacing: 14) {
                            Image(systemName: "square.dashed.inset.filled").font(.system(size: 42, weight: .ultraLight))
                            Text("Your next chapter\nstarts in this room.").font(.system(.title, design: .serif))
                            Text("Scan the space you have. Explore what it could become.")
                                .font(.subheadline).foregroundStyle(.secondary)
                        }.padding(.vertical, 48)
                    }
                    ForEach(store.rooms.filter { !store.deletionIds.contains($0.id) }) { room in
                        NavigationLink(value: AppRoute.room(room.id)) { roomCard(room) }
                            .buttonStyle(.plain)
                            .contextMenu {
                                Button("Rename", systemImage: "pencil") { renameRoom = room; renameText = room.name }
                                Button("Delete room", systemImage: "trash", role: .destructive) { deleteRoom = room }
                            }
                    }
                    if store.loading { ProgressView().frame(maxWidth: .infinity) }
                }.padding(24)
            }
            .background(ReSpaceTheme.cream)
            .navigationBarHidden(true)
            .refreshable { await store.refreshRooms(); await reloadRecoveries() }
            .navigationDestination(for: AppRoute.self) { route in
                switch route {
                case .room(let id): RoomReviewView(store: store, roomId: id)
                case .design(let id): DesignScreen(store: store, roomId: id)
                }
            }
        }
        .task { await store.bootstrap(); await reloadRecoveries() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await store.bootstrap(); await reloadRecoveries() } }
        }
        .fullScreenCover(item: $scanRoute, onDismiss: { Task { await reloadRecoveries() } }) { route in
            ScanCaptureScreen(store: store, recoveryId: route.recoveryId) { roomId in
                scanRoute = nil
                if let roomId { path.append(.room(roomId)) }
            }
        }
        .alert("Rename room", isPresented: Binding(get: { renameRoom != nil }, set: { if !$0 { renameRoom = nil } })) {
            TextField("Room name", text: $renameText)
            Button("Cancel", role: .cancel) { renameRoom = nil }
            Button("Save") { if let room = renameRoom { Task { await store.rename(room.id, name: renameText) } }; renameRoom = nil }
        }
        .alert("Delete this room?", isPresented: Binding(get: { deleteRoom != nil }, set: { if !$0 { deleteRoom = nil } })) {
            Button("Cancel", role: .cancel) { deleteRoom = nil }
            Button("Delete room", role: .destructive) {
                if let room = deleteRoom { Task { await store.deleteRoom(room.id); await reloadRecoveries() } }; deleteRoom = nil
            }
        } message: { Text("This permanently deletes its scan, raw photos and depth, designs, and conversation.") }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack { Text("ReSpace").font(.system(.title2, design: .serif).weight(.semibold)); Spacer(); Image(systemName: "square.stack.3d.up").foregroundStyle(ReSpaceTheme.olive) }
            Text("My rooms").font(.system(size: 38, weight: .regular, design: .serif)).padding(.top, 22)
            Text("A little possibility in every space.").foregroundStyle(.secondary).font(.subheadline)
        }
    }
    private var pendingDeletionRows: some View {
        ForEach(store.workspaces.keys.sorted(), id: \.self) { id in
            if let workspace = store.workspaces[id], workspace.deleting {
                VStack(alignment: .leading, spacing: 8) {
                    StatusBanner(text: workspace.error ?? "Deleting room…", isError: workspace.error != nil)
                    Button("Retry deletion") { Task { await store.deleteRoom(id); await reloadRecoveries() } }
                }
            }
        }
    }
    private func roomCard(_ room: RoomSummary) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            AsyncImage(url: room.thumbnailUrl) { phase in
                if let image = phase.image { image.resizable().scaledToFill() }
                else {
                    ZStack { ReSpaceTheme.olive.opacity(0.1); Image(systemName: "sofa").font(.system(size: 52, weight: .ultraLight)).foregroundStyle(ReSpaceTheme.olive) }
                }
            }.frame(height: 185).clipped()
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(room.name).font(.system(.title3, design: .serif))
                    Text((room.scannedAt ?? room.createdAt).scanDateLabel).font(.caption).foregroundStyle(.secondary)
                    if let status = store.workspaces[room.id]?.processingText {
                        Text(status).font(.caption).foregroundStyle(ReSpaceTheme.olive)
                    } else if room.currentOperationState.map({ !$0.isTerminal }) == true {
                        Text("Generating or updating…").font(.caption).foregroundStyle(ReSpaceTheme.olive)
                    }
                }
                Spacer(); Image(systemName: "arrow.up.right").padding(.top, 3)
            }.padding(18)
        }.background(ReSpaceTheme.surface, in: RoundedRectangle(cornerRadius: 22)).clipShape(RoundedRectangle(cornerRadius: 22))
    }
    private func reloadRecoveries() async {
        do {
            recoveries = try await store.captures.manifests().filter {
                ($0.state == "completed" || ($0.state == "finalized" && !$0.canEvictRawFiles)) && !store.deletionIds.contains($0.roomId)
            }
        } catch { store.listError = error.localizedDescription }
    }
}
