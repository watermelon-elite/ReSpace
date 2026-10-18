import Foundation
import Observation

@MainActor @Observable
final class RoomWorkspace {
    var record: ScanRoomRecord?
    var design: DesignVersion?
    var designSnapshot: RoomSnapshot?
    var conversation: [ConversationEntry] = []
    var draft = RoomDraft()
    var operation: RoomOperation?
    var pending: PendingMutation?
    var message: String?
    var error: String?
    var deleting = false
    var loading = false
    var answerSubmitting = false
    var isLocked: Bool {
        deleting || pending != nil || operation.map { !$0.state.isTerminal } == true ||
        record?.summary.currentOperationState.map { !$0.isTerminal } == true
    }
    var processingText: String? {
        if operation?.state == .needsClarification { return "Waiting for your answer" }
        guard isLocked else { return nil }
        if operation?.stage == "saving" { return "Saving…" }
        if operation?.kind == .generation || pending?.kind == .generation { return "Generating…" }
        return "Updating design…"
    }
}

@MainActor @Observable
final class WorkspaceStore {
    let api: ScanAPIClient
    let persistence: ClientPersistence
    let captures: CaptureRepository
    let localCaptureEnabled: Bool
    let reconstruction: ReconstructionClient?
    var rooms: [RoomSummary] = []
    var workspaces: [String: RoomWorkspace] = [:]
    var listError: String?
    var loading = false
    var deletionIds: Set<String> = []
    @ObservationIgnored private var tasks: [String: Task<Void, Never>] = [:]
    @ObservationIgnored private var bootstrapped = false

    init(configuration: AppConfiguration, deviceId: String) {
        localCaptureEnabled = configuration.localCaptureEnabled
        reconstruction = configuration.reconstructionURL.map { ReconstructionClient(baseURL: $0, token: configuration.reconstructionToken) }
        let directory = configuration.localCaptureEnabled
            ? configuration.storageURL.appendingPathComponent("LocalTesting", isDirectory: true)
            : configuration.storageURL
        api = ScanAPIClient(baseURL: configuration.serviceURL, appKey: configuration.appKey, deviceId: deviceId)
        persistence = ClientPersistence(directory: directory)
        captures = CaptureRepository(directory: directory.appendingPathComponent("Captures"),
                                     maximumFrames: configuration.localCaptureEnabled ? SamplingPolicy.reconstructionMaximumFrames : 40)
    }

    init(api: ScanAPIClient, persistence: ClientPersistence, captures: CaptureRepository) {
        localCaptureEnabled = false
        reconstruction = nil
        self.api = api; self.persistence = persistence; self.captures = captures
    }

    func workspace(_ id: String) -> RoomWorkspace {
        if let existing = workspaces[id] { return existing }
        let workspace = RoomWorkspace(); workspaces[id] = workspace; return workspace
    }

    func bootstrap() async {
        guard !localCaptureEnabled else { return }
        guard !bootstrapped else {
            do {
                let local = try await persistence.load()
                for id in local.deletions.keys { await deleteRoom(id) }
                for manifest in try await captures.manifests() where manifest.state == "abandoned" {
                    if manifest.roomId.isEmpty { await abandonUncertainDraft(manifest) }
                    else { await deleteRoom(manifest.roomId) }
                }
                for pending in local.mutations.values where !deletionIds.contains(pending.roomId) { resume(pending) }
            } catch { listError = error.localizedDescription }
            await refreshRooms(); return
        }
        do {
            let local = try await persistence.load()
            for (id, draft) in local.drafts { workspace(id).draft = draft }
            for id in local.deletions.keys { deletionIds.insert(id); workspace(id).deleting = true }
            for (id, pending) in local.mutations where !deletionIds.contains(id) {
                workspace(id).pending = pending
            }
            // An acquisition cannot be resumed after process death. Finished exports can.
            for manifest in try await captures.manifests() where manifest.state == "acquiring" || manifest.state == "creating" || manifest.state == "abandoned" {
                try await captures.abandon(manifest.captureId)
                if !manifest.roomId.isEmpty {
                    _ = try await persistence.markDeleted(roomId: manifest.roomId)
                    deletionIds.insert(manifest.roomId)
                } else {
                    // Reconcile draft creation with the same identity before deleting it.
                    await abandonUncertainDraft(manifest)
                }
            }
            bootstrapped = true
            for id in deletionIds { await deleteRoom(id) }
            for (id, pending) in local.mutations where !deletionIds.contains(id) { resume(pending) }
            await refreshRooms()
        } catch { listError = error.localizedDescription }
    }

    func refreshRooms() async {
        loading = true; defer { loading = false }
        do {
            var cursor: String?
            var found: [RoomSummary] = []
            repeat {
                let suffix = cursor.map { "?cursor=\(ScanAPIClient.segment($0))" } ?? ""
                let page: RoomList = try await api.get("rooms\(suffix)")
                guard page.schemaVersion == 1 else { throw ClientError.unsupportedSchema }
                found += page.rooms; cursor = page.nextCursor
            } while cursor != nil
            for summary in found where !deletionIds.contains(summary.id) { _ = workspace(summary.id) }
            rooms = found.filter { !deletionIds.contains($0.id) && $0.captureState == "completed" }
            listError = nil
            for summary in rooms {
                if let operationId = summary.currentOperationId,
                   summary.currentOperationState.map({ !$0.isTerminal }) == true,
                   tasks[summary.id] == nil, workspace(summary.id).pending == nil {
                    trackRemote(roomId: summary.id, operationId: operationId)
                }
            }
        } catch { listError = error.localizedDescription }
    }

    func refreshRoom(_ id: String) async throws {
        guard !deletionIds.contains(id) else { return }
        let state = workspace(id)
        let record = try await api.room(id)
        guard !deletionIds.contains(id) else { return }
        // A usable measured room can be reviewed even if conversation/design retrieval fails.
        state.record = record
        let conversation = try await loadConversation(id)
        var design: DesignVersion?
        var designSnapshot: RoomSnapshot?
        if let designId = record.summary.activeDesignId {
            design = try await api.design(designId)
            if let design {
                if record.snapshot?.id == design.roomSnapshotId { designSnapshot = record.snapshot }
                else { designSnapshot = try await api.snapshot(roomId: id, id: design.roomSnapshotId) }
            }
        }
        guard !deletionIds.contains(id) else { return }
        state.record = record; state.conversation = conversation
        state.design = design; state.designSnapshot = designSnapshot
        if let index = rooms.firstIndex(where: { $0.id == id }) { rooms[index] = record.summary }
        else if record.summary.captureState == "completed" { rooms.insert(record.summary, at: 0) }
        if tasks[id] == nil, state.pending == nil, let op = record.summary.currentOperationId,
           record.summary.currentOperationState.map({ !$0.isTerminal }) == true { trackRemote(roomId: id, operationId: op) }
    }

    private func loadConversation(_ id: String) async throws -> [ConversationEntry] {
        var cursor: String?
        var entries: [ConversationEntry] = []
        repeat {
            let suffix = cursor.map { "?cursor=\(ScanAPIClient.segment($0))" } ?? ""
            let page: ConversationPage = try await api.get("rooms/\(ScanAPIClient.segment(id))/conversation\(suffix)")
            guard page.schemaVersion == 1 else { throw ClientError.unsupportedSchema }
            entries += page.entries; cursor = page.nextCursor
        } while cursor != nil
        var seen = Set<String>()
        return entries.filter { seen.insert($0.id).inserted }.sorted { $0.createdAt < $1.createdAt }
    }

    func saveDraft(_ id: String) async {
        do { try await persistence.draft(workspace(id).draft, roomId: id) }
        catch { workspace(id).error = error.localizedDescription }
    }

    func generate(_ id: String, snapshotId: String) async {
        let state = workspace(id)
        guard !state.isLocked, let record = state.record, let inputs = state.draft.intent.inputs,
              record.snapshot?.validity.usable == true else { return }
        let operationId = UUID().uuidString
        let body = GenerationRequest(operationId: operationId, roomSnapshotId: snapshotId,
                                     planningRevision: record.planning.revision,
                                     expectedActiveDesignId: record.summary.activeDesignId,
                                     expectedActiveRevision: record.summary.activeRevision,
                                     intent: inputs.intent, styles: inputs.styles, budget: inputs.budget, text: inputs.text)
        do {
            await saveDraft(id)
            let request = try APIRequest.json(path: "rooms/\(ScanAPIClient.segment(id))/designs", identity: operationId, body: body)
            await submit(PendingMutation(id: operationId, roomId: id, kind: .generation, original: request))
        } catch { state.error = error.localizedDescription }
    }

    func command(_ id: String, designEditing: Bool, selectedId: String?) async {
        let state = workspace(id)
        guard !state.isLocked, let record = state.record, let snapshot = record.snapshot else { return }
        let text = (designEditing ? state.draft.designText : state.draft.reviewText).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        let operationId = UUID().uuidString
        let body = CommandRequest(operationId: operationId, message: text,
                                  selectedItemId: designEditing ? selectedId : nil,
                                  selectedObjectId: designEditing ? nil : selectedId,
                                  roomSnapshotId: designEditing ? (state.design?.roomSnapshotId ?? snapshot.id) : snapshot.id,
                                  planningRevision: designEditing ? (state.design?.planning.revision ?? record.planning.revision) : record.planning.revision,
                                  expectedActiveDesignId: record.summary.activeDesignId,
                                  expectedActiveRevision: record.summary.activeRevision)
        do {
            let path: String
            if designEditing {
                guard let design = state.design, design.id == record.summary.activeDesignId else { return }
                path = "designs/\(ScanAPIClient.segment(design.id))/chat"
            } else { path = "rooms/\(ScanAPIClient.segment(id))/planning-commands" }
            let request = try APIRequest.json(path: path, identity: operationId, body: body)
            let pending = PendingMutation(id: operationId, roomId: id, kind: designEditing ? .edit : .planning, original: request)
            await submit(pending)
            // Clear only after the exact command is safely in the journal.
            if state.pending?.id == operationId {
                if designEditing { state.draft.designText = "" } else { state.draft.reviewText = "" }
                await saveDraft(id)
            }
        } catch { state.error = error.localizedDescription }
    }

    func undo(_ id: String) async {
        let state = workspace(id)
        guard !state.isLocked, let design = state.design, design.parentId != nil, let record = state.record,
              design.id == record.summary.activeDesignId else { return }
        let operationId = UUID().uuidString
        do {
            let body = UndoRequest(operationId: operationId, expectedActiveDesignId: design.id,
                                   expectedActiveRevision: record.summary.activeRevision)
            let request = try APIRequest.json(path: "rooms/\(ScanAPIClient.segment(id))/undo", identity: operationId, body: body)
            await submit(PendingMutation(id: operationId, roomId: id, kind: .undo, original: request))
        } catch { state.error = error.localizedDescription }
    }

    private func submit(_ pending: PendingMutation) async {
        let state = workspace(pending.roomId)
        guard !state.isLocked else { return }
        // Reserve immediately, before the first suspension point.
        state.pending = pending; state.error = nil; state.message = nil
        do {
            try await persistence.journal(pending)
            resume(pending, firstSubmission: true)
        } catch { state.pending = nil; state.error = error.localizedDescription }
    }

    func retry(_ id: String) {
        let state = workspace(id)
        if let pending = state.pending { resume(pending) }
        else if let operation = state.operation { trackRemote(roomId: id, operationId: operation.id) }
    }

    func answer(_ id: String, text: String?, dismiss: Bool = false) async {
        let state = workspace(id)
        guard let operation = state.operation, let question = operation.clarification,
              operation.state == .needsClarification, tasks[id] == nil, !state.answerSubmitting else { return }
        state.answerSubmitting = true
        defer { state.answerSubmitting = false }
        do {
            // A remote pending operation can also be resumed after installing on a new phone.
            var pending = state.pending ?? PendingMutation(id: operation.id, roomId: id, kind: operation.kind,
                                                          original: APIRequest(method: "GET", path: "operations/\(ScanAPIClient.segment(operation.id))"))
            if pending.continuation == nil {
                pending.continuationQuestionId = question.id
                let replyId = UUID().uuidString
                if dismiss {
                    pending.continuation = try .json(path: "operations/\(ScanAPIClient.segment(operation.id))/dismiss-clarification", identity: replyId,
                                                    body: DismissalRequest(operationId: operation.id, questionId: question.id, dismissalId: replyId))
                } else {
                    guard let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
                    pending.continuation = try .json(path: "operations/\(ScanAPIClient.segment(operation.id))/clarifications", identity: replyId,
                                                    body: ClarificationRequest(operationId: operation.id, questionId: question.id, replyId: replyId,
                                                                               reply: text, replyToken: question.replyToken,
                                                                               originalRequest: pending.original.body ?? Data()))
                }
                try await persistence.journal(pending)
            }
            state.pending = pending
            resume(pending, firstSubmission: true)
        } catch { state.error = error.localizedDescription }
    }

    private func resume(_ pending: PendingMutation, firstSubmission: Bool = false) {
        guard tasks[pending.roomId] == nil, !deletionIds.contains(pending.roomId) else { return }
        let id = pending.roomId
        tasks[id] = Task { [self] in
            defer { tasks[id] = nil }
            do {
                let operation: RoomOperation
                if firstSubmission { operation = try await api.execute(pending.continuation ?? pending.original) }
                else { operation = try await OperationRecovery(api: api).reconcile(pending) }
                guard operation.id == pending.id, operation.roomId == pending.roomId else { throw ClientError.invalidResponse }
                try await follow(operation, pending: pending)
            } catch {
                guard !deletionIds.contains(id) else { return }
                let state = workspace(id)
                state.error = error.localizedDescription
                // Explicit rejection of a submission is definitive; transport errors are uncertain.
                if firstSubmission, let serverError = error as? APIErrorEnvelope, !serverError.retryable,
                   ["stale_base", "unavailable_capability", "invalid_room", "intent_conflict", "rejected", "invalid_request"].contains(serverError.code) {
                    do {
                        try await persistence.clearMutation(roomId: id, id: pending.id)
                        state.pending = nil; state.operation = nil
                        await restoreFailedCommand(pending)
                        try await refreshRoom(id)
                    } catch { state.error = error.localizedDescription }
                }
            }
        }
    }

    private func follow(_ initial: RoomOperation, pending: PendingMutation?) async throws {
        var operation = initial
        let id = initial.roomId
        while !deletionIds.contains(id) {
            guard operation.schemaVersion == 1 else { throw ClientError.unsupportedSchema }
            guard operation.id == initial.id, operation.roomId == id else { throw ClientError.invalidResponse }
            let state = workspace(id)
            state.operation = operation
            if operation.state.isTerminal {
                try await refreshRoom(id)
                guard !deletionIds.contains(id) else { return }
                if let pending { try await persistence.clearMutation(roomId: id, id: pending.id) }
                state.pending = nil
                state.message = operation.outcome?.summary
                state.error = operation.failure?.message
                if operation.state != .succeeded, let pending { await restoreFailedCommand(pending) }
                return
            }
            if operation.state == .needsClarification {
                // A canonical response acknowledges this reply, allowing a later distinct question.
                if var pending, pending.continuation != nil {
                    pending.continuation = nil
                    pending.continuationQuestionId = nil
                    try await persistence.journal(pending)
                    state.pending = pending
                }
                return
            }
            try await Task.sleep(for: .seconds(2))
            guard let next = try await api.lookup(operation.id) else { throw ClientError.invalidResponse }
            operation = next
        }
    }

    private func restoreFailedCommand(_ pending: PendingMutation) async {
        guard let data = pending.original.body,
              let command = try? Wire.decoder().decode(CommandRequest.self, from: data) else { return }
        let state = workspace(pending.roomId)
        if pending.kind == .edit, state.draft.designText.isEmpty { state.draft.designText = command.message }
        if pending.kind == .planning, state.draft.reviewText.isEmpty { state.draft.reviewText = command.message }
        await saveDraft(pending.roomId)
    }

    private func trackRemote(roomId: String, operationId: String) {
        guard tasks[roomId] == nil, !deletionIds.contains(roomId) else { return }
        tasks[roomId] = Task { [self] in
            defer { tasks[roomId] = nil }
            do {
                guard let operation = try await api.lookup(operationId) else { throw ClientError.invalidResponse }
                try await follow(operation, pending: nil)
            } catch { workspace(roomId).error = error.localizedDescription }
        }
    }

    func rename(_ id: String, name: String) async {
        let state = workspace(id)
        let summary = state.record?.summary ?? rooms.first { $0.id == id }
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let summary, !name.isEmpty, !deletionIds.contains(id) else { return }
        do {
            let request = try APIRequest.json(method: "PATCH", path: "rooms/\(ScanAPIClient.segment(id))", identity: UUID().uuidString,
                                             body: RenameRoomRequest(name: name, expectedMetadataRevision: summary.metadataRevision))
            let updated: RoomSummary = try await api.execute(request)
            guard !deletionIds.contains(id) else { return }
            if let index = rooms.firstIndex(where: { $0.id == id }) { rooms[index] = updated }
            state.record?.summary.name = updated.name
            state.record?.summary.metadataRevision = updated.metadataRevision
        } catch { listError = error.localizedDescription; state.error = error.localizedDescription }
    }

    func deleteRoom(_ id: String) async {
        let state = workspace(id)
        do {
            let deletion = try await persistence.markDeleted(roomId: id)
            deletionIds.insert(id); state.deleting = true
            tasks[id]?.cancel(); tasks[id] = nil
            let result: DeletionResult = try await api.execute(APIRequest(method: "DELETE", path: "rooms/\(ScanAPIClient.segment(id))", identity: deletion.identity))
            guard result.schemaVersion == 1, result.deleted else { throw ClientError.http(503) }
            try await captures.removeRoom(id)
            try await persistence.confirmDeleted(roomId: id)
            rooms.removeAll { $0.id == id }; workspaces[id] = nil
            // Keep a session tombstone even after server acknowledgment.
        } catch { state.error = "Deletion pending. \(error.localizedDescription)"; listError = state.error }
    }

    func abandonUncertainDraft(_ manifest: CaptureManifest) async {
        do {
            let request = try CaptureRepository.creationRequest(manifest)
            let result: DraftRoomResult = try await api.execute(request)
            await deleteRoom(result.summary.id)
            try await captures.removeCapture(manifest.captureId)
        } catch { listError = "Draft cleanup pending. \(error.localizedDescription)" }
    }
}
