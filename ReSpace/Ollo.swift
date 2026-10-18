import Foundation

enum OlloCue: Equatable {
    case idle, welcome, listening, presenting
    case thinking(String), question(operation: String, id: String, revision: Int), saved(operation: String, design: String)

    static func operation(_ operation: JSONValue) -> Self {
        let question = operation["pending_question"]
        if question != .null {
            return .question(operation: operation["operation_id"].text, id: question["question_id"].text, revision: question["question_revision"].int)
        }
        if ["queued", "running"].contains(operation["state"].text) { return .thinking(operation["operation_id"].text) }
        let outcome = operation["outcome"]
        if operation["state"].text == "succeeded", outcome["result_kind"].text == "design",
           !outcome["design_id"].text.isEmpty, outcome["warnings"].array.isEmpty,
           outcome["action_outcomes"].array.allSatisfy({ $0["outcome"].text == "applied" }) {
            return .saved(operation: operation["operation_id"].text, design: outcome["design_id"].text)
        }
        return operation == .null ? .idle : .presenting
    }

    var pose: String {
        switch self {
        case .listening, .question: "04-listening"
        case .thinking: "05-thinking"
        case .presenting, .saved: "09-presenting"
        default: "01-idle"
        }
    }
    var eventID: String? {
        switch self {
        case .welcome: "welcome"
        case .question(let operation, let id, let revision): "question:\(operation):\(id):\(revision)"
        case .saved(let operation, let design): "saved:\(operation):\(design)"
        default: nil
        }
    }
    var frames: [(String, Int)] {
        switch self {
        case .welcome: [("02-wave-a", 180), ("03-wave-b", 180), ("02-wave-a", 180)]
        case .question: [("06-asking", 500)]
        case .saved: [("01-idle", 100), ("07-crouch", 150), ("08-jump", 200)]
        default: []
        }
    }
    var workingOperation: String? {
        switch self {
        case .thinking(let operation), .question(let operation, _, _): operation
        default: nil
        }
    }
}

@MainActor final class OlloSession {
    static let shared = OlloSession()
    private var seen: Set<String> = []
    private var working: Set<String> = []
    func begin(_ cue: OlloCue) -> Bool {
        if let operation = cue.workingOperation { working.insert(operation) }
        guard let event = cue.eventID, seen.insert(event).inserted else { return false }
        // Loading a saved result from history must not trigger a celebration.
        if case .saved(let operation, _) = cue { return working.remove(operation) != nil }
        return true
    }
}

#if canImport(UIKit)
import SwiftUI

struct Ollo: View {
    var cue: OlloCue = .idle
    var size: CGFloat = 64
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @State private var frame: String?

    private var playbackID: String { "\(cue)-\(reduceMotion)-\(scenePhase)" }
    var body: some View {
        Group {
            if let image = UIImage(named: "Ollo-" + (frame ?? cue.pose)) {
                Image(uiImage: image).resizable().scaledToFit()
            }
        }.frame(width: size, height: size)
            .accessibilityHidden(true).allowsHitTesting(false)
            .task(id: playbackID) {
                frame = nil
                guard scenePhase == .active, OlloSession.shared.begin(cue), !reduceMotion else { return }
                do {
                    for (pose, milliseconds) in cue.frames {
                        try Task.checkCancellation()
                        frame = pose
                        try await Task.sleep(for: .milliseconds(milliseconds))
                    }
                    frame = nil
                } catch { /* The next cue replaces an interrupted sequence. */ }
            }
    }
}

struct OlloMessage<Content: View>: View {
    var cue: OlloCue
    var compact = false
    @ViewBuilder var content: Content
    @Environment(\.dynamicTypeSize) private var typeSize
    var body: some View {
        HStack(alignment: .center, spacing: 8) {
            if !typeSize.isAccessibilitySize { Ollo(cue: cue, size: compact ? 40 : 64) }
            content.frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
#endif
