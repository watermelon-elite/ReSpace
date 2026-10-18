import SwiftUI

struct IntentSheet: View {
    let store: WorkspaceStore
    let roomId: String
    let snapshotId: String
    @Environment(\.dismiss) private var dismiss
    private var workspace: RoomWorkspace { store.workspace(roomId) }

    var body: some View {
        @Bindable var workspace = workspace
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Text("Make room\nfor possibility.").font(.system(size: 35, weight: .regular, design: .serif))
                    VStack(spacing: 12) {
                        ForEach(DesignIntent.allCases, id: \.self) { intent in
                            Button { workspace.draft.intent.intent = intent } label: {
                                HStack(spacing: 14) {
                                    Image(systemName: intent == .add ? "sparkles" : "arrow.triangle.2.circlepath").font(.title2).frame(width: 30)
                                    VStack(alignment: .leading, spacing: 5) {
                                        Text(intent.title).font(.headline)
                                        Text(intent.subtitle).font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Image(systemName: workspace.draft.intent.intent == intent ? "checkmark.circle.fill" : "circle")
                                }.padding(18).background(ReSpaceTheme.surface, in: RoundedRectangle(cornerRadius: 18))
                                    .overlay(RoundedRectangle(cornerRadius: 18).stroke(workspace.draft.intent.intent == intent ? ReSpaceTheme.olive : .clear, lineWidth: 1.5))
                            }.buttonStyle(.plain)
                        }
                    }
                    VStack(alignment: .leading, spacing: 12) {
                        Text("The feeling").font(.headline)
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 145))], alignment: .leading, spacing: 10) {
                            ForEach(DesignStyle.allCases, id: \.self) { style in
                                Button { workspace.draft.intent.toggle(style) } label: {
                                    Text(style.title).font(.subheadline).frame(maxWidth: .infinity).padding(.vertical, 12)
                                        .foregroundStyle(workspace.draft.intent.styles.contains(style) ? .white : ReSpaceTheme.ink)
                                        .background(workspace.draft.intent.styles.contains(style) ? ReSpaceTheme.olive : ReSpaceTheme.surface, in: Capsule())
                                }.buttonStyle(.plain)
                            }
                        }
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Your budget").font(.headline)
                        HStack {
                            Text("USD").font(.subheadline.weight(.medium)).foregroundStyle(.secondary)
                            TextField("Enter an amount", text: $workspace.draft.intent.budgetText).keyboardType(.decimalPad)
                        }.padding(16).background(ReSpaceTheme.surface, in: RoundedRectangle(cornerRadius: 14))
                        if !workspace.draft.intent.budgetText.isEmpty && workspace.draft.intent.inputs == nil {
                            Text("Enter a positive USD amount with up to two decimal places.").font(.caption).foregroundStyle(.red)
                        }
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Or just tell us more").font(.headline)
                        TextField("A warm reading corner by the window…", text: $workspace.draft.intent.text, axis: .vertical)
                            .lineLimit(3...6).padding(16).background(ReSpaceTheme.surface, in: RoundedRectangle(cornerRadius: 14))
                    }
                    OperationStatusView(store: store, roomId: roomId)
                    PrimaryAction(title: workspace.isLocked ? "Request pending…" : "Create my design", symbol: "sparkles",
                                  disabled: workspace.draft.intent.inputs == nil || workspace.isLocked) {
                        Task { await store.generate(roomId, snapshotId: snapshotId) }
                    }
                    if workspace.isLocked {
                        Text("You can return to My Rooms while this request is processed.").font(.caption).foregroundStyle(.secondary)
                    }
                }.padding(24)
            }
            .background(ReSpaceTheme.cream)
            .navigationTitle("Your next design").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
            .onChange(of: workspace.draft.intent) { Task { await store.saveDraft(roomId) } }
        }
        .presentationDragIndicator(.visible)
    }
}
