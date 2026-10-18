import SwiftUI
import UIKit

enum ReSpaceTheme {
    static let olive = ReSpaceStyle.purple
    static let cream = ReSpaceStyle.canvas
    static let ink = ReSpaceStyle.ink
    static let surface = Color.white
}

struct PrimaryAction: View {
    let title: String
    var symbol = "arrow.right"
    var disabled = false
    var action: () -> Void
    var body: some View {
        Button(action: action) { Label(title, systemImage: symbol) }
            .buttonStyle(RSButtonStyle()).disabled(disabled)
    }
}

struct StatusBanner: View {
    let text: String
    var isError = false
    var body: some View { RSNotice(message: text, isError: isError) }
}

extension String {
    var scanDateLabel: String {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = parser.date(from: self) ?? ISO8601DateFormatter().date(from: self)
        return date?.formatted(date: .abbreviated, time: .omitted) ?? "Saved scan"
    }
}
