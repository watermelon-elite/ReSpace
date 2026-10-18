import SwiftUI

/// Saved scans open only a fully verified walkthrough. Incomplete assets remain
/// worker checkpoints and are never shown as a finished room.
struct LocalRoomPreviewView: View {
    let room: LocalSavedRoom
    let repository: CaptureRepository
    let reconstruction: ReconstructionClient?
    var app: AppModel? = nil
    @State private var planningRoomID: String?
    @State private var connecting = false
    @State private var planningError: String?
    @State private var showOptions = false
    @Environment(\.dismiss) private var dismiss
    @State private var job: ReconstructionJob?
    @State private var sceneURL: URL?
    @State private var priorSceneURL: URL?
    @State private var usdzURL: URL?
    @State private var error: String?
    @State private var submitting=false
    @State private var attempt=0
    @State private var confirmingRestart=false

    private var needsRescan: Bool { job?.error?.hasPrefix("Rescan required:") == true }
    private var title: String {
        if submitting { return "Saving your scan." }
        if job?.isRunning == true { return "Creating your room." }
        if needsRescan { return "Let’s scan again." }
        return "Your scan is saved."
    }
    var body: some View {
        NavigationStack {
            Group {
                if let sceneURL { walkthrough(sceneURL) }
                else { statusPage }
            }
            .background(ReSpaceStyle.canvas).foregroundStyle(ReSpaceStyle.ink)
            .toolbar(.hidden, for: .navigationBar).navigationBarBackButtonHidden()
            .fullScreenCover(isPresented: Binding(get: { planningRoomID != nil }, set: { if !$0 { planningRoomID = nil } })) {
                if let app, let id = planningRoomID { NavigationStack { RoomReview(app: app, roomID: id) } }
            }
            .sheet(isPresented: $showOptions) { optionsPage }
            .confirmationDialog("Generate a new 3D model?", isPresented: $confirmingRestart, titleVisibility: .visible) {
                Button("Start new generation · $10 limit") { Task { await submit(fromScratch: true) } }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Rebuild from the saved scan without reusing earlier generated models. This run can add up to $10 in API charges. Earlier results are kept.")
            }
            .task(id: attempt) { await watch() }
            .task(id: sceneURL) { await loadShareURL() }
        }
    }

    private var statusPage: some View {
        RSPage(title: title, topTitle: room.name, back: { dismiss() }, trailing: { showOptions = true }) {
            RSSymbol(name: needsRescan ? "camera" : "cube.transparent")
            if submitting { ProgressView("Sending your scan…") }
            else if job?.isRunning == true {
                ProgressView(job?.stageDescription ?? "Creating your room…")
                Text("You can leave for now. Your finished walkthrough will be here when it is ready.").foregroundStyle(ReSpaceStyle.secondary)
            } else if needsRescan {
                RSNotice(message: job?.error?.replacingOccurrences(of: "Rescan required: ", with: "") ?? "Capture clearer views around furniture and wall decor.")
            } else {
                Text("Explore a reconstruction of your room, or plan changes using your measured scan.").foregroundStyle(ReSpaceStyle.secondary)
                if reconstruction == nil { RSNotice(message: "Connect the reconstruction service to create a walkthrough. Your scan stays on this iPhone.") }
            }
            if let message = planningError ?? error ?? (needsRescan ? nil : job?.error) {
                RSNotice(message: message, isError: true)
                Button("Check again") { attempt += 1 }.buttonStyle(RSButtonStyle(kind: .secondary))
            }
        } footer: {
            if reconstruction != nil, !needsRescan, job?.isRunning != true {
                Button(submitting ? "Sending your scan…" : job?.canRetry == true ? "Retry walkthrough" : "Create walkthrough") {
                    Task { await submit() }
                }.buttonStyle(RSButtonStyle()).disabled(submitting)
            }
            if let priorSceneURL, job?.isRunning != true, !submitting {
                Button("Open previous version") { sceneURL = priorSceneURL }.buttonStyle(RSButtonStyle(kind: .secondary))
            }
            planningButton
        }
    }

    private func walkthrough(_ url: URL) -> some View {
        VStack(spacing: 0) {
            RSTopBar(title: room.name, back: { dismiss() }, trailing: { showOptions = true })
            WalkthroughView(sceneURL: url, reconstruction: reconstruction)
                .overlay(alignment: .top) {
                    if let message = planningError ?? error { RSNotice(message: message, isError: true).padding(16).background(.white) }
                }
        }.safeAreaInset(edge: .bottom) { planningButton.padding(.horizontal, 24).padding(.vertical, 12).background(.white) }
    }

    private var optionsPage: some View {
        RSPage(title: "Room options", back: { showOptions = false }) {
            Text("The walkthrough shows your captured room. Saved design edits stay in the planning view.").foregroundStyle(ReSpaceStyle.secondary)
            if let usdzURL, sceneURL != nil {
                ShareLink(item: usdzURL) { Label("Share room model", systemImage: "square.and.arrow.up") }.buttonStyle(RSButtonStyle(kind: .secondary))
            }
        } footer: {
            if reconstruction != nil {
                Button("Generate from scratch") { showOptions = false; confirmingRestart = true }
                    .buttonStyle(RSButtonStyle(kind: .secondary)).disabled(submitting || job?.isRunning == true)
            }
        }
    }

    @ViewBuilder private var planningButton: some View {
        if app != nil {
            Button(connecting ? "Preparing your room…" : "Plan changes") { Task { await connect() } }
                .buttonStyle(RSButtonStyle(kind: reconstruction == nil ? .primary : .secondary)).disabled(connecting)
        }
    }

    private func connect() async {
        guard let app, !connecting else { return }
        connecting = true; planningError = nil
        defer { connecting = false }
        do { planningRoomID = try await app.connectScan(room.id) }
        catch { planningError = error.localizedDescription }
    }

    private func loadShareURL() async {
        usdzURL = nil
        guard let sceneURL, let reconstruction else { return }
        do {
            let url = try await reconstruction.usdzURL(room.id, repository: repository, allowPrevious: true)
            if url?.deletingLastPathComponent() == sceneURL.deletingLastPathComponent() { usdzURL = url }
        } catch is CancellationError {} catch { self.error = error.localizedDescription }
    }

    private func submit(fromScratch: Bool = false) async {
        guard let reconstruction,!submitting else { return }
        submitting=true;error=nil
        if fromScratch { priorSceneURL=sceneURL ?? priorSceneURL;sceneURL=nil }
        defer { submitting=false }
        do {
            job=try await reconstruction.submit(room.id,repository:repository,retry:job?.canRetry==true,fromScratch:fromScratch)
            attempt += 1
        } catch is CancellationError {} catch { self.error=error.localizedDescription }
    }
    private func watch() async {
        guard let reconstruction else { return }
        do {
            job=try await reconstruction.cachedJob(room.id,repository:repository)
            priorSceneURL=try await reconstruction.sceneURL(room.id,repository:repository,allowPrevious:true)
            if job?.hasFinalWalkthrough==true { sceneURL=try await reconstruction.sceneURL(room.id,repository:repository) }
            while !Task.isCancelled {
                guard let updated=try await reconstruction.refresh(room.id,repository:repository) else { return }
                job=updated;error=nil
                if updated.hasFinalWalkthrough { sceneURL=try await reconstruction.sceneURL(room.id,repository:repository) }
                else { priorSceneURL=sceneURL ?? priorSceneURL;sceneURL=nil }
                if !updated.isRunning { return }
                try await Task.sleep(for:.seconds(3))
            }
        } catch is CancellationError {} catch { self.error=error.localizedDescription }
    }
}
