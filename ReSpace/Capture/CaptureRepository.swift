import Foundation
import CryptoKit

/// Device-only test capture, separate from backend RoomRecord and storage receipts.
struct LocalSavedRoom: Codable, Identifiable, Sendable {
    var id: String
    var name: String
    var createdAt: String
    var objectCount: Int
}

actor CaptureRepository {
    private let directory: URL
    private let maximumFrames: Int
    init(directory: URL, maximumFrames: Int = 40) {
        self.directory = directory; self.maximumFrames = maximumFrames
    }

    private func folder(_ id: String) -> URL {
        let safe = SHA256.hash(data: Data(id.utf8)).map { String(format: "%02x", $0) }.joined()
        return directory.appendingPathComponent(safe, isDirectory: true)
    }
    func create() throws -> CaptureManifest {
        let captureId = UUID().uuidString
        let manifest = CaptureManifest(roomId: "", captureId: captureId,
                                       creationId: UUID().uuidString, finalizeId: UUID().uuidString,
                                       createdAt: ISO8601DateFormatter().string(from: Date()),
                                       state: "creating", frames: [], acknowledgments: [])
        try save(manifest)
        return manifest
    }
    func save(_ manifest: CaptureManifest) throws {
        let folder = folder(manifest.captureId)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try Wire.encoder().encode(manifest).write(to: folder.appendingPathComponent("manifest.json"), options: .atomic)
    }
    func load(_ id: String) throws -> CaptureManifest {
        try Wire.decoder().decode(CaptureManifest.self, from: Data(contentsOf: folder(id).appendingPathComponent("manifest.json")))
    }
    func manifests() throws -> [CaptureManifest] {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil).map { url in
            try Wire.decoder().decode(CaptureManifest.self, from: Data(contentsOf: url.appendingPathComponent("manifest.json")))
        }
    }
    func assignRoom(_ id: String, roomId: String) throws {
        var manifest = try load(id); manifest.roomId = roomId; manifest.state = "acquiring"; try save(manifest)
    }
    func writeArtifact(captureId: String, type: String, bytes: Data, extension suffix: String) throws -> ArtifactRecord {
        let files = try FileManager.default.contentsOfDirectory(at: folder(captureId), includingPropertiesForKeys: [.fileSizeKey])
        let retainedBytes = try files.reduce(0) { try $0 + ($1.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0) }
        guard retainedBytes + bytes.count <= SamplingPolicy.reconstructionMaximumBytes else {
            throw ClientError.storage("This scan reached its 2 GB storage limit. Start a smaller room scan.")
        }
        let capacity = try? folder(captureId).resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey, .volumeAvailableCapacityKey])
        // Some macOS volumes report zero for important-usage capacity despite free space.
        let available = max(capacity?.volumeAvailableCapacityForImportantUsage ?? -1,
                            capacity?.volumeAvailableCapacity.map(Int64.init) ?? -1)
        if available >= 0 && available < Int64(bytes.count + 512 * 1024 * 1024) {
            throw ClientError.storage("Free more storage before continuing this scan.")
        }
        let id = UUID().uuidString
        let filename = "\(id).\(suffix)"
        try bytes.write(to: folder(captureId).appendingPathComponent(filename), options: .atomic)
        return ArtifactRecord(id: id, type: type, filename: filename, byteLength: bytes.count,
                              sha256: SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined())
    }
    func append(_ frame: CaptureFrame, captureId: String) throws {
        var manifest = try load(captureId)
        guard manifest.state == "acquiring", manifest.frames.count < maximumFrames else { throw ClientError.storage("This scan is no longer accepting frames.") }
        manifest.frames.append(frame); try save(manifest)
    }

    func hasReconstructionFrameCapacity(_ id: String) throws -> Bool {
        let manifest = try load(id)
        let reserve = 192 * 1024 * 1024 // Keep room for the final mesh and room export.
        guard manifest.frames.count < maximumFrames,
              manifest.allArtifacts.reduce(0, { $0 + $1.byteLength }) < SamplingPolicy.reconstructionMaximumBytes - reserve else { return false }
        let capacity = try? folder(id).resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey, .volumeAvailableCapacityKey])
        let available = max(capacity?.volumeAvailableCapacityForImportantUsage ?? -1,
                            capacity?.volumeAvailableCapacity.map(Int64.init) ?? -1)
        return available < 0 || available >= Int64(reserve + 512 * 1024 * 1024)
    }
    func complete(_ id: String, roomData: Data, thumbnailData: Data?, sceneMeshData: Data? = nil) throws {
        var manifest = try load(id)
        guard manifest.state == "acquiring" else { throw ClientError.storage("This scan was interrupted. Start again.") }
        if let sceneMeshData { _ = try ScanMeshSnapshot.decode(sceneMeshData, captureId: id) }
        manifest.roomExport = try writeArtifact(captureId: id, type: "roomplan", bytes: roomData, extension: "json")
        let thumbnailBytes = try thumbnailData ?? manifest.frames.last?.artifacts.first(where: { $0.type == "jpeg" }).map { try bytes($0, captureId: id) }
        if let thumbnailBytes { manifest.thumbnail = try writeArtifact(captureId: id, type: "thumbnail", bytes: thumbnailBytes, extension: "jpg") }
        if let sceneMeshData {
            manifest.sceneMesh = try writeArtifact(captureId: id, type: "scene_mesh", bytes: sceneMeshData, extension: "mesh")
        }
        manifest.state = "completed"
        try save(manifest)
    }
    func acknowledge(_ id: String, receipts: [ArtifactAcknowledgment]) throws {
        var manifest = try load(id)
        for receipt in receipts {
            manifest.acknowledgments.removeAll { $0.artifactId == receipt.artifactId }
            manifest.acknowledgments.append(receipt)
        }
        try save(manifest)
    }
    func bytes(_ artifact: ArtifactRecord, captureId: String) throws -> Data {
        let data = try Data(contentsOf: folder(captureId).appendingPathComponent(artifact.filename))
        guard data.count == artifact.byteLength,
              SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined() == artifact.sha256 else {
            throw ClientError.storage("A retained scan artifact failed its integrity check.")
        }
        return data
    }
    func frameRequest(_ frame: CaptureFrame, manifest: CaptureManifest) throws -> APIRequest {
        // A recovered upload has identical bytes as well as identical semantic artifacts.
        let identityHash = SHA256.hash(data: Data(frame.id.utf8)).map { String(format: "%02x", $0) }.joined()
        var multipart = MultipartBody(boundary: "ReSpace-\(identityHash)")
        multipart.append(name: "meta", type: "application/json", bytes: try Wire.encoder().encode(frame))
        for artifact in frame.artifacts {
            let type = artifact.type == "jpeg" ? "image/jpeg" : artifact.type == "metadata" ? "application/json" : "application/octet-stream"
            multipart.append(name: artifact.type, filename: artifact.filename, type: type,
                             bytes: try bytes(artifact, captureId: manifest.captureId))
        }
        multipart.finish()
        return APIRequest(method: "POST", path: "rooms/\(APIClient.segment(manifest.roomId))/keyframes",
                          body: multipart.data, identity: frame.id, contentType: multipart.contentType)
    }
    func finalizationRequest(_ id: String) throws -> APIRequest {
        let file = folder(id).appendingPathComponent("finalize-request.json")
        if FileManager.default.fileExists(atPath: file.path) {
            return try Wire.decoder().decode(APIRequest.self, from: Data(contentsOf: file))
        }
        let manifest = try load(id)
        guard let room = manifest.roomExport, manifest.state == "completed" else { throw ClientError.storage("The scan has no completed room export.") }
        // The export and thumbnail are included with finalization; their hashes remain in the manifest.
        let body = FinalizeRequest(operationId: manifest.finalizeId, manifest: manifest,
                        capturedRoom: try bytes(room, captureId: id),
                        thumbnail: try manifest.thumbnail.map { try bytes($0, captureId: id) })
        let request = try APIRequest.json(path: "rooms/\(APIClient.segment(manifest.roomId))/finalize", identity: manifest.finalizeId, body: body)
        try Wire.encoder().encode(request).write(to: file, options: .atomic)
        return request
    }
    func finalized(_ id: String, receipts: [ArtifactAcknowledgment], transform: [Float]) throws {
        try acknowledge(id, receipts: receipts)
        var manifest = try load(id)
        manifest.state = "finalized"; manifest.scanToRoomTransform = transform
        try save(manifest)
        if manifest.canEvictRawFiles {
            for artifact in manifest.allArtifacts { try FileManager.default.removeItem(at: folder(id).appendingPathComponent(artifact.filename)) }
            let request = folder(id).appendingPathComponent("finalize-request.json")
            if FileManager.default.fileExists(atPath: request.path) { try FileManager.default.removeItem(at: request) }
        }
    }
    func abandon(_ id: String) throws {
        var manifest = try load(id); manifest.state = "abandoned"; try save(manifest)
    }
    func removeCapture(_ id: String) throws {
        let url = folder(id)
        if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
    }
    func removeRoom(_ roomId: String) throws {
        for manifest in try manifests() where manifest.roomId == roomId { try removeCapture(manifest.captureId) }
    }
    func localPreviewURL(_ id: String) -> URL { folder(id).appendingPathComponent("preview.usdz") }

    func artifactURL(_ artifact: ArtifactRecord, captureId: String) throws -> URL {
        guard artifact.filename == URL(fileURLWithPath: artifact.filename).lastPathComponent,
              !artifact.filename.contains("..") else { throw ClientError.invalidResponse }
        let url = folder(captureId).appendingPathComponent(artifact.filename)
        // Incremental hashing avoids copying a large mesh into the upload's memory.
        let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
        var hash = SHA256(), size = 0
        while let chunk = try handle.read(upToCount: 1024 * 1024), !chunk.isEmpty { hash.update(data: chunk); size += chunk.count }
        guard size == artifact.byteLength, hash.finalize().map({ String(format: "%02x", $0) }).joined() == artifact.sha256 else {
            throw ClientError.storage("A scan artifact failed its integrity check.")
        }
        return url
    }

    func reconstructionDirectory(_ id: String) throws -> URL {
        let url = folder(id).appendingPathComponent("Reconstruction", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    func localRoom(_ id: String) throws -> LocalSavedRoom {
        try Wire.decoder().decode(LocalSavedRoom.self, from: Data(contentsOf: folder(id).appendingPathComponent("local-room.json")))
    }
    func localRooms() throws -> [LocalSavedRoom] {
        try manifests().filter { $0.state == "local_saved" }.map { try localRoom($0.captureId) }
            .sorted { $0.createdAt > $1.createdAt }
    }
    func saveLocalRoom(_ id: String, objectCount: Int) throws {
        var manifest = try load(id)
        guard manifest.state == "completed", manifest.roomExport != nil,
              FileManager.default.fileExists(atPath: localPreviewURL(id).path) else {
            throw ClientError.storage("The local room preview is not ready. Retry saving the scan.")
        }
        let room = LocalSavedRoom(id: id, name: "Room · \(manifest.createdAt.prefix(10)) · \(id.prefix(4))",
                                  createdAt: manifest.createdAt, objectCount: objectCount)
        try Wire.encoder().encode(room).write(to: folder(id).appendingPathComponent("local-room.json"), options: .atomic)
        // Local success never claims backend acknowledgment or permits raw-file eviction.
        manifest.state = "local_saved"
        try save(manifest)
    }
    func renameLocalRoom(_ id: String, name: String) throws {
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        var room = try localRoom(id); room.name = name
        try Wire.encoder().encode(room).write(to: folder(id).appendingPathComponent("local-room.json"), options: .atomic)
    }
    nonisolated static func creationRequest(_ manifest: CaptureManifest) throws -> APIRequest {
        let body = DraftRoomRequest(operationId: manifest.creationId, captureId: manifest.captureId,
                            name: "Room · \(manifest.createdAt.prefix(10)) · \(manifest.captureId.prefix(4))")
        return try .json(path: "rooms", identity: manifest.creationId, body: body)
    }
}
