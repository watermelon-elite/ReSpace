import SwiftUI

struct RoomReview: View {
    let app: AppModel
    let roomID: String
    @State private var detail: JSONValue = .null
    @State private var operation: JSONValue = .null
    @State private var conversation: [JSONValue] = []
    @State private var selected: String?
    @State private var text = ""
    @State private var rename = ""
    @State private var naming = false
    @State private var deleting = false
    @State private var error: String?
    @State private var intent = false
    @Environment(\.dismiss) private var dismiss
    var room: JSONValue { detail["room"] }
    var locked: Bool { room["current_operation_id"].string != nil || app.pending.contains { $0.roomID == roomID } }
    var body: some View {
        List {
            if let error { Text(error).foregroundStyle(.red) }
            if detail != .null {
                Section("Original measured room") {
                    if detail["raw_export"] != .null { RoomScene(document: detail["raw_export"], native: true, selectedID: $selected, ghosts: true, resetToken: 0).frame(height: 280).listRowInsets(EdgeInsets()) }
                    if !detail["capture_status"]["manifest"]["artifacts"].array.isEmpty {
                        ScrollView(.horizontal) { HStack { ForEach(detail["capture_status"]["manifest"]["artifacts"].array.filter { $0["kind"].text == "jpeg" }, id: \.self) { artifact in
                            PrivateCapturePhoto(app: app, path: "rooms/\(roomID)/artifacts/\(artifact["artifact_id"].text)").frame(width: 160, height: 120).clipped()
                        } } }
                    }
                    Text("Native RoomPlan measurements. Small-object detection has not run at this stage.").font(.caption).foregroundStyle(.secondary)
                    let capture = detail["capture_status"]
                    Text("Capture: \(capture["state"].text) · Expected \(capture["expected_artifacts"].int) · Stored \(capture["stored_artifacts"].int) · Missing \(capture["missing_artifacts"].int)").font(.caption)
                    if let design = room["active_design_id"].string { NavigationLink("Reopen design") { DesignView(app: app, roomID: roomID, designID: design) } }
                }
                Section("Objects") {
                    ForEach(detail["measured_context"]["objects"].array, id: \.self) { object in
                        let objectID = object["native_id"].string ?? object["id"].string ?? object["identifier"].text
                        VStack(alignment: .leading) {
                            Button { selected = objectID } label: { Label(object["category"].string ?? "Measured Object", systemImage: selected == objectID ? "checkmark.circle.fill" : "cube") }
                            Text(object["size"].numbers.map { String(format: "%.2f", $0) }.joined(separator: " × ") + " m").font(.caption)
                            Picker("Planning instruction", selection: Binding(get: { instruction(objectID) }, set: { value in Task { await command(value == "keep" ? "Keep this in place" : value == "remove" ? "Remove this from the design" : "Explicitly unlock this and let the design decide", target: objectID) } })) { Text("Keep").tag("keep"); Text("Decide").tag("decide"); Text("Remove").tag("remove") }.pickerStyle(.segmented).disabled(locked)
                        }
                    }
                }
                if operation != .null { Section { OperationPanel(app: app, operation: $operation, onUpdate: { await load() }) } }
                Section("Conversation · Room review") {
                    ForEach(conversation, id: \.self) { entry in VStack(alignment: .leading) { Text(entry["context"].text.capitalized).font(.caption).foregroundStyle(.secondary); Text(entry["text"].text) } }
                    if let selected { HStack { Text("Selected Object: \(selected)").font(.caption); Button("Clear") { self.selected = nil } } }
                    TextField("Ask about this room", text: $text, axis: .vertical)
                    Button("Send") { let message = text; Task { await command(message, target: selected) } }.disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || locked)
                }
                Button("Design this room") { intent = true }.disabled(locked || room["capture_state"].text != "complete")
            }
        }
        .navigationTitle(room["name"].string ?? "Room")
        .toolbar { Menu { Button("Rename") { rename = room["name"].text; naming = true }; Button("Delete Room", role: .destructive) { deleting = true } } label: { Image(systemName: "ellipsis.circle") } }
        .alert("Rename Room", isPresented: $naming) { TextField("Name", text: $rename); Button("Save") { Task { await renameRoom() } }; Button("Cancel", role: .cancel) {} }
        .confirmationDialog("Delete this scan, photos, designs and conversation?", isPresented: $deleting, titleVisibility: .visible) { Button("Delete Room", role: .destructive) { Task { await deleteRoom() } } }
        .sheet(isPresented: $intent) { IntentForm(app: app, detail: detail, onSubmit: { operation = $0; await load() }) }
        .refreshable { await load() }
        .task { text = UserDefaults.standard.string(forKey: "review_draft_\(roomID)") ?? ""; await load() }
        .onChange(of: text) { _, value in UserDefaults.standard.set(value, forKey: "review_draft_\(roomID)") }
        .task(id: operation["operation_id"].text) { await poll() }
    }
    func instruction(_ id: String) -> String { detail["planning"]["instructions"].array.first { $0["target"]["id"].text == id }?["instruction"].string ?? "decide" }
    func load() async {
        guard let client = app.client else { return }
        do {
            let next = try await client.request("rooms/\(roomID)"); _ = try RoomRecord(next["room"]); detail = next
            conversation = try await client.request("rooms/\(roomID)/conversation")["entries"].array
            if detail["current_operation"] != .null { operation = detail["current_operation"] }
            else if let id = room["current_operation_id"].string { operation = try await client.request("operations/\(id)")["operation"] }
            error = nil
        } catch { self.error = error.localizedDescription }
    }
    func poll() async {
        guard let client = app.client, let id = operation["operation_id"].string else { return }
        for _ in 0..<10 {
            guard !Task.isCancelled, !["succeeded", "failed", "cancelled", "rejected"].contains(operation["state"].text) else { await load(); return }
            do { try await Task.sleep(for: .seconds(2)); operation = try await client.request("operations/\(id)")["operation"] } catch { return }
        }
    }
    func command(_ message: String, target: String?) async {
        do {
            var body: [String: JSONValue] = ["text": .string(message), "capture_id": room["latest_capture_id"], "planning_revision": detail["planning"]["planning_revision"]]
            if let target { body["selected_object"] = .object(["kind": .string("native_object"), "id": .string(target), "capture_id": room["latest_capture_id"]]) }
            operation = try await app.submit(PendingRequest(path: "rooms/\(roomID)/planning-commands", roomID: roomID, body: body))["operation"]
            text = ""; await load()
        } catch { self.error = error.localizedDescription }
    }
    func renameRoom() async {
        do { _ = try await app.submit(PendingRequest(path: "rooms/\(roomID)", method: "PATCH", roomID: roomID, body: ["name": .string(rename), "expected_metadata_revision": room["metadata_revision"]])); await load() } catch { self.error = error.localizedDescription }
    }
    func deleteRoom() async {
        do {
            let result = try await app.submit(PendingRequest(path: "rooms/\(roomID)", method: "DELETE", roomID: roomID, body: [:]))
            if result["deletion"]["state"].text == "deleted" {
                for archive in CaptureArchive.recoverable() where archive.roomID == roomID { try FileManager.default.removeItem(at: archive.folder) }
                await app.refresh(); dismiss()
            } else { error = "Deletion pending. Refresh and retry until the backend confirms cleanup." }
        } catch { self.error = "Deletion pending: \(error.localizedDescription)" }
    }
}

struct IntentForm: View {
    let app: AppModel
    let detail: JSONValue
    let onSubmit: (JSONValue) async -> Void
    @State private var draft = IntentDraft()
    @State private var error: String?
    @State private var submitting = false
    @Environment(\.dismiss) private var dismiss
    private var key: String { "intent_\(detail["room"]["room_id"].text)" }
    var body: some View {
        NavigationStack { Form {
            Picker("Intent", selection: $draft.intent) { Text("Add a few things").tag("add"); Text("Full redesign").tag("redesign") }
            Section("Style") { ForEach(["match", "Cozy", "Minimal", "Japandi", "Industrial", "Boho", "Mid-century"], id: \.self) { style in Button { draft.toggleStyle(style) } label: { HStack { Text(style == "match" ? "Match what I have" : style); Spacer(); if draft.styles.contains(style) { Image(systemName: "checkmark") } } } } }
            Section("Required budget · USD") { TextField("Budget", text: $draft.budget).keyboardType(.decimalPad); Text("Purchase total excludes tax and shipping.").font(.caption) }
            Section("Anything else?") { TextField("Optional design priorities", text: $draft.text, axis: .vertical) }
            if let error { Text(error).foregroundStyle(.red) }
            Button("Start planning") { Task { await submit() } }.disabled(submitting || !IntentDraft.validBudget(draft.budget))
        }.navigationTitle("Design intent").toolbar { Button("Close") { dismiss() } } }
        .onAppear { if let data = UserDefaults.standard.data(forKey: key), let saved = try? JSONDecoder().decode(IntentDraft.self, from: data) { draft = saved } }
        .onChange(of: draft) { _, value in if let data = try? JSONEncoder().encode(value) { UserDefaults.standard.set(data, forKey: key) } }
    }
    func submit() async {
        submitting = true; defer { submitting = false }
        do {
            let room = detail["room"]
            let response = try await app.submit(PendingRequest(path: "rooms/\(room["room_id"].text)/designs", roomID: room["room_id"].text, body: ["capture_id": room["latest_capture_id"], "planning_revision": detail["planning"]["planning_revision"], "expected_active_design_id": room["active_design_id"], "expected_active_revision": room["active_revision"], "intent": .string(draft.intent), "styles": .array(draft.styles.map(JSONValue.string)), "budget": .string(draft.budget), "currency": .string("USD"), "text": .string(draft.text)]))
            await onSubmit(response["operation"]); dismiss()
        } catch { self.error = error.localizedDescription }
    }
}

struct OperationPanel: View {
    let app: AppModel
    @Binding var operation: JSONValue
    let onUpdate: () async -> Void
    @State private var choices: Set<String> = []
    @State private var text = ""
    @State private var number: Double?
    @State private var error: String?
    @State private var busy = false
    var question: JSONValue { operation["pending_question"] }
    var numeric: NumericQuestion { NumericQuestion(question) }
    var displayedNumber: Double { number ?? numeric.initialValue }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(operation["state"].text.replacingOccurrences(of: "_", with: " ").capitalized).font(.headline)
            Text(operation["phase"].text.replacingOccurrences(of: "_", with: " ")).font(.caption)
            if question != .null {
                Text(question["text"].text)
                ForEach(question["choices"].array, id: \.self) { choice in
                    Button {
                        let id = choice["choice_id"].text
                        if question["max_selections"].int <= 1 { choices = [id] }
                        else if choices.contains(id) { choices.remove(id) } else if choices.count < question["max_selections"].int { choices.insert(id) }
                    } label: { HStack { if let url = URL(string: choice["image_url"].text) { AsyncImage(url: url) { $0.resizable().scaledToFit() } placeholder: { ProgressView() }.frame(width: 72, height: 72) }; Text(choice["label"].text); Spacer(); if choices.contains(choice["choice_id"].text) { Image(systemName: "checkmark.circle.fill") } } }
                }
                if question["kind"].text == "numeric" {
                    Stepper("Answer: \(displayedNumber.formatted())",
                            onIncrement: numeric.next(displayedNumber, direction: 1).map { value in { number = value } },
                            onDecrement: numeric.next(displayedNumber, direction: -1).map { value in { number = value } })
                        .disabled(busy)
                }
                if question["kind"].text != "budget" { TextField("Optional details", text: $text) }
                if question["kind"].text == "budget" { Text("Current ceiling: USD \(question["budget_proposal"]["old_ceiling"].text) → Proposed: USD \(question["budget_proposal"]["new_ceiling"].text)"); Text("Resulting total: USD \(question["budget_proposal"]["resulting_total"].text)"); Button("Approve this budget increase") { Task { await answer("answer", approve: true) } }.disabled(busy) }
                else { Button("Answer") { Task { await answer("answer") } }.disabled(busy || !validAnswer) }
                HStack {
                    if question["allow_skip"].bool == true { Button("Skip") { Task { await answer("skip") } }.disabled(busy) }
                    if question["allow_delegate"].bool == true { Button("Decide for me") { Task { await answer("delegate") } }.disabled(busy) }
                    if question["context"].text == "command" { Button("Dismiss clarification") { Task { await control("dismiss-clarification", extra: ["question_id": question["question_id"], "dismissal_id": .string(UUID().uuidString)]) } }.disabled(busy) }
                }
            }
            if let failure = operation["failure"]["message"].string { Text(failure).foregroundStyle(.red) }
            if let error { Text(error).foregroundStyle(.red) }
            HStack { Button("Refresh") { Task { await refresh() } }; if !["succeeded", "failed", "cancelled", "rejected"].contains(operation["state"].text) { Button("Cancel", role: .destructive) { Task { await control("cancel", extra: ["cancellation_id": .string(UUID().uuidString)]) } }.disabled(busy) } }
        }
        .onChange(of: question["question_id"].text) { _, _ in choices = []; text = ""; number = nil }
    }
    var validAnswer: Bool {
        if question["kind"].text == "numeric" { return numeric.isValid(displayedNumber) }
        if question["kind"].text == "text" { return !text.isEmpty }
        return choices.count >= question["min_selections"].int && choices.count <= question["max_selections"].int
    }
    func refresh() async { guard let client = app.client else { return }; do { operation = try await client.request("operations/\(operation["operation_id"].text)")["operation"]; await onUpdate() } catch { self.error = error.localizedDescription } }
    func answer(_ action: String, approve: Bool = false) async {
        var body: [String: JSONValue] = ["question_id": question["question_id"], "reply_id": .string(UUID().uuidString), "expected_decision_revision": question["decision_revision"], "expected_question_revision": question["question_revision"], "choice_ids": .array(choices.sorted().map(JSONValue.string)), "text": .string(text), "action": .string(action)]
        if question["kind"].text == "numeric", action == "answer" { body["number"] = .number(displayedNumber) }
        if approve { body["budget_approval"] = .object(["old_ceiling": question["budget_proposal"]["old_ceiling"], "new_ceiling": question["budget_proposal"]["new_ceiling"], "resulting_total": question["budget_proposal"]["resulting_total"]]) }
        await control("answers", extra: body)
    }
    func control(_ action: String, extra: [String: JSONValue]) async {
        busy = true; defer { busy = false }
        do {
            var body = extra; body["operation_id"] = operation["operation_id"]
            let request = PendingRequest(path: "operations/\(operation["operation_id"].text)/\(action)", roomID: operation["room_id"].text, body: body)
            operation = try await app.submit(request)["operation"]; await onUpdate()
        } catch { self.error = error.localizedDescription }
    }
}

struct PrivateCapturePhoto: View {
    let app: AppModel
    let path: String
    @State private var image: UIImage?
    @State private var failed = false
    var body: some View {
        Group { if let image { Image(uiImage: image).resizable().scaledToFit() } else if failed { Label("Image unavailable", systemImage: "photo").font(.caption) } else { ProgressView() } }
            .task(id: path) { do { guard let client = app.client else { return }; let bytes = try await client.media(path); guard let decoded = UIImage(data: bytes) else { throw ContractError.invalid("Invalid image") }; image = decoded } catch { failed = true } }
    }
}
