import SwiftUI

struct RoomReviewView: View {
    let store: WorkspaceStore
    let roomId: String
    @State private var selectedId: String?
    @State private var resetToken = 0
    @State private var showIntent = false
    @State private var pendingDetailsChoice = false
    @State private var showRescan = false
    @State private var showDesign = false
    @State private var continueSnapshotId: String?
    @Environment(\.dismiss) private var dismiss

    private var workspace: RoomWorkspace { store.workspace(roomId) }
    var body: some View {
        @Bindable var workspace = workspace
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if let record = workspace.record, let snapshot = record.snapshot {
                    HStack {
                        VStack(alignment: .leading, spacing: 5) {
                            Text("Here’s your room.").font(.system(.largeTitle, design: .serif))
                            Text("\(snapshot.floor.areaM2, specifier: "%.1f") m² · \(snapshot.objects.count) items").font(.subheadline).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button { resetToken += 1 } label: { Image(systemName: "viewfinder") }.accessibilityLabel("Reset view")
                    }
                    if snapshot.floor.polygon.count >= 3 {
                        RoomSceneView(snapshot: snapshot, items: snapshot.reviewItems(planning: record.planning), selectedId: $selectedId, resetToken: resetToken)
                            .frame(height: 340).clipShape(RoundedRectangle(cornerRadius: 24))
                    } else {
                        ContentUnavailableView("Room boundary unavailable", systemImage: "viewfinder", description: Text("Rescan to capture the room boundary."))
                    }
                    if let selected = snapshot.objects.first(where: { $0.id == selectedId }) {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text(selected.label).font(.headline); Spacer()
                                Button { selectedId = nil } label: { Image(systemName: "xmark.circle.fill") }.accessibilityLabel("Clear selection")
                            }
                            Text((record.planning.instructions[selected.id] ?? .decide).label).font(.caption).foregroundStyle(ReSpaceTheme.olive)
                            Text("Tell the assistant to keep, unlock, or remove this item for your next design.")
                                .font(.caption).foregroundStyle(.secondary)
                        }.padding(16).background(ReSpaceTheme.surface, in: RoundedRectangle(cornerRadius: 16))
                    }
                    if snapshot.processing.pending > 0 {
                        HStack {
                            ProgressView(); Text("More room details are processing.").font(.caption)
                            Spacer(); Button("Refresh") { Task { await refresh() } }
                        }
                    }
                    ForEach(snapshot.validity.warnings + record.summary.warnings, id: \.self) { StatusBanner(text: $0) }
                    if snapshot.processing.failed > 0 { StatusBanner(text: "Some small details could not be processed. Your measured room is preserved.") }
                    if !snapshot.validity.usable {
                        StatusBanner(text: snapshot.validity.reasons.joined(separator: "\n"), isError: true)
                        PrimaryAction(title: "Rescan", symbol: "viewfinder") { showRescan = true }
                    } else {
                        PrimaryAction(title: record.summary.activeDesignId == nil ? "What do you want to do?" : "Generate again",
                                      disabled: workspace.isLocked) {
                            continueSnapshotId = snapshot.id
                            if snapshot.processing.pending > 0 { pendingDetailsChoice = true } else { showIntent = true }
                        }
                    }
                    if workspace.design != nil {
                        NavigationLink(value: AppRoute.design(roomId)) {
                            Label("Reopen active design", systemImage: "square.stack.3d.up").font(.headline).frame(maxWidth: .infinity).padding(12)
                        }
                    }
                    Divider().padding(.vertical, 4)
                    Text("Plan your next design").font(.system(.title2, design: .serif))
                    Text("These instructions guide the next design. Your measured room stays saved.").font(.caption).foregroundStyle(.secondary)
                    ConversationView(entries: workspace.conversation, context: "review")
                    OperationStatusView(store: store, roomId: roomId)
                    CommandComposer(text: $workspace.draft.reviewText, selectedLabel: snapshot.objects.first { $0.id == selectedId }?.label,
                                    disabled: workspace.isLocked, placeholder: "Keep the sofa, remove the shelf…",
                                    clearSelection: { selectedId = nil }) {
                        Task { await store.command(roomId, designEditing: false, selectedId: selectedId) }
                    }
                } else if workspace.loading { ProgressView("Loading your room…").frame(maxWidth: .infinity).padding(60) }
                else {
                    ContentUnavailableView("Room unavailable", systemImage: "square.dashed", description: Text(workspace.error ?? "Refresh to retrieve this saved room."))
                    Button("Refresh") { Task { await refresh() } }
                }
            }.padding(20)
        }
        .background(ReSpaceTheme.cream)
        .navigationTitle(workspace.record?.summary.name ?? "Room review").navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .task {
            let pollingDeadline = ContinuousClock.now.advanced(by: .seconds(20))
            workspace.loading = true; await refresh(); workspace.loading = false
            while ContinuousClock.now < pollingDeadline {
                guard workspace.record?.snapshot?.processing.pending ?? 0 > 0 else { break }
                do { try await Task.sleep(for: .seconds(2)) } catch { return }
                guard ContinuousClock.now < pollingDeadline else { break }
                await refresh()
            }
        }
        .refreshable { await refresh() }
        .onChange(of: workspace.draft.reviewText) { Task { await store.saveDraft(roomId) } }
        .onChange(of: workspace.record?.snapshot?.id) {
            if let id = selectedId, let snapshot = workspace.record?.snapshot,
               !snapshot.objects.contains(where: { $0.id == id }) {
                selectedId = snapshot.objectAliases?[id].flatMap { alias in snapshot.objects.contains { $0.id == alias } ? alias : nil }
            }
        }
        .sheet(isPresented: $showIntent) {
            IntentSheet(store: store, roomId: roomId, snapshotId: continueSnapshotId ?? workspace.record?.snapshot?.id ?? "")
        }
        .navigationDestination(isPresented: $showDesign) { DesignScreen(store: store, roomId: roomId) }
        .onChange(of: workspace.design?.id) { old, new in
            if old != new, new != nil, workspace.operation?.kind == .generation {
                showIntent = false; showDesign = true
            }
        }
        .confirmationDialog("Room details are still processing", isPresented: $pendingDetailsChoice, titleVisibility: .visible) {
            Button("Wait for details") { Task { await refresh() } }
            Button("Continue with current room") { showIntent = true }
            Button("Cancel", role: .cancel) {}
        } message: { Text("Continuing freezes the selected snapshot. Later details can be used in a new design.") }
        .fullScreenCover(isPresented: $showRescan) {
            CaptureScreen(store: store, recoveryId: nil) { _ in showRescan = false; dismiss() }
        }
    }
    private func refresh() async {
        do {
            try await store.refreshRoom(roomId)
            if workspace.pending == nil, workspace.operation?.failure == nil { workspace.error = nil }
        }
        catch { workspace.error = error.localizedDescription }
    }
}
