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
    @State private var error: String?
    @State private var showOperation = false
    @State private var page = "review"
    @State private var chosenInstruction = "decide"
    @State private var photo = 0
    @State private var saving = false
    @State private var designText = ""
    @State private var reset = 0
    @Environment(\.dismiss) private var dismiss
    var room: JSONValue { detail["room"] }
    var testNotice: JSONValue? { room["warnings"].array.first { ["offline_test", "local_test"].contains($0["code"].text) } }
    var locked: Bool { room["current_operation_id"].string != nil || app.pending.contains { $0.roomID == roomID } }
    private var objects: [JSONValue] { detail["measured_context"]["objects"].array }
    private var photos: [JSONValue] { detail["capture_status"]["manifest"]["artifacts"].array.filter { $0["kind"].text == "jpeg" } }
    private var selectedObject: JSONValue { objects.first { objectID($0) == selected } ?? .null }
    private var objectName: String { selectedObject["category"].string?.capitalized ?? "Object" }
    private var title: String {
        switch page {
        case "objects": return "What can change?"
        case "object": return "Your \(objectName.lowercased())"
        case "unlock": return "Unlock the \(objectName.lowercased())?"
        case "photos": return "Your scan photos"
        case "chat": return "What should we know?"
        case "rename": return "Name your room"
        case "delete": return "Delete this room?"
        case "deletion": return "Deletion pending"
        default: return room["name"].string ?? "Your room"
        }
    }
    var body: some View {
        Group {
            if page == "review" {
                VStack(spacing: 0) {
                    RSTopBar(title: room["name"].text, back: { dismiss() }, trailing: { page = "options" })
                    HStack {
                        Button { page = "objects" } label: {
                            Label("Objects", systemImage: "square.stack.3d.up")
                                .font(ReSpaceStyle.font(13, weight: .medium)).padding(.horizontal, 14).frame(height: 44)
                                .background(.white, in: Capsule())
                        }.buttonStyle(.plain)
                        Spacer()
                        if let designID = room["active_design_id"].string {
                            NavigationLink { DesignView(app: app, roomID: roomID, designID: designID) } label: {
                                Text("Saved design").font(ReSpaceStyle.font(13, weight: .medium))
                            }
                        }
                        RSIconButton(symbol: "viewfinder", label: "Reset View") { reset += 1 }
                    }.padding(.horizontal, 16).padding(.bottom, 8)
                    if detail == .null { ProgressView("Opening your room…").frame(maxWidth: .infinity, maxHeight: .infinity) }
                    else {
                        RoomScene(document: detail["raw_export"], native: true, selectedID: $selected, ghosts: true, resetToken: reset)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .ignoresSafeArea(.container, edges: .bottom)
                    }
                }
                .overlay(alignment: .bottom) {
                    RoomRequestBar(app: app, text: $designText, operation: $operation, selection: selected.map { _ in objectName },
                        selectedObjectID: selected, clear: { selected = nil }, prepareRoom: {
                            guard let client = app.client else { throw ContractError.invalid("Configure the backend before continuing.") }
                            return try await client.request("rooms/\(roomID)")
                        }, onUpdate: { await load() }, onDetails: { showOperation = true })
                }
                .background(ReSpaceStyle.canvas)
                .toolbar(.hidden, for: .navigationBar).navigationBarBackButtonHidden()
            } else {
                RSPage(title: title, topTitle: page == "chat" ? "Room instructions" : "", question: page == "unlock" || page == "delete", back: { goBack() }) {
                    if let error { RSNotice(message: error, isError: true) }
                    pageContent
                } footer: { pageFooter }
            }
        }
        .fullScreenCover(isPresented: $showOperation) {
            NavigationStack {
                OperationPanel(app: app, operation: $operation, roomDocument: detail["raw_export"], onUpdate: { await load() })
            }
        }
        .task {
            if !app.isUIDemo { text = UserDefaults.standard.string(forKey: "review_draft_\(roomID)") ?? "" }
            await load()
            if !app.isUIDemo { designText = UserDefaults.standard.string(forKey: "design_draft_\(roomID)") ?? "" }
        }
        .onChange(of: designText) { _, value in if !app.isUIDemo { UserDefaults.standard.set(value, forKey: "design_draft_\(roomID)") } }
        .onChange(of: text) { _, value in if !app.isUIDemo { UserDefaults.standard.set(value, forKey: "review_draft_\(roomID)") } }
        .task(id: [operation["operation_id"].text, operation["state"].text]) { await poll() }
    }
    @ViewBuilder private var pageContent: some View {
        switch page {
        case "objects":
            if objects.isEmpty { Text("No measured Objects are available in this scan.").foregroundStyle(ReSpaceStyle.secondary) }
            VStack(spacing: 0) {
                ForEach(objects, id: \.self) { object in
                    Button {
                        selected = objectID(object); chosenInstruction = instruction(objectID(object)); page = "object"
                    } label: { RSRow(title: object["category"].string?.capitalized ?? "Measured Object", subtitle: instructionLabel(instruction(objectID(object))), symbol: "cube") }.buttonStyle(.plain)
                }
            }
        case "object":
            measuredRoom.frame(maxHeight: 220)
            Text(selectedObject["size"].numbers.map { String(format: "%.2f", $0) }.joined(separator: " × ") + " m")
                .font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
            VStack(spacing: 16) {
                RSChoice(title: "Keep in place", subtitle: "Keep its position and presence.", symbol: "lock", selected: chosenInstruction == "keep") { chosenInstruction = "keep" }
                RSChoice(title: "Let the design decide", selected: chosenInstruction == "decide") { chosenInstruction = "decide" }
                RSChoice(title: "Remove from design", selected: chosenInstruction == "remove") { chosenInstruction = "remove" }
            }.disabled(locked || saving)
        case "unlock":
            RSSymbol(name: "lock")
            Text("You asked to keep it in place. Allow this design to change it?").foregroundStyle(ReSpaceStyle.secondary)
            Text("Permanent fixtures will still stay fixed.").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
        case "photos":
            if photos.indices.contains(photo) {
                PrivateCapturePhoto(app: app, path: "rooms/\(roomID)/artifacts/\(photos[photo]["artifact_id"].text)", fill: true)
                    .frame(height: 380).clipShape(RoundedRectangle(cornerRadius: 28))
                Text("Photo \(photo + 1) of \(photos.count)").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
            } else { Text("No scan photos are available.").foregroundStyle(ReSpaceStyle.secondary) }
        case "chat":
            Text("Tell us what to keep, remove or make room for.")
            ForEach(conversation, id: \.self) { RSMessage(entry: $0) }
            Text("Instructions apply to your next design.").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
            if locked { Button("View current request") { showOperation = true }.buttonStyle(RSButtonStyle(kind: .secondary)) }
        case "options":
            if let testNotice { RSNotice(message: testNotice["message"].text) }
            VStack(spacing: 0) {
                Button { photo = 0; page = "photos" } label: { RSRow(title: "Scan photos", symbol: "photo.on.rectangle") }
                Button { page = "chat" } label: { RSRow(title: "Room instructions", symbol: "bubble.left") }
                Button { rename = room["name"].text; page = "rename" } label: { RSRow(title: "Rename room", symbol: "pencil") }
                Button { page = "delete" } label: { RSRow(title: "Delete room", symbol: "trash") }
            }.buttonStyle(.plain)
        case "rename":
            VStack(alignment: .leading, spacing: 12) {
                Text("Room name").font(ReSpaceStyle.font(14, weight: .medium))
                TextField("Room name", text: $rename).rsInput()
            }
        case "delete":
            RSSymbol(name: "trash")
            Text("\(room["name"].text) and its scan, photos, designs and conversation will be removed.").foregroundStyle(ReSpaceStyle.secondary)
        case "deletion":
            RSSymbol(name: "arrow.clockwise")
            Text("We couldn’t confirm deletion of \(room["name"].text).")
            Text("Your other rooms are ready to use.").font(ReSpaceStyle.font(14)).foregroundStyle(ReSpaceStyle.secondary)
        default: EmptyView()
        }
    }
    @ViewBuilder private var pageFooter: some View {
        switch page {
        case "objects": Button("Done") { page = "review" }.buttonStyle(RSButtonStyle())
        case "object":
            Button(saving ? "Saving…" : "Save instruction") {
                if let selected, instruction(selected) == "keep", chosenInstruction == "decide" { page = "unlock" }
                else { Task { await saveInstruction() } }
            }.buttonStyle(RSButtonStyle()).disabled(locked || saving)
        case "unlock":
            Button("Unlock and continue") { Task { await saveInstruction() } }.buttonStyle(RSButtonStyle()).disabled(locked || saving)
            Button("Keep protected") { chosenInstruction = "keep"; page = "object" }.buttonStyle(RSButtonStyle(kind: .secondary))
        case "photos":
            HStack(spacing: 8) {
                Button("Previous") { photo -= 1 }.disabled(photo == 0).buttonStyle(RSButtonStyle(kind: .secondary))
                Button("Next") { photo += 1 }.disabled(photo + 1 >= photos.count).buttonStyle(RSButtonStyle(kind: .secondary))
                Button("Done") { page = "review" }.buttonStyle(RSButtonStyle(kind: .secondary))
            }
        case "chat":
            RSComposer(text: $text, placeholder: "Tell us what to keep…", selection: selected.map { _ in objectName }, clear: { selected = nil }, disabled: locked) {
                let message = text; Task { await command(message, target: selected); if operation["pending_question"] != .null { showOperation = true } }
            }
        case "rename":
            Button(saving ? "Saving…" : "Save name") {
                Task { saving = true; await renameRoom(); saving = false; if error == nil { page = "review" } }
            }.buttonStyle(RSButtonStyle()).disabled(saving || rename.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            Button("Cancel") { page = "options" }.buttonStyle(RSButtonStyle(kind: .quiet))
        case "delete", "deletion":
            Button(saving ? "Deleting…" : page == "deletion" ? "Retry deletion" : "Delete room") {
                Task { saving = true; await deleteRoom(); saving = false; if error != nil { page = "deletion" } }
            }.buttonStyle(RSButtonStyle(kind: page == "deletion" ? .primary : .danger)).disabled(saving)
            Button(page == "deletion" ? "Other rooms" : "Keep room") { if page == "deletion" { dismiss() } else { page = "review" } }.buttonStyle(RSButtonStyle(kind: .secondary))
        default: EmptyView()
        }
    }
    private var measuredRoom: some View {
        Group {
            if detail["raw_export"] != .null {
                RoomScene(document: detail["raw_export"], native: true, selectedID: $selected, ghosts: true, resetToken: 0)
            } else { ReSpaceStyle.canvas.overlay { Image(systemName: "cube.transparent").font(.system(size: 48, weight: .ultraLight)).foregroundStyle(ReSpaceStyle.purple) } }
        }.frame(height: page == "object" ? 200 : 260).clipShape(RoundedRectangle(cornerRadius: 28))
    }
    private func goBack() {
        switch page {
        case "review": dismiss()
        case "object": page = "objects"
        case "unlock": page = "object"
        case "rename", "delete": page = "options"
        default: page = "review"
        }
    }
    private func objectID(_ object: JSONValue) -> String { object["native_id"].string ?? object["id"].string ?? object["identifier"].text }
    private func instructionLabel(_ value: String) -> String { value == "keep" ? "Keep in place" : value == "remove" ? "Remove from design" : "Let the design decide" }
    private func saveInstruction() async {
        guard let selected else { return }
        saving = true
        await command(chosenInstruction == "keep" ? "Keep this in place" : chosenInstruction == "remove" ? "Remove this from the design" : "Explicitly unlock this and let the design decide", target: selected)
        saving = false
        if error == nil { page = "objects" }
        if operation["pending_question"] != .null { showOperation = true }
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
        while !Task.isCancelled, operation["operation_id"].text == id, ["queued", "running"].contains(operation["state"].text), operation["pending_question"] == .null {
            do {
                try await Task.sleep(for: .seconds(2))
                let next = try await client.request("operations/\(id)")["operation"]
                guard !Task.isCancelled, operation["operation_id"].text == id else { return }
                operation = next; error = nil
            } catch {
                guard !Task.isCancelled else { return }
                self.error = error.localizedDescription
            }
        }
        if !Task.isCancelled, operation["operation_id"].text == id { await load() }
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
                if !app.isUIDemo {
                    for archive in CaptureArchive.recoverable() where archive.roomID == roomID { try FileManager.default.removeItem(at: archive.folder) }
                }
                await app.refresh(); dismiss()
            } else { error = "Deletion pending. Refresh and retry until the backend confirms cleanup." }
        } catch { self.error = "Deletion pending: \(error.localizedDescription)" }
    }
}

struct PrivateCapturePhoto: View {
    let app: AppModel
    let path: String
    var fill = false
    @State private var image: UIImage?
    @State private var failed = false
    var body: some View {
        Group { if let image { Image(uiImage: image).resizable().aspectRatio(contentMode: fill ? .fill : .fit) } else if failed { Label("Image unavailable", systemImage: "photo").font(.caption) } else { ProgressView() } }
            .task(id: path) { image = nil; failed = false; do { guard let client = app.client else { return }; let bytes = try await client.media(path); guard let decoded = UIImage(data: bytes) else { throw ContractError.invalid("Invalid image") }; image = decoded } catch { failed = true } }
    }
}

#if DEBUG
#Preview("Room review") { UIDemoPreview(.room) }
#endif
