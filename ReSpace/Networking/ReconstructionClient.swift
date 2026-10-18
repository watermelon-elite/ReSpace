import CryptoKit
import Foundation

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
        guard baseURL.scheme == "https" || (baseURL.scheme == "http" && (host == "localhost" || host.hasSuffix(".local") || privateIPv4)) else {
            throw ClientError.storage("Use HTTPS or a local Mac address for reconstruction.")
        }
        // Append raw components once. Pre-encoding with APIClient.segment here
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

    func submit(_ id: String, repository: CaptureRepository, retry: Bool = false) async throws -> ReconstructionJob {
        let manifest = try await repository.load(id)
        guard ["completed", "local_saved"].contains(manifest.state), manifest.sceneMesh != nil else {
            throw ClientError.storage("This room has no retained surface mesh. Scan it again before processing.")
        }
        let folder = try await folder(id, repository: repository)
        var retained = try receipt(folder: folder) ?? ReconstructionReceipt(origin: baseURL.absoluteString)
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
        let job = try await execute(request(path + [retry ? "retry" : "run"], method: "POST"), id: id)
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
        retained.job = job; try save(retained, folder: folder)
        return try await retainResult(job, retained: retained, folder: folder)
    }

    func cachedJob(_ id: String, repository: CaptureRepository) async throws -> ReconstructionJob? {
        try receipt(folder: await folder(id, repository: repository))?.job
    }

    func modelURL(_ id: String, repository: CaptureRepository) async throws -> URL? {
        let folder = try await folder(id, repository: repository)
        guard let record = try receipt(folder: folder), let result = record.job?.result,
              record.downloadedRevision == result.revision else { return nil }
        if result.sceneSchemaVersion != nil && record.job?.hasFinalWalkthrough != true { return nil }
        try result.validate()
        return folder.appendingPathComponent("result-\(result.revision)").appendingPathComponent(result.modelFilename)
    }

    func sceneURL(_ id: String, repository: CaptureRepository) async throws -> URL? {
        let folder=try await folder(id,repository:repository)
        guard let retained=try receipt(folder:folder), let job=retained.job, job.hasFinalWalkthrough,
              let result=job.result, retained.downloadedRevision==result.revision,
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
