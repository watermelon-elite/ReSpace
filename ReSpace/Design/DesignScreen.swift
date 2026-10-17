import SwiftUI

private enum SheetPosition: CaseIterable {
    case collapsed, medium, expanded
    func height(in available: CGFloat) -> CGFloat {
        switch self {
        case .collapsed: min(190, available * 0.4)
        case .medium: available * 0.5
        case .expanded: available * 0.85
        }
    }
}

struct DesignScreen: View {
    let store: WorkspaceStore
    let roomId: String
    @State private var selectedId: String?
    @State private var showGhosts = true
    @State private var resetToken = 0
    @State private var tab = "Assistant"
    @State private var sheetPosition = SheetPosition.medium
    @State private var dragOffset: CGFloat = 0
    private var workspace: RoomWorkspace { store.workspace(roomId) }

    var body: some View {
        @Bindable var workspace = workspace
        GeometryReader { geometry in
            ZStack(alignment: .bottom) {
                if let design = workspace.design, let snapshot = workspace.designSnapshot {
                    RoomSceneView(snapshot: snapshot, items: design.items, selectedId: $selectedId,
                                  showGhosts: showGhosts, resetToken: resetToken)
                        .padding(.bottom, 130)
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(spacing: 10) {
                            Button { Task { await store.undo(roomId) } } label: { Label("Undo", systemImage: "arrow.uturn.backward") }
                                .disabled(workspace.isLocked || design.parentId == nil)
                            Spacer()
                            Button { resetToken += 1 } label: { Image(systemName: "viewfinder") }.accessibilityLabel("Reset view")
                            Button { showGhosts.toggle() } label: { Image(systemName: showGhosts ? "eye" : "eye.slash") }.accessibilityLabel(showGhosts ? "Hide removed furniture" : "Show removed furniture")
                        }.buttonStyle(.bordered).background(.regularMaterial, in: Capsule())
                        if let status = workspace.processingText {
                            Text(status).font(.caption.weight(.medium)).padding(10).background(.regularMaterial, in: Capsule())
                        }
                        if let error = workspace.error {
                            Text(error).font(.caption).foregroundStyle(.red).lineLimit(3)
                                .padding(10).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
                        }
                        Spacer()
                    }.padding(14)
                    productSheet(design: design, available: geometry.size.height)
                } else {
                    ContentUnavailableView("No active design", systemImage: "square.stack.3d.up", description: Text(workspace.error ?? "Return to room review to create your design."))
                }
            }
        }
        .background(ReSpaceTheme.cream)
        .navigationTitle(workspace.record?.summary.name ?? "Your design")
        .navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
        .task { do { try await store.refreshRoom(roomId) } catch { workspace.error = error.localizedDescription } }
        .onChange(of: selectedId) { _, id in
            if id != nil { tab = "Items"; if sheetPosition == .collapsed { sheetPosition = .medium } }
        }
        .onChange(of: workspace.design?.id) {
            if let id = selectedId, workspace.design?.items.contains(where: { $0.id == id && $0.isVisible && !$0.isGhost }) != true { selectedId = nil }
        }
        .onChange(of: showGhosts) { if !showGhosts, workspace.design?.items.first(where: { $0.id == selectedId })?.isGhost == true { selectedId = nil } }
        .onChange(of: workspace.draft.designText) { Task { await store.saveDraft(roomId) } }
    }

    private func productSheet(design: DesignVersion, available: CGFloat) -> some View {
        @Bindable var workspace = workspace
        return VStack(spacing: 10) {
            Capsule().fill(.secondary.opacity(0.35)).frame(width: 38, height: 5).frame(maxWidth: .infinity).padding(.top, 10)
                .contentShape(Rectangle())
                .gesture(DragGesture().onChanged { dragOffset = $0.translation.height }.onEnded { value in
                    let projected = sheetPosition.height(in: available) - value.predictedEndTranslation.height
                    sheetPosition = SheetPosition.allCases.min { abs($0.height(in: available) - projected) < abs($1.height(in: available) - projected) } ?? .medium
                    dragOffset = 0
                })
                .accessibilityLabel("Sheet height")
                .accessibilityAdjustableAction { direction in
                    if direction == .increment { sheetPosition = sheetPosition == .collapsed ? .medium : .expanded }
                    else { sheetPosition = sheetPosition == .expanded ? .medium : .collapsed }
                }
            Picker("Panel", selection: $tab) { Text("Assistant").tag("Assistant"); Text("Items").tag("Items") }.pickerStyle(.segmented)
            if sheetPosition != .collapsed {
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 14) {
                            if tab == "Assistant" {
                                Text(design.summary).font(.system(.title3, design: .serif))
                                ConversationView(entries: workspace.conversation)
                            } else {
                                HStack {
                                    Text("In your design").font(.system(.title3, design: .serif)); Spacer()
                                    if let monetary = design.monetary, monetary.designId == design.id {
                                        VStack(alignment: .trailing) {
                                            Text(monetary.text).font(.subheadline.weight(.medium))
                                            if monetary.isDemo { Text("Demo total").font(.caption2).foregroundStyle(.secondary) }
                                        }
                                    } else { Text("Total unavailable").font(.caption).foregroundStyle(.secondary) }
                                }
                                ForEach(design.items.filter(\.isVisible)) { item in
                                    ItemPresentationCard(item: item, selected: item.id == selectedId) { selectedId = item.id }.id(item.id)
                                }
                                ForEach(design.warnings, id: \.self) { StatusBanner(text: $0) }
                            }
                            OperationStatusView(store: store, roomId: roomId)
                        }.padding(.vertical, 8)
                    }
                    .onChange(of: selectedId) { _, id in if let id { proxy.scrollTo(id, anchor: .center) } }
                    .onChange(of: tab) { if tab == "Items", let id = selectedId { proxy.scrollTo(id, anchor: .center) } }
                }
            } else if let status = workspace.processingText { Text(status).font(.caption).frame(maxWidth: .infinity, alignment: .leading) }
            CommandComposer(text: $workspace.draft.designText, selectedLabel: design.items.first { $0.id == selectedId }?.label,
                            disabled: workspace.isLocked, clearSelection: { selectedId = nil }) {
                Task { await store.command(roomId, designEditing: true, selectedId: selectedId) }
            }
        }
        .padding(.horizontal, 16).padding(.bottom, 10)
        .frame(height: max(155, min(available * 0.92, sheetPosition.height(in: available) - dragOffset)))
        .frame(maxWidth: .infinity)
        .background(ReSpaceTheme.cream, in: UnevenRoundedRectangle(topLeadingRadius: 26, topTrailingRadius: 26))
        .shadow(color: .black.opacity(0.07), radius: 20, y: -5)
    }
}
