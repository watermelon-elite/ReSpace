import SwiftUI
import RoomPlan
import ARKit
import AVFoundation
import CoreImage
import ImageIO
import CryptoKit

struct CaptureArchive: Codable {
    var roomID: String
    var captureID: String
    var startedAt: String
    var phase = "capturing"
    var frames: [JSONValue] = []
    var storedFrameIDs: [String] = []
    var finalizeRequest: PendingRequest?
    var cleanupOperationID = UUID().uuidString
    var folder: URL { URL.documentsDirectory.appendingPathComponent("Captures/\(captureID)") }
    func save() throws {
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try JSONEncoder().encode(self).write(to: folder.appendingPathComponent("capture.json"), options: [.atomic, .completeFileProtectionUnlessOpen])
    }
    static func recoverable() -> [CaptureArchive] {
        let folder = URL.documentsDirectory.appendingPathComponent("Captures")
        return ((try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)) ?? []).compactMap { try? JSONDecoder().decode(Self.self, from: Data(contentsOf: $0.appendingPathComponent("capture.json"))) }
    }
}

private struct EncodedFrame {
    let parts: [String: Data]
    let meta: JSONValue
}

@MainActor @Observable final class CaptureController: NSObject, RoomCaptureViewDelegate, RoomCaptureSessionDelegate {
    var view: RoomCaptureView?
    var archive: CaptureArchive
    var status = "Scan slowly around the room. Aim for 60–120 seconds."
    var failure: String?
    var encoding = false
    var uploading = false
    var finishing = false
    var finished = false
    var preview: JSONValue = .null
    var started = false
    var gate = SamplingGate()
    private var timer: Timer?
    private let client: APIClient
    private let app: AppModel
    var stored: Int { archive.storedFrameIDs.count }
    var accepted: Int { archive.frames.count }
    init(archive: CaptureArchive, app: AppModel, client: APIClient) { self.archive = archive; self.app = app; self.client = client; super.init(); if let encoded = archive.finalizeRequest?.body["raw_export_base64"].string, let raw = Data(base64Encoded: encoded), let decoded = try? JSONDecoder().decode(JSONValue.self, from: raw) { preview = decoded } }
    required init?(coder: NSCoder) { return nil }
    func encode(with coder: NSCoder) {}
    func attach(_ view: RoomCaptureView) {
        guard self.view == nil else { return }
        self.view = view; view.delegate = self; view.captureSession.delegate = self
        if archive.phase == "capturing" {
            view.captureSession.run(configuration: .init())
            timer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in guard let controller = self else { return }; Task { @MainActor [controller] in controller.sample() } }
        } else { Task { await recover() } }
    }
    func captureSession(_ session: RoomCaptureSession, didStartWith configuration: RoomCaptureSession.Configuration) { started = true }
    func captureSession(_ session: RoomCaptureSession, didProvide instruction: RoomCaptureSession.Instruction) { status = String(describing: instruction) }
    func captureSession(_ session: RoomCaptureSession, didEndWith data: CapturedRoomData, error: Error?) {
        started = false
        if let error { interrupt(error.localizedDescription) }
        else if !finishing { interrupt("Scan interrupted. Start again to capture this room.") }
    }
    func captureView(shouldPresent roomDataForProcessing: CapturedRoomData, error: Error?) -> Bool { error == nil && finishing }
    func captureView(didPresent processedResult: CapturedRoom, error: Error?) {
        if let error { interrupt(error.localizedDescription); return }
        Task {
            while encoding { try? await Task.sleep(for: .milliseconds(50)) }
            do {
                let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
                let raw = try encoder.encode(processedResult)
                preview = try JSONDecoder().decode(JSONValue.self, from: raw)
                let exportID = "export_\(archive.captureID)"
                let descriptor = Self.descriptor(id: exportID, captureID: archive.captureID, frameID: nil, kind: "roomplan", format: "application/json", data: raw)
                let completionID = UUID().uuidString
                let manifest: JSONValue = .object(["room_id": .string(archive.roomID), "capture_id": .string(archive.captureID), "final_export_artifact_id": .string(exportID), "frames": .array(archive.frames.map { .object(["frame_id": $0["frame_id"], "idx": $0["idx"]]) }), "artifacts": .array(archive.frames.flatMap { $0["artifacts"].array } + [descriptor]), "completion_id": .string(completionID), "started_at": .string(archive.startedAt), "completed_at": .string(ISO8601DateFormatter().string(from: Date()))])
                archive.finalizeRequest = PendingRequest(path: "rooms/\(archive.roomID)/finalize", roomID: archive.roomID, body: ["operation_id": .string(completionID), "capture_id": .string(archive.captureID), "raw_export_base64": .string(raw.base64EncodedString()), "export_descriptor": descriptor, "manifest": manifest])
                archive.phase = "upload_pending"; try archive.save(); await recover()
            } catch { failure = error.localizedDescription }
        }
    }
    func done() { guard !finishing else { return }; finishing = true; timer?.invalidate(); view?.captureSession.stop() }
    func interrupt(_ message: String) {
        guard archive.phase == "capturing" else { return }
        failure = message; started = false; timer?.invalidate(); archive.phase = "interrupted"
        do { try archive.save() } catch { failure = error.localizedDescription }
        view?.captureSession.stop()
    }
    func abandon() async {
        timer?.invalidate(); started = false; archive.phase = "abandoned"; view?.captureSession.stop()
        do {
            try archive.save()
            _ = try await app.submit(PendingRequest(path: "rooms/\(archive.roomID)", method: "DELETE", roomID: archive.roomID, body: ["operation_id": .string(archive.cleanupOperationID)]))
            if FileManager.default.fileExists(atPath: archive.folder.path) { try FileManager.default.removeItem(at: archive.folder) }
        } catch { failure = "Cleanup is pending: \(error.localizedDescription)" }
    }
    func sample() {
        guard started, !finishing, !encoding, archive.phase == "capturing", let frame = view?.captureSession.arSession.currentFrame else { return }
        guard case .normal = frame.camera.trackingState else { status = "Tracking paused. Move slowly and show more room detail."; return }
        let pose = frame.camera.transform
        var candidate = gate
        guard candidate.accept(time: frame.timestamp, position: [Double(pose.columns.3.x), Double(pose.columns.3.y), Double(pose.columns.3.z)], forward: [Double(-pose.columns.2.x), Double(-pose.columns.2.y), Double(-pose.columns.2.z)], trackingNormal: true) else { return }
        encoding = true
        let index = archive.frames.count; let captureID = archive.captureID
        Task {
            do {
                let encoded = try await Task.detached(priority: .utility) { try Self.encode(frame, index: index, captureID: captureID) }.value
                guard archive.phase == "capturing" else { encoding = false; return }
                let frameID = encoded.meta["frame_id"].text
                for (kind, bytes) in encoded.parts { try bytes.write(to: archive.folder.appendingPathComponent("\(frameID).\(kind)"), options: [.atomic, .completeFileProtectionUnlessOpen]) }
                archive.frames.append(encoded.meta); try archive.save(); gate = candidate; encoding = false
                status = accepted == 40 ? "40 frames accepted. Continue scanning; tap Done when the room is measured." : "Scanning room"
                await uploadPending()
            } catch { encoding = false; interrupt("Capture storage failed: \(error.localizedDescription)") }
        }
    }
    func uploadPending() async {
        guard !uploading else { return }; uploading = true; defer { uploading = false }
        for meta in archive.frames where !archive.storedFrameIDs.contains(meta["frame_id"].text) {
            do {
                let boundary = UUID().uuidString
                var body = Data()
                func append(_ text: String) { body.append(Data(text.utf8)) }
                append("--\(boundary)\r\nContent-Disposition: form-data; name=\"meta\"\r\nContent-Type: application/json\r\n\r\n")
                body.append(try meta.data()); append("\r\n")
                for artifact in meta["artifacts"].array {
                    let kind = artifact["kind"].text
                    append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(kind)\"; filename=\"\(kind)\"\r\nContent-Type: \(kind == "jpeg" ? "image/jpeg" : "application/octet-stream")\r\n\r\n")
                    body.append(try Data(contentsOf: archive.folder.appendingPathComponent("\(meta["frame_id"].text).\(kind)"))); append("\r\n")
                }
                append("--\(boundary)--\r\n")
                var result: JSONValue
                do { result = try await client.request("rooms/\(archive.roomID)/keyframes", method: "POST", data: body, contentType: "multipart/form-data; boundary=\(boundary)") }
                catch let error as APIError where error.retryable { result = try await client.request("rooms/\(archive.roomID)/keyframes", method: "POST", data: body, contentType: "multipart/form-data; boundary=\(boundary)") }
                let expected = Set(meta["artifacts"].array.map { $0["artifact_id"].text })
                let received = Set(result["receipts"].array.filter { $0["durable"].bool == true || $0["outcome"].text == "stored" }.map { $0["artifact_id"].text })
                guard expected.isSubset(of: received) else { throw ContractError.invalid("The backend did not acknowledge all frame artifacts.") }
                archive.storedFrameIDs.append(meta["frame_id"].text); try archive.save()
            } catch {
                if archive.phase == "capturing" { interrupt("Upload interrupted. Start again to capture this room. \(error.localizedDescription)") }
                else { failure = "Finished scan retained. Retry upload: \(error.localizedDescription)" }
                return
            }
        }
    }
    func recover() async {
        failure = nil
        while uploading && !Task.isCancelled { try? await Task.sleep(for: .milliseconds(50)) }
        await uploadPending()
        guard !uploading, let request = archive.finalizeRequest else { return }
        do {
            let result = try await app.submit(request)
            guard result["capture_status"]["state"].text == "complete", result["capture_status"]["missing_artifacts"].int == 0 else { throw ContractError.invalid("Native preview is available. Upload acknowledgment is incomplete; retry finalization.") }
            try FileManager.default.removeItem(at: archive.folder); finished = true
        } catch { failure = error.localizedDescription }
    }
    nonisolated private static func descriptor(id: String, captureID: String, frameID: String?, kind: String, format: String, data: Data) -> JSONValue {
        .object(["artifact_id": .string(id), "capture_id": .string(captureID), "frame_id": frameID.map(JSONValue.string) ?? .null, "kind": .string(kind), "format": .string(format), "byte_length": .number(Double(data.count)), "checksum": .string(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined())])
    }
    nonisolated private static func packed(_ buffer: CVPixelBuffer, bytesPerPixel: Int) throws -> Data {
        CVPixelBufferLockBaseAddress(buffer, .readOnly); defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
        guard let address = CVPixelBufferGetBaseAddress(buffer) else { throw ContractError.invalid("Depth buffer is unavailable.") }
        var data = Data(); let width = CVPixelBufferGetWidth(buffer); let height = CVPixelBufferGetHeight(buffer)
        for row in 0..<height { data.append(address.advanced(by: row * CVPixelBufferGetBytesPerRow(buffer)).assumingMemoryBound(to: UInt8.self), count: width * bytesPerPixel) }
        return data
    }
    nonisolated private static func encode(_ frame: ARFrame, index: Int, captureID: String) throws -> EncodedFrame {
        let image = CIImage(cvPixelBuffer: frame.capturedImage)
        let scale = min(1, 1280 / max(image.extent.width, image.extent.height))
        let resized = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        let context = CIContext(options: [.cacheIntermediates: false])
        guard let cg = context.createCGImage(resized, from: CGRect(x: 0, y: 0, width: floor(resized.extent.width), height: floor(resized.extent.height))) else { throw ContractError.invalid("Could not encode camera image.") }
        let output = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(output, "public.jpeg" as CFString, 1, nil) else { throw ContractError.invalid("JPEG encoder unavailable.") }
        CGImageDestinationAddImage(destination, cg, [kCGImageDestinationLossyCompressionQuality: 0.7] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw ContractError.invalid("JPEG encoding failed.") }
        let frameID = UUID().uuidString
        let intrinsics = frame.camera.intrinsics
        let sx = Double(cg.width) / Double(CVPixelBufferGetWidth(frame.capturedImage)); let sy = Double(cg.height) / Double(CVPixelBufferGetHeight(frame.capturedImage))
        var parts: [String: Data] = ["jpeg": output as Data]
        var meta: [String: JSONValue] = ["schema_version": .number(1), "operation_id": .string(UUID().uuidString), "capture_id": .string(captureID), "frame_id": .string(frameID), "idx": .number(Double(index)), "w": .number(Double(cg.width)), "h": .number(Double(cg.height)), "orientation": .string("sensor_landscape"), "timestamp": .number(frame.timestamp), "timestamp_source": .string("ar_session_seconds"), "intrinsics": .object(["fx": .number(Double(intrinsics.columns.0.x) * sx), "fy": .number(Double(intrinsics.columns.1.y) * sy), "cx": .number(Double(intrinsics.columns.2.x) * sx), "cy": .number(Double(intrinsics.columns.2.y) * sy)]), "transform": .array((0..<4).flatMap { column in (0..<4).map { .number(Double(frame.camera.transform[column][$0])) } })]
        if let depth = frame.sceneDepth, CVPixelBufferGetPixelFormatType(depth.depthMap) == kCVPixelFormatType_DepthFloat32 {
            parts["depth"] = try packed(depth.depthMap, bytesPerPixel: 4)
            let w = CVPixelBufferGetWidth(depth.depthMap); let h = CVPixelBufferGetHeight(depth.depthMap)
            meta["depth_w"] = .number(Double(w)); meta["depth_h"] = .number(Double(h)); meta["depth_format"] = .string("float32_le_m")
            if let confidence = depth.confidenceMap, CVPixelBufferGetPixelFormatType(confidence) == kCVPixelFormatType_OneComponent8, CVPixelBufferGetWidth(confidence) == w, CVPixelBufferGetHeight(confidence) == h { parts["confidence"] = try packed(confidence, bytesPerPixel: 1); meta["confidence_format"] = .string("uint8") }
        }
        meta["artifacts"] = .array(parts.keys.sorted().map { kind in
            var fields = descriptor(id: "\(frameID)_\(kind)", captureID: captureID, frameID: frameID, kind: kind, format: kind == "jpeg" ? "image/jpeg" : kind == "depth" ? "float32_le_m" : "uint8", data: parts[kind]!).object
            fields["w"] = kind == "jpeg" ? meta["w"] : meta["depth_w"]; fields["h"] = kind == "jpeg" ? meta["h"] : meta["depth_h"]; fields["orientation"] = .string("sensor_landscape")
            return .object(fields)
        })
        return EncodedFrame(parts: parts, meta: .object(meta))
    }
}

struct CaptureSurface: UIViewRepresentable {
    let controller: CaptureController
    func makeUIView(context: Context) -> RoomCaptureView { let view = RoomCaptureView(frame: .zero); controller.attach(view); return view }
    func updateUIView(_ uiView: RoomCaptureView, context: Context) {}
}

struct CaptureScreen: View {
    @State var controller: CaptureController
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @State private var confirmDiscard = false
    @State private var showPreview = false
    @State private var selectedObject: String?
    var body: some View {
        ZStack(alignment: .bottom) {
            CaptureSurface(controller: controller).ignoresSafeArea()
            VStack {
                Text(controller.status)
                Text("Accepted \(controller.accepted) · Stored \(controller.stored) · Pending \(controller.accepted - controller.stored)").font(.caption.monospacedDigit())
                if let error = controller.failure { Text(error).foregroundStyle(.red); if controller.archive.phase == "upload_pending" { Button("Retry finished upload") { Task { await controller.recover() } } } }
                if controller.preview != .null { Button("Review native measurements") { showPreview = true } }
                if controller.archive.phase == "capturing" { Button("Done") { controller.done() }.buttonStyle(.borderedProminent).disabled(controller.finishing) }
                Button("Cancel Scan", role: .destructive) { confirmDiscard = true }
            }.padding().background(.regularMaterial).clipShape(RoundedRectangle(cornerRadius: 20)).padding()
        }
        .sheet(isPresented: $showPreview) { NavigationStack { RoomScene(document: controller.preview, native: true, selectedID: $selectedObject, ghosts: true, resetToken: 0).navigationTitle("Native measurements").toolbar { Button("Done") { showPreview = false } } } }
        .interactiveDismissDisabled()
        .confirmationDialog("Discard this scan and its photos?", isPresented: $confirmDiscard) { Button("Discard Scan", role: .destructive) { Task { await controller.abandon(); dismiss() } } }
        .onChange(of: controller.finished) { _, value in if value { dismiss() } }
        .onChange(of: scenePhase) { _, phase in if phase != .active { controller.interrupt("Scan interrupted. Start again to capture this room.") } }
    }
}
