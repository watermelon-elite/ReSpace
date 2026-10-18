import XCTest
@testable import ReSpaceContracts

final class OlloTests: XCTestCase {
    private func operation(state: String = "succeeded", kind: String = "design", actions: [String] = [], design: String? = "design-1") -> JSONValue {
        .object(["operation_id": .string("operation-1"), "state": .string(state), "outcome": .object([
            "result_kind": .string(kind), "design_id": design.map(JSONValue.string) ?? .null,
            "action_outcomes": .array(actions.map { .object(["outcome": .string($0)]) })
        ])])
    }

    func testOnlyCompleteCommittedDesignsCanCelebrate() {
        XCTAssertEqual(OlloCue.operation(operation()), .saved(operation: "operation-1", design: "design-1"))
        for state in ["failed", "cancelled", "rejected"] {
            XCTAssertEqual(OlloCue.operation(operation(state: state)), .presenting)
        }
        XCTAssertEqual(OlloCue.operation(operation(kind: "selection")), .presenting)
        XCTAssertEqual(OlloCue.operation(operation(design: nil)), .presenting)
        XCTAssertEqual(OlloCue.operation(operation(actions: ["applied", "failed"])), .presenting)
        XCTAssertEqual(OlloCue.operation(operation(actions: ["rejected"])), .presenting)
    }

    func testPollingKeepsQuestionIdentityButRevisionChangesIt() {
        func question(_ revision: Int) -> JSONValue {
            .object(["operation_id": .string("operation-1"), "pending_question": .object([
                "question_id": .string("question-1"), "question_revision": .number(Double(revision))
            ])])
        }
        XCTAssertEqual(OlloCue.operation(question(1)), OlloCue.operation(question(1)))
        XCTAssertNotEqual(OlloCue.operation(question(1)).eventID, OlloCue.operation(question(2)).eventID)
    }

    func testNavigationAndPollingNeverReplayGesturesOrCelebrateHistory() async {
        await MainActor.run {
            let session = OlloSession()
            XCTAssertTrue(session.begin(.welcome))
            XCTAssertFalse(session.begin(.welcome))
            XCTAssertFalse(session.begin(.saved(operation: "historical", design: "old")))
            XCTAssertTrue(session.begin(.question(operation: "new", id: "q", revision: 1)))
            XCTAssertFalse(session.begin(.question(operation: "new", id: "q", revision: 1)))
            XCTAssertFalse(session.begin(.listening))
            XCTAssertTrue(session.begin(.saved(operation: "new", design: "new-design")))
            XCTAssertFalse(session.begin(.saved(operation: "new", design: "new-design")))
        }
    }
}
