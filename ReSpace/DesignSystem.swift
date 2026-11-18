import SwiftUI
import CoreText

enum ReSpaceStyle {
    static let ink = Color(red: 0.047, green: 0.063, blue: 0.067)
    static let secondary = Color(red: 0.30, green: 0.34, blue: 0.34)
    static let orange = Color(red: 238/255, green: 80/255, blue: 1/255)
    static let lime = Color(red: 200/255, green: 253/255, blue: 3/255)
    static let white = Color(red: 252/255, green: 1, blue: 1)
    // Darkened accent is for small text on white; the exact orange is used on
    // primary surfaces with dark labels to preserve readable contrast.
    static let accent = Color(red: 0.66, green: 0.20, blue: 0)
    static let purple = accent
    static let gold = lime
    static let actionInk = ink
    static let actionGradient = LinearGradient(colors: [orange, orange], startPoint: .topLeading, endPoint: .bottomTrailing)
    static let wash = Color(red: 1, green: 0.94, blue: 0.89)
    static let canvas = white
    static let line = Color(red: 0.84, green: 0.88, blue: 0.87)
    static let danger = Color(red: 0.66, green: 0.12, blue: 0.12)

    static func font(_ size: CGFloat = 16, weight: Font.Weight = .regular, relativeTo: Font.TextStyle = .body) -> Font {
        .custom("InterVariable", size: size, relativeTo: relativeTo).weight(weight)
    }
    static func registerFonts() {
        if let url = Bundle.main.url(forResource: "InterVariable", withExtension: "ttf") {
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        }
    }
}

struct RSTitle: View {
    let text: String
    var body: some View {
        Text(text).font(ReSpaceStyle.font(34, weight: .semibold, relativeTo: .largeTitle))
            .tracking(-1.4).foregroundStyle(ReSpaceStyle.ink)
            .frame(maxWidth: .infinity, alignment: .leading).accessibilityAddTraits(.isHeader)
    }
}

struct RSRoomCard<Thumbnail: View>: View {
    let title: String
    let subtitle: String
    var status: String? = nil
    var hero = true
    @ViewBuilder var thumbnail: Thumbnail
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if hero { thumbnail.frame(height: 240).clipped().clipShape(RoundedRectangle(cornerRadius: 28)) }
            HStack(spacing: 16) {
                if !hero { thumbnail.frame(width: 64, height: 64).clipped().clipShape(RoundedRectangle(cornerRadius: 16)) }
                VStack(alignment: .leading, spacing: 5) {
                    Text(title).font(ReSpaceStyle.font(18, weight: .semibold))
                    Text(subtitle).font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
                    if let status, !status.isEmpty {
                        Text(status).font(ReSpaceStyle.font(12, weight: .medium)).foregroundStyle(ReSpaceStyle.purple)
                    }
                }
                Spacer(minLength: 8)
                Image(systemName: "arrow.right").font(.system(size: 16)).accessibilityHidden(true)
            }.padding(.vertical, 8)
        }.foregroundStyle(ReSpaceStyle.ink)
    }
}

struct RSIconButton: View {
    let symbol: String
    let label: String
    var prominent = false
    let action: () -> Void
    @Environment(\.isEnabled) private var enabled
    var body: some View {
        Button(action: action) {
            Image(systemName: symbol).font(.system(size: 19, weight: .regular)).frame(width: 44, height: 44)
                .background { if prominent { Circle().fill(ReSpaceStyle.actionGradient) } }
                .contentShape(Circle())
        }.buttonStyle(.plain).accessibilityLabel(label).opacity(enabled ? 1 : 0.45)
    }
}

struct RSWalkControls: View {
    let walk: (Double, Double) -> Void
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    var body: some View {
        HStack(spacing: 8) {
            if !dynamicTypeSize.isAccessibilitySize {
                Text("EXPLORE").font(ReSpaceStyle.font(10, weight: .bold)).tracking(2)
                    .foregroundStyle(ReSpaceStyle.white).accessibilityHidden(true)
            }
            Spacer()
            control("arrow.left", "Walk left", x: -0.15, z: 0)
            control("arrow.up", "Walk forward", x: 0, z: -0.15)
            control("arrow.down", "Walk backward", x: 0, z: 0.15)
            control("arrow.right", "Walk right", x: 0.15, z: 0)
        }.padding(8).background(ReSpaceStyle.ink.opacity(0.94), in: RoundedRectangle(cornerRadius: 20))
    }
    private func control(_ symbol: String, _ label: String, x: Double, z: Double) -> some View {
        Button { walk(x, z) } label: {
            Image(systemName: symbol).frame(width: 44, height: 44)
                .foregroundStyle(ReSpaceStyle.ink).background(ReSpaceStyle.lime, in: Circle())
        }.buttonStyle(.plain).buttonRepeatBehavior(.enabled).accessibilityLabel(label)
    }
}

struct RSTopBar: View {
    var title = ""
    var companion: OlloCue? = nil
    var back: (() -> Void)?
    var trailingSymbol = "ellipsis"
    var trailingLabel = "Options"
    var trailingProminent = false
    var trailingDisabled = false
    var trailing: (() -> Void)?
    var body: some View {
        HStack(spacing: 8) {
            if let back { RSIconButton(symbol: "chevron.left", label: "Back", action: back) }
            else { Color.clear.frame(width: 44, height: 44) }
            Group {
                if let companion { Ollo(cue: companion, size: 44) }
                else { Text(title).font(ReSpaceStyle.font(14, weight: .semibold)).lineLimit(2).multilineTextAlignment(.center) }
            }.frame(maxWidth: .infinity)
            if let trailing { RSIconButton(symbol: trailingSymbol, label: trailingLabel, prominent: trailingProminent, action: trailing).disabled(trailingDisabled) }
            else { Color.clear.frame(width: 44, height: 44) }
        }.padding(.horizontal, 16).padding(.vertical, 8).foregroundStyle(ReSpaceStyle.ink)
    }
}

struct RSPage<Content: View, Footer: View>: View {
    var title: String
    var topTitle = ""
    var topCompanion: OlloCue? = nil
    var question = false
    var showsBack = true
    var inlineTitle = false
    var back: (() -> Void)?
    var trailingSymbol = "ellipsis"
    var trailingLabel = "Options"
    var trailing: (() -> Void)?
    @ViewBuilder var content: Content
    @ViewBuilder var footer: Footer
    @Environment(\.dismiss) private var dismiss
    @AccessibilityFocusState private var titleFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            if inlineTitle {
                HStack(spacing: 16) {
                    RSTitle(text: title).accessibilityFocused($titleFocused)
                    if let trailing { RSIconButton(symbol: trailingSymbol, label: trailingLabel, action: trailing) }
                }.padding(.horizontal, 24).padding(.top, 16).padding(.bottom, 8)
            } else {
                RSTopBar(title: topTitle, companion: topCompanion, back: showsBack ? (back ?? { dismiss() }) : nil,
                         trailingSymbol: trailingSymbol, trailingLabel: trailingLabel, trailing: trailing)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    if !title.isEmpty && !inlineTitle { RSTitle(text: title).padding(.bottom, question ? 16 : 4).accessibilityFocused($titleFocused) }
                    content
                }.frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 24).padding(.top, question ? 56 : 16).padding(.bottom, 24)
            }.scrollDismissesKeyboard(.interactively)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 8) { footer }.padding(.horizontal, 24).padding(.top, 12).padding(.bottom, 16).background(.white)
        }
        .background(ReSpaceStyle.white).foregroundStyle(ReSpaceStyle.ink).font(ReSpaceStyle.font())
        .toolbar(.hidden, for: .navigationBar).navigationBarBackButtonHidden()
        .onAppear { titleFocused = true }
    }
}

struct RSButtonStyle: ButtonStyle {
    enum Kind { case primary, secondary, quiet, danger }
    var kind: Kind = .primary
    var compact = false
    @Environment(\.isEnabled) private var enabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(ReSpaceStyle.font(15, weight: .semibold))
            .frame(maxWidth: .infinity).frame(minHeight: kind == .quiet || compact ? 44 : 56)
            .padding(.horizontal, 20)
            .foregroundStyle(kind == .primary ? ReSpaceStyle.actionInk : kind == .danger ? .white : kind == .secondary ? ReSpaceStyle.ink : ReSpaceStyle.secondary)
            .background {
                RoundedRectangle(cornerRadius: 16).fill(kind == .primary ? ReSpaceStyle.orange : kind == .danger ? ReSpaceStyle.danger : kind == .secondary ? ReSpaceStyle.wash : Color.clear)
            }
            .opacity(enabled ? 1 : 0.45)
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.975 : 1)
            .brightness(configuration.isPressed ? -0.04 : 0)
            .animation(reduceMotion ? nil : .spring(response:0.28,dampingFraction:0.7),value:configuration.isPressed)
    }
}

struct RSChoice: View {
    let title: String
    var subtitle = ""
    var symbol: String? = nil
    var selected = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 16) {
                if let symbol { Image(systemName: symbol).foregroundStyle(ReSpaceStyle.purple).frame(width: 28).accessibilityHidden(true) }
                VStack(alignment: .leading, spacing: 5) {
                    Text(title).font(ReSpaceStyle.font(16, weight: .medium))
                    if !subtitle.isEmpty { Text(subtitle).font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary) }
                }.frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 22, weight: .light)).foregroundStyle(selected ? ReSpaceStyle.purple : ReSpaceStyle.secondary.opacity(0.6))
            }.padding(18).frame(minHeight: 80).foregroundStyle(ReSpaceStyle.ink)
                .background(selected ? ReSpaceStyle.wash : .white, in: RoundedRectangle(cornerRadius: 20))
                .overlay { RoundedRectangle(cornerRadius: 20).stroke(selected ? ReSpaceStyle.purple : ReSpaceStyle.line, lineWidth: 1) }
                .shadow(color: ReSpaceStyle.purple.opacity(0.04), radius: 8, y: 3)
        }.buttonStyle(.plain).accessibilityAddTraits(selected ? .isSelected : [])
    }
}

struct RSRow: View {
    let title: String
    var subtitle = ""
    var symbol: String? = nil
    var body: some View {
        HStack(spacing: 16) {
            if let symbol { Image(systemName: symbol).frame(width: 22).accessibilityHidden(true) }
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(ReSpaceStyle.font(16, weight: .medium))
                if !subtitle.isEmpty { Text(subtitle).font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary) }
            }.frame(maxWidth: .infinity, alignment: .leading)
            Image(systemName: "arrow.right").font(.system(size: 14)).accessibilityHidden(true)
        }.foregroundStyle(ReSpaceStyle.ink).padding(.vertical, 18).frame(minHeight: 64)
            .overlay(alignment: .bottom) { Rectangle().fill(ReSpaceStyle.line).frame(height: 1) }.contentShape(Rectangle())
    }
}

struct RSNotice: View {
    let message: String
    var isError = false
    var body: some View {
        Label(message, systemImage: isError ? "exclamationmark.circle" : "info.circle")
            .font(ReSpaceStyle.font(14)).foregroundStyle(isError ? ReSpaceStyle.danger : ReSpaceStyle.secondary)
            .padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(isError ? ReSpaceStyle.danger.opacity(0.06) : ReSpaceStyle.canvas, in: RoundedRectangle(cornerRadius: 16))
            .accessibilityElement(children: .combine)
    }
}

struct RSSymbol: View {
    let name: String
    var body: some View {
        Image(systemName: name).font(.system(size: 25, weight: .light)).foregroundStyle(ReSpaceStyle.purple)
            .frame(width: 64, height: 64).background(ReSpaceStyle.wash, in: RoundedRectangle(cornerRadius: 20)).accessibilityHidden(true)
    }
}

struct RSKeyValue: View {
    let title: String
    let value: String
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 16) {
            Text(title).foregroundStyle(ReSpaceStyle.secondary)
            Spacer(minLength: 8)
            Text(value).fontWeight(.medium).multilineTextAlignment(.trailing)
        }.font(ReSpaceStyle.font(14)).padding(.vertical, 18)
            .overlay(alignment: .bottom) { Rectangle().fill(ReSpaceStyle.line).frame(height: 1) }
    }
}

struct RSComposer: View {
    @Binding var text: String
    var placeholder = "Ask for a change…"
    var selection: String? = nil
    var clear: (() -> Void)? = nil
    var disabled = false
    var onFocusChange: (Bool) -> Void = { _ in }
    let send: () -> Void
    @FocusState private var focused: Bool
    var body: some View {
        VStack(spacing: 8) {
            if let selection {
                HStack {
                    Text(selection).font(ReSpaceStyle.font(13)).lineLimit(2)
                    Spacer()
                    if let clear { RSIconButton(symbol: "xmark", label: "Clear selected Object or Item", action: clear) }
                }.padding(.leading, 16).foregroundStyle(ReSpaceStyle.purple).background(ReSpaceStyle.wash, in: RoundedRectangle(cornerRadius: 16))
            }
            HStack(alignment: .bottom, spacing: 8) {
                TextField(placeholder, text: $text, prompt: Text(placeholder).foregroundStyle(ReSpaceStyle.secondary), axis: .vertical).font(ReSpaceStyle.font(14)).lineLimit(1...4).padding(.vertical, 12).padding(.leading, 16).accessibilityLabel(placeholder).focused($focused)
                Button(action: send) {
                    Image(systemName: "arrow.up").font(.system(size: 18, weight: .medium)).foregroundStyle(ReSpaceStyle.actionInk)
                        .frame(width: 44, height: 44).background(ReSpaceStyle.actionGradient, in: Circle())
                }.buttonStyle(.plain).disabled(disabled || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .opacity(disabled || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? 0.45 : 1).accessibilityLabel("Send message")
            }.padding(4).background(.white, in: RoundedRectangle(cornerRadius: 28))
                .overlay { RoundedRectangle(cornerRadius: 28).stroke(ReSpaceStyle.secondary.opacity(0.5), lineWidth: 1) }
        }
        .onChange(of: focused) { _, value in onFocusChange(value) }
        .onDisappear { onFocusChange(false) }
    }
}

struct RSMessage: View {
    let entry: JSONValue
    private var isUser: Bool { entry["role"].text == "user" }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if !entry["context"].text.isEmpty { Text(entry["context"].text.replacingOccurrences(of: "_", with: " ").capitalized).font(ReSpaceStyle.font(12)).foregroundStyle(ReSpaceStyle.secondary) }
            Text(entry["text"].text).font(ReSpaceStyle.font(15)).textSelection(.enabled)
        }.padding(isUser ? 16 : 0).background(isUser ? ReSpaceStyle.wash : .clear, in: RoundedRectangle(cornerRadius: 20))
            .frame(maxWidth: .infinity, alignment: isUser ? .trailing : .leading)
    }
}

extension View {
    func rsInput() -> some View {
        padding(16).background(.white, in: RoundedRectangle(cornerRadius: 16))
            .overlay { RoundedRectangle(cornerRadius: 16).stroke(ReSpaceStyle.secondary.opacity(0.6), lineWidth: 1) }
    }
}

func displayDate(_ raw: String) -> String {
    let parser = ISO8601DateFormatter()
    parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let date = parser.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
    return date?.formatted(date: .abbreviated, time: .omitted) ?? raw
}
