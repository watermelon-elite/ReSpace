import XCTest
@testable import ReSpaceContracts

final class Wave3ContractsTests: XCTestCase {
    private func fixture(_ path: String) throws -> JSONValue {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        return try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: root.appendingPathComponent("backend/tests/fixtures/" + path)))
    }

    func testRemovedProductRetainsIdentityAndRequiresRestorablePlacement() throws {
        var envelope = try fixture("api/roundtrip.json")["design"].object
        var design = envelope["design"]!.object
        var scene = design["scene"]!.object
        var item = scene["items"]!.array[0].object
        let placement = item["placement"]!
        let identity = item["id"]!, selection = item["selection_id"]!
        item["status"] = .string("removed"); item.removeValue(forKey: "last_valid_placement")
        scene["items"] = .array([.object(item)]); design["scene"] = .object(scene); envelope["design"] = .object(design)
        XCTAssertThrowsError(try SavedDesign(envelope: .object(envelope)))

        item["last_valid_placement"] = placement
        scene["items"] = .array([.object(item)]); design["scene"] = .object(scene); envelope["design"] = .object(design)
        let saved = try SavedDesign(envelope: .object(envelope))
        XCTAssertEqual(saved.items[0]["id"], identity)
        XCTAssertEqual(saved.items[0]["selection_id"], selection)
        XCTAssertEqual(saved.items[0]["last_valid_placement"], placement)
        XCTAssertTrue(SceneItems.visible(in: saved.value["scene"], showGhosts: true).isEmpty)
    }

    func testSharedRemoveAndRestoreTransportRetainsSupportChainAndPurchaseEvidence() throws {
        let transport = try fixture("api/removal-v1.json")
        let parent = try SavedDesign(envelope: transport["parent"])
        let removed = try SavedDesign(envelope: transport["removed"])
        let restored = try SavedDesign(envelope: transport["restored"])
        XCTAssertEqual(parent.items.count, 3)
        XCTAssertEqual(transport["remove_operation"]["operation"]["outcome"], transport["remove_replay"]["operation"]["outcome"])
        XCTAssertEqual(removed.value["parent_id"], parent.value["design_id"])
        XCTAssertTrue(SceneItems.visible(in: removed.value["scene"], showGhosts: true).isEmpty)
        for original in parent.items {
            let retained = try XCTUnwrap(removed.items.first { $0["id"] == original["id"] })
            XCTAssertEqual(retained["last_valid_placement"], original["placement"])
            XCTAssertEqual(retained["product"], original["product"])
        }
        XCTAssertEqual(parent.value["scene"]["purchase_summary"]["total"].text, "60.00")
        XCTAssertEqual(removed.value["scene"]["purchase_summary"]["total"].text, "0.00")
        XCTAssertEqual(restored.value["scene"]["purchase_summary"]["total"].text, "20.00")
        XCTAssertEqual(SceneItems.visible(in: restored.value["scene"], showGhosts: true).map { $0["id"].text }, ["i_a_0"])
        XCTAssertEqual(transport["remove_operation"]["operation"]["outcome"]["warnings"].array.map { $0["code"].text }, ["dependent_omitted", "dependent_omitted"])
    }

    func testSharedObservedColorSnapshotUsesSampledAndDefaultTintsWithoutTintingReplacementProducts() throws {
        let transport = try fixture("api/observed-color-v1.json")
        let saved = try SavedDesign(envelope: transport["design"])
        let room = transport["snapshot"]["snapshot"]["room"]
        XCTAssertEqual(saved.value["scene"]["room"], room)
        let sampled = try XCTUnwrap(saved.items.first { $0["render"]["tint"].text == "#408141" })
        let fallback = try XCTUnwrap(saved.items.first { $0["id"] != sampled["id"] })
        XCTAssertEqual(ObservedColor.hex(for: sampled, room: room), "#408141")
        XCTAssertEqual(ObservedColor.hex(for: fallback, room: room), fallback["render"]["tint"].text)
        var replacement = sampled.object
        replacement["selection_id"] = .string("new-product")
        replacement["render"] = .object(["tint": .string("#112233")])
        XCTAssertEqual(ObservedColor.hex(for: .object(replacement), room: room), "#112233")
    }
}
