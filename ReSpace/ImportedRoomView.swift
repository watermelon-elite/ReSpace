import SwiftUI

struct ImportedRoomView: View {
    let app: AppModel
    static var modelURL: URL? { Bundle.main.url(forResource: "kitchenette", withExtension: "usdz") }
    @State private var manifest: JSONValue = .null
    @State private var selectedID: String?
    @State private var loading = true
    @State private var error: String?
    @State private var reset = 0
    @AppStorage("imported_room_request") private var text = ""
    @State private var showObjects = false
    @State private var showDetails = false
    @State private var retry = 0
    @State private var detail: JSONValue = .null
    @State private var operation: JSONValue = .null
    @State private var showOperation = false
    @State private var shoppingList: ShoppingList?
    @State private var shoppingError: String?
    @State private var savingShoppingList = false
    @Environment(\.dismiss) private var dismiss
    private var objects: [JSONValue] { manifest["entities"].array.filter { !["wall", "floor", "ceiling"].contains($0["kind"].text) } }
    private var selected: JSONValue { objects.first { $0["id"].text == selectedID } ?? .null }

    var body: some View {
        VStack(spacing: 0) {
            RSTopBar(back: { dismiss() }, trailingSymbol: "bag", trailingLabel: "Save and share shopping list",
                     trailingProminent: true, trailingDisabled: loading || savingShoppingList,
                     trailing: { Task { await openShoppingList() } })
            HStack {
                Button { showObjects.toggle() } label: {
                    Label("Objects", systemImage: "square.stack.3d.up")
                        .font(ReSpaceStyle.font(13, weight: .medium)).padding(.horizontal, 14).frame(height: 44)
                        .foregroundStyle(showObjects ? ReSpaceStyle.purple : ReSpaceStyle.ink)
                        .background(showObjects ? ReSpaceStyle.wash : .white, in: Capsule())
                }.buttonStyle(.plain).disabled(loading || error != nil).accessibilityAddTraits(showObjects ? .isSelected : [])
                Spacer()
                RSIconButton(symbol: "viewfinder", label: "Reset View") { reset += 1 }
                RSIconButton(symbol: "info.circle", label: "Room details") { showDetails = true }
            }.padding(.horizontal, 16).padding(.bottom, 8)
            ZStack {
                if manifest != .null, let url = Self.modelURL {
                    RoomScene(document: manifest, native: false, selectedID: $selectedID, ghosts: false, resetToken: reset,
                              importedModelURL: url, onModelLoad: { message in error = message; loading = false })
                        .id(retry)
                        .accessibilityLabel("Reconstructed kitchenette. Drag to orbit, use two fingers to pan, and pinch to zoom.")
                }
                if loading { ProgressView("Opening your scan…").padding(24).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 20)) }
                if let error {
                    VStack(spacing: 16) {
                        RSNotice(message: error, isError: true)
                        Button("Try again") { loading = true; self.error = nil; retry += 1 }.buttonStyle(RSButtonStyle(kind: .secondary))
                    }.padding(24)
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
                .ignoresSafeArea(.container, edges: .bottom)
                .overlay(alignment: .bottom) {
                    VStack(spacing: 0) {
                        if showObjects {
                            ScrollView {
                                VStack(spacing: 0) {
                                    ForEach(objects, id: \.self) { object in
                                        Button { selectedID = object["id"].text; showObjects = false } label: {
                                            RSRow(title: object["label"].text, subtitle: object["kind"].text == "fixed" ? "Installed fixture" : "Scanned Object", symbol: selectedID == object["id"].text ? "checkmark.circle" : "cube")
                                        }.buttonStyle(.plain)
                                    }
                                }.padding(.horizontal, 16)
                            }.frame(maxHeight: 300).background(.white, in: RoundedRectangle(cornerRadius: 24)).padding(12)
                        }
                        RoomRequestBar(app: app, text: $text, operation: $operation, selection: selected == .null ? nil : selected["label"].text,
                            selectedObjectID: selectedID, clear: { selectedID = nil }, prepareRoom: { try await connectRoom() },
                            onUpdate: { await load() }, onDetails: { showOperation = true })
                    }
                }
        }
        .background(ReSpaceStyle.canvas).foregroundStyle(ReSpaceStyle.ink)
        .toolbar(.hidden, for: .navigationBar).navigationBarBackButtonHidden()
        .task(id: retry) {
            do {
                guard Self.modelURL != nil, let url = Bundle.main.url(forResource: "kitchenette", withExtension: "json") else {
                    throw ContractError.invalid("The imported scan is missing from this app build.")
                }
                manifest = try await Task.detached { try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: url)) }.value
                await load()
            } catch { self.error = error.localizedDescription; loading = false }
        }
        .task(id: [operation["operation_id"].text, operation["state"].text]) {
            guard let client = app.client, let id = operation["operation_id"].string else { return }
            while !Task.isCancelled && ["queued", "running"].contains(operation["state"].text) {
                do {
                    try await Task.sleep(for: .seconds(2))
                    let next = try await client.request("operations/\(id)")["operation"]
                    guard !Task.isCancelled else { return }
                    operation = next
                } catch { return }
            }
            if !Task.isCancelled { await load() }
        }
        .sheet(isPresented: $showOperation) {
            NavigationStack { OperationPanel(app: app, operation: $operation, onUpdate: { await load() }) }
        }
        .sheet(item: $shoppingList) { ShoppingListView(list: $0) }
        .alert("Shopping list unavailable", isPresented: Binding(get: { shoppingError != nil }, set: { if !$0 { shoppingError = nil } })) {
            Button("Try again") { Task { await openShoppingList() } }
            Button("Cancel", role: .cancel) { shoppingError = nil }
        } message: { Text(shoppingError ?? "") }
        .sheet(isPresented: $showDetails) {
            RSPage(title: "Room details", back: { showDetails = false }) {
                Text("The measured room shell and reconstructed furnishings are assembled in their original arrangement.")
                VStack(spacing: 0) {
                    RSKeyValue(title: "Objects and fixtures", value: String(objects.count))
                    RSKeyValue(title: "Separate scene parts", value: String(manifest["entities"].array.count))
                    RSKeyValue(title: "Units", value: "Metres")
                }
                RSNotice(message: "The furnishings include AI reconstruction. \(Int(manifest["coarse_object_count"].number ?? 0)) Objects use coarse geometry; dimensions and hidden surfaces may be approximate.")
                Text("Drag to orbit, use two fingers to pan, and pinch to zoom.").font(ReSpaceStyle.font(14)).foregroundStyle(ReSpaceStyle.secondary)
            } footer: { EmptyView() }
        }
    }

    private func existingRoom() async throws -> JSONValue? {
        guard let client = app.client else { throw ContractError.invalid("Configure the backend before continuing.") }
        let rooms = try await client.request("rooms")["rooms"].array
        guard let room = rooms.first(where: { $0["source_scene_sha256"] == manifest["source_scene_sha256"] }) else { return nil }
        return try await client.request("rooms/\(room["room_id"].text)")
    }

    private func openShoppingList() async {
        savingShoppingList = true
        defer { savingShoppingList = false }
        do {
            guard let store = app.shoppingLists else { throw ContractError.invalid("Local storage is unavailable. Reopen the app and try again.") }
            await load()
            let name = detail["room"]["name"].string ?? "Kitchenette"
            let list: ShoppingList
            if let designID = detail["room"]["active_design_id"].string, let client = app.client {
                let design = try SavedDesign(envelope: await client.request("designs/\(designID)"))
                list = try ShoppingList(design: design.value, roomName: name)
            } else {
                list = try ShoppingList(operation: operation, roomName: name)
            }
            try store.save(list)
            shoppingError = nil
            shoppingList = list
        } catch { shoppingError = error.localizedDescription }
    }

    private func connectRoom() async throws -> JSONValue {
        if let existing = try await existingRoom() { detail = existing; return existing }
        let importKey = "imported-" + manifest["source_scene_sha256"].text
        if let pending = app.pending.first(where: { $0.roomID == importKey }) {
            detail = try await app.reconcile(pending)
        } else {
            let entities = manifest["entities"].array.map { entity in
                JSONValue.object(Dictionary(uniqueKeysWithValues: ["id", "label", "kind", "category", "bounds_min", "bounds_max"].map { ($0, entity[$0]) }))
            }
            detail = try await app.submit(PendingRequest(path: "rooms/imported", roomID: importKey, body: [
                "name": .string("Kitchenette"), "source_capture_id": manifest["capture_id"],
                "source_scene_sha256": manifest["source_scene_sha256"], "entities": .array(entities)]))
        }
        await app.refresh()
        return detail
    }

    private func load() async {
        do {
            guard let existing = try await existingRoom(), let client = app.client else { return }
            detail = existing
            if existing["current_operation"] != .null { operation = existing["current_operation"] }
            else if operation == .null {
                let entries = try await client.request("rooms/\(detail["room"]["room_id"].text)/conversation")["entries"].array
                if let id = entries.last?["operation_id"].string { operation = try await client.request("operations/\(id)")["operation"] }
            }
        } catch { /* The local model remains viewable when the backend is offline. Sending reports the error. */ }
    }
}
