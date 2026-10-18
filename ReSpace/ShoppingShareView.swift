import SwiftUI
import UIKit

struct ShoppingShareView: View {
    let list: ShoppingList
    @State private var images: [UIImage] = []
    @State private var files: [URL] = []
    @State private var exportFolder: URL?
    @State private var page = 0
    @State private var destination: Destination?
    @State private var error: String?
    @State private var copied = false

    private enum Destination: String, Identifiable {
        case messages, instagram
        var id: String { rawValue }
    }

    var body: some View {
        RSPage(title: "Share your room", topTitle: list.roomName) {
            if images.isEmpty {
                if let error {
                    RSNotice(message: error, isError: true)
                    Button("Try again") { Task { await render() } }.buttonStyle(RSButtonStyle(kind: .secondary))
                } else {
                    ProgressView("Preparing your images…").frame(maxWidth: .infinity, minHeight: 240)
                }
            } else {
                Image(uiImage: images[page]).resizable().scaledToFit()
                    .clipShape(RoundedRectangle(cornerRadius: 20))
                    .accessibilityLabel("Post image \(page + 1) of \(images.count). Placeholder room. "
                        + list.postPages[page].map { "\($0.title), \($0.priceLabel)" }.joined(separator: ". "))
                if images.count > 1 {
                    HStack {
                        RSIconButton(symbol: "chevron.left", label: "Previous image") { page -= 1 }.disabled(page == 0)
                        Spacer()
                        Text("\(page + 1) of \(images.count)").font(ReSpaceStyle.font(14))
                        Spacer()
                        RSIconButton(symbol: "chevron.right", label: "Next image") { page += 1 }.disabled(page == images.count - 1)
                    }
                }
                Text("Illustrative room · saved prices")
                    .font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
                if let error { RSNotice(message: error, isError: true) }
                DisclosureGroup {
                    Text(list.postCaption).font(ReSpaceStyle.font(13)).textSelection(.enabled).padding(.top, 8)
                    Text("For Instagram, copy the caption, then choose Instagram in the share sheet. If it isn’t listed, save the images and post them from Instagram.")
                        .font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary).padding(.top, 12)
                } label: {
                    Text("Caption & sharing details").frame(minHeight: 44)
                }.font(ReSpaceStyle.font(14))
            }
        } footer: {
            Button { destination = .messages } label: {
                Label("Share images & links", systemImage: "message")
            }.buttonStyle(RSButtonStyle()).disabled(files.isEmpty)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) { secondaryActions }
                VStack(spacing: 8) { secondaryActions }
            }
        }
        .task { await render() }
        .sheet(item: $destination) { target in
            ShoppingActivityView(items: files.map { $0 as Any } + (target == .messages ? [list.postCaption] : [])) { message in
                destination = nil
                error = message
            }
        }
        .onDisappear {
            if destination == nil, let exportFolder { try? FileManager.default.removeItem(at: exportFolder) }
        }
    }

    @ViewBuilder private var secondaryActions: some View {
        Button("Instagram") { destination = .instagram }
            .buttonStyle(RSButtonStyle(kind: .secondary, compact: true)).disabled(files.isEmpty)
        Button(copied ? "Copied" : "Copy caption") {
            UIPasteboard.general.string = list.postCaption
            copied = true
        }.buttonStyle(RSButtonStyle(kind: .secondary, compact: true)).disabled(files.isEmpty)
            .accessibilityLabel(copied ? "Caption and links copied" : "Copy caption and shopping links")
    }

    @MainActor private func render() async {
        guard images.isEmpty else { return }
        error = nil
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("ReSpace-share-\(UUID().uuidString)", isDirectory: true)
        do {
            guard let placeholder = UIImage(named: "CozyInspiration") else { throw ContractError.invalid("The placeholder room image is missing from this build.") }
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            var rendered: [UIImage] = []
            var urls: [URL] = []
            let pages = list.postPages
            guard !pages.isEmpty else { throw ContractError.invalid("This list has no purchases to share.") }
            for index in pages.indices {
                await Task.yield()
                try Task.checkCancellation()
                let renderer = ImageRenderer(content: ShoppingPostImage(list: list, lines: pages[index], page: index + 1,
                    pageCount: pages.count, placeholder: placeholder).environment(\.colorScheme, .light).environment(\.dynamicTypeSize, .medium))
                renderer.scale = 3
                renderer.isOpaque = true
                guard let image = renderer.uiImage, let jpeg = image.jpegData(compressionQuality: 0.92) else {
                    throw ContractError.invalid("The post image could not be rendered. Try again.")
                }
                assert(image.cgImage?.width == 1080 && image.cgImage?.height == 1350)
                let url = folder.appendingPathComponent("ReSpace-\(index + 1).jpg")
                try jpeg.write(to: url, options: [.atomic, .completeFileProtectionUnlessOpen])
                rendered.append(image); urls.append(url)
            }
            images = rendered; files = urls; exportFolder = folder
        } catch {
            try? FileManager.default.removeItem(at: folder)
            if !Task.isCancelled { self.error = error.localizedDescription }
        }
    }
}

private struct ShoppingPostImage: View {
    let list: ShoppingList
    let lines: [ShoppingList.Line]
    let page: Int
    let pageCount: Int
    let placeholder: UIImage

    var body: some View {
        ZStack {
            Image(uiImage: placeholder).resizable().scaledToFill().frame(width: 360, height: 450).clipped()
            LinearGradient(stops: [.init(color: .black.opacity(0.65), location: 0), .init(color: .clear, location: 0.4),
                                   .init(color: .clear, location: 0.7), .init(color: .black.opacity(0.8), location: 1)],
                           startPoint: .top, endPoint: .bottom)
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("ReSpace").font(ReSpaceStyle.font(14, weight: .semibold))
                    Spacer()
                    Text("PLACEHOLDER ROOM").font(ReSpaceStyle.font(8, weight: .semibold)).tracking(1)
                }
                Text(list.roomName).font(ReSpaceStyle.font(28, weight: .semibold)).lineLimit(1).minimumScaleFactor(0.6)
                Text("Purchase total · USD \(list.total)").font(ReSpaceStyle.font(13, weight: .medium))
                Spacer()
                HStack(alignment: .bottom) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Illustrative image · saved purchase prices")
                        Text("Whole packs · tax & shipping excluded")
                        if list.fitPending { Text("Room fit is still pending") }
                    }.font(ReSpaceStyle.font(9, weight: .medium))
                    Spacer(minLength: 4)
                    if pageCount > 1 { Text("\(page) / \(pageCount)").font(ReSpaceStyle.font(11, weight: .semibold)) }
                }
            }.padding(22).foregroundStyle(.white)
            // shortcut: fixed label slots suit the placeholder; anchor to projected Items when real renders are supplied.
            ForEach(Array(lines.enumerated()), id: \.element.id) { index, line in
                VStack(alignment: .leading, spacing: 5) {
                    HStack(alignment: .firstTextBaseline, spacing: 5) {
                        Text(String((page - 1) * 4 + index + 1)).font(ReSpaceStyle.font(9, weight: .semibold))
                            .frame(width: 19, height: 19).background(ReSpaceStyle.actionGradient, in: Circle())
                        Text("$\(line.total)").font(ReSpaceStyle.font(21, weight: .semibold)).lineLimit(1).minimumScaleFactor(0.65)
                    }
                    Text(line.title).font(ReSpaceStyle.font(10, weight: .medium)).lineLimit(2).frame(height: 26, alignment: .top)
                    Text("\(line.packCount) \(line.packCount == 1 ? "pack" : "packs") · line total").font(ReSpaceStyle.font(8)).foregroundStyle(ReSpaceStyle.secondary)
                }.padding(10).frame(width: 148, alignment: .leading)
                    .foregroundStyle(ReSpaceStyle.ink).background(.white.opacity(0.96), in: RoundedRectangle(cornerRadius: 14))
                    .shadow(color: .black.opacity(0.12), radius: 8, y: 3)
                    .position(x: index % 2 == 0 ? 96 : 264, y: index < 2 ? 208 : 326)
            }
        }.frame(width: 360, height: 450).clipped()
    }
}

private struct ShoppingActivityView: UIViewControllerRepresentable {
    let items: [Any]
    let completion: (String?) -> Void

    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItems: items, applicationActivities: nil)
        controller.completionWithItemsHandler = { _, _, _, error in completion(error?.localizedDescription) }
        return controller
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

#if DEBUG
#Preview("Share images") { UIDemoPreview(.share) }
#endif
