import XCTest
@testable import ReSpaceContracts
final class ContractsTests: XCTestCase {
    func testBudgetAcceptsOnlyPositiveUSDDecimals() {
        XCTAssertTrue(IntentDraft.validBudget("1200.05"))
        for value in ["", "0", "0.00", "-1", "1.234", "1e2", "nan", " 1", ".50"] { XCTAssertFalse(IntentDraft.validBudget(value), value) }
    }
    func testSamplingCoalescesTriggersAndEnforcesCapAndMotion() {
        var gate = SamplingGate()
        XCTAssertTrue(gate.accept(time: 1, position: [0, 0, 0], forward: [0, 0, -1], trackingNormal: true))
        XCTAssertFalse(gate.accept(time: 1.1, position: [1, 0, 0], forward: [1, 0, 0], trackingNormal: true))
        XCTAssertTrue(gate.accept(time: 4.5, position: [1, 0, 0], forward: [1, 0, 0], trackingNormal: true))
        for i in 1...38 { XCTAssertTrue(gate.accept(time: 4.5 + Double(i) * 2, position: [1, 0, 0], forward: [1, 0, 0], trackingNormal: true)) }
        XCTAssertFalse(gate.accept(time: 200, position: [1, 0, 0], forward: [1, 0, 0], trackingNormal: true))
        XCTAssertEqual(gate.count, 40)
    }
    func testPlacementPreservesNonFloorElevationAndAxisOrder() throws {
        let value = try JSONDecoder().decode(JSONValue.self, from: Data(#"{"position":[1,1.4,-2],"yaw":0.4,"size":[0.8,0.04,0.6],"mount":"wall","wall_id":"w1"}"#.utf8))
        let placement = try Placement(value)
        XCTAssertEqual(placement.position, [1, 1.4, -2])
        XCTAssertEqual(placement.size, [0.8, 0.04, 0.6])
        XCTAssertEqual(placement.mount, "wall")
        XCTAssertThrowsError(try Placement(.object(["position": .array([.number(1)])])))
    }
    private func fixture(_ path: String) throws -> JSONValue {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        return try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: root.appendingPathComponent("backend/tests/fixtures/" + path)))
    }
    func testActualAPIRoundtripDecodesSavedRoomQuestionAndExactBuyLink() throws {
        let transport = try fixture("api/roundtrip.json")
        let detail = transport["room_detail"]
        let room = try RoomRecord(detail["room"]).value
        XCTAssertEqual(room["capture_state"].text, "complete")
        XCTAssertEqual(detail["capture_status"]["missing_artifacts"].int, 0)
        let saved = try SavedDesign(envelope: transport["design"])
        XCTAssertEqual(saved.value["design_id"], room["active_design_id"])
        let product = try ProductChoice(saved.value["scene"]["selections"]["sel"])
        XCTAssertEqual(product.exactOfferURL.absoluteString, "https://example.com/chair")
        XCTAssertEqual(product.value["offer"]["price"].text, "50.00")
        XCTAssertEqual(saved.value["scene"]["purchase_summary"]["total"].text, "50.00")
        let question = transport["operation"]["operation"]["pending_question"]
        XCTAssertEqual(question["choices"].array.map { $0["choice_id"].text }, ["relax", "work"])
        XCTAssertEqual(question["question_revision"].int, 1)
        XCTAssertEqual(question["allow_skip"].bool, true)
    }
    func testUnverifiedOrMismatchedSavedProductCannotOpenBuy() throws {
        let original = try fixture("api/roundtrip.json")["design"]["design"]["scene"]["selections"]["sel"]
        var fields = original.object; var evidence = fields["dimension_evidence"]!.object
        evidence["outcome"] = .string("unverified"); fields["dimension_evidence"] = .object(evidence)
        XCTAssertThrowsError(try ProductChoice(.object(fields)))
        evidence = original["dimension_evidence"].object; evidence["dimensions"] = .array([.number(2), .number(1), .number(1)])
        fields["dimension_evidence"] = .object(evidence)
        XCTAssertThrowsError(try ProductChoice(.object(fields)))
    }
    func testSharedSnapshotRetainsTabletopElevationAndSupport() throws {
        let room = try fixture("spatial/supported_objects_v1.json")["snapshot"]["room"]
        let tv = try XCTUnwrap(room["objects"].array.first { $0["category"].text == "tv" })
        XCTAssertEqual(tv["base_y"].number, 0.75)
        XCTAssertEqual(tv["size"].numbers, [0.7, 0.08, 0.4])
        XCTAssertEqual(tv["mount"].text, "tabletop")
        XCTAssertEqual(tv["support_id"].text, "o_1")
        let placement = try Placement(.object(["position": .array([.number(2), tv["base_y"], .number(1.5)]), "size": tv["size"], "yaw": tv["yaw"], "mount": tv["mount"]]))
        XCTAssertEqual(placement.position[1] + placement.size[2] / 2, 0.95, accuracy: 0.00001)
    }
    func testHiddenGhostAndRemovedNewItemAreAbsentFromHitTestEntities() {
        let scene: JSONValue = .object(["items": .array([
            .object(["id": .string("kept"), "origin": .string("existing"), "status": .string("existing")]),
            .object(["id": .string("ghost"), "origin": .string("existing"), "status": .string("removed")]),
            .object(["id": .string("new"), "origin": .string("new"), "status": .string("removed")])])])
        XCTAssertEqual(SceneItems.visible(in: scene, showGhosts: false).map { $0["id"].text }, ["kept"])
        XCTAssertEqual(SceneItems.visible(in: scene, showGhosts: true).map { $0["id"].text }, ["kept", "ghost"])
    }
    func testPendingRequestRetainsExactPayloadAcrossRelaunch() throws {
        let request = PendingRequest(path: "rooms/r/designs", roomID: "r", body: ["operation_id": .string("op-original"), "budget": .string("123.45"), "expected_active_revision": .number(4)])
        let recovered = try JSONDecoder().decode(PendingRequest.self, from: JSONEncoder().encode(request))
        XCTAssertEqual(recovered.operationID, "op-original")
        XCTAssertEqual(recovered.body, request.body)
        XCTAssertEqual(recovered.body["budget"].text, "123.45")
        XCTAssertEqual(recovered.body["expected_active_revision"].int, 4)
    }

}
