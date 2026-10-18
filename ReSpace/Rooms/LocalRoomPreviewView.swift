import SwiftUI

/// Saved scans open only a fully verified walkthrough. Incomplete assets remain
/// worker checkpoints and are never shown as a finished room.
struct LocalRoomPreviewView: View {
    let room: LocalSavedRoom
    let repository: CaptureRepository
    let reconstruction: ReconstructionClient?
    @Environment(\.dismiss) private var dismiss
    @State private var job: ReconstructionJob?
    @State private var sceneURL: URL?
    @State private var error: String?
    @State private var submitting=false
    @State private var attempt=0

    private var needsRescan: Bool { job?.error?.hasPrefix("Rescan required:")==true }
    var body: some View {
        NavigationStack {
            Group {
                if let sceneURL { WalkthroughView(sceneURL:sceneURL) }
                else {
                    VStack(spacing:20) {
                        Image(systemName:"cube.transparent").font(.system(size:64)).foregroundStyle(.secondary)
                        if submitting { ProgressView("Sending your scan…") }
                        else if job?.isRunning==true {
                            ProgressView("Creating your room…")
                            Text("You can close this screen. Your finished walkthrough will be here when it is ready.").multilineTextAlignment(.center)
                        } else if needsRescan {
                            Text("This room needs another scan").font(.headline)
                            Text(job?.error?.replacingOccurrences(of:"Rescan required: ",with:"") ?? "Capture clearer views around furniture and wall decor.")
                            Button("Done") { dismiss() }
                        } else {
                            Text("Your room scan is saved").font(.headline)
                            Text("Create a walkthrough to explore your room and arrange its furniture.").multilineTextAlignment(.center)
                            if reconstruction != nil { Button(job?.canRetry==true ? "Retry walkthrough" : "Create walkthrough") { Task { await submit() } }.buttonStyle(.borderedProminent) }
                            else { Text("Connect the reconstruction service to create your walkthrough.").font(.caption) }
                        }
                        if let message=error ?? (needsRescan ? nil : job?.error) {
                            Text(message).font(.caption).foregroundStyle(.red)
                            Button("Check again") { attempt += 1 }
                        }
                    }.padding(28)
                }
            }
            .navigationTitle(room.name).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement:.cancellationAction) { Button("Done") { dismiss() } } }
            .task(id:attempt) { await watch() }
        }
    }
    private func submit() async {
        guard let reconstruction,!submitting else { return }
        submitting=true;error=nil
        defer { submitting=false }
        do {
            job=try await reconstruction.submit(room.id,repository:repository,retry:job?.canRetry==true)
            attempt += 1
        } catch is CancellationError {} catch { self.error=error.localizedDescription }
    }
    private func watch() async {
        guard let reconstruction else { return }
        do {
            job=try await reconstruction.cachedJob(room.id,repository:repository)
            if job?.hasFinalWalkthrough==true { sceneURL=try await reconstruction.sceneURL(room.id,repository:repository) }
            while !Task.isCancelled {
                guard let updated=try await reconstruction.refresh(room.id,repository:repository) else { return }
                job=updated;error=nil
                if updated.hasFinalWalkthrough { sceneURL=try await reconstruction.sceneURL(room.id,repository:repository) }
                if !updated.isRunning { return }
                try await Task.sleep(for:.seconds(3))
            }
        } catch is CancellationError {} catch { self.error=error.localizedDescription }
    }
}
