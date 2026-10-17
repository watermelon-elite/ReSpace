import SwiftUI

struct ConversationView: View {
    let entries: [ConversationEntry]
    var context: String?
    var body: some View {
        LazyVStack(alignment: .leading, spacing: 14) {
            if entries.filter({ context == nil || $0.context == context }).isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Image(systemName: "sparkles").foregroundStyle(ReSpaceTheme.olive)
                    Text(context == "review" ? "What should stay? What could change?" : "Tell me what you’d like to change.")
                        .font(.system(.title3, design: .serif))
                    Text("Type a request below. Select an item to give your message context.").font(.caption).foregroundStyle(.secondary)
                }.padding(.vertical, 12)
            }
            ForEach(entries.filter { context == nil || $0.context == context }) { entry in
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text(entry.role == "user" ? "You" : "ReSpace").fontWeight(.semibold)
                        Text(entry.context == "review" ? "Room review" : "Design editing").foregroundStyle(.secondary)
                        if entry.role == "undo" { Text("Undo").foregroundStyle(ReSpaceTheme.olive) }
                    }.font(.caption2)
                    Text(entry.text).font(.subheadline).textSelection(.enabled)
                    if let version = entry.resultingVersionId { Text("Saved version · \(version)").font(.caption2).foregroundStyle(.secondary) }
                }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
                    .background(entry.role == "user" ? ReSpaceTheme.olive.opacity(0.07) : ReSpaceTheme.surface, in: RoundedRectangle(cornerRadius: 16))
                    .id(entry.id)
            }
        }
    }
}

struct CommandComposer: View {
    @Binding var text: String
    var selectedLabel: String?
    var disabled: Bool
    var placeholder = "Make it warmer, move this…"
    var clearSelection: () -> Void
    var send: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let selectedLabel {
                HStack(spacing: 6) {
                    Image(systemName: "scope"); Text(selectedLabel).lineLimit(1)
                    Button(action: clearSelection) { Image(systemName: "xmark.circle.fill") }.accessibilityLabel("Clear selected item")
                }.font(.caption).padding(.horizontal, 10).padding(.vertical, 6).background(ReSpaceTheme.olive.opacity(0.1), in: Capsule())
            }
            HStack(alignment: .bottom, spacing: 10) {
                TextField(placeholder, text: $text, axis: .vertical).lineLimit(1...4).padding(.vertical, 8)
                    .submitLabel(.send)
                Button(action: send) {
                    Image(systemName: "arrow.up").font(.headline).foregroundStyle(.white).frame(width: 38, height: 38)
                        .background(disabled || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? .gray : ReSpaceTheme.olive, in: Circle())
                }.disabled(disabled || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty).accessibilityLabel("Send instruction")
            }.padding(10).background(ReSpaceTheme.surface, in: RoundedRectangle(cornerRadius: 20))
        }
    }
}

struct OperationStatusView: View {
    let store: WorkspaceStore
    let roomId: String
    @State private var reply = ""
    private var workspace: RoomWorkspace { store.workspace(roomId) }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let status = workspace.processingText {
                HStack { if workspace.operation?.state != .needsClarification { ProgressView() }; Text(status).font(.subheadline.weight(.medium)) }
                if workspace.pending?.kind == .generation || workspace.operation?.kind == .generation,
                   let story = workspace.record?.snapshot?.story, !story.isEmpty {
                    TimelineView(.periodic(from: .now, by: 4)) { context in
                        let index = Int(context.date.timeIntervalSince1970 / 4) % story.count
                        Text(story[index]).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            if let question = workspace.operation?.clarification, workspace.operation?.state == .needsClarification {
                VStack(alignment: .leading, spacing: 12) {
                    Text(question.text).font(.headline)
                    ForEach(question.candidates) { candidate in
                        Button(candidate.label) { Task { await store.answer(roomId, text: candidate.id) } }
                    }
                    TextField("Your answer", text: $reply, axis: .vertical).textFieldStyle(.roundedBorder)
                    HStack {
                        Button("Send answer") { let answer = reply; Task { await store.answer(roomId, text: answer); reply = "" } }
                            .disabled(reply.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        Spacer()
                        Button("Dismiss") { Task { await store.answer(roomId, text: nil, dismiss: true) } }
                    }
                }.padding(14).background(ReSpaceTheme.olive.opacity(0.08), in: RoundedRectangle(cornerRadius: 16))
                    .disabled(workspace.answerSubmitting || workspace.pending?.continuation != nil)
            }
            if let message = workspace.message { StatusBanner(text: message) }
            if let error = workspace.error {
                StatusBanner(text: error, isError: true)
                if workspace.pending != nil || (workspace.operation.map { !$0.state.isTerminal } == true) {
                    Button("Reconcile and retry") { store.retry(roomId) }
                }
            }
        }
    }
}
