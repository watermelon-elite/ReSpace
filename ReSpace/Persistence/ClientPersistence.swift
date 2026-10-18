import Foundation

struct RoomDraft: Codable, Sendable {
    var intent = ScanIntentDraft()
    var reviewText = ""
    var designText = ""
}
struct PendingMutation: Codable, Identifiable, Sendable {
    var id: String
    var roomId: String
    var kind: OperationKind
    var original: APIRequest
    var continuation: APIRequest?
    var continuationQuestionId: String?
}
struct PendingDeletion: Codable, Sendable {
    var roomId: String
    var identity: String
}
struct LocalState: Codable, Sendable {
    var drafts: [String: RoomDraft] = [:]
    var mutations: [String: PendingMutation] = [:]
    var deletions: [String: PendingDeletion] = [:]
}

/// One actor serializes atomic state writes. Failures are surfaced before sending mutations.
actor ClientPersistence {
    private let directory: URL
    private var cached: LocalState?
    init(directory: URL) { self.directory = directory }

    func load() throws -> LocalState {
        if let cached { return cached }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent("client-state.json")
        let state = FileManager.default.fileExists(atPath: url.path) ? try Wire.decoder().decode(LocalState.self, from: Data(contentsOf: url)) : LocalState()
        cached = state
        return state
    }
    private func save(_ state: LocalState) throws {
        let data = try Wire.encoder().encode(state)
        try data.write(to: directory.appendingPathComponent("client-state.json"), options: .atomic)
        cached = state
    }
    func draft(_ draft: RoomDraft, roomId: String) throws {
        var state = try load(); state.drafts[roomId] = draft; try save(state)
    }
    func journal(_ mutation: PendingMutation) throws {
        var state = try load()
        guard state.deletions[mutation.roomId] == nil else { throw ClientError.storage("This room is being deleted.") }
        if let pending = state.mutations[mutation.roomId], pending.id != mutation.id {
            throw ClientError.storage("Another command is still pending for this room.")
        }
        state.mutations[mutation.roomId] = mutation; try save(state)
    }
    func clearMutation(roomId: String, id: String) throws {
        var state = try load()
        if state.mutations[roomId]?.id == id { state.mutations[roomId] = nil; try save(state) }
    }
    func markDeleted(roomId: String) throws -> PendingDeletion {
        var state = try load()
        if let pending = state.deletions[roomId] { return pending }
        let pending = PendingDeletion(roomId: roomId, identity: UUID().uuidString)
        state.deletions[roomId] = pending
        try save(state)
        return pending
    }
    func confirmDeleted(roomId: String) throws {
        var state = try load()
        state.deletions[roomId] = nil; state.mutations[roomId] = nil; state.drafts[roomId] = nil
        try save(state)
    }
}
