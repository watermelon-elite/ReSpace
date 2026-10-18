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

    func testFindMorePresentationRetainsSavedChoiceAndAppendsUnseenOptions() throws {
        let selected = try fixture("api/roundtrip.json")["design"]["design"]["scene"]["selections"]["sel"]
        func choice(_ variant: String, price: String = "60.00") -> JSONValue {
            var fields = selected.object
            fields["variant_id"] = .string(variant)
            var offer = selected["offer"].object
            offer["variant_id"] = .string(variant); offer["price"] = .string(price)
            fields["offer"] = .object(offer)
            var evidence = selected["dimension_evidence"].object
            evidence["variant_id"] = .string(variant)
            fields["dimension_evidence"] = .object(evidence)
            return .object(fields)
        }
        let search: JSONValue = .object([
            "prior_displayed_choices": .array([choice("prior1"), selected, choice("prior2")]),
            "displayed_choices": .array([choice("new1"), choice("new2"), choice("new3"), choice("prior1"), choice("v", price: "99.00")])
        ])
        let choices = ProductOptions.choices(selected: selected, search: search)
        XCTAssertEqual(choices.map { $0["variant_id"].text }, ["v", "prior1", "prior2", "new1", "new2", "new3"])
        XCTAssertEqual(choices.first?["offer"]["price"].text, "50.00")
        XCTAssertEqual(selected["offer"]["price"].text, "50.00")
        XCTAssertEqual(ProductOptions.choices(selected: selected, search: .null), [selected])
    }

    func testNumericQuestionSupportsTouchAnswersWithinServerBoundsAndStep() {
        let bounded = NumericQuestion(.object(["numeric_min": .number(2), "numeric_max": .number(3), "numeric_step": .number(0.5)]))
        XCTAssertEqual(bounded.initialValue, 2)
        XCTAssertTrue(bounded.isValid(bounded.initialValue))
        XCTAssertEqual(bounded.next(2, direction: 1), 2.5)
        XCTAssertEqual(bounded.next(2.5, direction: 1), 3)
        XCTAssertNil(bounded.next(3, direction: 1))
        XCTAssertNil(bounded.next(2, direction: -1))
        XCTAssertFalse(bounded.isValid(2.25))
        XCTAssertFalse(bounded.isValid(.infinity))
        let unbounded = NumericQuestion(.object([:]))
        XCTAssertEqual(unbounded.initialValue, 0)
        XCTAssertEqual(unbounded.next(1_000_000, direction: 1), 1_000_001)
        XCTAssertEqual(unbounded.next(0, direction: -1), -1)
    }

    func testSwapPreviewChangesOnlyTargetGeometryAndNeverSavedPurchases() throws {
        let scene = try fixture("api/roundtrip.json")["design"]["design"]["scene"]
        var choice = scene["selections"]["sel"].object
        let dimensions: JSONValue = .array([.number(1.2), .number(0.6), .number(0.8)])
        choice["dimensions"] = dimensions
        var evidence = choice["dimension_evidence"]!.object; evidence["dimensions"] = dimensions; choice["dimension_evidence"] = .object(evidence)
        let preview = try SwapPreview(scene: scene, itemID: "i_a_0", choice: .object(choice), searchID: "search-current", activeRevision: 3)
        let shown = preview.scene(over: scene)
        XCTAssertEqual(shown["items"].array[0]["placement"]["position"], scene["items"].array[0]["placement"]["position"])
        XCTAssertEqual(shown["items"].array[0]["placement"]["yaw"], scene["items"].array[0]["placement"]["yaw"])
        XCTAssertEqual(shown["items"].array[0]["placement"]["size"], dimensions)
        XCTAssertEqual(shown["purchase_summary"], scene["purchase_summary"])
        XCTAssertEqual(scene["items"].array[0]["placement"]["size"].numbers, [1, 0.5, 0.7])
        XCTAssertEqual(preview.requestBody["expected_active_revision"]?.int, 3)
        XCTAssertEqual(preview.requestBody["offer_id"], scene["selections"]["sel"]["offer"]["offer_id"])
        XCTAssertEqual(preview.requestBody["search_id"]?.text, "search-current")
    }

    func testAnswerRevisionUsesOriginalQuestionAndCurrentDecisionIdentity() throws {
        let source = try fixture("api/roundtrip.json")["operation"]["operation"]
        let question = source["pending_question"]
        let entry: JSONValue = .object(["answer_id": .string("answer-original"), "question": question, "request": .object(["choice_ids": .array([.string("work")]), "action": .string("answer")])])
        var operation = source.object
        operation["answer_history"] = .array([entry]); operation["decision_revision"] = .number(4); operation["answer_revision_allowed"] = .bool(true)
        let fields = try AnswerHistory.revisionIdentity(answerID: "answer-original", operation: .object(operation))
        XCTAssertEqual(fields["question_id"], question["question_id"])
        XCTAssertEqual(fields["expected_question_revision"]?.int, 1)
        XCTAssertEqual(fields["expected_decision_revision"]?.int, 4)
        XCTAssertEqual(fields["revision_of_answer_id"]?.text, "answer-original")
        XCTAssertEqual(AnswerHistory.summary(entry), "Working from home")
        operation["answer_revision_allowed"] = .bool(false)
        XCTAssertThrowsError(try AnswerHistory.revisionIdentity(answerID: "answer-original", operation: .object(operation)))
    }

    func testSharedSpatialRelationsDesignKeepsElevationsSupportsAndPurchases() throws {
        let transport = try fixture("spatial-relations-v1.json")
        let saved = try SavedDesign(envelope: transport["design_envelope"])
        XCTAssertEqual(saved.items.count, 5)
        let items = Dictionary(uniqueKeysWithValues: saved.items.map { ($0["id"].text, $0) })
        XCTAssertEqual(items["i_o_light"]?["placement"]["position"].numbers[1], 2.3)
        XCTAssertEqual(items["i_lamp_0"]?["placement"]["position"].numbers[1], 0.7)
        XCTAssertEqual(items["i_lamp_0"]?["placement"]["support_id"].text, "i_desk_0")
        XCTAssertEqual(items["i_art_0"]?["placement"]["position"].numbers[1], 1.2)
        XCTAssertEqual(items["i_art_0"]?["placement"]["wall_id"].text, "w_1")
        XCTAssertEqual(items["i_desk_0"]?["placement"]["position"].numbers[0], items["i_rug_0"]?["placement"]["position"].numbers[0])
        XCTAssertEqual(saved.value["scene"]["purchase_summary"]["total"].text, "400.00")
    }

    func testSharedAPIAnswerRevisionPreservesHistoryAndNextRequiredQuestion() throws {
        let transport = try fixture("api/wave2.json")
        let before = transport["revision_before"]["operation"], after = transport["revision_after"]["operation"]
        let expected = transport["revision_request"]
        let identity = try AnswerHistory.revisionIdentity(answerID: expected["revision_of_answer_id"].text, operation: before)
        for field in ["revision_of_answer_id", "question_id", "expected_question_revision", "expected_decision_revision"] { XCTAssertEqual(identity[field], expected[field]) }
        XCTAssertEqual(after["decision_revision"].int, before["decision_revision"].int + 1)
        XCTAssertEqual(after["answer_history"].array.count, before["answer_history"].array.count + 1)
        XCTAssertEqual(after["answer_history"].array.first, before["answer_history"].array.first)
        XCTAssertEqual(AnswerHistory.summary(try XCTUnwrap(after["answer_history"].array.last)), "Relaxation")
        let question = after["pending_question"]
        XCTAssertEqual(question["allow_skip"].bool, false); XCTAssertEqual(question["allow_delegate"].bool, false)
        XCTAssertEqual(NumericQuestion(question).initialValue, 1)
        XCTAssertTrue(NumericQuestion(question).isValid(1))
    }
    func testSharedAPISwapPreviewAdoptsOnlyValidatedChildAndRetainsParentPrice() throws {
        let transport = try fixture("api/wave2.json")
        let parent = try SavedDesign(envelope: transport["swap_parent"])
        let child = try SavedDesign(envelope: transport["swap_child"])
        let request = transport["swap_request"]
        let targetID = request["item_id"].text
        let original = try XCTUnwrap(parent.items.first { $0["id"].text == targetID })
        let replacement = try XCTUnwrap(child.items.first { $0["id"].text == targetID })
        let choice = child.value["scene"]["selections"][replacement["selection_id"].text]
        let preview = try SwapPreview(scene: parent.value["scene"], itemID: targetID, choice: choice, searchID: request["search_id"].text, activeRevision: request["expected_active_revision"].int)
        let shown = preview.scene(over: parent.value["scene"])
        XCTAssertEqual(shown["purchase_summary"]["total"].text, "50.00")
        XCTAssertEqual(parent.value["scene"]["purchase_summary"]["total"].text, "50.00")
        XCTAssertEqual(child.value["scene"]["purchase_summary"]["total"].text, "70.00")
        XCTAssertEqual(replacement["placement"]["position"], original["placement"]["position"])
        XCTAssertEqual(replacement["placement"]["yaw"], original["placement"]["yaw"])
        XCTAssertEqual(replacement["placement"]["size"].numbers, [0.8, 0.4, 0.7])
        XCTAssertEqual(transport["swap_success"]["operation"]["outcome"]["design_id"], child.value["design_id"])
        XCTAssertEqual(transport["swap_rejected"]["operation"]["state"].text, "rejected")
        XCTAssertEqual(transport["swap_rejected"]["operation"]["outcome"]["action_outcomes"].array.first?["code"].text, "collision")
    }

}
