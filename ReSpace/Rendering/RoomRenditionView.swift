import SwiftUI
import UIKit

struct RoomRenditionInput: Identifiable {
    let id: String
    let scene: WalkthroughBundle
    let image: Data
    let cachedURL: URL
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
                    Text("AI rendition of your 3D room · Corner view").font(.caption).foregroundStyle(.secondary)
                    ShareLink(item:input.cachedURL) { Label("Share image",systemImage:"square.and.arrow.up") }
                } else if !busy && error == nil {
                    if let preview=UIImage(data:input.image) { Image(uiImage:preview).resizable().scaledToFit() }
                    Text("Recreate this corner view as a natural iPhone photo, using your original scan photos to interpret the real furniture and materials.").multilineTextAlignment(.center)
                    Button("Generate image") { started=true;attempt += 1 }.buttonStyle(.borderedProminent)
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
                        .buttonStyle(.borderedProminent).disabled(busy)
                    Text("Refresh creates a new iPhone-style photo using this 3D corner view and original scan photos. Each refresh has a separate image-generation charge.")
                        .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
                } else if !busy {
                    Text("Sends this rendered view and up to six original scan photos to OpenAI. Image generation has a separate API charge from the 3D model’s $10 limit.").font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
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
                        guard try await client.existingRendition(scene:input.scene,requestId:savedRefresh?.requestId) != nil else { return }
                        started=true
                    }
                    let data=try await client.rendition(scene:input.scene,image:input.image,requestId:savedRefresh?.requestId)
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

    private func refresh() {
        guard !busy else { return }
        do {
            try JSONEncoder().encode(SavedRefresh(requestId:UUID(),completed:false)).write(to:refreshURL,options:.atomic)
            error=nil;started=true;attempt += 1
        } catch { self.error=error.localizedDescription }
    }
}
