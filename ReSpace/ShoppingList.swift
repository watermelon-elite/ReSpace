import Foundation
import Observation

struct ShoppingList: Codable, Identifiable, Equatable {
    struct Line: Codable, Identifiable, Equatable {
        let id: String
        let title: String
        let merchant: String
        let url: URL
        let packCount: Int
        let suppliedCount: Int
        let surplusCount: Int
        let total: String

        var quantity: String { "\(packCount) \(packCount == 1 ? "pack" : "packs") · \(suppliedCount) supplied" }
        var priceLabel: String { "USD \(total) · \(packCount) \(packCount == 1 ? "pack" : "packs")" }
    }

    let id: String
    let roomID: String
    let roomName: String
    let savedAt: Date
    let lines: [Line]
    let total: String
    let approvedCeiling: String?
    let fitPending: Bool

    init(design: JSONValue, roomName: String, savedAt: Date = Date()) throws {
        try self.init(id: design["design_id"].text, roomID: design["room_id"].text, roomName: roomName,
                      summary: design["scene"]["purchase_summary"], products: Array(design["scene"]["selections"].object.values),
                      fitPending: false, savedAt: savedAt)
    }

    init(operation: JSONValue, roomName: String, savedAt: Date = Date()) throws {
        guard operation["state"].text == "succeeded", operation["outcome"]["result_kind"].text == "selection" else {
            throw ContractError.invalid("Complete a Product plan to collect its shopping links.")
        }
        let selection = operation["controller"]["selection"]
        try self.init(id: selection["selection_snapshot_id"].text, roomID: operation["room_id"].text, roomName: roomName,
                      summary: selection["purchases"], products: selection["selected"].array,
                      fitPending: true, savedAt: savedAt)
    }

    private init(id: String, roomID: String, roomName: String, summary: JSONValue, products: [JSONValue], fitPending: Bool, savedAt: Date) throws {
        guard !id.isEmpty, !roomID.isEmpty,
              case .array(let purchases) = summary["lines"], summary["currency"].text == "USD",
              Self.validAmount(summary["total"].text) else {
            throw ContractError.invalid("The shopping list is incomplete. Reopen the saved design and try again.")
        }
        var offers = Set<String>()
        lines = try purchases.map { line in
            let offer = line["offer"]
            guard !line["offer_id"].text.isEmpty, offers.insert(line["offer_id"].text).inserted,
                  offer["offer_id"] == line["offer_id"], offer["currency"].text == "USD",
                  let url = URL(string: offer["product_url"].text), url.scheme == "https",
                  let host = url.host, !host.isEmpty, url.user == nil, url.password == nil,
                  line["purchased_pack_count"].int > 0, line["supplied_unit_count"].int > 0,
                  let surplus = line["paid_surplus_count"].number.flatMap(Int.init(exactly:)), surplus >= 0,
                  surplus <= line["supplied_unit_count"].int,
                  Self.validAmount(line["line_total"].text) else {
                throw ContractError.invalid("A purchase is missing its exact link, quantity or price. Reopen the saved design and try again.")
            }
            let titles = products.filter { $0["offer"]["offer_id"] == line["offer_id"] }
                .map { $0["title"].string ?? $0["variant"]["title"].text }.filter { !$0.isEmpty }
            let title = Set(titles).sorted().joined(separator: " + ")
            return Line(id: line["offer_id"].text, title: title.isEmpty ? "Selected Product" : title,
                        merchant: offer["merchant"].string ?? host, url: url,
                        packCount: line["purchased_pack_count"].int, suppliedCount: line["supplied_unit_count"].int,
                        surplusCount: surplus, total: line["line_total"].text)
        }
        self.id = id
        self.roomID = roomID
        self.roomName = roomName
        self.savedAt = savedAt
        total = summary["total"].text
        approvedCeiling = summary["approved_ceiling"].string
        self.fitPending = fitPending
    }

    var shareText: String {
        let purchases = lines.enumerated().map { index, line in
            "\(index + 1). \(line.title) — \(line.merchant)\n\(line.quantity) · USD \(line.total)"
                + (line.surplusCount > 0 ? "\n\(line.surplusCount) unplaced paid units" : "")
                + "\n\(line.url.absoluteString)"
        }
        return (["ReSpace shopping list — \(roomName)\(fitPending ? "\nProduct plan · room fit is still pending." : "")"] + purchases
                + ["Total: USD \(total)", "Saved prices. Whole packs included; existing Objects, tax and shipping excluded. Confirm price and availability with each merchant."])
            .joined(separator: "\n\n")
    }

    var postPages: [[Line]] {
        stride(from: 0, to: lines.count, by: 4).map { Array(lines[$0..<min($0 + 4, lines.count)]) }
    }

    var postCaption: String {
        shareText + "\n\nRoom image is a placeholder. Price labels show the saved purchases, not the furniture pictured."
    }

    private static func validAmount(_ value: String) -> Bool {
        value.range(of: #"^[0-9]+(?:\.[0-9]{1,2})?$"#, options: .regularExpression) != nil
    }
}

@MainActor @Observable final class ShoppingListStore {
    private let fileURL: URL
    private(set) var lists: [ShoppingList]

    init(fileURL: URL) throws {
        self.fileURL = fileURL
        lists = FileManager.default.fileExists(atPath: fileURL.path)
            ? try JSONDecoder().decode([ShoppingList].self, from: Data(contentsOf: fileURL)) : []
    }

    func save(_ list: ShoppingList) throws {
        try replace([list] + lists.filter { $0.roomID != list.roomID })
    }

    func remove(roomID: String) throws {
        guard lists.contains(where: { $0.roomID == roomID }) else { return }
        try replace(lists.filter { $0.roomID != roomID })
    }

    private func replace(_ updated: [ShoppingList]) throws {
        try JSONEncoder().encode(updated).write(to: fileURL, options: [.atomic, .completeFileProtectionUnlessOpen])
        lists = updated
    }
}
