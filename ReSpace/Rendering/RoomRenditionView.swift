import SwiftUI
import UIKit

struct RoomRenditionInput: Identifiable, Codable {
    let id: String
    let scene: WalkthroughBundle
    let image: Data
    let cachedURL: URL
    var perspective: RenditionPerspective? = nil
    var design: RenditionDesign? = nil
    private var retainedURL: URL { cachedURL.deletingLastPathComponent().appendingPathComponent("latest-room-image.json") }
    func retain() throws { try JSONEncoder().encode(self).write(to:retainedURL,options:[.atomic,.completeFileProtectionUnlessOpen]) }
    static func retained(in directory:URL) throws -> Self {
        let input=try JSONDecoder().decode(Self.self,from:Data(contentsOf:directory.appendingPathComponent("latest-room-image.json")))
        // Resolve the path from the currently verified result directory in case
        // iOS moved the application's data container between launches.
        return Self(id:input.id,scene:input.scene,image:input.image,
            cachedURL:directory.appendingPathComponent(input.cachedURL.lastPathComponent),perspective:input.perspective,design:input.design)
    }
}

struct RoomRenditionView: View {
    let input: RoomRenditionInput
    let client: ReconstructionClient
    @Environment(\.dismiss) private var dismiss
    @State private var image: UIImage?
    @State private var error: String?
    @State private var started=false
    @State private var checking=true
    @State private var attempt=0

    private struct SavedRefresh: Codable {
        let requestId: UUID
        var completed: Bool
    }

    private var refreshURL: URL { input.cachedURL.deletingPathExtension().appendingPathExtension("json") }
    private var busy: Bool { started || checking }

    var body: some View {
        NavigationStack {
            ScrollView { VStack(spacing:20) {
                if let image {
                    Image(uiImage:image).resizable().scaledToFit()
                    Text("AI concept image · Your chosen viewpoint").font(ReSpaceStyle.font(13)).foregroundStyle(.secondary)
                    ShareLink(item:input.cachedURL) { Label("Share image",systemImage:"square.and.arrow.up") }
                } else if !busy && error == nil {
                    if let preview=UIImage(data:input.image) { Image(uiImage:preview).resizable().scaledToFit() }
                    Text("Turn this viewpoint into a realistic room image. Your saved layout guides the composition; original scan photos guide the room’s materials. AI images can vary from the exact products.").multilineTextAlignment(.center)
                    Button("Generate image") { generate() }.buttonStyle(RSButtonStyle())
                }
                if busy {
                    ProgressView(started ? "Creating a realistic view of your room…" : "Checking for a saved room image…")
                    Text("You can close this screen and reopen the image to check its progress.").font(.callout).multilineTextAlignment(.center)
                }
                if let error {
                    Text(error).foregroundStyle(.red).multilineTextAlignment(.center)
                    Button("Check again") { self.error=nil;checking=true;attempt += 1 }.disabled(busy)
                }
                if image != nil || error != nil {
                    Button(action:refresh) { Label("Refresh image",systemImage:"arrow.clockwise") }
                        .buttonStyle(RSButtonStyle()).disabled(busy)
                    Text("Refresh creates a new iPhone-style photo using this viewpoint, saved arrangement and original scan photos. Each refresh has a separate image-generation charge.")
                        .font(ReSpaceStyle.font(13)).foregroundStyle(.secondary).multilineTextAlignment(.center)
                } else if !busy {
                    Text("Sends this rendered view and up to six original scan photos to OpenAI. Image generation has a separate API charge from the 3D model’s $10 limit.").font(ReSpaceStyle.font(13)).foregroundStyle(.secondary).multilineTextAlignment(.center)
                }
            }.padding() }
            .navigationTitle("Realistic room image").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement:.confirmationAction) { Button("Done") { dismiss() } } }
            .task(id:attempt) {
                defer { checking=false;started=false }
                do {
                    var savedRefresh: SavedRefresh?
                    if FileManager.default.fileExists(atPath:refreshURL.path) {
                        savedRefresh=try JSONDecoder().decode(SavedRefresh.self,from:Data(contentsOf:refreshURL))
                    }
                    if FileManager.default.fileExists(atPath:input.cachedURL.path) {
                        guard let cached=UIImage(contentsOfFile:input.cachedURL.path) else { throw ClientError.invalidResponse }
                        image=cached
                        if savedRefresh?.completed != false { return }
                    }
                    // The refresh identity is written before any network work.
                    // A pending refresh resumes after closing or restarting the app.
                    if savedRefresh?.completed == false { started=true }
                    if !started {
                        guard try await client.existingRendition(scene:input.scene,requestId:savedRefresh?.requestId,perspective:input.perspective,design:input.design) != nil else { return }
                        started=true
                    }
                    let data=try await client.rendition(scene:input.scene,image:input.image,requestId:savedRefresh?.requestId,perspective:input.perspective,design:input.design)
                    try Task.checkCancellation()
                    guard let result=UIImage(data:data) else { throw ClientError.invalidResponse }
                    try data.write(to:input.cachedURL,options:.atomic)
                    if var completed=savedRefresh {
                        completed.completed=true
                        try JSONEncoder().encode(completed).write(to:refreshURL,options:.atomic)
                    }
                    image=result
                } catch is CancellationError {} catch { self.error=error.localizedDescription }
            }
        }
    }

    private func generate() {
        guard !busy else { return }
        do { try input.retain();error=nil;started=true;attempt += 1 }
        catch { self.error=error.localizedDescription }
    }
    private func refresh() {
        guard !busy else { return }
        do {
            try input.retain()
            try JSONEncoder().encode(SavedRefresh(requestId:UUID(),completed:false)).write(to:refreshURL,options:.atomic)
            error=nil;started=true;attempt += 1
        } catch { self.error=error.localizedDescription }
    }
}
