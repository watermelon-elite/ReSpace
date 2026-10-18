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
    @State private var tab = "Assistant"
    @State private var detent = PresentationDetent.height(170)
    @State private var text = ""
    @State private var ghosts = true
    @State private var reset = 0
    @State private var sheet = true
    @State private var error: String?
    @State private var selectedProduct: JSONValue?
    @State private var selectedProductItemID: String?
    @State private var productSearches: [String: String] = [:]
    @State private var swapPreview: SwapPreview?
    @State private var swapSubmitted = false
    @State private var assetManifest: JSONValue = .null
    var scene: JSONValue { design["scene"] }
    var locked: Bool { swapPreview != nil || room["current_operation_id"].string != nil || app.pending.contains { $0.roomID == roomID } }
    var selectedItem: JSONValue { scene["items"].array.first { ($0["id"].string ?? $0["item_id"].string) == selectedID } ?? .null }
    var body: some View {
        ZStack(alignment: .top) {
            RoomScene(document: swapPreview?.scene(over: scene) ?? scene, native: false, selectedID: $selectedID, ghosts: ghosts, resetToken: reset, assetBaseURL: app.client?.baseURL, assetManifest: assetManifest).ignoresSafeArea(edges: .bottom)
            VStack(spacing: 8) {
            HStack {
                Button("Undo", systemImage: "arrow.uturn.backward") { Task { await mutate("rooms/\(roomID)/undo", body: [:]) } }.disabled(locked || design["parent_id"] == .null)
                Button("Reset View", systemImage: "viewfinder") { reset += 1 }
                Toggle("Ghosts", isOn: $ghosts).toggleStyle(.button)
            }.buttonStyle(.bordered).padding(8).background(.regularMaterial)
            if let preview = swapPreview {
                VStack {
                    Text("Preview: \(preview.choice["title"].text)")
                    Text(swapSubmitted ? "Swap preview · awaiting server validation" : "Swap preview · fit is not yet validated").font(.headline)
                    HStack {
                        if !swapSubmitted { Button("Confirm Swap") { Task { await submitSwap() } } }
                        else { Button("Refresh Swap") { Task { await refreshSwap() } } }
                        Button(swapSubmitted ? "Cancel Swap" : "Cancel Preview", role: .cancel) { Task { await cancelSwap() } }
                    }
                }.padding().background(.regularMaterial)
            }
            }
        }
        .navigationTitle("Design")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { Button("Assistant / Items") { sheet = true } }
        .sheet(isPresented: $sheet) {
            VStack(spacing: 0) {
                Picker("Panel", selection: $tab) { Text("Assistant").tag("Assistant"); Text("Items").tag("Items") }.pickerStyle(.segmented).padding()
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 16) {
                            if let error { Text(error).foregroundStyle(.red) }
                            if operation != .null { OperationPanel(app: app, operation: $operation, onUpdate: { await load() }) }
                            if tab == "Assistant" {
                                Text(scene["summary"].text)
                                ForEach(entries, id: \.self) { entry in VStack(alignment: .leading) { Text(entry["context"].text + (entry["base_design_id"].string.map { " · \($0)" } ?? "")).font(.caption).foregroundStyle(.secondary); Text(entry["text"].text) }.id(entry["message_id"].text) }
                                ForEach(scene["warnings"].array, id: \.self) { warning in Text(warning["message"].text).foregroundStyle(.orange) }
                            } else {
                                purchaseSummary
                                ForEach(scene["items"].array.filter { $0["origin"].text != "new" || $0["status"].text != "removed" }, id: \.self) { item in itemCard(item).id(item["id"].string ?? item["item_id"].text) }
                            }
                        }.frame(maxWidth: .infinity, alignment: .leading).padding()
                    }
                    .onChange(of: selectedID) { _, value in if let value { tab = "Items"; if detent == .height(170) { detent = .medium }; proxy.scrollTo(value, anchor: .center) } }
                }
                Divider()
                VStack(alignment: .leading, spacing: 4) {
                    if let selectedID { HStack { Text("Selected: \(selectedItem["label"].string ?? selectedID)").font(.caption); Button("Clear") { self.selectedID = nil } } }
                    HStack(alignment: .bottom) { TextField("Ask ReSpace to change the design", text: $text, axis: .vertical).lineLimit(1...4); Button("Send", systemImage: "arrow.up.circle.fill") { let submitted = text; Task { let accepted = await mutate("designs/\(design["design_id"].text)/chat", body: ["text": .string(submitted), "selected_item_id": selectedID.map(JSONValue.string) ?? .null]); if accepted { text = "" } } }.disabled(locked || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) }
                }.padding().background(.regularMaterial)
            }
            .presentationDetents([.height(170), .medium, .large], selection: $detent)
            .presentationBackgroundInteraction(.enabled(upThrough: .medium))
            .interactiveDismissDisabled()
            .sheet(item: $selectedProduct) { ProductDetail(app: app, product: $0, searchID: selectedProductItemID.flatMap { productSearches[$0] }, canSwap: !locked, onPreview: { choice, search in beginPreview(choice, searchID: search) }) }
        }
        .task { text = UserDefaults.standard.string(forKey: "design_draft_\(roomID)") ?? ""; await load(initial: true) }
        .onChange(of: text) { _, value in UserDefaults.standard.set(value, forKey: "design_draft_\(roomID)") }
        .task(id: operation["operation_id"].text) { await poll() }
    }
    var purchaseSummary: some View {
        let purchases = scene["purchase_summary"]
        return VStack(alignment: .leading) {
            Text("Purchase total · USD \(purchases["total"].string ?? purchases["total"]["amount"].text)").font(.headline)
            Text("Excludes tax and shipping. Saved price snapshot.").font(.caption).foregroundStyle(.secondary)
            ForEach(purchases["lines"].array, id: \.self) { line in Text("\(line["purchased_pack_count"].int) packs · \(line["supplied_unit_count"].int) supplied · \(line["paid_surplus_count"].int) paid surplus · USD \(line["line_total"].text)").font(.caption) }
        }
    }
    func itemCard(_ item: JSONValue) -> some View {
        let id = item["id"].string ?? item["item_id"].text
        let product = scene["selections"][item["selection_id"].text]
        return VStack(alignment: .leading, spacing: 8) {
            Button { selectedID = id } label: { HStack { Image(systemName: selectedID == id ? "checkmark.circle.fill" : "cube"); Text(item["label"].string ?? item["category"].text).font(.headline); Spacer(); Text(item["status"].text).font(.caption) } }
            Text(item["reason"].text)
            if let placement = try? Placement(item["placement"]) { Text(String(format: "%.2f × %.2f × %.2f m · %@", placement.size[0], placement.size[1], placement.size[2], placement.mount)).font(.caption) }
            Text("Representative geometry · saved placement validated").font(.caption).foregroundStyle(.secondary)
            if product != .null { ProductSummary(product: product); Button("Product evidence and options") { selectedProductItemID = id; selectedProduct = product } }
            HStack { Button("Remove") { Task { await mutate("designs/\(design["design_id"].text)/remove", body: ["item_id": .string(id)]) } }.disabled(locked || item["status"].text == "removed"); if product != .null { Button("Find more") { Task { await mutate("designs/\(design["design_id"].text)/find-more", body: ["item_id": .string(id)]) } }.disabled(locked) } }
        }.padding().background(selectedID == id ? Color.accentColor.opacity(0.1) : Color.secondary.opacity(0.06)).clipShape(RoundedRectangle(cornerRadius: 12))
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
            swapSubmitted = false; selectedProduct = nil; selectedID = itemID; detent = .height(170)
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
        for _ in 0..<10 {
            guard !Task.isCancelled, !["succeeded", "failed", "cancelled", "rejected"].contains(operation["state"].text) else { await load(); return }
            do { try await Task.sleep(for: .seconds(2)); operation = try await client.request("operations/\(id)")["operation"] } catch { return }
        }
    }
}

struct ProductSummary: View {
    let product: JSONValue
    var offer: JSONValue { product["offer"] == .null ? product["chosen_offer"] : product["offer"] }
    var body: some View {
        HStack(alignment: .top) {
            if let url = URL(string: product["variant"]["image_references"].array.first?.string ?? "") { AsyncImage(url: url) { $0.resizable().scaledToFit() } placeholder: { Image(systemName: "photo") }.frame(width: 76, height: 76) }
            VStack(alignment: .leading, spacing: 4) { Text(product["title"].string ?? product["variant"]["title"].text).font(.headline); Text(offer["merchant"].string ?? offer["merchant_id"].text); Text("USD \(offer["price"].string ?? offer["price"]["amount"].text)"); Text("Checked \(offer["checked_at"].text)").font(.caption) }
        }
    }
}

struct ProductDetail: View {
    let app: AppModel
    let product: JSONValue
    let searchID: String?
    let canSwap: Bool
    let onPreview: (JSONValue, String) -> Void
    @Environment(\.openURL) private var openURL
    @Environment(\.dismiss) private var dismiss
    @State private var search: JSONValue = .null
    @State private var error: String?
    var offer: JSONValue { product["offer"] }
    var choices: [JSONValue] { ProductOptions.choices(selected: product, search: search) }
    var effectiveSearchID: String? { searchID ?? product["search_id"].string }
    var body: some View {
        NavigationStack { List {
            ProductSummary(product: product)
            Section("Saved selection") {
                Text("Selected variant: \(product["variant_id"].text)").font(.caption)
                Text(product["reason"].text)
                Text(product["fit_state"].text == "pending" ? "Product verified · placement fit pending" : "Saved placement validated")
                Text("Representative model; verified measurements determine its size.").font(.caption)
                Text(product["dimensions"].numbers.map { String(format: "%.3f", $0) }.joined(separator: " × ") + " m (width × depth × height)")
                Text("Dimensions checked \(product["dimension_evidence"]["verified_at"].text)").font(.caption)
            }
            if let selected = try? ProductChoice(product) { Button("Buy at \(offer["merchant"].text)", systemImage: "arrow.up.right.square") { openURL(selected.exactOfferURL) } }
            DisclosureGroup("Evidence, scores and uncertainty") {
                ForEach(["practical", "style", "value", "overall"], id: \.self) { component in
                    if let score = product["scores"][component].number { Text("\(component.capitalized): \(score, specifier: "%.1f") / 100"); Text(product["reasons"][component].text).font(.caption) }
                }
                Text("Scores are judgments, not probabilities.").font(.caption)
                ForEach(product["dimension_evidence"]["original_measurements"].array, id: \.self) { measurement in
                    Text("\(measurement["axis"].text) · \(measurement["label"].text): \(measurement["value"].string ?? measurement["value"].number.map(String.init(describing:)) ?? "") \(measurement["unit"].text)").font(.caption)
                }
                Text(product["uncertainty"].string ?? product["uncertainty"].array.compactMap(\.string).joined(separator: "\n"))
                if let url = URL(string: product["dimension_evidence"]["source_url"].text), ["https", "http"].contains(url.scheme ?? "") { Link("Measurement source", destination: url) }
            }
            if !product["offers"].array.isEmpty { Section("Merchant offers for this exact variant") { ForEach(product["offers"].array, id: \.self) { offer in VStack(alignment: .leading) { Text("\(offer["merchant"].text) · USD \(offer["price"].text)"); if let url = URL(string: offer["product_url"].text), ["http", "https"].contains(url.scheme ?? "") { Link("Open exact offer", destination: url) } } } } }
            Section("Eligible options") {
                Text("Selected identity is separate from rank. Fewer than three verified options may be available.").font(.caption)
                ForEach(choices, id: \.self) { choice in VStack(alignment: .leading) {
                    ProductSummary(product: choice)
                    Text(choice["variant_id"].text == product["variant_id"].text ? "Selected · saved evidence" : "Alternative · placement fit pending").font(.caption)
                    if choice["variant_id"].text != product["variant_id"].text {
                        NavigationLink("Inspect option evidence") { OptionEvidence(choice: choice) }
                        if let search = effectiveSearchID { Button("Preview Swap") { onPreview(choice, search) }.disabled(!canSwap) }
                    }
                } }
                if let error { Text(error).foregroundStyle(.secondary) }
            }
        }.navigationTitle("Product details").toolbar { Button("Done") { dismiss() } } }
        .task(id: effectiveSearchID) {
            search = .null; error = nil
            if let id = effectiveSearchID, let client = app.client {
                do {
                    let result = try await client.request("searches/\(id)")["search"]
                    if !Task.isCancelled, id == effectiveSearchID { search = result }
                }
                catch { if !Task.isCancelled { self.error = "Current alternatives unavailable: \(error.localizedDescription). Saved selection retained." } }
            }
        }
    }
}

private struct OptionEvidence: View {
    let choice: JSONValue
    var body: some View {
        List {
            ProductSummary(product: choice)
            Text("Product verified · placement fit pending")
            Text(choice["dimensions"].numbers.map { String(format: "%.3f", $0) }.joined(separator: " × ") + " m")
            ForEach(["practical", "style", "value"], id: \.self) { component in Text("\(component.capitalized): \(choice["reasons"][component].text)") }
            Text("Dimension check: \(choice["dimension_evidence"]["verified_at"].text)")
            if let url = URL(string: choice["dimension_evidence"]["source_url"].text), ["https", "http"].contains(url.scheme ?? "") { Link("Measurement evidence", destination: url) }
        }.navigationTitle("Option evidence")
    }
}

extension JSONValue: Identifiable { public var id: String { (try? String(data: data(), encoding: .utf8)) ?? "" } }
