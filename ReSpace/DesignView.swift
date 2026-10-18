import SwiftUI

struct DesignView: View {
    let app: AppModel
    let roomID: String
    let designID: String
    @State private var design: JSONValue = .null
    @State private var room: JSONValue = .null
    @State private var operation: JSONValue = .null
    @State private var entries: [JSONValue] = []
    @State private var selectedID: String?
    @State private var showItems = false
    @State private var text = ""
    @State private var typing = false
    @State private var ghosts = true
    @State private var reset = 0
    @State private var error: String?
    @State private var selectedProduct: JSONValue?
    @State private var selectedProductItemID: String?
    @State private var productSearches: [String: String] = [:]
    @State private var swapPreview: SwapPreview?
    @State private var swapSubmitted = false
    @State private var assetManifest: JSONValue = .null
    @State private var showOperation = false
    @State private var showViewControls = false
    @State private var shoppingList: ShoppingList?
    @State private var shoppingError: String?
    @State private var removeItem: JSONValue?
    @State private var showingAlternatives = false
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var scene: JSONValue { design["scene"] }
    var locked: Bool { swapPreview != nil || room["current_operation_id"].string != nil || app.pending.contains { $0.roomID == roomID } }
    var selectedItem: JSONValue { scene["items"].array.first { ($0["id"].string ?? $0["item_id"].string) == selectedID } ?? .null }
    private var total: String { scene["purchase_summary"]["total"].string ?? scene["purchase_summary"]["total"]["amount"].text }
    private var activeOperation: Bool { operation != .null && !["succeeded", "failed", "cancelled", "rejected"].contains(operation["state"].text) }
    private var visibleItems: [JSONValue] { scene["items"].array.filter { $0["origin"].text != "new" || $0["status"].text != "removed" } }
    private var feedback: String? {
        if let error { return error }
        guard operation != .null else { return nil }
        if operation["pending_question"] != .null { return "Answer a question to continue" }
        if activeOperation { return operation["progress_message"].string ?? operation["phase"].text.replacingOccurrences(of: "_", with: " ").capitalized }
        if let failure = operation["failure"]["message"].string { return failure }
        return entries.last(where: { $0["role"].text == "assistant" })?["text"].string
    }
    var body: some View {
        VStack(spacing: 0) {
            RSTopBar(title: room["name"].string ?? "Your room", back: { dismiss() },
                     trailingSymbol: "bag", trailingLabel: "Save and share shopping list", trailingProminent: true,
                     trailingDisabled: design == .null, trailing: { openShoppingList() })
            HStack {
                Button {
                    withAnimation(reduceMotion ? nil : .easeOut(duration: 0.25)) { showItems.toggle() }
                } label: {
                    Label("Items", systemImage: "square.grid.2x2")
                        .font(ReSpaceStyle.font(13, weight: .medium)).padding(.horizontal, 14).frame(height: 44)
                        .foregroundStyle(showItems ? ReSpaceStyle.purple : ReSpaceStyle.ink)
                        .background(showItems ? ReSpaceStyle.wash : .white, in: Capsule())
                }.buttonStyle(.plain).accessibilityAddTraits(showItems ? .isSelected : []).disabled(swapPreview != nil)
                Spacer()
                RSIconButton(symbol: "arrow.uturn.backward", label: "Undo") { Task { await mutate("rooms/\(roomID)/undo", body: [:]) } }.disabled(locked || design["parent_id"] == .null)
                RSIconButton(symbol: "viewfinder", label: "Reset View") { reset += 1 }
                RSIconButton(symbol: "ellipsis", label: "Room view options") { showViewControls = true }
            }.padding(.horizontal, 16).padding(.bottom, 8)
            GeometryReader { geometry in
                ZStack(alignment: .bottom) {
                    RoomScene(document: swapPreview?.scene(over: scene) ?? scene, native: false, selectedID: $selectedID, ghosts: ghosts, resetToken: reset, assetBaseURL: app.client?.baseURL, assetManifest: assetManifest)
                        #if DEBUG
                        .id(scene["ui_demo_image"].text)
                        #endif
                        .frame(width: geometry.size.width, height: min(geometry.size.width, geometry.size.height))
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    VStack(spacing: 0) {
                        if showItems || swapPreview != nil {
                            let height: CGFloat = swapPreview != nil ? 270 : selectedItem != .null ? 330 : min(330, 72 + CGFloat(max(1, visibleItems.count)) * 88)
                            itemPanel.frame(height: min(height, geometry.size.height * 0.8))
                                .background(.white, in: RoundedRectangle(cornerRadius: 24))
                                .overlay { RoundedRectangle(cornerRadius: 24).stroke(ReSpaceStyle.line, lineWidth: 1).allowsHitTesting(false) }
                                .padding(12).transition(.move(edge: .bottom).combined(with: .opacity))
                        }
                        composer
                    }
                }.clipped()
            }.background(Color(white: 0.93).ignoresSafeArea(.container, edges: .bottom))
        }.background(ReSpaceStyle.canvas).foregroundStyle(ReSpaceStyle.ink).font(ReSpaceStyle.font())
        .toolbar(.hidden, for: .navigationBar).navigationBarBackButtonHidden()
        .sheet(item: $selectedProduct) { product in
            ProductDetail(app: app, product: product, searchID: selectedProductItemID.flatMap { productSearches[$0] }, canSwap: !locked,
                          startWithAlternatives: showingAlternatives, onFindMore: {
                guard let id = selectedProductItemID else { return }
                selectedProduct = nil
                Task { await mutate("designs/\(design["design_id"].text)/find-more", body: ["item_id": .string(id)]); showItems = false; if activeOperation { showOperation = true } }
            }, onPreview: { choice, search in beginPreview(choice, searchID: search) })
        }
        .sheet(isPresented: $showViewControls) { viewControls }
        .sheet(item: $shoppingList) { ShoppingListView(list: $0) }
        .alert("Shopping list couldn’t be saved", isPresented: Binding(get: { shoppingError != nil }, set: { if !$0 { shoppingError = nil } })) {
            Button("Try again") { openShoppingList() }
            Button("Cancel", role: .cancel) { shoppingError = nil }
        } message: { Text(shoppingError ?? "") }
        .sheet(item: $removeItem) { item in removalPage(item) }
        .fullScreenCover(isPresented: $showOperation) { NavigationStack { OperationPanel(app: app, operation: $operation, onUpdate: { await load() }) } }
        .task { if !app.isUIDemo { text = UserDefaults.standard.string(forKey: "design_draft_\(roomID)") ?? "" }; await load(initial: true) }
        .onChange(of: text) { _, value in if !app.isUIDemo { UserDefaults.standard.set(value, forKey: "design_draft_\(roomID)") } }
        .task(id: [operation["operation_id"].text, operation["state"].text]) { await poll() }
    }
    private var itemPanel: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                if swapPreview != nil { Text("Preview").font(ReSpaceStyle.font(15, weight: .semibold)) }
                else {
                    if selectedItem != .null {
                        Button { selectedID = nil } label: { Label("All items", systemImage: "chevron.left").font(ReSpaceStyle.font(13, weight: .medium)).frame(minHeight: 44) }.buttonStyle(.plain)
                    } else { Text("Items").font(ReSpaceStyle.font(15, weight: .semibold)) }
                    Spacer(minLength: 4)
                    Button { openShoppingList() } label: { Text(total.isEmpty ? "Purchases" : "$\(total)").font(ReSpaceStyle.font(14, weight: .semibold)).frame(minHeight: 44) }.buttonStyle(.plain).accessibilityLabel("Purchase total, \(total) US dollars")
                    RSIconButton(symbol: "xmark", label: "Close items") {
                        withAnimation(reduceMotion ? nil : .easeOut(duration: 0.25)) { showItems = false }
                    }
                }
            }.frame(minHeight: 44).padding(.leading, 20).padding(.trailing, 8).padding(.top, 8)
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let preview = swapPreview { swapCard(preview) }
                    else if selectedItem != .null { selectedCard }
                    else {
                        ForEach(visibleItems, id: \.self) { item in itemRow(item) }
                        if visibleItems.isEmpty { Text(design == .null ? "Opening your design…" : "No Items in this design.").foregroundStyle(ReSpaceStyle.secondary) }
                    }
                }.padding(.horizontal, 20).padding(.top, 8).padding(.bottom, 16).frame(maxWidth: .infinity, alignment: .leading)
            }.scrollDismissesKeyboard(.interactively)
        }
    }
    private var composer: some View {
        VStack(spacing: 8) {
            if let feedback, !feedback.isEmpty {
                Button { showOperation = true } label: {
                    OlloMessage(cue: typing ? .listening : .operation(operation), compact: typing) {
                        HStack(spacing: 10) {
                            if activeOperation { ProgressView().controlSize(.small) }
                            Text(feedback).font(ReSpaceStyle.font(12)).lineLimit(error == nil && !activeOperation ? 2 : nil).multilineTextAlignment(.leading).frame(maxWidth: .infinity, alignment: .leading)
                            if operation != .null { Image(systemName: "chevron.right").font(.system(size: 12)) }
                        }.foregroundStyle(error != nil ? ReSpaceStyle.danger : ReSpaceStyle.ink).frame(minHeight: 44)
                            .padding(.horizontal, 14).background(.white, in: RoundedRectangle(cornerRadius: 20))
                    }
                }.buttonStyle(.plain).disabled(operation == .null).accessibilityHint(operation == .null ? "" : "Open request details")
            } else if swapPreview == nil && !showItems {
                OlloMessage(cue: typing ? .listening : .idle, compact: typing) {
                    Text("What would you like to change?").font(ReSpaceStyle.font(14))
                        .padding(14).background(.white, in: RoundedRectangle(cornerRadius: 20))
                }
            }
            RSComposer(text: $text, selection: selectedID.map { selectedItem["label"].string ?? $0 }, clear: { selectedID = nil }, disabled: locked, onFocusChange: { typing = $0 }) {
                let submitted = text
                Task {
                    let accepted = await mutate("designs/\(design["design_id"].text)/chat", body: ["text": .string(submitted), "selected_item_id": selectedID.map(JSONValue.string) ?? .null])
                    if accepted { text = ""; showItems = false }
                }
            }
        }.padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 12)
    }
    private func itemRow(_ item: JSONValue) -> some View {
        let id = item["id"].string ?? item["item_id"].text
        let product = scene["selections"][item["selection_id"].text]
        return Button { selectedID = id } label: {
            HStack(spacing: 16) {
                if product != .null { ProductImage(product: product).frame(width: 56, height: 56).clipShape(RoundedRectangle(cornerRadius: 14)) }
                else { Image(systemName: item["status"].text == "removed" ? "square.dashed" : "cube").foregroundStyle(ReSpaceStyle.purple).frame(width: 56, height: 56) }
                VStack(alignment: .leading, spacing: 5) {
                    Text(item["label"].string ?? item["category"].text).font(ReSpaceStyle.font(15, weight: .medium))
                    Text(product != .null ? "$\(productPrice(product)) · New" : item["status"].text.replacingOccurrences(of: "_", with: " ").capitalized).font(ReSpaceStyle.font(12)).foregroundStyle(ReSpaceStyle.secondary)
                }.frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "arrow.right").font(.system(size: 14))
            }.padding(.bottom, 16).overlay(alignment: .bottom) { Rectangle().fill(ReSpaceStyle.line).frame(height: 1) }.contentShape(Rectangle())
        }.buttonStyle(.plain)
    }
    @ViewBuilder private var selectedCard: some View {
        let item = selectedItem
        let id = item["id"].string ?? item["item_id"].text
        let product = scene["selections"][item["selection_id"].text]
        VStack(alignment: .leading, spacing: 12) {
            Text(item["label"].string ?? item["category"].text).font(ReSpaceStyle.font(22, weight: .semibold)).tracking(-0.6)
            if product != .null {
                HStack(spacing: 16) {
                    ProductImage(product: product).frame(width: 72, height: 72).clipShape(RoundedRectangle(cornerRadius: 16))
                    VStack(alignment: .leading, spacing: 8) {
                        Text("$\(productPrice(product))").font(ReSpaceStyle.font(16, weight: .semibold))
                        Text(productOffer(product)["merchant"].text).font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
                    }
                }
            }
            if item["status"].text == "removed" {
                Text("Its faint outline shows where it was.").font(ReSpaceStyle.font(14))
                Button("Restore Object") { Task { await mutate("designs/\(design["design_id"].text)/chat", body: ["text": .string("Restore this"), "selected_item_id": .string(id)]) } }.buttonStyle(RSButtonStyle(kind: .secondary)).disabled(locked)
            } else {
                HStack(spacing: 8) {
                    if product != .null {
                        Button("Details") { openProduct(product, itemID: id) }.buttonStyle(RSButtonStyle(kind: .secondary, compact: true))
                        Button("Swap") { openProduct(product, itemID: id, alternatives: true) }.buttonStyle(RSButtonStyle(kind: .secondary, compact: true)).disabled(locked)
                    }
                    Button("Remove") { removeItem = item }.buttonStyle(RSButtonStyle(kind: .secondary, compact: true)).disabled(locked)
                }
            }
            DisclosureGroup("Item details") {
                VStack(alignment: .leading, spacing: 8) {
                    if !item["reason"].text.isEmpty { Text(item["reason"].text) }
                    if let placement = try? Placement(item["placement"]) {
                        Text(String(format: "%.2f × %.2f × %.2f m", placement.size[0], placement.size[1], placement.size[2]))
                    }
                    Text("Representative geometry · saved placement validated")
                }.padding(.top, 8)
            }.font(ReSpaceStyle.font(12)).foregroundStyle(ReSpaceStyle.secondary)
        }
    }

    private func openProduct(_ product: JSONValue, itemID: String, alternatives: Bool = false) {
        selectedProductItemID = itemID; showingAlternatives = alternatives; selectedProduct = product
    }
    private var viewControls: some View {
        RSPage(title: "Room view", back: { showViewControls = false }) {
            VStack(spacing: 0) {
                Button { reset += 1; showViewControls = false } label: { RSRow(title: "Reset View", subtitle: "Return to the original camera framing", symbol: "viewfinder") }
                Button { ghosts.toggle() } label: { RSRow(title: ghosts ? "Hide removed Objects" : "Show removed Objects", subtitle: "Faint ghosts keep spatial context", symbol: ghosts ? "eye.slash" : "eye") }
            }.buttonStyle(.plain)
            Text("Pinch to zoom. Drag to orbit. Use two fingers to pan.").font(ReSpaceStyle.font(14)).foregroundStyle(ReSpaceStyle.secondary)
            if !scene["summary"].text.isEmpty || !scene["warnings"].array.isEmpty {
                DisclosureGroup("Design notes") {
                    VStack(alignment: .leading, spacing: 12) {
                        if !scene["summary"].text.isEmpty { Text(scene["summary"].text) }
                        ForEach(scene["warnings"].array, id: \.self) { RSNotice(message: $0["message"].text) }
                    }.padding(.top, 12)
                }
            }
        } footer: { Button("Back to design") { showViewControls = false }.buttonStyle(RSButtonStyle()) }
    }
    private func openShoppingList() {
        do {
            #if DEBUG
            if app.isUIDemo {
                shoppingList = try ShoppingList(design: design, roomName: room["name"].text)
                return
            }
            #endif
            guard let store = app.shoppingLists else { throw ContractError.invalid("Local storage is unavailable. Reopen the app and try again.") }
            let list = try ShoppingList(design: design, roomName: room["name"].string ?? "Your room")
            try store.save(list)
            shoppingError = nil
            shoppingList = list
        } catch { shoppingError = error.localizedDescription }
    }
    private func removalPage(_ item: JSONValue) -> some View {
        let product = scene["selections"][item["selection_id"].text]
        return RSPage(title: "Remove this \((item["label"].string ?? item["category"].text).lowercased())?", back: { removeItem = nil }) {
            if product != .null { ProductImage(product: product).frame(height: 280).clipShape(RoundedRectangle(cornerRadius: 28)) }
            else { RSSymbol(name: "cube") }
            Text(item["origin"].text == "new" ? "This new piece will leave the design." : "This Object will leave the design. A faint outline will show where it was.")
            Text("The purchase total is recalculated when your change is saved. Kept Objects require an explicit unlock.").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
        } footer: {
            Button("Remove from design") {
                let id = item["id"].string ?? item["item_id"].text
                removeItem = nil
                Task { await mutate("designs/\(design["design_id"].text)/remove", body: ["item_id": .string(id)]); showItems = false; if operation["pending_question"] != .null { showOperation = true } }
            }.buttonStyle(RSButtonStyle(kind: .danger)).disabled(locked)
            Button("Keep it") { removeItem = nil }.buttonStyle(RSButtonStyle(kind: .secondary))
        }
    }
    private func swapCard(_ preview: SwapPreview) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(preview.choice["title"].text).font(ReSpaceStyle.font(22, weight: .semibold))
            Text(swapSubmitted ? "Awaiting server validation" : "Temporary preview · fit pending").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
            if !swapSubmitted { Button("Use this Product") { Task { await submitSwap() } }.buttonStyle(RSButtonStyle()) }
            else { Button("Check swap") { Task { await refreshSwap() } }.buttonStyle(RSButtonStyle()) }
            Button(swapSubmitted ? "Cancel swap" : "Keep saved choice") { Task { await cancelSwap() } }.buttonStyle(RSButtonStyle(kind: .quiet))
        }
    }
    func load(initial: Bool = false) async {
        guard let client = app.client else { return }
        do {
            let detail = try await client.request("rooms/\(roomID)"); room = detail["room"]
            if assetManifest == .null { assetManifest = (try? await client.request("catalog/manifest")) ?? .null }
            let id = initial ? designID : room["active_design_id"].string ?? designID
            let envelope = try await client.request("designs/\(id)")
            design = try SavedDesign(envelope: envelope).value
            var searches: [String: String] = [:]
            for reference in detail["product_searches"].array where reference["design_id"].text == id {
                if let itemID = reference["item_id"].string, let searchID = reference["search_id"].string { searches[itemID] = searchID }
            }
            productSearches = searches
            if let selectedID, !scene["items"].array.contains(where: { ($0["id"].string ?? $0["item_id"].string) == selectedID && $0["status"].text != "removed" }) { self.selectedID = nil }
            entries = try await client.request("rooms/\(roomID)/conversation")["entries"].array
            if detail["current_operation"] != .null { operation = detail["current_operation"] }
            if let preview = swapPreview, swapSubmitted, operation["operation_id"] == preview.requestBody["operation_id"], ["succeeded", "rejected", "failed", "cancelled"].contains(operation["state"].text) {
                swapPreview = nil; swapSubmitted = false
                if operation["state"].text != "succeeded" { error = operation["failure"]["message"].string ?? operation["outcome"]["message"].string ?? "Swap was not applied. Saved design restored." }
            } else { error = nil }
        } catch { self.error = error.localizedDescription }
    }
    @discardableResult func mutate(_ path: String, body: [String: JSONValue]) async -> Bool {
        do {
            var value = body; value["expected_active_design_id"] = room["active_design_id"]; value["expected_active_revision"] = room["active_revision"]
            let result = try await app.submit(PendingRequest(path: path, roomID: roomID, body: value))
            operation = result["operation"]; await load(); return true
        } catch { self.error = error.localizedDescription; return false }
    }
    func beginPreview(_ choice: JSONValue, searchID: String) {
        guard !locked, let itemID = selectedProductItemID else { return }
        do {
            swapPreview = try SwapPreview(scene: scene, itemID: itemID, choice: choice, searchID: searchID, activeRevision: room["active_revision"].int)
            swapSubmitted = false; selectedProduct = nil; selectedID = itemID
        } catch { self.error = error.localizedDescription }
    }
    func submitSwap() async {
        guard let preview = swapPreview, !swapSubmitted else { return }
        swapSubmitted = true
        do {
            let request = PendingRequest(path: "designs/\(preview.designID)/swap", roomID: roomID, body: preview.requestBody)
            operation = try await app.submit(request)["operation"]
            await load()
        } catch let error as APIError {
            if !error.retryable { swapPreview = nil; swapSubmitted = false; await load() }
            self.error = error.localizedDescription
        } catch { self.error = "Swap outcome is unconfirmed. Refresh to reconcile: \(error.localizedDescription)" }
    }
    func refreshSwap() async {
        guard let preview = swapPreview, let client = app.client else { return }
        do {
            if let pending = app.pending.first(where: { $0.operationID == preview.operationID }) { operation = try await app.reconcile(pending)["operation"] }
            else { operation = try await client.request("operations/\(preview.operationID)")["operation"] }
            await load()
        } catch { self.error = "Swap remains unconfirmed: \(error.localizedDescription)" }
    }
    func cancelSwap() async {
        guard let preview = swapPreview else { return }
        guard swapSubmitted else { swapPreview = nil; return }
        do {
            if let pending = app.pending.first(where: { $0.operationID == preview.operationID }) { operation = try await app.reconcile(pending)["operation"] }
            if ["succeeded", "rejected", "failed", "cancelled"].contains(operation["state"].text) {
                let completed = operation["state"].text == "succeeded"
                await load()
                if completed { error = "Swap completed before cancellation. Its saved result is shown." }
                return
            }
            let body: [String: JSONValue] = ["operation_id": preview.requestBody["operation_id"]!, "cancellation_id": .string(UUID().uuidString)]
            operation = try await app.submit(PendingRequest(path: "operations/\(preview.operationID)/cancel", roomID: roomID, body: body))["operation"]
            await load()
        } catch { self.error = "Cancellation is not confirmed: \(error.localizedDescription)" }
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
}

#if DEBUG
#Preview("Design") { UIDemoPreview(.design) }
#endif
