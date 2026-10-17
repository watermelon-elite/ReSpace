import SwiftUI
import UIKit

enum ReSpaceTheme {
    static let olive = Color(red: 0.29, green: 0.36, blue: 0.24)
    static let cream = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(red: 0.08, green: 0.09, blue: 0.07, alpha: 1) : UIColor(red: 0.97, green: 0.96, blue: 0.93, alpha: 1)
    })
    static let ink = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(red: 0.93, green: 0.94, blue: 0.91, alpha: 1) : UIColor(red: 0.18, green: 0.21, blue: 0.17, alpha: 1)
    })
    static let surface = Color(uiColor: .secondarySystemGroupedBackground)
}

struct PrimaryAction: View {
    let title: String
    var symbol = "arrow.right"
    var disabled = false
    var action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack { Text(title); Spacer(); Image(systemName: symbol) }
                .font(.headline).padding(18).foregroundStyle(.white)
                .background(disabled ? Color.gray : ReSpaceTheme.olive, in: RoundedRectangle(cornerRadius: 18))
        }.disabled(disabled)
    }
}

struct StatusBanner: View {
    let text: String
    var isError = false
    var body: some View {
        Label(text, systemImage: isError ? "exclamationmark.circle" : "info.circle")
            .font(.subheadline).frame(maxWidth: .infinity, alignment: .leading)
            .padding(12).foregroundStyle(isError ? Color.red : ReSpaceTheme.ink)
            .background(isError ? Color.red.opacity(0.07) : ReSpaceTheme.olive.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
    }
}

extension String {
    var scanDateLabel: String {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = parser.date(from: self) ?? ISO8601DateFormatter().date(from: self)
        return date?.formatted(date: .abbreviated, time: .omitted) ?? "Saved scan"
    }
}
