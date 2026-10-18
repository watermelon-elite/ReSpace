import Foundation
import XCTest
@testable import ReSpaceCore

@MainActor final class WorkspaceLifecycleTests: XCTestCase {
    private func fixture<T: Decodable>(_ name: String, as: T.Type) throws -> T {
        let url = try XCTUnwrap(Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures"))
        return try Wire.decoder().decode(T.self, from: Data(contentsOf: url))
    }
    private func setup(_ mode: LifecycleTransport.Mode) throws -> (WorkspaceStore, LifecycleTransport, URL) {
        let room = try fixture("room", as: ScanRoomRecord.self)
        let design = try fixture("design", as: DesignVersion.self)
        let transport = LifecycleTransport(room: room, design: design, mode: mode)
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let api = ScanAPIClient(baseURL: URL(string: "https://rooms.example.com"), appKey: "test", deviceId: "device", transport: transport)
        let store = WorkspaceStore(api: api, persistence: ClientPersistence(directory: directory),
                                   captures: CaptureRepository(directory: directory.appendingPathComponent("Captures")))
        let state = store.workspace("room_1")
        state.record = room; state.design = design; state.designSnapshot = room.snapshot
        store.rooms = [room.summary]
        addTeardownBlock { try? FileManager.default.removeItem(at: directory) }
        return (store, transport, directory)
    }
    private func eventually(_ condition: @escaping @MainActor () -> Bool) async throws {
        for _ in 0..<200 {
            if condition() { return }
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTFail("State did not settle")
    }

    func testOneCommandCreatesOneVersionAndDuplicateSubmissionIsBlocked() async throws {
        let (store, transport, _) = try setup(.commit)
        let state = store.workspace("room_1")
        state.draft.designText = "Unlock this sofa and move it to the window"
        let first = Task { await store.command("room_1", designEditing: true, selectedId: "i_sofa") }
        let second = Task { await store.command("room_1", designEditing: true, selectedId: "i_sofa") }
        await first.value; await second.value
        try await eventually { state.pending == nil && state.design?.id == "design_3" }
        XCTAssertEqual(state.design?.parentId, "design_2")
        XCTAssertEqual(state.record?.summary.activeDesignId, "design_3")
        let postCount = await transport.postCount
        XCTAssertEqual(postCount, 1)
    }

    func testRejectedMultiActionCommandLeavesWholeVersionUnchanged() async throws {
        let (store, transport, _) = try setup(.reject)
        let state = store.workspace("room_1")
        let original = state.design
        state.draft.designText = "Move the sofa and block the doorway"
        await store.command("room_1", designEditing: true, selectedId: nil)
        try await eventually { state.pending == nil && state.operation?.state == .rejected }
        XCTAssertEqual(state.design, original)
        XCTAssertEqual(state.error, "The chair would block the door.")
        XCTAssertEqual(state.draft.designText, "Move the sofa and block the doorway")
        let postCount = await transport.postCount
        XCTAssertEqual(postCount, 1)
    }

    func testLostResponseRelaunchUsesOperationLookupWithoutDuplicatingEdit() async throws {
        let (store, transport, directory) = try setup(.lostResponse)
        let state = store.workspace("room_1")
        state.draft.designText = "Move this beside the window"
        await store.command("room_1", designEditing: true, selectedId: "i_sofa")
        try await eventually { state.error != nil }
        XCTAssertTrue(state.isLocked)
        XCTAssertEqual(state.design?.id, "design_2")
        let pending = try await store.persistence.load().mutations["room_1"]
        XCTAssertNotNil(pending)
        let recovered = WorkspaceStore(api: store.api, persistence: ClientPersistence(directory: directory),
                                       captures: CaptureRepository(directory: directory.appendingPathComponent("Captures")))
        await recovered.bootstrap()
        try await eventually { recovered.workspace("room_1").pending == nil && recovered.workspace("room_1").design?.id == "design_3" }
        XCTAssertEqual(recovered.workspace("room_1").record?.summary.activeDesignId, "design_3")
        let postCount = await transport.postCount
        XCTAssertEqual(postCount, 1)
    }

    func testUndoUsesPersistedParentAndNextEditBranchesFromRestoredVersion() async throws {
        let (store, transport, _) = try setup(.commit)
        let state = store.workspace("room_1")
        await store.undo("room_1")
        try await eventually { state.pending == nil && state.design?.id == "design_1" }
        XCTAssertNil(state.design?.parentId)
        state.draft.designText = "Make the room warmer"
        await store.command("room_1", designEditing: true, selectedId: nil)
        try await eventually { state.pending == nil && state.design?.id == "design_3" }
        XCTAssertEqual(state.design?.parentId, "design_1")
        let history = await transport.designs
        XCTAssertNotNil(history["design_2"])
        XCTAssertEqual(history["design_2"]?.parentId, "design_1")
    }

    func testConfirmedDeletionDiscardsLateCommandResult() async throws {
        let (store, transport, _) = try setup(.slowResponse)
        let state = store.workspace("room_1")
        state.draft.designText = "Move this"
        await store.command("room_1", designEditing: true, selectedId: "i_sofa")
        for _ in 0..<100 {
            if await transport.postCount > 0 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        await store.deleteRoom("room_1")
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertTrue(store.rooms.isEmpty)
        XCTAssertNil(store.workspaces["room_1"])
        XCTAssertTrue(store.deletionIds.contains("room_1"))
        let local = try await store.persistence.load()
        XCTAssertNil(local.mutations["room_1"])
        XCTAssertNil(local.deletions["room_1"])
    }
}

private actor LifecycleTransport: HTTPTransport {
    enum Mode: Sendable { case commit, reject, lostResponse, slowResponse }
    var room: ScanRoomRecord
    private(set) var designs: [String: DesignVersion]
    private(set) var postCount = 0
    var operations: [String: RoomOperation] = [:]
    var deleted = false
    let mode: Mode

    init(room: ScanRoomRecord, design: DesignVersion, mode: Mode) {
        self.room = room; self.mode = mode
        var parent = design; parent.id = "design_1"; parent.parentId = nil
        designs = [design.id: design, parent.id: parent]
    }
    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let path = request.url!.path
        func response<T: Encodable>(_ value: T) throws -> (Data, HTTPURLResponse) {
            (try Wire.encoder().encode(value), HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!)
        }
        if request.httpMethod == "DELETE" {
            deleted = true
            return try response(DeletionResult(schemaVersion: 1, deleted: true))
        }
        if request.httpMethod == "GET" {
            if path == "/v1/rooms" { return try response(RoomList(schemaVersion: 1, rooms: deleted ? [] : [room.summary])) }
            if path.hasSuffix("/conversation") { return try response(ConversationPage(schemaVersion: 1, entries: [])) }
            if path == "/v1/rooms/room_1" { return try response(room) }
            if path.contains("/operations/"), let operation = operations[String(path.split(separator: "/").last!)] { return try response(operation) }
            if path.contains("/designs/"), let design = designs[String(path.split(separator: "/").last!)] { return try response(design) }
        }
        if request.httpMethod == "POST" {
            postCount += 1
            let id = request.value(forHTTPHeaderField: "Idempotency-Key")!
            var operation = RoomOperation(schemaVersion: 1, id: id, roomId: "room_1", kind: path.hasSuffix("/undo") ? .undo : .edit, state: .succeeded)
            if mode == .reject {
                operation.state = .rejected
                operation.failure = APIErrorEnvelope(code: "blocked_doorway", message: "The chair would block the door.", retryable: false)
            } else if path.hasSuffix("/undo") {
                let active = designs[room.summary.activeDesignId!]!
                room.summary.activeDesignId = active.parentId
                room.summary.activeRevision += 1
                operation.outcome = OperationOutcome(designId: active.parentId, activeRevision: room.summary.activeRevision, summary: "Undid the last change.", messageIds: ["undo_event"])
            } else {
                var child = designs[room.summary.activeDesignId!]!
                child.parentId = room.summary.activeDesignId; child.id = "design_3"
                designs[child.id] = child
                room.summary.activeDesignId = child.id; room.summary.activeRevision += 1
                operation.outcome = OperationOutcome(designId: child.id, activeRevision: room.summary.activeRevision, summary: "Updated the room.", messageIds: ["edit_event"])
            }
            operations[id] = operation
            if mode == .lostResponse { throw URLError(.timedOut) }
            if mode == .slowResponse { try? await Task.sleep(for: .milliseconds(400)) }
            return try response(operation)
        }
        throw URLError(.badServerResponse)
    }
}
