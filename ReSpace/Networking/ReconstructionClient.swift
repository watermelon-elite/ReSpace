import CryptoKit
import Foundation

struct RoomRenditionStatus: Decodable {
    let state: String
    let error: String?
    let sha256: String?
    let byteLength: Int?
}

/// Reconstruction is independent of connected room/design mutations. Files and job
/// identity survive view/app closure; the Mac owns the long-running computation.
actor ReconstructionClient {
    private let baseURL: URL
    private let token: String
    private let session: URLSession

    init(baseURL: URL, token: String, session: URLSession? = nil) {
        self.baseURL = baseURL; self.token = token
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 120
        configuration.timeoutIntervalForResource = 1800
        self.session = session ?? URLSession(configuration: configuration)
    }

    private func request(_ components: [String], method: String = "GET") throws -> URLRequest {
        guard let host = baseURL.host, !host.isEmpty, baseURL.user == nil, baseURL.password == nil,
              baseURL.query == nil, baseURL.fragment == nil, token.count >= 16 else {
            throw ClientError.storage("Set the reconstruction service address and token in Local.xcconfig.")
        }
        // Plain HTTP is restricted to local development hosts. Remote hosting requires HTTPS.
        let privateIPv4: Bool = {
            let parts = host.split(separator: ".").compactMap { Int($0) }
            guard parts.count == 4, parts.allSatisfy({ (0...255).contains($0) }) else { return false }
            return parts[0] == 10 || parts[0] == 127 || (parts[0] == 192 && parts[1] == 168) || (parts[0] == 172 && (16...31).contains(parts[1]))
        }()
        #if DEBUG
        let allowsLocalHTTP = host == "localhost" || host.hasSuffix(".local") || privateIPv4
        #else
        let allowsLocalHTTP = false
        #endif
        guard baseURL.scheme == "https" || (baseURL.scheme == "http" && allowsLocalHTTP) else {
            throw ClientError.storage("Use HTTPS for reconstruction. Debug builds also allow a local Mac address.")
        }
        // Append raw components once. Pre-encoding with ScanAPIClient.segment here
        // encodes '%' again, so UUID hyphens become '%252D' on the wire.
        let url = components.reduce(baseURL) { $0.appendingPathComponent($1) }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        return request
    }

    private func checked(_ response: URLResponse, body: Data? = nil) throws {
        guard let http = response as? HTTPURLResponse else { throw ClientError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            let envelope = body.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            let detail = (envelope?["detail"] as? String).map { String($0.prefix(500)) }
            throw ReconstructionServiceError.http(http.statusCode, detail)
        }
    }

    private func folder(_ id: String, repository: CaptureRepository) async throws -> URL {
        let root = try await repository.reconstructionDirectory(id)
        let hash = SHA256.hash(data: Data(baseURL.absoluteString.utf8)).map { String(format: "%02x", $0) }.joined()
        let folder = root.appendingPathComponent(hash, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        return folder
    }

    private func save(_ receipt: ReconstructionReceipt, folder: URL) throws {
        try Wire.encoder().encode(receipt).write(to: folder.appendingPathComponent("job.json"), options: .atomic)
    }

    private func receipt(folder: URL) throws -> ReconstructionReceipt? {
        let url = folder.appendingPathComponent("job.json")
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let receipt = try Wire.decoder().decode(ReconstructionReceipt.self, from: Data(contentsOf: url))
        guard receipt.origin == baseURL.absoluteString else { throw ClientError.invalidResponse }
        return receipt
    }

    private func execute(_ request: URLRequest, id: String) async throws -> ReconstructionJob {
        let (data, response) = try await session.data(for: request)
        try checked(response, body: data)
        let job = try Wire.decoder().decode(ReconstructionJob.self, from: data)
        try job.validate(captureId: id)
        return job
    }

    func submit(_ id: String, repository: CaptureRepository, retry: Bool = false, fromScratch: Bool = false) async throws -> ReconstructionJob {
        let manifest = try await repository.load(id)
        guard ["completed", "local_saved"].contains(manifest.state), manifest.sceneMesh != nil else {
            throw ClientError.storage("This room has no retained surface mesh. Scan it again before processing.")
        }
        let folder = try await folder(id, repository: repository)
        var retained = try receipt(folder: folder) ?? ReconstructionReceipt(origin: baseURL.absoluteString)
        if fromScratch && retained.pendingRestartId == nil {
            retained.pendingRestartId = UUID().uuidString
        }
        // Record intent before the first network write; known capture identity recovers unknown outcomes.
        try save(retained, folder: folder)
        let path = ["v1", "reconstructions", id]
        var upload = try request(path, method: "PUT")
        upload.httpBody = try Wire.encoder().encode(manifest)
        upload.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let created = try await execute(upload, id: id)
        retained.job = created; try save(retained, folder: folder)
        let missing = Set(created.missingArtifactIds)
        guard missing.isSubset(of: Set(manifest.allArtifacts.map(\.id))) else { throw ClientError.invalidResponse }
        for artifact in manifest.allArtifacts where missing.contains(artifact.id) {
            try Task.checkCancellation()
            let url = try await repository.artifactURL(artifact, captureId: id)
            var upload = try request(path + ["artifacts", artifact.id], method: "PUT")
            upload.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
            let (data, response) = try await session.upload(for: upload, fromFile: url)
            try checked(response, body: data)
        }
        var start = try request(path + [fromScratch ? "restart" : (retry ? "retry" : "run")], method: "POST")
        if fromScratch {
            struct RestartBody: Encodable { let requestId: String }
            start.httpBody = try Wire.encoder().encode(RestartBody(requestId: retained.pendingRestartId!))
            start.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let job = try await execute(start, id: id)
        if fromScratch { retained.pendingRestartId = nil }
        retained.job = job; try save(retained, folder: folder)
        return try await retainResult(job, retained: retained, folder: folder)
    }

    func refresh(_ id: String, repository: CaptureRepository) async throws -> ReconstructionJob? {
        let folder = try await folder(id, repository: repository)
        guard var retained = try receipt(folder: folder) else { return nil }
        let job: ReconstructionJob
        do {
            job = try await execute(request(["v1", "reconstructions", id]), id: id)
        } catch ReconstructionServiceError.http(404, _) {
            // A failed/unknown-outcome first PUT leaves a local intent. It is
            // legitimate for that job not to exist yet; Improve model retries it.
            return nil
        }
        if let pending=retained.pendingRestartId, job.generationId?.lowercased()==pending.lowercased() {
            retained.pendingRestartId=nil
        }
        retained.job = job; try save(retained, folder: folder)
        return try await retainResult(job, retained: retained, folder: folder)
    }

    func cachedJob(_ id: String, repository: CaptureRepository) async throws -> ReconstructionJob? {
        try receipt(folder: await folder(id, repository: repository))?.job
    }

    nonisolated static func renditionKey(_ scene: WalkthroughBundle, requestId: UUID? = nil) throws -> String {
        var data = try Wire.encoder().encode(scene)
        data.append(Data(RoomRenditionCamera.viewID.utf8))
        // A refresh gets its own persisted identity. Reopening or retrying that
        // same refresh must keep the identity and recover its existing receipt.
        if let requestId { data.append(Data(requestId.uuidString.lowercased().utf8)) }
        return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private func renditionPath(_ scene: WalkthroughBundle, requestId: UUID? = nil) throws -> [String] {
        ["v1", "reconstructions", scene.captureId, "results", String(scene.reconstructionRevision), "renditions", try Self.renditionKey(scene,requestId:requestId)]
    }

    private func transientRenditionError(_ error: Error) -> Bool {
        if let error=error as? URLError {
            return [.timedOut,.networkConnectionLost,.notConnectedToInternet,.cannotConnectToHost,.cannotFindHost,.dnsLookupFailed].contains(error.code)
        }
        if case let ReconstructionServiceError.http(code,_)=error { return [408,429,500,502,503,504].contains(code) }
        return false
    }

    private func renditionRead(_ request: URLRequest) async throws -> Data {
        for attempt in 0..<3 {
            do {
                let (data,response)=try await session.data(for:request)
                try checked(response,body:data)
                return data
            } catch {
                guard attempt<2,transientRenditionError(error) else { throw error }
                try await Task.sleep(for:.seconds(attempt+1))
            }
        }
        throw ClientError.invalidResponse
    }

    private func renditionStatus(_ request: URLRequest) async throws -> RoomRenditionStatus {
        let data: Data
        if request.httpMethod == "GET" { data=try await renditionRead(request) }
        else {
            let (body,response)=try await session.data(for:request)
            try checked(response,body:body);data=body
        }
        let result=try Wire.decoder().decode(RoomRenditionStatus.self,from:data)
        guard ["generating","succeeded","failed"].contains(result.state) else { throw ClientError.invalidResponse }
        return result
    }

    /// Reads are safe to retry. This never submits an image-generation request.
    func existingRendition(scene: WalkthroughBundle, requestId: UUID? = nil) async throws -> RoomRenditionStatus? {
        var read=try request(renditionPath(scene,requestId:requestId));read.timeoutInterval=30
        do { return try await renditionStatus(read) }
        catch ReconstructionServiceError.http(404,_) { return nil }
    }

    func rendition(scene: WalkthroughBundle, image: Data, requestId: UUID? = nil) async throws -> Data {
        let path = try renditionPath(scene,requestId:requestId)
        let initial: RoomRenditionStatus
        if let saved=try await existingRendition(scene:scene,requestId:requestId) { initial=saved }
        else {
            struct Body: Encodable { let imageBase64: String; let scene: WalkthroughBundle }
            var create = try request(path, method: "POST")
            create.setValue("application/json", forHTTPHeaderField: "Content-Type")
            create.httpBody = try Wire.encoder().encode(Body(imageBase64: image.base64EncodedString(), scene: scene))
            do { initial=try await renditionStatus(create) }
            catch {
                guard transientRenditionError(error) else { throw error }
                // A lost acknowledgement can hide a successful submission.
                // Recover its receipt with GET; never repeat an ambiguous POST.
                var recovered: RoomRenditionStatus?
                for attempt in 0..<3 {
                    if let saved=try await existingRendition(scene:scene,requestId:requestId) { recovered=saved;break }
                    try await Task.sleep(for:.seconds(attempt+1))
                }
                guard let recovered else {
                    throw ClientError.storage("The connection was interrupted. Reopen this image to check whether generation started.")
                }
                initial=recovered
            }
        }
        var result = initial
        let deadline = ContinuousClock.now + .seconds(3600)
        while result.state == "generating" {
            guard ContinuousClock.now < deadline else {
                throw ClientError.storage("The image is still processing. Reopen it to check again.")
            }
            try await Task.sleep(for: .seconds(2))
            guard let saved=try await existingRendition(scene:scene,requestId:requestId) else { throw ClientError.invalidResponse }
            result=saved
        }
        guard result.state == "succeeded" else {
            throw ClientError.storage(result.error ?? "The room image could not be generated.")
        }
        guard let size = result.byteLength, (1...16*1024*1024).contains(size),
              let checksum = result.sha256, checksum.count == 64 else { throw ClientError.invalidResponse }
        let data = try await renditionRead(request(path + ["image"]))
        guard data.count == size,
              SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined() == checksum else {
            throw ClientError.storage("The room image failed its integrity check.")
        }
        return data
    }

    func modelURL(_ id: String, repository: CaptureRepository) async throws -> URL? {
        let folder = try await folder(id, repository: repository)
        guard let record = try receipt(folder: folder), let result = record.job?.result,
              record.downloadedRevision == result.revision else { return nil }
        if result.sceneSchemaVersion != nil && record.job?.hasFinalWalkthrough != true { return nil }
        try result.validate()
        return folder.appendingPathComponent("result-\(result.revision)").appendingPathComponent(result.modelFilename)
    }

    func sceneURL(_ id: String, repository: CaptureRepository, allowPrevious: Bool = false) async throws -> URL? {
        let folder=try await folder(id,repository:repository)
        guard let retained=try receipt(folder:folder), let job=retained.job,
              job.hasFinalWalkthrough || allowPrevious,
              let result=job.result, result.isWalkthrough, retained.downloadedRevision==result.revision,
              let name=result.sceneFilename else { return nil }
        let directory=folder.appendingPathComponent("result-\(result.revision)")
        // Recheck cached bytes as well as new downloads before native import.
        for asset in result.assets {
            guard try verify(directory.appendingPathComponent(asset.filename),asset:asset) else { throw ClientError.invalidResponse }
        }
        let scene=try Wire.decoder().decode(WalkthroughBundle.self,from:Data(contentsOf:directory.appendingPathComponent(name)))
        try scene.validate(captureId:id,revision:result.revision,assets:Set(result.assets.map(\.filename)))
        try scene.validateFiles(in:directory,assets:Set(result.assets.map(\.filename)))
        return directory.appendingPathComponent(name)
    }

    func usdzURL(_ id: String, repository: CaptureRepository, allowPrevious: Bool = false) async throws -> URL? {
        let folder = try await folder(id, repository: repository)
        guard let record = try receipt(folder: folder), let job = record.job,
              let result = job.result, record.downloadedRevision == result.revision,
              let name = result.usdzFilename else { return nil }
        if result.sceneSchemaVersion != nil && !job.hasFinalWalkthrough && !allowPrevious { return nil }
        try result.validate()
        guard let asset = result.assets.first(where: { $0.filename == name }) else { throw ClientError.invalidResponse }
        let url = folder.appendingPathComponent("result-\(result.revision)").appendingPathComponent(name)
        guard try verify(url, asset: asset) else { throw ClientError.invalidResponse }
        return url
    }

    private func retainResult(_ job: ReconstructionJob, retained: ReconstructionReceipt, folder: URL) async throws -> ReconstructionJob {
        guard let result = job.result, retained.downloadedRevision != result.revision else { return job }
        if result.sceneSchemaVersion != nil && !job.hasFinalWalkthrough { return job }
        try result.validate()
        let destination = folder.appendingPathComponent("result-\(result.revision)", isDirectory: true)
        try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
        for asset in result.assets {
            let url = destination.appendingPathComponent(asset.filename)
            if (try? verify(url, asset: asset)) == true { continue }
            let path = ["v1", "reconstructions", job.id, "results", String(result.revision), "assets", asset.filename]
            let (temporary, response) = try await session.download(for: request(path))
            defer { try? FileManager.default.removeItem(at: temporary) }
            try checked(response)
            guard try verify(temporary, asset: asset) else { throw ClientError.storage("A processed model failed its integrity check.") }
            if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
            try FileManager.default.moveItem(at: temporary, to: url)
        }
        var retained = retained; retained.downloadedRevision = result.revision
        try save(retained, folder: folder)
        return job
    }

    private func verify(_ url: URL, asset: ReconstructionAsset) throws -> Bool {
        guard try url.resourceValues(forKeys: [.fileSizeKey]).fileSize == asset.byteLength else { return false }
        let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
        var hash = SHA256()
        while let chunk = try handle.read(upToCount: 1024 * 1024), !chunk.isEmpty { hash.update(data: chunk) }
        return hash.finalize().map { String(format: "%02x", $0) }.joined() == asset.sha256
    }
}
