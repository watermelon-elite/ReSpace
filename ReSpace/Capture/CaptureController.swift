import ARKit
import AVFoundation
import Network
import Observation
import RoomPlan
import UIKit

@MainActor @Observable
final class ScanCaptureController: NSObject, RoomCaptureSessionDelegate {
    enum Phase: Equatable { case preparing, permissionDenied, scanning, finishing, recovering, interrupted, failed, ready(String) }
    var phase: Phase = .preparing
    var guidance = "Move slowly to capture the walls and furniture."
    var acceptedFrames = 0
    var elapsedSeconds = 0
    var canFinish: Bool { store.localCaptureEnabled ? sourceRecorder?.canFinish == true : true }
    var highResolutionPhotos = true { didSet { sourceRecorder?.highResolutionPhotos = highResolutionPhotos } }
    var canTakeDetailPhoto: Bool { sourceRecorder?.canTakePhoto == true }
    var sourceView: UIView? { sourceRecorder?.scanView.view }
    private var sourceRecorder: SourceCaptureRecorder?
    private var sourceSession: RoomCaptureSession?
    private var sourceMeshExport: Task<(vertices: Int, faces: Int, covered: Float), Error>?
    private var captureStartedAt: ContinuousClock.Instant?
    var detailText = "Details processing"
    var error: String?
    private(set) var roomView: RoomCaptureView?
    private let arSession = ARSession()
    private let store: WorkspaceStore
    private let encoder = FrameEncoder()
    private var manifest: CaptureManifest?
    private var policy = SamplingPolicy()
    private var timer: Timer?
    private var encoding: Task<Void, Never>?
    private var uploads: [String: Task<Void, Never>] = [:]
    private var completedUploads = Set<String>()
    private var started = false
    var hasCompletedCapture = false
    private var pathMonitor: NWPathMonitor?
    private var lastCameraTransform: simd_float4x4?
    private var lastCameraTimestamp: Double?
    private var lastFrameTimestamp: Double?
    private var lastFreshFrameTime = ContinuousClock.now

    init(store: WorkspaceStore) {
        self.store = store
        super.init()
        if store.localCaptureEnabled {
            detailText = "Local scan · saved on this iPhone"
        }
    }

    func prepare(recovering captureId: String? = nil) async {
        guard !started else { return }; started = true
        if let captureId {
            do { manifest = try await store.captures.load(captureId); hasCompletedCapture = true; phase = .recovering; await finalize() }
            catch { self.error = error.localizedDescription; phase = .failed }
            return
        }
        let permission = AVCaptureDevice.authorizationStatus(for: .video)
        var allowed = permission == .authorized
        if permission == .notDetermined { allowed = await AVCaptureDevice.requestAccess(for: .video) }
        guard allowed else { phase = .permissionDenied; return }
        do {
            let local = try await store.captures.create()
            manifest = local
            if store.localCaptureEnabled {
                try await store.captures.assignRoom(local.captureId, roomId: local.captureId)
            } else {
                let request = try CaptureRepository.creationRequest(local)
                let draft: DraftRoomResult = try await store.api.execute(request)
                guard draft.schemaVersion == 1, draft.captureId == local.captureId else { throw ClientError.invalidResponse }
                try await store.captures.assignRoom(local.captureId, roomId: draft.summary.id)
            }
            manifest = try await store.captures.load(local.captureId)
            if store.localCaptureEnabled {
                guard RoomCaptureSession.isSupported,
                      ARWorldTrackingConfiguration.supportsSceneReconstruction(.meshWithClassification) else {
                    throw ClientError.storage("Scanning requires a LiDAR-equipped iPhone Pro or iPad Pro.")
                }
                let directory = try await store.captures.createSourceBundle(local.captureId)
                let recorder = try SourceCaptureRecorder(session: arSession, directory: directory)
                sourceRecorder = recorder
                recorder.highResolutionPhotos = highResolutionPhotos
                recorder.onUpdate = { [weak self, weak recorder] in
                    guard let self, let recorder, self.phase == .scanning else { return }
                    self.acceptedFrames = recorder.photos.count
                    self.elapsedSeconds = recorder.elapsedSeconds
                    self.guidance = recorder.guidance
                    self.detailText = "\(recorder.stats.percent)% photo detail on observed surfaces"
                    if let error = recorder.recordingError { self.interrupt(reason: error.localizedDescription) }
                }
                let session = RoomCaptureSession(arSession: arSession)
                sourceSession = session; session.delegate = self
                phase = .scanning
                session.run(configuration: .init())
                recorder.start()
                return
            }
            // Historical 40-frame planning capture only. New reconstruction scans
            // return through the native source recorder above.
            let configuration = ARWorldTrackingConfiguration()
            // Apple requires the custom session to be running before RoomCaptureView receives it.
            arSession.run(configuration)
            let view = RoomCaptureView(frame: .zero, arSession: arSession)
            view.captureSession.delegate = self
            roomView = view
            phase = .scanning
            captureStartedAt = .now
            lastFreshFrameTime = .now
            view.captureSession.run(configuration: .init())
            if !store.localCaptureEnabled { watchConnectivity() }
            timer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
                guard let controller = self else { return }
                Task { @MainActor in controller.sample() }
            }
        } catch { arSession.pause(); self.error = error.localizedDescription; phase = .failed }
    }

    private func watchConnectivity() {
        let monitor = NWPathMonitor(); pathMonitor = monitor
        monitor.pathUpdateHandler = { [weak self] path in
            guard let controller = self else { return }
            if path.status != .satisfied { Task { @MainActor in controller.interrupt() } }
        }
        monitor.start(queue: DispatchQueue(label: "ReSpace.capture-connectivity"))
    }

    private func sample() {
        guard phase == .scanning, let manifest else { return }
        if let captureStartedAt { elapsedSeconds = Int((ContinuousClock.now - captureStartedAt).components.seconds) }
        guard let frame = arSession.currentFrame else {
            if ContinuousClock.now - lastFreshFrameTime > .seconds(2) { interrupt(reason: "Camera tracking stopped. Start a new scan.") }
            return
        }
        if let previous = lastFrameTimestamp, frame.timestamp <= previous {
            if ContinuousClock.now - lastFreshFrameTime > .seconds(2) { interrupt(reason: "Camera tracking stopped. Start a new scan.") }
            return
        }
        lastFreshFrameTime = .now; lastFrameTimestamp = frame.timestamp
        if case .limited(.relocalizing) = frame.camera.trackingState { interrupt(); return }
        guard case .normal = frame.camera.trackingState else {
            guidance = "Tracking paused. Move slowly toward an area you’ve already scanned."
            _ = policy.consider(observation(frame, normal: false), encoderAvailable: false)
            return
        }
        // A discontinuous jump suggests relocalization/origin loss. Never mix frames.
        if let last = lastCameraTransform, let timestamp = lastCameraTimestamp,
           frame.timestamp - timestamp < 0.5,
           (simd_distance(frame.camera.transform.columns.3, last.columns.3) > 1 ||
            simd_dot(SIMD3(frame.camera.transform.columns.2.x, frame.camera.transform.columns.2.y, frame.camera.transform.columns.2.z),
                     SIMD3(last.columns.2.x, last.columns.2.y, last.columns.2.z)) < 0) {
            interrupt(reason: "Tracking changed abruptly. Start again to keep the room aligned."); return
        }
        lastCameraTransform = frame.camera.transform; lastCameraTimestamp = frame.timestamp
        guidance = "Move slowly to capture every wall."
        guard policy.consider(observation(frame, normal: true), encoderAvailable: encoding == nil) else { return }
        acceptedFrames = policy.acceptedCount
        encoding = Task { [self] in
            defer { encoding = nil }
            do {
                _ = try await encoder.encode(frame, captureId: manifest.captureId, repository: store.captures, highQuality: store.localCaptureEnabled)
                await pumpUploads()
            } catch {
                if phase == .scanning || phase == .finishing { interrupt(reason: error.localizedDescription) }
            }
        }
    }

    private func observation(_ frame: ARFrame, normal: Bool) -> SamplingObservation {
        let pose = frame.camera.transform
        return SamplingObservation(time: frame.timestamp,
                                   position: SIMD3(pose.columns.3.x, pose.columns.3.y, pose.columns.3.z),
                                   forward: -SIMD3(pose.columns.2.x, pose.columns.2.y, pose.columns.2.z), trackingNormal: normal)
    }

    private func pumpUploads() async {
        guard !store.localCaptureEnabled else { return }
        guard let manifest, [.scanning, .finishing, .recovering].contains(phase) else { return }
        do {
            let fresh = try await store.captures.load(manifest.captureId)
            for frame in fresh.frames where uploads.count < 4 && uploads[frame.id] == nil && !completedUploads.contains(frame.id) {
                let acknowledged = frame.artifacts.allSatisfy { artifact in
                    fresh.acknowledgments.contains { $0.artifactId == artifact.id && $0.durable && $0.sha256 == artifact.sha256 && $0.byteLength == artifact.byteLength }
                }
                if acknowledged { completedUploads.insert(frame.id); continue }
                uploads[frame.id] = Task { [self] in
                    defer { uploads[frame.id] = nil }
                    do {
                        let request = try await store.captures.frameRequest(frame, manifest: fresh)
                        let result: FrameUploadResult
                        do {
                            let initial: FrameUploadResult = try await store.api.execute(request)
                            try initial.validateStorage(for: frame)
                            result = initial
                        }
                        catch let response as APIErrorEnvelope where response.retryable {
                            result = try await store.api.execute(request) // one server-response retry, same frame ID
                            try result.validateStorage(for: frame)
                        }
                        try await store.captures.acknowledge(fresh.captureId, receipts: result.acknowledgments)
                        completedUploads.insert(frame.id)
                        if let count = result.distinctDetails { detailText = "\(count) distinct details found" }
                        else if result.perceptionState == "failed" { detailText = "Some details unavailable. Room measurements are preserved." }
                        await pumpUploads()
                    } catch {
                        if phase == .scanning { interrupt(reason: error.localizedDescription) }
                        else if phase == .finishing || phase == .recovering { self.error = error.localizedDescription }
                    }
                }
            }
        } catch { self.error = error.localizedDescription; if phase == .scanning { interrupt() } }
    }

    func done() {
        guard phase == .scanning else { return }
        if let sourceRecorder {
            guard canFinish else { guidance = "Hold steady while the first useful photo is saved."; return }
            phase = .finishing
            let export = Task { try await sourceRecorder.freeze() }
            sourceMeshExport = export
            Task {
                do {
                    _ = try await export.value
                    guard phase == .finishing else { return }
                    sourceSession?.stop(pauseARSession: false)
                } catch {
                    guard phase == .finishing else { return }
                    self.error = error.localizedDescription; phase = .failed; sourceRecorder.stop(); arSession.pause()
                }
            }
            return
        }
        phase = .finishing; stopSampling()
        roomView?.captureSession.stop(pauseARSession: true)
    }

    nonisolated func captureSession(_ session: RoomCaptureSession, didEndWith data: CapturedRoomData, error: Error?) {
        Task { @MainActor [self] in
            guard phase == .finishing, let manifest else { if phase == .scanning { interrupt() }; return }
            if let error { interrupt(reason: error.localizedDescription); return }
            do {
                if let sourceRecorder {
                    // Attempt the optional raw recovery archive before RoomBuilder,
                    // as upstream does. A framework encoding rejection must not skip
                    // building the layout from the original in-memory capture.
                    try sourceRecorder.saveRawRoom(data)
                    let room: CapturedRoom?
                    var layoutError: String?
                    do { room = try await RoomBuilder(options: [.beautifyObjects]).capturedRoom(from: data) }
                    catch { room = nil; layoutError = String(error.localizedDescription.prefix(1000)) }
                    guard let sourceMeshExport else { throw ClientError.storage("The source mesh export was not completed.") }
                    let mesh = try await sourceMeshExport.value
                    guard phase == .finishing else { return }
                    try await sourceRecorder.complete(room: room, mesh: mesh, layoutError: layoutError)
                    guard phase == .finishing else { return }
                    let thumbnail = try sourceRecorder.photos.last.map { try Data(contentsOf: sourceRecorder.bundle.file($0.file)) }
                    let roomBytes = try room.map { _ in try Data(contentsOf: sourceRecorder.bundle.file("rooms/room-0.json")) }
                    let integrity = try Data(contentsOf: sourceRecorder.bundle.file("integrity.json"))
                    try await store.captures.complete(manifest.captureId, roomData: roomBytes, thumbnailData: thumbnail, sourceIntegrityData: integrity, sourceLayoutError: layoutError)
                    guard phase == .finishing else { return }
                    hasCompletedCapture = true; arSession.pause(); phase = .recovering
                    await finalize()
                    return
                }
                let room = try await RoomBuilder(options: [.beautifyObjects]).capturedRoom(from: data)
                await encoding?.value
                guard phase == .finishing else { return }
                let export = try await encoder.export(room)
                guard phase == .finishing else { return }
                try await store.captures.complete(manifest.captureId, roomData: export, thumbnailData: nil)
                hasCompletedCapture = true
                phase = .recovering
                await finalize()
            } catch {
                guard phase == .finishing else { return }
                self.error = error.localizedDescription; phase = .failed; sourceRecorder?.stop(); arSession.pause()
            }
        }
    }
    nonisolated func captureSession(_ session: RoomCaptureSession, didProvide instruction: RoomCaptureSession.Instruction) {
        Task { @MainActor [self] in
            guard phase == .scanning else { return }
            switch instruction {
            case .moveCloseToWall: guidance = "Move closer to the wall."
            case .moveAwayFromWall: guidance = "Step back from the wall."
            case .slowDown: guidance = "Slow down for a clearer scan."
            case .turnOnLight: guidance = "Turn on more lights to help the scan."
            case .normal: guidance = "Keep moving slowly around the room."
            case .lowTexture: guidance = "Aim toward furniture or a wall with more visible detail."
            @unknown default: break
            }
        }
    }

    nonisolated func captureSession(_ session: RoomCaptureSession, didUpdate room: CapturedRoom) {
        Task { @MainActor [weak self] in
            guard let self, phase == .scanning else { return }
            sourceRecorder?.updateRoom(room)
        }
    }
    func takeDetailPhoto() { sourceRecorder?.takePhoto() }

    func finalize() async {
        guard let manifest else { return }
        phase = .recovering; error = nil
        do {
            let retained = try await store.captures.load(manifest.captureId)
            if store.localCaptureEnabled {
                if retained.sourceBundleFormat == "house-capture/5" {
                    var count = 0
                    if let artifact = retained.roomExport {
                        let data = try await store.captures.bytes(artifact, captureId: retained.captureId)
                        count = try JSONDecoder().decode(CapturedRoom.self, from: data).objects.count
                    }
                    if retained.state != "local_saved" { try await store.captures.saveLocalRoom(retained.captureId, objectCount: count) }
                    phase = .ready(retained.captureId)
                    return
                }
                if retained.state != "local_saved" {
                    guard let artifact = retained.roomExport else { throw ClientError.storage("The completed room export is missing.") }
                    let bytes = try await store.captures.bytes(artifact, captureId: retained.captureId)
                    let url = await store.captures.localPreviewURL(retained.captureId)
                    let objectCount = try await encoder.exportLocalPreview(bytes, to: url)
                    try await store.captures.saveLocalRoom(retained.captureId, objectCount: objectCount)
                }
                phase = .ready(retained.captureId)
                return
            }
            if retained.state == "finalized", retained.canEvictRawFiles {
                try await store.refreshRoom(retained.roomId)
                phase = .ready(retained.roomId)
                return
            }
            await pumpUploads()
            while !uploads.isEmpty {
                let batch = Array(uploads.values)
                for task in batch { await task.value }
                if error != nil { throw ClientError.storage("Some uploads need retry. The finished scan is retained.") }
                await pumpUploads()
            }
            if let known = try await store.api.lookup(manifest.finalizeId) {
                var operation = known
                while !operation.state.isTerminal {
                    guard operation.state != .needsClarification else { throw ClientError.invalidResponse }
                    try await Task.sleep(for: .seconds(2))
                    guard let next = try await store.api.lookup(manifest.finalizeId) else { throw ClientError.invalidResponse }
                    operation = next
                }
                if operation.state != .succeeded { throw operation.failure ?? APIErrorEnvelope(code: "finalize_failed", message: "The room could not be finalized. Retry or discard this scan.", retryable: true) }
            }
            let request = try await store.captures.finalizationRequest(manifest.captureId)
            var result: FinalizeResult = try await store.api.execute(request)
            if var operation = result.operation {
                while !operation.state.isTerminal {
                    try await Task.sleep(for: .seconds(2))
                    guard let next = try await store.api.lookup(operation.id) else { throw ClientError.invalidResponse }
                    operation = next
                }
                guard operation.state == .succeeded else {
                    if let failure = operation.failure { throw failure }
                    throw ClientError.invalidResponse
                }
                result = try await store.api.execute(request)
            }
            guard let record = result.room, let snapshot = record.snapshot else { throw ClientError.invalidResponse }
            guard result.schemaVersion == 1, record.summary.id == manifest.roomId,
                  snapshot.captureId == manifest.captureId else { throw ClientError.invalidResponse }
            try snapshot.validateGeometry()
            try await store.captures.finalized(manifest.captureId, receipts: result.acknowledgments, transform: snapshot.scanToRoomTransform)
            let acknowledgedCapture = try await store.captures.load(manifest.captureId)
            if !acknowledgedCapture.canEvictRawFiles {
                throw ClientError.storage("The room is ready, but some raw artifacts are not yet acknowledged. Retry to finish protecting your scan.")
            }
            try await store.refreshRoom(record.summary.id)
            phase = .ready(record.summary.id)
        } catch { self.error = error.localizedDescription; phase = .failed }
    }

    func interrupt(reason: String? = nil) {
        guard phase == .scanning || phase == .finishing else { return }
        phase = .interrupted; error = reason
        stopSampling(); roomView?.captureSession.stop(pauseARSession: true); arSession.pause()
        sourceRecorder?.stop(); sourceSession?.stop(pauseARSession: true)
    }
    func appBecameInactive() { if phase == .scanning { interrupt() } }
    private func stopSampling() {
        timer?.invalidate(); timer = nil; pathMonitor?.cancel(); pathMonitor = nil
    }
    func discard() async {
        interrupt(); stopSampling()
        for task in uploads.values { task.cancel() }
        await sourceRecorder?.drainAfterStop()
        _ = await sourceMeshExport?.result; sourceMeshExport = nil
        await encoding?.value
        guard let manifest else { return }
        do {
            if store.localCaptureEnabled {
                try await store.captures.removeCapture(manifest.captureId)
                return
            }
            try await store.captures.abandon(manifest.captureId)
            if manifest.roomId.isEmpty { await store.abandonUncertainDraft(manifest) }
            else { await store.deleteRoom(manifest.roomId) }
        } catch { self.error = error.localizedDescription }
    }
}
