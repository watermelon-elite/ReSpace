import Foundation

enum OperationState: String, Codable, Sendable {
    case queued, running, needsClarification = "needs_clarification"
    case succeeded, rejected, failed, cancelled
    var isTerminal: Bool { [.succeeded, .rejected, .failed, .cancelled].contains(self) }
}
enum OperationKind: String, Codable, Sendable { case generation, planning, edit, undo, finalize }
struct RoomOperation: Codable, Identifiable, Sendable {
    var schemaVersion: Int
    var id: String
    var roomId: String
    var kind: OperationKind
    var state: OperationState
    var stage: String?
    var clarification: Clarification?
    var outcome: OperationOutcome?
    var failure: APIErrorEnvelope?
    var messageIds: [String]?
}
struct OperationOutcome: Codable, Sendable {
    var designId: String?
    var roomSnapshotId: String?
    var activeRevision: Int?
    var planningRevision: Int?
    var summary: String?
    var messageIds: [String]
}
struct Clarification: Codable, Identifiable, Sendable {
    var questionId: String
    var text: String
    var candidates: [ClarificationCandidate]
    var replyToken: String?
    var id: String { questionId }
}
struct ClarificationCandidate: Codable, Identifiable, Sendable {
    var id: String
    var label: String
}
struct ConversationEntry: Codable, Identifiable, Sendable {
    var id: String
    var roomId: String
    var context: String
    var role: String
    var text: String
    var createdAt: String
    var operationId: String?
    var baseDesignId: String?
    var roomSnapshotId: String?
    var planningRevision: Int?
    var selectedItemId: String?
    var selectedObjectId: String?
    var resultingVersionId: String?
    var fromDesignId: String?
    var toDesignId: String?
    var delivery: String?
}
struct ConversationPage: Codable, Sendable {
    var schemaVersion: Int
    var entries: [ConversationEntry]
    var nextCursor: String?
}
struct APIErrorEnvelope: Codable, Error, LocalizedError, Sendable {
    var code: String
    var message: String
    var retryable: Bool
    var field: String?
    var operationId: String?
    var currentRevision: Int?
    var details: [String: JSONValue]?
    var errorDescription: String? { message }
}

struct GenerationRequest: Codable, Sendable {
    var schemaVersion = 1
    var operationId: String
    var roomSnapshotId: String
    var planningRevision: Int
    var expectedActiveDesignId: String?
    var expectedActiveRevision: Int
    var intent: DesignIntent
    var styles: [DesignStyle]
    var budget: String
    var currency = "USD"
    var text: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion, operationId, roomSnapshotId, planningRevision, expectedActiveDesignId
        case expectedActiveRevision, intent, styles, budget, currency, text
    }
    func encode(to encoder: any Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(schemaVersion, forKey: .schemaVersion)
        try values.encode(operationId, forKey: .operationId)
        try values.encode(roomSnapshotId, forKey: .roomSnapshotId)
        try values.encode(planningRevision, forKey: .planningRevision)
        try values.encode(expectedActiveDesignId, forKey: .expectedActiveDesignId)
        try values.encode(expectedActiveRevision, forKey: .expectedActiveRevision)
        try values.encode(intent, forKey: .intent)
        try values.encode(styles, forKey: .styles)
        try values.encode(budget, forKey: .budget)
        try values.encode(currency, forKey: .currency)
        try values.encode(text, forKey: .text)
    }
}
struct CommandRequest: Codable, Sendable {
    var schemaVersion = 1
    var operationId: String
    var message: String
    var selectedItemId: String?
    var selectedObjectId: String?
    var roomSnapshotId: String
    var planningRevision: Int
    var expectedActiveDesignId: String?
    var expectedActiveRevision: Int

    enum CodingKeys: String, CodingKey {
        case schemaVersion, operationId, message, selectedItemId, selectedObjectId, roomSnapshotId
        case planningRevision, expectedActiveDesignId, expectedActiveRevision
    }
    func encode(to encoder: any Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(schemaVersion, forKey: .schemaVersion)
        try values.encode(operationId, forKey: .operationId)
        try values.encode(message, forKey: .message)
        try values.encodeIfPresent(selectedItemId, forKey: .selectedItemId)
        try values.encodeIfPresent(selectedObjectId, forKey: .selectedObjectId)
        try values.encode(roomSnapshotId, forKey: .roomSnapshotId)
        try values.encode(planningRevision, forKey: .planningRevision)
        try values.encode(expectedActiveDesignId, forKey: .expectedActiveDesignId)
        try values.encode(expectedActiveRevision, forKey: .expectedActiveRevision)
    }
}
struct UndoRequest: Codable, Sendable {
    var schemaVersion = 1
    var operationId: String
    var expectedActiveDesignId: String
    var expectedActiveRevision: Int
}
struct ClarificationRequest: Codable, Sendable {
    var schemaVersion = 1
    var operationId: String
    var questionId: String
    var replyId: String
    var reply: String
    var replyToken: String?
    var originalRequest: Data
}
struct DismissalRequest: Codable, Sendable {
    var schemaVersion = 1
    var operationId: String
    var questionId: String
    var dismissalId: String
}
