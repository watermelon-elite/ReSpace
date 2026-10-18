import Foundation

enum DesignIntent: String, Codable, Sendable, CaseIterable {
    case add, redesign
    var title: String { self == .add ? "Add a few things" : "Full redesign" }
    var subtitle: String {
        self == .add ? "Build on what’s already here." : "Explore a fresh arrangement."
    }
}
enum DesignStyle: String, Codable, Sendable, CaseIterable {
    case match, cozy, minimal, japandi, industrial, boho
    case midCentury = "mid_century"
    var title: String {
        switch self {
        case .match: "Match what I have"
        case .midCentury: "Mid-century"
        default: rawValue.capitalized
        }
    }
}
struct GenerationInputs: Codable, Sendable, Equatable {
    var intent: DesignIntent
    var styles: [DesignStyle]
    var budget: String
    var currency: String = "USD"
    var text: String
}
struct ScanIntentDraft: Codable, Sendable, Equatable {
    var intent: DesignIntent = .add
    var styles: Set<DesignStyle> = [.match]
    var budgetText = ""
    var text = ""

    mutating func toggle(_ style: DesignStyle) {
        if style == .match { styles = [.match]; return }
        styles.remove(.match)
        if styles.contains(style) { styles.remove(style) } else { styles.insert(style) }
        if styles.isEmpty { styles = [.match] }
    }

    var inputs: GenerationInputs? {
        guard let budget = Self.parseBudget(budgetText) else { return nil }
        return GenerationInputs(intent: intent, styles: styles.sorted { $0.rawValue < $1.rawValue },
                                budget: budget, text: text.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    static func parseBudget(_ text: String) -> String? {
        // Fixed USD decimal format; do not round invalid input into a valid budget.
        guard text.range(of: #"\A[0-9]+(?:\.[0-9]{1,2})?\z"#, options: .regularExpression) != nil,
              let decimal = Decimal(string: text, locale: Locale(identifier: "en_US_POSIX")),
              decimal > 0 else { return nil }
        let parts = text.split(separator: ".", omittingEmptySubsequences: false)
        let whole = String(parts[0].drop(while: { $0 == "0" }))
        let cents = parts.count == 2 ? String(parts[1]).padding(toLength: 2, withPad: "0", startingAt: 0) : "00"
        return "\(whole.isEmpty ? "0" : whole).\(cents)"
    }
}
