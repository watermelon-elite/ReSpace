import Foundation
import XCTest
@testable import ReSpaceCore

final class ClientCoreTests: XCTestCase {
    private func fixture(_ name: String) throws -> Data {
        try Data(contentsOf: XCTUnwrap(Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures")))
    }
    private func temporaryDirectory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        addTeardownBlock { try FileManager.default.removeItem(at: url) }
        return url
    }

    func testContractsDecodeAndRoundTrip() throws {
        let room = try Wire.decoder().decode(RoomRecord.self, from: fixture("room"))
        try XCTUnwrap(room.snapshot).validateGeometry()
        XCTAssertEqual(room.planning.instructions["sofa_1"], .keep)
        let design = try Wire.decoder().decode(DesignVersion.self, from: fixture("design"))
        try design.validateGeometry()
        XCTAssertEqual(design.parentId, "design_1")
        XCTAssertEqual(design, try Wire.decoder().decode(DesignVersion.self, from: Wire.encoder().encode(design)))
        for name in ["queued", "running", "clarification", "succeeded", "rejected", "failed", "cancelled"] {
            let operation = try Wire.decoder().decode(RoomOperation.self, from: fixture(name))
            XCTAssertEqual(operation.id, "op_1")
        }
    }

    func testUSDInputNeverRoundsOrPrefills() {
        XCTAssertNil(IntentDraft().inputs)
        for invalid in ["", " ", "0", "0.00", "-1", ".99", "1.234", "1e3", "1,000", "NaN", "1.", "1\n"] {
            XCTAssertNil(IntentDraft.parseBudget(invalid), invalid)
        }
        XCTAssertEqual(IntentDraft.parseBudget("0012.3"), "12.30")
        XCTAssertEqual(IntentDraft.parseBudget("0.01"), "0.01")
        XCTAssertEqual(IntentDraft.parseBudget("300"), "300.00")
    }

    func testStyleExclusivityAndSelectedIntent() {
        var draft = IntentDraft()
        draft.toggle(.cozy); draft.toggle(.japandi)
        XCTAssertEqual(draft.styles, [.cozy, .japandi])
        draft.toggle(.cozy); draft.toggle(.japandi)
        XCTAssertEqual(draft.styles, [.match])
        draft.toggle(.industrial); draft.toggle(.match)
        XCTAssertEqual(draft.styles, [.match])
        draft.text = "Replace everything"
        draft.budgetText = "1000"
        XCTAssertEqual(draft.inputs?.intent, .add) // semantic conflicts are a backend handoff
    }

    func testFirstGenerationExplicitlyRequiresNoExistingActiveVersion() throws {
        let request = GenerationRequest(operationId: "op_1", roomSnapshotId: "snapshot_1", planningRevision: 4,
                                        expectedActiveRevision: 0, intent: .add, styles: [.match], budget: "300.00", text: "")
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: Wire.encoder().encode(request)) as? [String: Any])
        XCTAssertTrue(json["expected_active_design_id"] is NSNull)
        XCTAssertEqual(json["budget"] as? String, "300.00")
    }

    func testUploadReceiptIsSeparateFromOptionalDetectorSuccess() throws {
        let artifact = ArtifactRecord(id: "jpeg_1", type: "jpeg", filename: "photo.jpg", byteLength: 100, sha256: "hash")
        let metadata = FrameMetadata(id: "frame_1", captureId: "capture_1", timestamp: 1,
                                     width: 1280, height: 960, intrinsics: [1000, 1000, 640, 480], cameraToScanTransform: [])
        let frame = CaptureFrame(id: "frame_1", metadata: metadata, artifacts: [artifact])
        let failure = FrameUploadResult(schemaVersion: 1,
                                        acknowledgments: [ArtifactAcknowledgment(artifactId: "jpeg_1", byteLength: 100, sha256: "hash", durable: true)], perceptionState: "failed")
        XCTAssertNoThrow(try failure.validateStorage(for: frame))
        let undurable = FrameUploadResult(schemaVersion: 1, acknowledgments: [], perceptionState: "completed")
        XCTAssertThrowsError(try undurable.validateStorage(for: frame))
    }

    func testStructuredFailureDetailsPreserveReadableReason() throws {
        let data = Data(#"{"code":"collision","message":"The table overlaps your sofa.","retryable":false,"details":{"items":["table","sofa"],"clearance":0.2,"geometry":{"valid":false}}}"#.utf8)
        let failure = try Wire.decoder().decode(APIErrorEnvelope.self, from: data)
        XCTAssertEqual(failure.message, "The table overlaps your sofa.")
        XCTAssertEqual(failure.details?["items"], .array([.string("table"), .string("sofa")]))
    }

    func testSamplingRejectsMotionTrackingAndPressureAndCapsAtForty() {
        var policy = SamplingPolicy()
        func observation(_ time: Double, x: Float = 0, normal: Bool = true) -> SamplingObservation {
            SamplingObservation(time: time, position: [x, 0, 0], forward: [0, 0, -1], trackingNormal: normal)
        }
        XCTAssertTrue(policy.consider(observation(0), encoderAvailable: true))
        XCTAssertFalse(policy.consider(observation(0.2, x: 1), encoderAvailable: true))
        XCTAssertFalse(policy.consider(observation(2, normal: false), encoderAvailable: true))
        XCTAssertFalse(policy.consider(observation(4), encoderAvailable: false))
        XCTAssertEqual(policy.acceptedCount, 1)
        for index in 1...45 { _ = policy.consider(observation(Double(index) * 10), encoderAvailable: true) }
        XCTAssertEqual(policy.acceptedCount, 40)
    }

    func testRenderCoordinatesAndRemovedItemVisibility() throws {
        let room = try Wire.decoder().decode(RoomRecord.self, from: fixture("room"))
        let snapshot = try XCTUnwrap(room.snapshot)
        let sofa = try XCTUnwrap(snapshot.reviewItems(planning: room.planning).first)
        XCTAssertEqual(sofa.position, [2, 0, 2])
        XCTAssertEqual(sofa.size, [2.1, 0.9, 0.8])
        var item = sofa
        item.status = .removed
        XCTAssertTrue(item.isGhost)
        XCTAssertTrue(item.isVisible)
        item.origin = .new
        XCTAssertFalse(item.isGhost)
        XCTAssertFalse(item.isVisible)
    }

    func testMalformedGeometryIsRejectedBeforeIndexing() throws {
        var snapshot = try Wire.decoder().decode(RoomSnapshot.self, from: fixture("snapshot"))
        snapshot.objects[0].center = [2]
        XCTAssertThrowsError(try snapshot.validateGeometry())
        var design = try Wire.decoder().decode(DesignVersion.self, from: fixture("design"))
        design.items[0].status = .removed
        XCTAssertThrowsError(try design.validateGeometry()) // removed existing items need last-valid geometry
    }

    func testConcaveFloorTrianglesCoverTheFloorAndKeepUpwardWinding() {
        let floor: [[Float]] = [[0, 0], [4, 0], [4, 2], [2, 2], [2, 4], [0, 4]]
        for polygon in [floor, floor.reversed().map { $0 }, floor + [floor[0]]] {
            let indices = PolygonTriangulation.indices(polygon)
            XCTAssertEqual(indices.count, 12)
            var area: Float = 0
            for i in stride(from: 0, to: indices.count, by: 3) {
                let a = polygon[Int(indices[i])], b = polygon[Int(indices[i + 1])], c = polygon[Int(indices[i + 2])]
                let cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                XCTAssertLessThan(cross, 0)
                area += abs(cross) / 2
            }
            XCTAssertEqual(area, 12, accuracy: 0.001)
        }
    }

    func testJournalSurvivesRelaunchAndDeletionBlocksNewMutations() async throws {
        let directory = try temporaryDirectory()
        let disk = ClientPersistence(directory: directory)
        let request = APIRequest(method: "POST", path: "designs/d1/chat", body: Data("exact bytes".utf8), identity: "op_1")
        let pending = PendingMutation(id: "op_1", roomId: "room_1", kind: .edit, original: request)
        try await disk.journal(pending)
        let reopened = ClientPersistence(directory: directory)
        let loaded = try await reopened.load()
        XCTAssertEqual(loaded.mutations["room_1"]?.original, request)
        _ = try await reopened.markDeleted(roomId: "room_1")
        do { try await reopened.journal(pending); XCTFail("Deletion must supersede mutation") } catch {}
        try await reopened.confirmDeleted(roomId: "room_1")
        let deleted = try await reopened.load()
        XCTAssertNil(deleted.mutations["room_1"])
    }

    func testCaptureEvictionRequiresEveryMatchingDurableAcknowledgment() async throws {
        let repository = CaptureRepository(directory: try temporaryDirectory())
        let draft = try await repository.create()
        try await repository.assignRoom(draft.captureId, roomId: "room_1")
        try await repository.complete(draft.captureId, roomData: Data("{}".utf8), thumbnailData: Data([1, 2, 3]))
        var manifest = try await repository.load(draft.captureId)
        XCTAssertFalse(manifest.canEvictRawFiles)
        manifest.state = "finalized"
        manifest.acknowledgments = manifest.allArtifacts.map {
            ArtifactAcknowledgment(artifactId: $0.id, byteLength: $0.byteLength, sha256: $0.sha256, durable: true)
        }
        XCTAssertTrue(manifest.canEvictRawFiles)
        manifest.acknowledgments[0].sha256 = "wrong"
        XCTAssertFalse(manifest.canEvictRawFiles)
        manifest.acknowledgments.removeFirst()
        XCTAssertFalse(manifest.canEvictRawFiles)
    }

    func testRecoveredFrameUploadsKeepIdenticalMultipartBytes() async throws {
        let directory = try temporaryDirectory()
        let repository = CaptureRepository(directory: directory)
        let draft = try await repository.create()
        try await repository.assignRoom(draft.captureId, roomId: "room_1")
        let jpeg = try await repository.writeArtifact(captureId: draft.captureId, type: "jpeg", bytes: Data([1, 2, 3]), extension: "jpg")
        let frame = CaptureFrame(id: "frame_1", metadata: FrameMetadata(id: "frame_1", captureId: draft.captureId, timestamp: 1,
                                                                       width: 1280, height: 960, intrinsics: [1000, 1000, 640, 480], cameraToScanTransform: []), artifacts: [jpeg])
        try await repository.append(frame, captureId: draft.captureId)
        let manifest = try await repository.load(draft.captureId)
        let first = try await repository.frameRequest(frame, manifest: manifest)
        let relaunched = CaptureRepository(directory: directory)
        let restored = try await relaunched.load(draft.captureId)
        let retry = try await relaunched.frameRequest(restored.frames[0], manifest: restored)
        XCTAssertEqual(first, retry)
    }

    func testUnknownOperationReplaysExactOriginalIdentityAndPayload() async throws {
        let transport = RecordingTransport(responses: [
            (404, Data(#"{"code":"unknown_operation","message":"Unknown operation","retryable":false}"#.utf8)),
            (200, try fixture("succeeded"))
        ])
        let api = APIClient(baseURL: URL(string: "https://rooms.example.com"), appKey: "test", deviceId: "device", transport: transport)
        let body = Data(#"{"operation_id":"op_1","message":"move this"}"#.utf8)
        let pending = PendingMutation(id: "op_1", roomId: "room_1", kind: .edit,
                                      original: APIRequest(method: "POST", path: "designs/d1/chat", body: body, identity: "op_1"))
        let result = try await OperationRecovery(api: api).reconcile(pending)
        XCTAssertEqual(result.state, .succeeded)
        let requests = await transport.requests
        XCTAssertEqual(requests.map(\.httpMethod), ["GET", "POST"])
        XCTAssertEqual(requests[0].url?.path, "/v1/operations/op_1")
        XCTAssertEqual(requests[1].httpBody, body)
        XCTAssertEqual(requests[1].value(forHTTPHeaderField: "Idempotency-Key"), "op_1")
    }

    func testRunningOperationAndTransportFailureNeverReplay() async throws {
        let transport = RecordingTransport(responses: [(200, try fixture("running"))])
        let api = APIClient(baseURL: URL(string: "https://rooms.example.com"), appKey: "test", deviceId: "device", transport: transport)
        let pending = PendingMutation(id: "op_1", roomId: "room_1", kind: .edit,
                                      original: APIRequest(method: "POST", path: "designs/d1/chat", identity: "op_1"))
        let operation = try await OperationRecovery(api: api).reconcile(pending)
        XCTAssertEqual(operation.state, .running)
        let requests = await transport.requests
        XCTAssertEqual(requests.count, 1)
        let broken = RecordingTransport(responses: [])
        let brokenAPI = APIClient(baseURL: URL(string: "https://rooms.example.com"), appKey: "test", deviceId: "device", transport: broken)
        do { _ = try await OperationRecovery(api: brokenAPI).reconcile(pending); XCTFail("Expected transport failure") } catch {}
        let failedRequests = await broken.requests
        XCTAssertEqual(failedRequests.count, 1)
    }

    func testClarificationRetryKeepsOriginalAndReplyIdentities() async throws {
        let transport = RecordingTransport(responses: [(200, try fixture("clarification")), (200, try fixture("succeeded"))])
        let api = APIClient(baseURL: URL(string: "https://rooms.example.com"), appKey: "test", deviceId: "device", transport: transport)
        let continuation = APIRequest(method: "POST", path: "operations/op_1/clarifications", body: Data("reply bytes".utf8), identity: "reply_1")
        let pending = PendingMutation(id: "op_1", roomId: "room_1", kind: .edit,
                                      original: APIRequest(method: "POST", path: "designs/d1/chat", identity: "op_1"), continuation: continuation)
        _ = try await OperationRecovery(api: api).reconcile(pending)
        let requests = await transport.requests
        XCTAssertEqual(requests[1].value(forHTTPHeaderField: "Idempotency-Key"), "reply_1")
        XCTAssertEqual(requests[1].httpBody, continuation.body)
    }

    func testNewClarificationQuestionDoesNotReplayAnswerToPreviousQuestion() async throws {
        let transport = RecordingTransport(responses: [(200, try fixture("clarification"))])
        let api = APIClient(baseURL: URL(string: "https://rooms.example.com"), appKey: "test", deviceId: "device", transport: transport)
        let pending = PendingMutation(id: "op_1", roomId: "room_1", kind: .edit,
                                      original: APIRequest(method: "POST", path: "designs/d1/chat", identity: "op_1"),
                                      continuation: APIRequest(method: "POST", path: "operations/op_1/clarifications", identity: "reply_1"),
                                      continuationQuestionId: "older_question")
        let result = try await OperationRecovery(api: api).reconcile(pending)
        XCTAssertEqual(result.clarification?.id, "q1")
        let requests = await transport.requests
        XCTAssertEqual(requests.count, 1)
    }
}

private actor RecordingTransport: HTTPTransport {
    var responses: [(Int, Data)]
    private(set) var requests: [URLRequest] = []
    init(responses: [(Int, Data)]) { self.responses = responses }
    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        requests.append(request)
        guard !responses.isEmpty else { throw URLError(.timedOut) }
        let (status, body) = responses.removeFirst()
        return (body, HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!)
    }
}
