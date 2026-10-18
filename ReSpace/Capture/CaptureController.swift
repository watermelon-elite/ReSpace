import ARKit
import AVFoundation
import Network
import Observation
import RoomPlan
import UIKit

@MainActor @Observable
final class CaptureController: NSObject, RoomCaptureSessionDelegate {
    enum Phase: Equatable { case preparing, permissionDenied, scanning, finishing, recovering, interrupted, failed, ready(String) }
    var phase: Phase = .preparing
    var guidance = "Move slowly to capture the walls and furniture."
    var acceptedFrames = 0
    var elapsedSeconds = 0
    var canFinish: Bool { !store.localCaptureEnabled || elapsedSeconds >= SamplingPolicy.reconstructionMinimumSeconds }
    private var captureStartedAt: ContinuousClock.Instant?
    private var photoBudgetReached = false
    var detailText = "Details processing"
    var error: String?
    private(set) var roomView: RoomCaptureView?
    private let arSession = ARSession()
    private let meshEncoder = SceneMeshEncoder()
    private var meshExport: Task<Data, Error>?
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
            policy = .reconstruction
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
            let configuration = ARWorldTrackingConfiguration()
            if store.localCaptureEnabled {
                guard ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh) else {
                    throw ClientError.storage("This device does not support LiDAR surface capture.")
                }
                configuration.sceneReconstruction = .mesh
                if let format = ARWorldTrackingConfiguration.supportedVideoFormats
                    .filter({ $0.framesPerSecond == 30 && $0.imageResolution.width <= 3840 })
                    .max(by: { $0.imageResolution.width * $0.imageResolution.height < $1.imageResolution.width * $1.imageResolution.height }) {
                    configuration.videoFormat = format
                }
                // Keep measured surfaces; do not deliberately flatten them to detected planes.
                configuration.planeDetection = []
                if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
                    configuration.frameSemantics.insert(.sceneDepth)
                }
            }
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
        if store.localCaptureEnabled,
           !ScanMeshConfiguration.isEnabled(
                (arSession.configuration as? ARWorldTrackingConfiguration)?.sceneReconstruction, mesh: .mesh) {
            interrupt(reason: "Surface capture stopped. Start a new scan to keep the room aligned."); return
        }
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
        guidance = store.localCaptureEnabled ? (photoBudgetReached ? "Photo storage limit reached. Finish when the three-minute minimum is complete." : "Move around furniture and scan each surface from several sides.") : "Move slowly to capture every wall."
        guard policy.consider(observation(frame, normal: true), encoderAvailable: encoding == nil && !photoBudgetReached) else { return }
        acceptedFrames = policy.acceptedCount
        encoding = Task { [self] in
            defer { encoding = nil }
            do {
                _ = try await encoder.encode(frame, captureId: manifest.captureId, repository: store.captures, highQuality: store.localCaptureEnabled)
                if store.localCaptureEnabled { photoBudgetReached = !(try await store.captures.hasReconstructionFrameCapacity(manifest.captureId)) }
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
        guard canFinish else { guidance = "Scan for at least three minutes before finishing."; return }
        if store.localCaptureEnabled {
            guard let frame = arSession.currentFrame, case .normal = frame.camera.trackingState else {
                guidance = "Wait for tracking to recover before finishing."; return
            }
            let anchors = frame.anchors.compactMap { $0 as? ARMeshAnchor }
            guard anchors.contains(where: { $0.geometry.faces.count > 0 }), let manifest else {
                guidance = "No surfaces captured yet. Move slowly around the room."; return
            }
            // Freeze a single current anchor set before stopping; no older anchor versions are merged.
            let captureId = manifest.captureId, timestamp = frame.timestamp
            meshExport = Task { try await meshEncoder.encode(anchors, captureId: captureId, timestamp: timestamp) }
        }
        phase = .finishing; stopSampling()
        roomView?.captureSession.stop(pauseARSession: true)
    }

    nonisolated func captureSession(_ session: RoomCaptureSession, didEndWith data: CapturedRoomData, error: Error?) {
        Task { @MainActor [self] in
            guard phase == .finishing, let manifest else { if phase == .scanning { interrupt() }; return }
            if let error { interrupt(reason: error.localizedDescription); return }
            do {
                // Preserve observed furniture positions for local scans; beautification may move chairs.
                let options: RoomBuilder.ConfigurationOptions = store.localCaptureEnabled ? [] : [.beautifyObjects]
                let room = try await RoomBuilder(options: options).capturedRoom(from: data)
                await encoding?.value
                guard phase == .finishing else { return }
                let export = try await encoder.export(room)
                guard phase == .finishing else { return }
                let meshData: Data?
                if store.localCaptureEnabled {
                    guard let meshExport else { throw ClientError.storage("The surface scan is missing. Scan this room again.") }
                    meshData = try await meshExport.value
                } else { meshData = nil }
                guard phase == .finishing else { return }
                try await store.captures.complete(manifest.captureId, roomData: export, thumbnailData: nil, sceneMeshData: meshData)
                meshExport = nil
                hasCompletedCapture = true
                phase = .recovering
                await finalize()
            } catch { self.error = error.localizedDescription; phase = .failed }
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

    func finalize() async {
        guard let manifest else { return }
        phase = .recovering; error = nil
        do {
            let retained = try await store.captures.load(manifest.captureId)
            if store.localCaptureEnabled {
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
        stopSampling(); meshExport?.cancel(); roomView?.captureSession.stop(pauseARSession: true); arSession.pause()
    }
    func appBecameInactive() { if phase == .scanning { interrupt() } }
    private func stopSampling() {
        timer?.invalidate(); timer = nil; pathMonitor?.cancel(); pathMonitor = nil
    }
    func discard() async {
        interrupt(); stopSampling()
        for task in uploads.values { task.cancel() }
        await encoding?.value
        _ = await meshExport?.result; meshExport = nil
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
