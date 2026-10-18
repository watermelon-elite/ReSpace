import SwiftUI

/// A cached redesign of the bundled sample_room_2 scan. It needs no backend, so a demo still works offline.
struct DemoRedesignView: View {
    let app: AppModel
    static var modelURL: URL? { Bundle.main.url(forResource: "sample-room-2", withExtension: "usdz") }
    @State private var document: JSONValue = .null
    @State private var showAfter = true
    @State private var selectedID: String?
    @State private var loading = true
    @State private var error: String?
    @State private var reset = 0
    @State private var detail: JSONValue?
    @State private var shoppingList: ShoppingList?
    @State private var shoppingError: String?
    @State private var showNotes = false
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var design: JSONValue { document["design"] }
    private var selections: JSONValue { design["scene"]["selections"] }
    private var additions: [JSONValue] { document["additions"].array }
    private var total: String { design["scene"]["purchase_summary"]["total"].text }
    private var sceneDocument: JSONValue {
        guard !showAfter, case .object(var values) = document else { return document }
        values["hidden_nodes"] = .array([]); values["additions"] = .array([])
        return .object(values)
    }
    private var selectedProduct: JSONValue {
        guard let addition = additions.first(where: { $0["id"].text == selectedID }) else { return .null }
        return selections[addition["selection_id"].text]
    }
    private var selectedObjectLabel: String? {
        guard let selectedID else { return nil }
        return (document["entities"].array + document["removed"].array).first { $0["id"].text == selectedID }?["label"].string
    }

    var body: some View {
        VStack(spacing: 0) {
            RSTopBar(title: document["name"].string ?? "Meeting room", back: { dismiss() }, trailingSymbol: "bag",
                     trailingLabel: "Save and share shopping list", trailingProminent: true, trailingDisabled: document == .null,
                     trailing: { openShoppingList() })
            HStack(spacing: 8) {
                HStack(spacing: 0) {
                    segment("Before", selected: !showAfter) { showAfter = false }
                    segment("After", selected: showAfter) { showAfter = true }
                }.padding(3).background(.white, in: Capsule()).overlay { Capsule().stroke(ReSpaceStyle.line, lineWidth: 1) }
                Spacer()
                RSIconButton(symbol: "viewfinder", label: "Reset View") { reset += 1 }
                RSIconButton(symbol: "info.circle", label: "Design notes") { showNotes = true }
            }.padding(.horizontal, 16).padding(.bottom, 8)
            ZStack {
                if document != .null, let url = Self.modelURL {
                    RoomScene(document: sceneDocument, native: false, selectedID: $selectedID, ghosts: false, resetToken: reset,
                              zoomSteps: 2, importedModelURL: url, onModelLoad: { message in error = message; loading = false })
                        .accessibilityLabel(showAfter ? "Redesigned meeting room with three new IKEA pieces. Tap a piece to see its price. Drag to orbit, pinch to zoom." : "Original meeting room scan. Drag to orbit, pinch to zoom.")
                }
                if loading { ProgressView("Opening the room…").padding(24).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 20)) }
                if let error { RSNotice(message: error, isError: true).padding(24) }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
                .ignoresSafeArea(.container, edges: .bottom)
                .overlay(alignment: .bottom) { bottomCard.padding(12) }
        }
        .background(ReSpaceStyle.canvas).foregroundStyle(ReSpaceStyle.ink).font(ReSpaceStyle.font())
        .toolbar(.hidden, for: .navigationBar).navigationBarBackButtonHidden()
        .animation(reduceMotion ? nil : .easeOut(duration: 0.25), value: selectedID)
        .sensoryFeedback(.selection, trigger: selectedID)
        .onChange(of: showAfter) { _, _ in selectedID = nil; loading = true }
        .task {
            do {
                guard Self.modelURL != nil, let url = Bundle.main.url(forResource: "sample-room-2-redesign", withExtension: "json") else {
                    throw ContractError.invalid("The demo room is missing from this app build.")
                }
                document = try await Task.detached { try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: url)) }.value
                #if DEBUG
                if let index = ProcessInfo.processInfo.arguments.firstIndex(of: "--demo-select"), index + 1 < ProcessInfo.processInfo.arguments.count {
                    selectedID = ProcessInfo.processInfo.arguments[index + 1]
                }
                #endif
            } catch { self.error = error.localizedDescription; loading = false }
        }
        .sheet(item: $detail) { product in
            ProductDetail(app: app, product: product, searchID: nil, canSwap: false, onPreview: { _, _ in })
        }
        .sheet(item: $shoppingList) { ShoppingListView(list: $0) }
        .alert("Shopping list couldn’t be saved", isPresented: Binding(get: { shoppingError != nil }, set: { if !$0 { shoppingError = nil } })) {
            Button("OK", role: .cancel) { shoppingError = nil }
        } message: { Text(shoppingError ?? "") }
        .sheet(isPresented: $showNotes) { notes }
    }

    @ViewBuilder private var bottomCard: some View {
        if selectedProduct != .null {
            ProductSelectionCard(product: selectedProduct, onDetails: { detail = selectedProduct }, onClose: { selectedID = nil })
                .transition(.move(edge: .bottom).combined(with: .opacity)).id(selectedID)
        } else if let label = selectedObjectLabel {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(label).font(ReSpaceStyle.font(15, weight: .semibold))
                    Text(showAfter ? "Kept from your scan" : "Original scan").font(ReSpaceStyle.font(12)).foregroundStyle(ReSpaceStyle.secondary)
                }.frame(maxWidth: .infinity, alignment: .leading)
                RSIconButton(symbol: "xmark", label: "Clear selection") { selectedID = nil }
            }.padding(.leading, 16).padding(8).background(.white, in: RoundedRectangle(cornerRadius: 20))
                .overlay { RoundedRectangle(cornerRadius: 20).stroke(ReSpaceStyle.line, lineWidth: 1) }
                .transition(.opacity)
        } else if document != .null {
            VStack(alignment: .leading, spacing: 12) {
                OlloMessage(cue: .presenting, compact: true) {
                    Text(showAfter ? "Tap a new piece to see it." : "Your room as scanned. Switch to After to see the redesign.")
                        .font(ReSpaceStyle.font(14, weight: .medium))
                }
                if showAfter {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(additions, id: \.self) { addition in
                                let product = selections[addition["selection_id"].text]
                                Button { selectedID = addition["id"].text } label: {
                                    HStack(spacing: 10) {
                                        ProductImage(product: product).frame(width: 44, height: 44).clipShape(RoundedRectangle(cornerRadius: 10))
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(addition["label"].text).font(ReSpaceStyle.font(13, weight: .semibold))
                                            Text("$\(productPrice(product))").font(ReSpaceStyle.font(12)).foregroundStyle(ReSpaceStyle.secondary)
                                        }
                                    }.padding(6).padding(.trailing, 8).background(ReSpaceStyle.canvas, in: RoundedRectangle(cornerRadius: 16))
                                }.buttonStyle(.plain).accessibilityLabel("\(productTitle(product)), \(productPrice(product)) dollars")
                            }
                        }
                    }
                    Button { openShoppingList() } label: {
                        Text("\(additions.count) new pieces · $\(total)").font(ReSpaceStyle.font(13, weight: .semibold)).foregroundStyle(ReSpaceStyle.purple).frame(minHeight: 44)
                    }.buttonStyle(.plain).accessibilityHint("Opens the shopping list")
                }
            }.padding(16).background(.white, in: RoundedRectangle(cornerRadius: 24))
                .overlay { RoundedRectangle(cornerRadius: 24).stroke(ReSpaceStyle.line, lineWidth: 1).allowsHitTesting(false) }
                .transition(.opacity)
        }
    }

    private func segment(_ title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title).font(ReSpaceStyle.font(13, weight: .semibold)).padding(.horizontal, 16).frame(minHeight: 38)
                .foregroundStyle(selected ? ReSpaceStyle.purple : ReSpaceStyle.secondary)
                .background(selected ? ReSpaceStyle.wash : .clear, in: Capsule())
        }.buttonStyle(.plain).accessibilityAddTraits(selected ? .isSelected : []).disabled(loading)
    }

    private var notes: some View {
        RSPage(title: "Design notes", back: { showNotes = false }) {
            Text(design["scene"]["summary"].text)
            VStack(spacing: 0) {
                ForEach(additions, id: \.self) { addition in
                    let product = selections[addition["selection_id"].text]
                    RSKeyValue(title: "Added · \(productTitle(product))", value: "$\(productPrice(product))")
                }
                ForEach(document["removed"].array, id: \.self) { RSKeyValue(title: "Removed", value: $0["label"].text) }
            }
            RSNotice(message: "A cached demo design. The new pieces are AI reconstructions from IKEA product photos, sized to IKEA's published dimensions. Prices were checked on IKEA US on Oct 18, 2026; confirm them before buying.")
        } footer: { Button("Back to room") { showNotes = false }.buttonStyle(RSButtonStyle()) }
    }

    private func openShoppingList() {
        do {
            let list = try ShoppingList(design: design, roomName: document["name"].string ?? "Meeting room")
            try app.shoppingLists?.save(list)
            shoppingList = list
        } catch { shoppingError = error.localizedDescription }
    }
}
