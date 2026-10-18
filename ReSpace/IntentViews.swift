import SwiftUI

struct RoomRequestBar: View {
    let app: AppModel
    @Binding var text: String
    @Binding var operation: JSONValue
    var selection: String?
    var selectedObjectID: String?
    var clear: () -> Void = {}
    let prepareRoom: () async throws -> JSONValue
    let onUpdate: () async -> Void
    let onDetails: () -> Void
    @State private var submitting = false
    @State private var error: String?
    @State private var typing = false
    private var question: JSONValue { operation["pending_question"] }
    private var active: Bool { ["queued", "running", "needs_clarification"].contains(operation["state"].text) }
    private var canReply: Bool { ["text", "single_choice", "multi_choice"].contains(question["kind"].text) }
    private var statusText: String {
        if active { return operation["progress_message"].string ?? operation["phase"].text.replacingOccurrences(of: "_", with: " ").capitalized }
        if let failure = operation["failure"]["message"].string { return failure }
        return operation["outcome"]["result_kind"].text == "selection" ? "View your product plan" : "View your design"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let error { Text(error).font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.danger) }
            OlloMessage(cue: typing ? .listening : .operation(operation), compact: typing) {
                if question != .null || active || operation["outcome"] != .null || operation["failure"] != .null {
                    Button(action: onDetails) {
                        HStack(spacing: 10) {
                            if active && question == .null { ProgressView() }
                            Text(question == .null ? statusText : question["text"].text)
                                .font(ReSpaceStyle.font(14)).fixedSize(horizontal: false, vertical: true)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Image(systemName: "chevron.right").font(.caption)
                        }.padding(14).background(.white, in: RoundedRectangle(cornerRadius: 20))
                    }.buttonStyle(.plain)
                } else {
                    Text("What would you like to change?").font(ReSpaceStyle.font(14))
                        .padding(14).background(.white, in: RoundedRectangle(cornerRadius: 20))
                }
            }
            RSComposer(text: $text, placeholder: question == .null ? "Describe your new design…" : "Your answer…", selection: selection, clear: clear,
                       disabled: submitting || (active && !canReply), onFocusChange: { typing = $0 }) {
                Task { await submit() }
            }
        }.padding(.horizontal, 16).padding(.top, 10).padding(.bottom, 12)
    }

    private func submit() async {
        submitting = true; error = nil
        defer { submitting = false }
        do {
            let detail = try await prepareRoom()
            let room = detail["room"]
            let roomID = room["room_id"].text
            if let pending = app.pending.first(where: { $0.roomID == roomID }) {
                operation = try await app.reconcile(pending)["operation"]
                await onUpdate()
                return
            }
            let request: PendingRequest
            if question != .null {
                request = PendingRequest(path: "operations/\(operation["operation_id"].text)/answers", roomID: roomID, body: [
                    "operation_id": operation["operation_id"], "question_id": question["question_id"], "reply_id": .string(UUID().uuidString),
                    "expected_decision_revision": operation["decision_revision"], "expected_question_revision": question["question_revision"],
                    "text": .string(text), "action": .string("answer")])
            } else {
                var body: [String: JSONValue] = ["capture_id": room["latest_capture_id"], "planning_revision": detail["planning"]["planning_revision"],
                    "expected_active_design_id": room["active_design_id"], "expected_active_revision": room["active_revision"],
                    "intent": .string("auto"), "currency": .string("USD"), "text": .string(text)]
                if let selectedObjectID { body["selected_object_id"] = .string(selectedObjectID) }
                request = PendingRequest(path: "rooms/\(roomID)/designs", roomID: roomID, body: body)
            }
            operation = try await app.submit(request)["operation"]
            text = ""
            await onUpdate()
        } catch { self.error = error.localizedDescription }
    }
}
