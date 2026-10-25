import Foundation
import CryptoKit

/// Retained reconstruction evidence; backend links never permit raw-file eviction.
struct LocalSavedRoom: Codable, Identifiable, Sendable {
    var id: String
    var name: String
    var createdAt: String
    var objectCount: Int
    var backendRoomId: String?
    var backendCaptureId: String?
    var backendCreationName: String?
}

actor CaptureRepository {
    private let directory: URL
    private let maximumFrames: Int
    private let freshCaptureOnly: Bool
    init(directory: URL, maximumFrames: Int = 40, freshCaptureOnly: Bool = false) {
        self.directory = directory; self.maximumFrames = maximumFrames; self.freshCaptureOnly = freshCaptureOnly
    }

    private func folder(_ id: String) -> URL {
        let safe = SHA256.hash(data: Data(id.utf8)).map { String(format: "%02x", $0) }.joined()
        return directory.appendingPathComponent(safe, isDirectory: true)
    }
    func create() throws -> CaptureManifest {
        if freshCaptureOnly { try clearLegacyCapturesOnce() }
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
        return try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.isDirectoryKey]).filter {
            try $0.resourceValues(forKeys: [.isDirectoryKey]).isDirectory == true
        }.map { url in
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
        guard manifest.sourceBundleFormat == nil, manifest.state == "acquiring", manifest.frames.count < maximumFrames else { throw ClientError.storage("This scan is no longer accepting legacy frames.") }
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
    func complete(_ id: String, roomData: Data?, thumbnailData: Data?, sceneMeshData: Data? = nil, sourceIntegrityData: Data? = nil, sourceLayoutError: String? = nil) throws {
        var manifest = try load(id)
        guard manifest.state == "acquiring" else { throw ClientError.storage("This scan was interrupted. Start again.") }
        if manifest.sourceBundleFormat == "house-capture/5", sourceIntegrityData == nil {
            throw ClientError.storage("The native source capture must finish its integrity record before saving.")
        }
        if let sceneMeshData { _ = try ScanMeshSnapshot.decode(sceneMeshData, captureId: id) }
        if let roomData { manifest.roomExport = try writeArtifact(captureId: id, type: "roomplan", bytes: roomData, extension: "json") }
        else if manifest.sourceBundleFormat == nil { throw ClientError.storage("The completed room export is missing.") }
        let thumbnailBytes = try thumbnailData ?? manifest.frames.last?.artifacts.first(where: { $0.type == "jpeg" }).map { try bytes($0, captureId: id) }
        if let thumbnailBytes { manifest.thumbnail = try writeArtifact(captureId: id, type: "thumbnail", bytes: thumbnailBytes, extension: "jpg") }
        if let sceneMeshData {
            manifest.sceneMesh = try writeArtifact(captureId: id, type: "scene_mesh", bytes: sceneMeshData, extension: "mesh")
        }
        if let sourceIntegrityData {
            manifest.sourceBundleIntegrity = try writeArtifact(captureId: id, type: "source_bundle_integrity", bytes: sourceIntegrityData, extension: "json")
            manifest.sourceLayoutError = sourceLayoutError
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
        return APIRequest(method: "POST", path: "rooms/\(ScanAPIClient.segment(manifest.roomId))/keyframes",
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
        let request = try APIRequest.json(path: "rooms/\(ScanAPIClient.segment(manifest.roomId))/finalize", identity: manifest.finalizeId, body: body)
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
        if freshCaptureOnly { try clearLegacyCapturesOnce() }
        return try manifests().filter { $0.state == "local_saved" }.map { try localRoom($0.captureId) }
            .sorted { $0.createdAt > $1.createdAt }
    }

    /// User-requested fresh start, applied once to this local capture store.
    /// Room planning/shopping stores and native bundles are outside this cleanup.
    func clearLegacyCapturesOnce() throws {
        let marker = directory.appendingPathComponent(".source-capture-fresh-start-v1")
        guard !FileManager.default.fileExists(atPath: marker.path) else { return }
        for capture in try manifests() where capture.sourceBundleFormat != "house-capture/5" {
            try removeCapture(capture.captureId)
        }
        try Data("Legacy local scans cleared at the user's request.\n".utf8).write(to: marker, options: .atomic)
    }

    func createSourceBundle(_ id: String) throws -> URL {
        var manifest = try load(id)
        guard manifest.state == "acquiring" else { throw ClientError.storage("Start a new scan before recording.") }
        manifest.sourceBundleFormat = "house-capture/5"
        try save(manifest)
        let url = folder(id).appendingPathComponent("house-capture", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }
    func sourceBundleURL(_ id: String) throws -> URL? {
        let manifest = try load(id)
        guard manifest.sourceBundleFormat == "house-capture/5" else { return nil }
        return folder(id).appendingPathComponent("house-capture", isDirectory: true)
    }
    func sourceBundleArchive(_ id: String) throws -> URL {
        guard let source = try sourceBundleURL(id), ["completed","local_saved"].contains(try load(id).state) else {
            throw ClientError.storage("Finish saving this scan before sharing it.")
        }
        let sourceManifest = try JSONSerialization.jsonObject(with: Data(contentsOf: source.appendingPathComponent("manifest.json"))) as? [String: Any]
        guard sourceManifest?["format"] as? String == "house-capture/5", sourceManifest?["state"] as? String == "completed" else {
            throw ClientError.storage("The source capture is incomplete. Its raw data is retained.")
        }
        guard let integrityArtifact = try load(id).sourceBundleIntegrity else { throw ClientError.storage("The source integrity record is missing.") }
        let seal = try JSONDecoder().decode(SourceBundleIntegrity.self, from: bytes(integrityArtifact, captureId: id))
        try seal.verify(at: source)
        let destination = FileManager.default.temporaryDirectory.appendingPathComponent("ReSpace-scan-\(UUID().uuidString).zip")
        var coordinationError: NSError?
        var copyError: Error?
        NSFileCoordinator().coordinate(readingItemAt: source, options: .forUploading, error: &coordinationError) { archive in
            do { try FileManager.default.copyItem(at: archive, to: destination) }
            catch { copyError = error }
        }
        if let coordinationError { throw coordinationError }
        if let copyError { throw copyError }
        return destination
    }

    func nativeReconstructionUpload(_ id: String) throws -> NativeReconstructionUpload {
        let manifest = try load(id)
        guard ["completed","local_saved"].contains(manifest.state), manifest.sourceLayoutError == nil,
              let source = try sourceBundleURL(id), let artifact = manifest.sourceBundleIntegrity else {
            throw ClientError.storage("This capture needs its measured layout before creating a walkthrough. The original scan is retained.")
        }
        let integrity = try JSONDecoder().decode(SourceBundleIntegrity.self, from: bytes(artifact, captureId: id))
        try integrity.verify(at: source)
        var entries = integrity.files
        let sealURL = source.appendingPathComponent("integrity.json")
        let seal = try Data(contentsOf: sealURL)
        entries.append(.init(path:"integrity.json",byteLength:seal.count,sha256:SHA256.hash(data:seal).map { String(format:"%02x",$0) }.joined()))
        let files = entries.map { entry in
            let key = SHA256.hash(data:Data(entry.path.utf8)).map { String(format:"%02x",$0) }.joined()
            return NativeReconstructionFile(id:key,filename:key,relativePath:entry.path,byteLength:entry.byteLength,sha256:entry.sha256)
        }
        guard files.count <= 30000, files.allSatisfy({ $0.byteLength > 0 && $0.byteLength <= 512*1024*1024 }),
              files.reduce(0, { $0+$1.byteLength }) <= 8*1024*1024*1024 else {
            throw ClientError.storage("This scan exceeds the native reconstruction upload limits.")
        }
        return NativeReconstructionUpload(captureId:id,state:manifest.state,files:files)
    }
    func nativeReconstructionFileURL(_ file: NativeReconstructionFile, captureId: String) throws -> URL {
        guard let root = try sourceBundleURL(captureId) else { throw ClientError.invalidResponse }
        let path = root.appendingPathComponent(file.relativePath).standardizedFileURL
        guard path.path.hasPrefix(root.standardizedFileURL.path+"/"),
              !file.relativePath.split(separator:"/").contains("..") else { throw ClientError.invalidResponse }
        return path
    }
    func saveLocalRoom(_ id: String, objectCount: Int) throws {
        var manifest = try load(id)
        guard manifest.state == "completed", manifest.roomExport != nil || manifest.sourceBundleIntegrity != nil,
              manifest.sourceBundleFormat == "house-capture/5" || FileManager.default.fileExists(atPath: localPreviewURL(id).path) else {
            throw ClientError.storage("The local room preview is not ready. Retry saving the scan.")
        }
        let room = LocalSavedRoom(id: id, name: "Room · \(manifest.createdAt.prefix(10)) · \(id.prefix(4))",
                                  createdAt: manifest.createdAt, objectCount: objectCount)
        try Wire.encoder().encode(room).write(to: folder(id).appendingPathComponent("local-room.json"), options: .atomic)
        // Local success never claims backend acknowledgment or permits raw-file eviction.
        manifest.state = "local_saved"
        try save(manifest)
    }
    func backendCreationName(_ id: String) throws -> String {
        var room = try localRoom(id)
        if let name = room.backendCreationName { return name }
        room.backendCreationName = room.name
        try Wire.encoder().encode(room).write(to: folder(id).appendingPathComponent("local-room.json"), options: .atomic)
        return room.name
    }

    func linkBackend(_ id: String, roomId: String, captureId: String) throws {
        var room = try localRoom(id)
        room.backendRoomId = roomId; room.backendCaptureId = captureId
        try Wire.encoder().encode(room).write(to: folder(id).appendingPathComponent("local-room.json"), options: .atomic)
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
