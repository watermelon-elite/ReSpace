import Foundation

/// The original bytes stay journaled until a terminal outcome AND canonical refresh succeed.
/// No transport timeout is treated as proof that a command failed.
struct OperationRecovery: Sendable {
    let api: APIClient

    func reconcile(_ mutation: PendingMutation) async throws -> RoomOperation {
        if let known = try await api.lookup(mutation.id) {
            if known.state == .needsClarification, let continuation = mutation.continuation,
               mutation.continuationQuestionId == nil || known.clarification?.id == mutation.continuationQuestionId {
                return try await api.execute(continuation)
            }
            return known
        }
        return try await api.execute(mutation.original)
    }
}
