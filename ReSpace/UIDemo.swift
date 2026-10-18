#if DEBUG
import SwiftUI

/// In-memory responses for the real screens. Never reads or writes saved Rooms.
@MainActor final class UIDemoSession {
    private let sample: JSONValue
    var room: JSONValue
    private var design: JSONValue
    private var operation: JSONValue = .null
    private var instructions: [JSONValue] = []
    private var entries: [JSONValue] = []
    private var deleted = false

    init() {
        do {
            let url = Bundle.main.url(forResource: "UIDemo", withExtension: "json")!
            sample = try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: url))
            room = sample["room"]
            design = sample["design"]
            _ = try RoomRecord(room)
            _ = try SavedDesign(envelope: .object(["schema_version": .number(1), "design": design]))
            _ = try ShoppingList(design: design, roomName: room["name"].text)
        } catch { preconditionFailure("Invalid UI sample data: \(error)") }
    }

    var roomID: String { room["room_id"].text }
    var designID: String { design["design_id"].text }
    var product: JSONValue { design["scene"]["selections"]["lamp"] }
    var shoppingList: ShoppingList { try! ShoppingList(design: design, roomName: room["name"].text, savedAt: Date(timeIntervalSince1970: 1_792_262_700)) }
    var question: JSONValue { sample["question"] }
    var ready: JSONValue {
        replacing(question, ["state": .string("succeeded"), "pending_question": .null,
            "outcome": .object(["design_id": .string(designID), "message": .string("Your room has a warmer, softer feel."), "result_kind": .string("design")])])
    }
    var generating: JSONValue {
        replacing(question, ["state": .string("running"), "pending_question": .null,
            "phase": .string("planning"), "progress_message": .string("Finding pieces that fit your room and your budget.")])
    }

    static func roomImage() throws -> Data {
        guard let data = UIImage(named: "RoomInspiration")?.jpegData(compressionQuality: 0.9) else {
            throw ContractError.invalid("The bundled room image is missing.")
        }
        return data
    }

    func request(_ path: String, method: String, body: JSONValue) throws -> JSONValue {
        let parts = path.split(separator: "/").map(String.init)
        let last = parts.last ?? ""
        if path == "rooms", method == "GET" { return .object(["rooms": .array(deleted ? [] : [room])]) }
        if path == "catalog/manifest" { return .object(["assets": .array([])]) }
        if last == "conversation" { return .object(["entries": .array(entries)]) }
        if parts.first == "searches" { return .object(["search": .object(["displayed_choices": .array([product])])]) }
        if parts.first == "designs", method == "GET" {
            return .object(["schema_version": .number(1), "design": design])
        }
        if parts.first == "operations", method == "GET" { return .object(["operation": operation == .null ? ready : operation]) }
        if parts.first == "rooms", parts.count == 2 {
            if method == "DELETE" { deleted = true; return .object(["deletion": .object(["state": .string("deleted")])]) }
            if method == "PATCH" { room = replacing(room, ["name": body["name"]]) }
            return .object(["room": room, "raw_export": sample["raw_export"], "measured_context": sample["measured_context"],
                "planning": .object(["planning_revision": .number(0), "instructions": .array(instructions)]),
                "capture_status": .object(["manifest": .object(["artifacts": .array([.object(["kind": .string("jpeg"), "artifact_id": .string("demo-photo")])])])]),
                "current_operation": operation])
        }
        if method == "POST" {
            if last == "planning-commands", let target = body["selected_object"]["id"].string {
                let text = body["text"].text.lowercased()
                let value = text.contains("unlock") ? "decide" : text.contains("keep") ? "keep" : "remove"
                instructions.removeAll { $0["target"]["id"].text == target }
                instructions.append(.object(["target": .object(["id": .string(target)]), "instruction": .string(value)]))
            }
            if last == "remove" {
                var scene = design["scene"].object
                scene["items"] = .array(design["scene"]["items"].array.filter { $0["id"] != body["item_id"] })
                let lines = design["scene"]["purchase_summary"]["lines"].array.filter { $0["offer_id"] != body["item_id"] }
                let total = lines.reduce(Decimal.zero) { $0 + (Decimal(string: $1["line_total"].text) ?? 0) }
                scene["purchase_summary"] = replacing(design["scene"]["purchase_summary"], ["lines": .array(lines), "total": .string(NSDecimalNumber(decimal: total).stringValue)])
                // shortcut: demo Undo restores the sample; real version history stays backend-owned.
                design = replacing(design, ["scene": .object(scene), "parent_id": .string("demo-original")])
            }
            if last == "undo" { design = sample["design"] }
            operation = last == "designs" ? question : ready
            if last == "cancel" || last == "dismiss-clarification" {
                operation = replacing(ready, ["state": .string("cancelled"), "outcome": .null])
            }
            if let text = body["text"].string, !text.isEmpty {
                entries.append(.object(["role": .string("user"), "text": .string(text)]))
                entries.append(.object(["role": .string("assistant"), "text": .string("A warmer palette and softer lighting will make this room feel more inviting.")]))
            }
            return .object(["operation": operation])
        }
        throw ContractError.invalid("UI demo does not simulate \(method) \(path).")
    }

    private func replacing(_ value: JSONValue, _ fields: [String: JSONValue]) -> JSONValue {
        .object(value.object.merging(fields) { _, new in new })
    }
}

enum UIDemoScreen: String, CaseIterable, Identifiable {
    case rooms = "My Rooms", room = "Room review", design = "Design", question = "Question"
    case generating = "Generating", ready = "Ready", product = "Product", shopping = "Shopping list", share = "Share images"
    var id: String { rawValue }
}

struct UIDemoGallery: View {
    @State private var selected: UIDemoScreen?
    var body: some View {
        NavigationStack {
            RSPage(title: "UI studio", topTitle: "ReSpace", showsBack: false) {
                Text("Real screens, sample data. Choose a screen to rehearse or record. Relaunch to reset.")
                    .foregroundStyle(ReSpaceStyle.secondary)
                ForEach(UIDemoScreen.allCases) { screen in
                    Button { selected = screen } label: { RSRow(title: screen.rawValue, symbol: "iphone") }.buttonStyle(.plain)
                }
            } footer: { EmptyView() }
        }
        .fullScreenCover(item: $selected) { screen in
            UIDemoPreview(screen)
                .simultaneousGesture(LongPressGesture(minimumDuration: 1.5).onEnded { _ in selected = nil })
        }
    }
}

struct UIDemoPreview: View {
    let screen: UIDemoScreen
    @State private var app: AppModel
    @State private var operation: JSONValue

    init(_ screen: UIDemoScreen) {
        self.screen = screen
        ReSpaceStyle.registerFonts()
        let app = AppModel(demo: true)
        _app = State(initialValue: app)
        let session = app.uiDemo!
        _operation = State(initialValue: screen == .generating ? session.generating : screen == .ready ? session.ready : session.question)
    }

    var body: some View {
        NavigationStack {
            if let session = app.uiDemo {
                switch screen {
                case .rooms: ContentView(app: app)
                case .room: RoomReview(app: app, roomID: session.roomID)
                case .design: DesignView(app: app, roomID: session.roomID, designID: session.designID)
                case .question, .generating, .ready:
                    OperationPanel(app: app, operation: $operation, onUpdate: {})
                case .product:
                    ProductDetail(app: app, product: session.product, searchID: "demo-search", canSwap: true, onPreview: { _, _ in })
                case .shopping: ShoppingListView(list: session.shoppingList)
                case .share: ShoppingShareView(list: session.shoppingList)
                }
            }
        }
        .tint(ReSpaceStyle.purple).font(ReSpaceStyle.font()).preferredColorScheme(.light)
        .toolbar(.hidden, for: .navigationBar)
        .environment(\.openURL, OpenURLAction { _ in .handled })
    }
}

#Preview("Screen picker") { UIDemoGallery() }
#endif
