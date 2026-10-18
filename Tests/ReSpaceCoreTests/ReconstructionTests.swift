import Foundation
import CryptoKit
import XCTest
@testable import ReSpaceCore

final class ReconstructionTests: XCTestCase {
    func testLiveSwiftClientUploadsProcessesAndDownloadsRetainedScan() async throws {
        let env = ProcessInfo.processInfo.environment
        guard let fixture = env["RESPACE_TEST_SWIFT_RECONSTRUCTION_FIXTURE"],
              let token = env["RESPACE_RECONSTRUCTION_TOKEN"] else {
            throw XCTSkip("Opt-in integration requires a local reconstruction service and synthetic fixture")
        }
        let source = URL(fileURLWithPath: fixture)
        let manifest = try Wire.decoder().decode(CaptureManifest.self, from: Data(contentsOf: source.appendingPathComponent("manifest.json")))
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }
        let repository = CaptureRepository(directory: root, maximumFrames: SamplingPolicy.reconstructionMaximumFrames)
        try await repository.save(manifest)
        let hash = SHA256.hash(data: Data(manifest.captureId.utf8)).map { String(format: "%02x", $0) }.joined()
        let inputFolder = root.appendingPathComponent(hash)
        for artifact in manifest.allArtifacts {
            try FileManager.default.copyItem(at: source.appendingPathComponent(artifact.filename),
                to: inputFolder.appendingPathComponent(artifact.filename))
        }
        let origin = env["RESPACE_TEST_ORIGIN"] ?? "http://127.0.0.1:8008"
        let client = ReconstructionClient(baseURL: URL(string: origin)!, token: token)
        var job = try await client.submit(manifest.captureId, repository: repository)
        let deadline = ContinuousClock.now + .seconds(1200)
        while job.isRunning && ContinuousClock.now < deadline {
            try await Task.sleep(for: .milliseconds(500))
            let refreshed = try await client.refresh(manifest.captureId, repository: repository)
            job = try XCTUnwrap(refreshed)
        }
        XCTAssertEqual(job.state, "succeeded", job.error ?? "No completed result")
        let model = try await client.modelURL(manifest.captureId, repository: repository)
        let url = try XCTUnwrap(model)
        let expectedModel = env["RESPACE_TEST_EXPECTED_MODEL"] ?? "astra.obj"
        XCTAssertEqual(url.lastPathComponent, expectedModel)
        if expectedModel == "astra.obj" { XCTAssertTrue(job.result?.isAIGenerated == true) }
        XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
        let original = try XCTUnwrap(manifest.sceneMesh)
        let retainedOriginal = try await repository.artifactURL(original, captureId: manifest.captureId)
        XCTAssertTrue(FileManager.default.fileExists(atPath: retainedOriginal.path))
    }

    func testSubmissionAndRefreshPreserveLiteralUUIDInRequestPath() async throws {
        let id = "6310E20F-1D0B-473E-A944-BBE7709E29A5"
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }
        let repository = CaptureRepository(directory: root)
        var manifest = try await repository.create()
        manifest.captureId = id; manifest.state = "local_saved"
        manifest.sceneMesh = ArtifactRecord(id: "mesh", type: "scene_mesh", filename: "mesh.mesh", byteLength: 1, sha256: String(repeating: "a", count: 64))
        try await repository.save(manifest)
        let expected = "/v1/reconstructions/\(id)"
        let recorder = ReconstructionRequestRecorder { request in
            let path = request.url!.path
            guard path == expected || path == expected + "/run" else {
                let status = request.httpMethod == "PUT" ? 422 : 404
                return (status, Data("{\"detail\":\"Capture identity mismatch\"}".utf8))
            }
            let state = request.httpMethod == "PUT" ? "uploading" : "queued"
            let response = ReconstructionJob(schemaVersion: 1, id: id, state: state, revision: 0,
                stage: state, missingArtifactIds: [])
            return (200, try Wire.encoder().encode(response))
        }
        let client = ReconstructionClient(baseURL: URL(string: "http://mac.local:8008")!, token: "test-reconstruction-token",
                                          session: recorder.session())
        do {
            let submitted = try await client.submit(id, repository: repository)
            XCTAssertEqual(submitted.state, "queued")
            let refreshed = try await client.refresh(id, repository: repository)
            XCTAssertEqual(refreshed?.id, id)
        } catch { XCTFail("A valid UUID submission must succeed: \(error)") }
        XCTAssertTrue(recorder.requests.allSatisfy { !$0.url!.absoluteString.contains("%25") })
    }

    func testRefreshOfUnsubmittedIntentDoesNotShowMissingJobAsSetupFailure() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }
        let repository = CaptureRepository(directory: root)
        var manifest = try await repository.create()
        manifest.state = "local_saved"
        manifest.sceneMesh = ArtifactRecord(id: "mesh", type: "scene_mesh", filename: "mesh.mesh", byteLength: 1, sha256: String(repeating: "a", count: 64))
        try await repository.save(manifest)
        let recorder = ReconstructionRequestRecorder { request in
            (request.httpMethod == "PUT" ? 422 : 404, Data("{\"detail\":\"Unknown reconstruction\"}".utf8))
        }
        let client = ReconstructionClient(baseURL: URL(string: "http://mac.local:8008")!, token: "test-reconstruction-token",
                                          session: recorder.session())
        do { _ = try await client.submit(manifest.captureId, repository: repository); XCTFail("Expected rejected submission") }
        catch { }
        do {
            let refreshed = try await client.refresh(manifest.captureId, repository: repository)
            XCTAssertNil(refreshed)
        } catch { XCTFail("A job not yet created must not appear as a configuration failure: \(error)") }
    }

    func testExpandedProfileKeepsSamplingBeyondFortyWithoutBursts() {
        var policy = SamplingPolicy.reconstruction
        for i in 0..<1900 {
            _ = policy.consider(SamplingObservation(time: Double(i) * 0.6, position: .zero,
                forward: SIMD3(0, 0, -1), trackingNormal: true), encoderAvailable: true)
        }
        XCTAssertEqual(policy.acceptedCount, SamplingPolicy.reconstructionMaximumFrames)
        XCTAssertEqual(SamplingPolicy.reconstructionMinimumSeconds, 60)
        var burst = SamplingPolicy.reconstruction
        XCTAssertTrue(burst.consider(SamplingObservation(time: 0, position: .zero, forward: SIMD3(0,0,-1), trackingNormal: true), encoderAvailable: true))
        XCTAssertFalse(burst.consider(SamplingObservation(time: 0.1, position: SIMD3(0.01,0,0), forward: SIMD3(0,0,-1), trackingNormal: true), encoderAvailable: true))
    }

    func testDerivedAssetsRejectTraversalAndUnsupportedCoordinates() throws {
        let asset = ReconstructionAsset(filename: "model.obj", byteLength: 12, sha256: String(repeating: "a", count: 64))
        var result = ReconstructionResult(revision: 1, status: "succeeded", modelFilename: "model.obj",
            assets: [asset, ReconstructionAsset(filename: "quality.json", byteLength: 1, sha256: asset.sha256)],
            needsReview: false, coordinateSystem: "arkit_scan_meters_y_up", qualityFilename: "quality.json")
        try result.validate()
        result.coordinateSystem = "normalized_unit_cube"
        XCTAssertThrowsError(try result.validate())
        XCTAssertThrowsError(try ReconstructionAsset(filename: "../outside.obj", byteLength: 12, sha256: asset.sha256).validate())
        XCTAssertThrowsError(try ReconstructionAsset(filename: "oversized.obj", byteLength: 129*1024*1024, sha256: asset.sha256).validate())
    }

    func testWorkerResponseContractRoundTripAndCaptureIdentity() throws {
        let data = Data(#"{"schema_version":1,"id":"capture","state":"running","revision":1,"stage":"depth_fusion","error":null,"result":null,"missing_artifact_ids":[]}"#.utf8)
        let job = try Wire.decoder().decode(ReconstructionJob.self, from: data)
        try job.validate(captureId: "capture")
        XCTAssertTrue(job.isRunning)
        XCTAssertFalse(job.canRetry)
        XCTAssertThrowsError(try job.validate(captureId: "another-capture"))
        let receipt = ReconstructionReceipt(origin: "http://mac.local:8008", job: job)
        let decoded = try Wire.decoder().decode(ReconstructionReceipt.self, from: Wire.encoder().encode(receipt))
        XCTAssertEqual(decoded.job?.id, "capture")
        XCTAssertNil(decoded.downloadedRevision)
    }

    func testAstraResultMetadataAndLegacyUpgrade() throws {
        let checksum = String(repeating: "a", count: 64)
        let data = Data("""
        {"schema_version":1,"id":"capture","state":"succeeded","revision":2,"stage":"finished",
         "result":{"revision":2,"status":"succeeded","model_filename":"astra.obj",
           "assets":[{"filename":"astra.obj","byte_length":12,"sha256":"\(checksum)"},
                     {"filename":"quality.json","byte_length":12,"sha256":"\(checksum)"}],
           "needs_review":true,"coordinate_system":"arkit_scan_meters_y_up","quality_filename":"quality.json",
           "generation_model":"gpt-6-astra","generated_triangle_count":12},"missing_artifact_ids":[]}
        """.utf8)
        var job = try Wire.decoder().decode(ReconstructionJob.self, from: data)
        try job.validate(captureId: "capture")
        XCTAssertTrue(job.result?.isAIGenerated == true)
        job.result?.generationModel = "gpt-6-sol"
        XCTAssertTrue(job.result?.isAIGenerated == true)
        job.stage = "astra_batch:1-4/12"
        XCTAssertEqual(job.stageDescription, "Building objects · 1-4/12")
        XCTAssertEqual(job.result?.generatedTriangleCount, 12)
        XCTAssertFalse(job.canRetry)
        job.result?.generationModel = nil
        job.result?.generatedTriangleCount = nil
        XCTAssertTrue(job.canRetry) // Earlier completed reconstructions can generate an AI model.
        job.stage = "astra_generating_scene"
        XCTAssertEqual(job.stageDescription, "AI is generating your room…")
        job.result?.generatedTriangleCount = -1
        XCTAssertThrowsError(try job.validate(captureId: "capture"))
    }

    func testLocalRepositoryRetainsMoreThanFortyFrames() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }
        let repository = CaptureRepository(directory: root, maximumFrames: SamplingPolicy.reconstructionMaximumFrames)
        let manifest = try await repository.create()
        try await repository.assignRoom(manifest.captureId, roomId: manifest.captureId)
        for index in 0..<60 {
            let meta = FrameMetadata(id: "frame-\(index)", captureId: manifest.captureId, timestamp: Double(index),
                width: 2560, height: 1920, intrinsics: [2000,2000,1280,960], cameraToScanTransform: [])
            try await repository.append(CaptureFrame(id: meta.id, metadata: meta, artifacts: []), captureId: manifest.captureId)
        }
        let reopened = try await repository.load(manifest.captureId)
        XCTAssertEqual(reopened.frames.count, 60)
        let hasCapacity = try await repository.hasReconstructionFrameCapacity(manifest.captureId)
        XCTAssertTrue(hasCapacity)
    }
}

private final class ReconstructionRequestRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var recorded: [URLRequest] = []
    private let respond: (URLRequest) throws -> (Int, Data)
    init(respond: @escaping (URLRequest) throws -> (Int, Data)) { self.respond = respond }
    var requests: [URLRequest] { lock.lock(); defer { lock.unlock() }; return recorded }
    func response(_ request: URLRequest) throws -> (Int, Data) {
        lock.lock(); recorded.append(request); lock.unlock()
        return try respond(request)
    }
    func session() -> URLSession {
        ReconstructionTestURLProtocol.recorder = self
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ReconstructionTestURLProtocol.self]
        return URLSession(configuration: configuration)
    }
}

private final class ReconstructionTestURLProtocol: URLProtocol, @unchecked Sendable {
    static var recorder: ReconstructionRequestRecorder?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, data) = try Self.recorder!.response(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}
