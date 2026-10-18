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
    @State private var attempt=0

    var body: some View {
        NavigationStack {
            VStack(spacing:20) {
                if let image {
                    Image(uiImage:image).resizable().scaledToFit()
                    Text("AI rendition of your 3D room · Corner view").font(.caption).foregroundStyle(.secondary)
                    ShareLink(item:input.cachedURL) { Label("Share image",systemImage:"square.and.arrow.up") }
                } else if let error {
                    ContentUnavailableView("Image unavailable",systemImage:"photo",description:Text(error))
                    Button("Check again") { self.error=nil;attempt += 1 }
                } else if started {
                    ProgressView("Creating a realistic view of your room…")
                    Text("You can close this screen and reopen the image to check its progress.").font(.callout).multilineTextAlignment(.center)
                } else {
                    if let preview=UIImage(data:input.image) { Image(uiImage:preview).resizable().scaledToFit() }
                    Text("Create one photorealistic image from a room corner looking toward the center.").multilineTextAlignment(.center)
                    Button("Generate image") { started=true;attempt += 1 }.buttonStyle(.borderedProminent)
                    Text("Sends this rendered view to OpenAI. Image generation has a separate API charge from the 3D model’s $10 limit.").font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
                }
            }.padding()
            .navigationTitle("Realistic room image").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement:.confirmationAction) { Button("Done") { dismiss() } } }
            .task(id:attempt) {
                do {
                    if FileManager.default.fileExists(atPath:input.cachedURL.path) {
                        guard let cached=UIImage(contentsOfFile:input.cachedURL.path) else { throw ClientError.invalidResponse }
                        image=cached;return
                    }
                    guard started else { return }
                    let data=try await client.rendition(scene:input.scene,image:input.image)
                    guard let result=UIImage(data:data) else { throw ClientError.invalidResponse }
                    try data.write(to:input.cachedURL,options:.atomic)
                    image=result
                } catch is CancellationError {} catch { self.error=error.localizedDescription }
            }
        }
    }
}
