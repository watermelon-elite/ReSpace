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
    @State private var uploadProgress: Double?
    @State private var submitting=false
    @State private var attempt=0
    @State private var confirmingRestart=false
    @State private var confirmingCreate=false
    @State private var captureKindLoaded = false
    @State private var isSourceCapture = false
    @State private var sourceLayoutError: String?
    @State private var sourceArchive: URL?
    @State private var preparingSourceArchive = false
    @State private var presentingSourceShare = false
    @State private var isVisible = false

    private var needsRescan: Bool { job?.error?.hasPrefix("Rescan required:") == true }
    var body: some View {
        NavigationStack {
            Group {
                if !captureKindLoaded { ProgressView("Opening your scan…") }
                else if let sceneURL { walkthrough(sceneURL) }
                else { statusPage }
            }
            .background(ReSpaceStyle.canvas).foregroundStyle(ReSpaceStyle.ink)
            .toolbar(.hidden, for: .navigationBar).navigationBarBackButtonHidden()
            .fullScreenCover(isPresented: Binding(get: { planningRoomID != nil }, set: { if !$0 { planningRoomID = nil } })) {
                if let app, let id = planningRoomID { NavigationStack { RoomReview(app: app, roomID: id) } }
            }
            .sheet(isPresented: $showOptions, onDismiss: {
                if sourceArchive != nil { presentingSourceShare = true }
            }) { optionsPage }
            .sheet(isPresented: $presentingSourceShare, onDismiss: clearSourceArchive) {
                if let sourceArchive {
                    SourceCaptureActivityView(url: sourceArchive) { message in
                        if let message { error = message }
                        presentingSourceShare = false
                    }
                }
            }
            .onAppear { isVisible = true; UIApplication.shared.isIdleTimerDisabled = submitting }
            .onDisappear { isVisible = false; UIApplication.shared.isIdleTimerDisabled = false; if !presentingSourceShare { clearSourceArchive() } }
            .onChange(of: submitting) { _, uploading in UIApplication.shared.isIdleTimerDisabled = uploading && isVisible }
            .confirmationDialog("Rebuild your 3D model?", isPresented: $confirmingRestart, titleVisibility: .visible) {
                Button("Start new generation · $10 limit") { Task { await submit(fromScratch: true) } }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Rebuild from the saved scan without reusing earlier generated models. This run can add up to $10 in API charges. Earlier results are kept.")
            }
            .confirmationDialog("Build your 3D model?", isPresented: $confirmingCreate, titleVisibility: .visible) {
                Button("Build model · $10 limit") { Task { await submit() } }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Send the saved scan and photos to your reconstruction service and OpenAI to model your room and its textures. This generation can add up to $10 in API charges.")
            }
            .task(id: attempt) { await watch() }
            .task(id: sceneURL) { await loadShareURL() }
        }
    }

    private func prepareSourceArchive() async {
        guard !preparingSourceArchive else { return }
        preparingSourceArchive = true; error = nil
        defer { preparingSourceArchive = false }
        do {
            let archive = try await repository.sourceBundleArchive(room.id)
            guard isVisible, !Task.isCancelled else { try? FileManager.default.removeItem(at: archive); return }
            sourceArchive = archive
            if showOptions { showOptions = false } else { presentingSourceShare = true }
        }
        catch { self.error = error.localizedDescription }
    }
    private func clearSourceArchive() {
        if let sourceArchive { try? FileManager.default.removeItem(at: sourceArchive) }
        sourceArchive = nil
    }

    private var statusPage: some View {
        RSPage(title: "", topTitle: room.displayName, back: { dismiss() }, trailing: { showOptions = true }) {
            VStack(alignment: .leading, spacing: 24) {
                Label("Scan saved", systemImage: "checkmark.circle.fill").font(ReSpaceStyle.font(14, weight: .medium)).foregroundStyle(ReSpaceStyle.secondary)
                Text(submitting ? "Sending your scan" : job?.isRunning == true ? "Building your 3D room" : needsRescan ? "A new scan is needed" : job?.canRetry == true ? "Model needs another try" : "Ready to build your room").font(ReSpaceStyle.font(28, weight: .semibold))
                if submitting || job?.isRunning == true {
                    if submitting, let uploadProgress {
                        ProgressView(value: uploadProgress) {
                            Text("Upload \(Int(uploadProgress * 100))%").font(ReSpaceStyle.font(14))
                        }.tint(ReSpaceStyle.accent)
                    } else { ProgressView() }
                    Text(submitting ? "Uploading photos and measurements. Keep ReSpace open until the upload finishes." : job?.stageDescription ?? "Preparing your room…")
                    if !submitting { Text("You can leave this screen. Your Mac will keep working, and you can check back here.").font(ReSpaceStyle.font(14)).foregroundStyle(ReSpaceStyle.secondary) }
                } else {
                    Text(sourceLayoutError != nil || needsRescan ? "Your scan is saved, but it doesn’t contain the data needed for this model. Scan the room again to continue." : job?.canRetry == true ? "Your scan is safe. Retry continues from the saved model progress." : "Turn your photos and measurements into a model you can walk through.").foregroundStyle(ReSpaceStyle.secondary)
                    if reconstruction == nil { RSNotice(message: "Set up your Mac connection in Settings before building the model.") }
                }
                if let message = planningError ?? error ?? job?.error {
                    RSNotice(message: message, isError: true)
                    Button("Check again") { attempt += 1 }.buttonStyle(RSButtonStyle(kind: .secondary))
                }
                if !submitting && !needsRescan && job?.isRunning != true && sourceLayoutError == nil {
                    Text(job?.canRetry == true ? "Retry keeps the same $10 generation limit." : "Building uses your Mac and OpenAI. You’ll confirm the $10 limit before it starts.").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
                }
            }.padding(.top, 20)
        } footer: {
            if reconstruction != nil, !needsRescan, job?.isRunning != true {
                Button(submitting ? "Sending scan…" : job?.canRetry == true ? "Retry model" : "Build 3D model") {
                    if job?.canRetry == true || job?.state == "uploading" { Task { await submit() } }
                    else { confirmingCreate = true }
                }.buttonStyle(RSButtonStyle()).disabled(submitting || sourceLayoutError != nil)
            }
            if let priorSceneURL, job?.isRunning != true, !submitting {
                Button("Open previous model") { sceneURL = priorSceneURL }.buttonStyle(RSButtonStyle(kind: .secondary))
            }
            planningButton
        }
    }

    private func walkthrough(_ url: URL) -> some View {
        VStack(spacing: 0) {
            RSTopBar(title: room.displayName, back: { dismiss() }, trailing: { showOptions = true })
            WalkthroughView(sceneURL: url, reconstruction: reconstruction, imageGenerationEnabled: app?.designFeaturesEnabled == true)
                .overlay(alignment: .top) {
                    if let message = planningError ?? error { RSNotice(message: message, isError: true).padding(16).background(.white) }
                }
        }.safeAreaInset(edge: .bottom) {
            if app?.designFeaturesEnabled == true { planningButton.padding(.horizontal, 24).padding(.vertical, 12).background(.white) }
        }
    }

    private var optionsPage: some View {
        RSPage(title: "Room options", back: { showOptions = false }) {
            Text("Your original scan is kept on this iPhone. Rebuilding creates a separate model and keeps earlier results.").foregroundStyle(ReSpaceStyle.secondary)
            if isSourceCapture {
                Button(preparingSourceArchive ? "Preparing scan…" : "Export original scan") { Task { await prepareSourceArchive() } }
                    .buttonStyle(RSButtonStyle(kind: .secondary)).disabled(preparingSourceArchive)
            }
            if let usdzURL, sceneURL != nil {
                ShareLink(item: usdzURL) { Label("Share room model", systemImage: "square.and.arrow.up") }.buttonStyle(RSButtonStyle(kind: .secondary))
            }
        } footer: {
            if reconstruction != nil, job != nil {
                Button("Rebuild model") { showOptions = false; confirmingRestart = true }
                    .buttonStyle(RSButtonStyle(kind: .secondary)).disabled(submitting || job?.isRunning == true)
            }
        }
    }

    @ViewBuilder private var planningButton: some View {
        if app?.designFeaturesEnabled == true {
            Button(connecting ? "Preparing your room…" : "Decorate this room") { Task { await connect() } }
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
        submitting=true;error=nil;uploadProgress=nil
        if fromScratch { priorSceneURL=sceneURL ?? priorSceneURL;sceneURL=nil }
        defer { submitting=false }
        do {
            job=try await reconstruction.submit(room.id,repository:repository,retry:job?.canRetry==true,fromScratch:fromScratch) { @MainActor completed, total in
                uploadProgress = total > 0 ? Double(completed) / Double(total) : nil
            }
            attempt += 1
        } catch is CancellationError {} catch { self.error=error.localizedDescription }
    }
    private func watch() async {
        do {
            let manifest = try await repository.load(room.id)
            isSourceCapture = manifest.sourceBundleFormat == "house-capture/5"
            sourceLayoutError = manifest.sourceLayoutError
            captureKindLoaded = true
        } catch { self.error = error.localizedDescription; captureKindLoaded = true; return }
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

private struct SourceCaptureActivityView: UIViewControllerRepresentable {
    let url: URL
    let completion: (String?) -> Void
    func makeUIViewController(context: Context) -> UIActivityViewController {
        let view = UIActivityViewController(activityItems: [url], applicationActivities: nil)
        view.completionWithItemsHandler = { _, _, _, error in completion(error?.localizedDescription) }
        return view
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
