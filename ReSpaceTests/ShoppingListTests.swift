import XCTest
@testable import ReSpaceContracts

final class ShoppingListTests: XCTestCase {
    private func fixture(_ name: String = "roundtrip") throws -> JSONValue {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        return try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: root.appendingPathComponent("backend/tests/fixtures/api/\(name).json")))
    }

    func testCollectsEveryPurchaseLinkWithoutRoomDataOrDuplicateUnits() throws {
        var fields = try fixture("removal-v1")["parent"]["design"].object
        fields["room_id"] = .string("private-room-identity")
        var scene = fields["scene"]!.object
        var summary = scene["purchase_summary"]!.object
        summary["lines"] = .array(summary["lines"]!.array.map { value in
            var line = value.object
            var offer = line["offer"]!.object
            offer["product_url"] = .string("https://example.com/\(line["offer_id"]!.text)?variant=exact")
            line["offer"] = .object(offer)
            return .object(line)
        })
        scene["purchase_summary"] = .object(summary); fields["scene"] = .object(scene)
        let design = JSONValue.object(fields)
        let list = try ShoppingList(design: design, roomName: "Living room")
        XCTAssertEqual(list.lines.count, 3)
        XCTAssertEqual(list.total, "60.00")
        for line in list.lines {
            XCTAssertEqual(list.shareText.components(separatedBy: line.url.absoluteString).count, 2)
            XCTAssertTrue(list.shareText.contains(line.title))
            XCTAssertTrue(list.shareText.contains(line.quantity))
        }
        XCTAssertTrue(list.shareText.contains("tax and shipping excluded"))
        XCTAssertFalse(list.shareText.contains(design["room_id"].text))
        XCTAssertFalse(list.shareText.contains("floor"))
    }

    func testOnlyCompletedProductPlansCanBeSharedAndPendingFitStaysVisible() throws {
        let design = try fixture()["design"]["design"]
        var operation: [String: JSONValue] = ["room_id": design["room_id"], "state": .string("succeeded"),
            "outcome": .object(["result_kind": .string("selection")]),
            "controller": .object(["selection": design["selection_snapshot"]])]
        let list = try ShoppingList(operation: .object(operation), roomName: "Kitchenette")
        XCTAssertEqual(list.lines.count, 1)
        XCTAssertTrue(list.fitPending)
        XCTAssertTrue(list.shareText.contains("room fit is still pending"))
        operation["state"] = .string("running")
        XCTAssertThrowsError(try ShoppingList(operation: .object(operation), roomName: "Kitchenette"))
    }

    func testWholePackQuantitiesAndPaidSurplusComeFromPurchaseSummary() throws {
        var design = try fixture()["design"]["design"].object
        var scene = design["scene"]!.object
        var summary = scene["purchase_summary"]!.object
        var line = summary["lines"]!.array[0].object
        line["purchased_pack_count"] = .number(2)
        line["supplied_unit_count"] = .number(4)
        line["paid_surplus_count"] = .number(1)
        line["line_total"] = .string("100.00")
        summary["lines"] = .array([.object(line)]); summary["total"] = .string("100.00")
        var selections = scene["selections"]!.object
        selections["same-offer"] = selections["sel"]
        scene["selections"] = .object(selections); scene["purchase_summary"] = .object(summary)
        design["scene"] = .object(scene)
        let list = try ShoppingList(design: .object(design), roomName: "Room")
        XCTAssertEqual(list.lines.count, 1)
        XCTAssertEqual(list.lines[0].title, "Measured desk")
        XCTAssertEqual(list.lines[0].packCount, 2)
        XCTAssertEqual(list.total, "100.00")
        XCTAssertTrue(list.shareText.contains("2 packs · 4 supplied · USD 100.00"))
        XCTAssertTrue(list.shareText.contains("1 unplaced paid units"))
    }

    func testRemovedProductsDoNotSurviveInShoppingList() throws {
        let transport = try fixture("removal-v1")
        let removed = try ShoppingList(design: transport["removed"]["design"], roomName: "Room")
        XCTAssertTrue(removed.lines.isEmpty)
        XCTAssertEqual(removed.total, "0.00")
        let restored = try ShoppingList(design: transport["restored"]["design"], roomName: "Room")
        XCTAssertEqual(restored.lines.count, 1)
        XCTAssertEqual(restored.total, "20.00")
    }

    func testInvalidLinkOrIncompleteSummaryCannotBeSavedAsAnEmptyOrPartialList() throws {
        var design = try fixture()["design"]["design"].object
        var scene = design["scene"]!.object
        let original = scene["purchase_summary"]!
        for url in ["", "https:///", "javascript:alert(1)", "file:///private/data", "https://user:password@example.com/product"] {
            var summary = original.object
            var line = summary["lines"]!.array[0].object
            var offer = line["offer"]!.object
            offer["product_url"] = .string(url); line["offer"] = .object(offer)
            summary["lines"] = .array([.object(line)]); scene["purchase_summary"] = .object(summary)
            design["scene"] = .object(scene)
            XCTAssertThrowsError(try ShoppingList(design: .object(design), roomName: "Room"), url)
        }
        scene["purchase_summary"] = .null; design["scene"] = .object(scene)
        XCTAssertThrowsError(try ShoppingList(design: .object(design), roomName: "Room"))
        var summary = original.object
        var line = summary["lines"]!.array[0].object
        line["paid_surplus_count"] = .number(0.5)
        summary["lines"] = .array([.object(line)]); scene["purchase_summary"] = .object(summary)
        design["scene"] = .object(scene)
        XCTAssertThrowsError(try ShoppingList(design: .object(design), roomName: "Room"))
    }

    @MainActor func testSavedListsSurviveRelaunchReplaceOnlyTheirRoomAndDelete() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let url = folder.appendingPathComponent("shopping-lists.json")
        let store = try ShoppingListStore(fileURL: url)
        let transport = try fixture("removal-v1")
        let first = try ShoppingList(design: transport["parent"]["design"], roomName: "Living room")
        let other = try ShoppingList(design: fixture()["design"]["design"], roomName: "Office")
        try store.save(first); try store.save(other); try store.save(first)
        XCTAssertEqual(store.lists.count, 2)
        let relaunched = try ShoppingListStore(fileURL: url)
        XCTAssertEqual(relaunched.lists, store.lists)
        let removed = try ShoppingList(design: transport["removed"]["design"], roomName: "Living room")
        try relaunched.save(removed)
        XCTAssertEqual(relaunched.lists.count, 2)
        XCTAssertEqual(relaunched.lists.first, removed)
        XCTAssertTrue(relaunched.lists.contains(other))
        try relaunched.remove(roomID: first.roomID)
        XCTAssertEqual(try ShoppingListStore(fileURL: url).lists, [other])
    }

    @MainActor func testFailedSaveKeepsLastSuccessfulListAndCorruptFileIsNotOverwritten() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let url = folder.appendingPathComponent("shopping-lists.json")
        let store = try ShoppingListStore(fileURL: url)
        let list = try ShoppingList(design: fixture()["design"]["design"], roomName: "Room")
        try store.save(list)
        try FileManager.default.removeItem(at: url)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        XCTAssertThrowsError(try store.remove(roomID: list.roomID))
        XCTAssertEqual(store.lists, [list])
        try FileManager.default.removeItem(at: url)
        let corrupt = Data("invalid JSON".utf8)
        try corrupt.write(to: url)
        XCTAssertThrowsError(try ShoppingListStore(fileURL: url))
        XCTAssertEqual(try Data(contentsOf: url), corrupt)
    }
}
