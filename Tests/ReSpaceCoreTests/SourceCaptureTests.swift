import Foundation
import CryptoKit
import ModelIO
import SceneKit
import SceneKit.ModelIO
import XCTest
@testable import ReSpaceCore

final class SourceCaptureTests: XCTestCase {
    private func directory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }
    private func nativeCapture(_ repository: CaptureRepository, layoutAvailable: Bool = true) async throws -> CaptureManifest {
        let capture = try await repository.create()
        try await repository.assignRoom(capture.captureId, roomId: capture.captureId)
        let source = try await repository.createSourceBundle(capture.captureId)
        try Data(#"{"format":"house-capture/5","state":"completed","rooms":[]}"#.utf8)
            .write(to: source.appendingPathComponent("manifest.json"))
        try Data("original pixels".utf8).write(to: source.appendingPathComponent("photo.jpg"))
        let seal = try SourceBundleIntegrity.create(at: source)
        let sealData = try JSONEncoder().encode(seal)
        try sealData.write(to: source.appendingPathComponent("integrity.json"))
        try await repository.complete(capture.captureId, roomData: layoutAvailable ? Data("measured room".utf8) : nil, thumbnailData: nil,
                                      sourceIntegrityData: sealData, sourceLayoutError: layoutAvailable ? nil : "RoomBuilder could not finish")
        try await repository.saveLocalRoom(capture.captureId, objectCount: 0)
        return try await repository.load(capture.captureId)
    }
    func testFreshStartRemovesOnlyLegacyCapturesOnceAndKeepsNativeCapture() async throws {
        let parent = try directory(), root = parent.appendingPathComponent("Captures")
        let unrelated = parent.appendingPathComponent("planning-and-shopping.json")
        try Data("keep".utf8).write(to: unrelated)
        let legacy = CaptureRepository(directory: root)
        let old = try await legacy.create()
        let native = try await nativeCapture(legacy)
        let fresh = CaptureRepository(directory: root, freshCaptureOnly: true)
        let rooms = try await fresh.localRooms()
        XCTAssertEqual(rooms.map(\.id), [native.captureId])
        let manifests = try await fresh.manifests()
        XCTAssertEqual(manifests.map(\.captureId), [native.captureId])
        do { _ = try await fresh.load(old.captureId); XCTFail("The authorized legacy scan should be removed") } catch {}
        XCTAssertEqual(try Data(contentsOf: unrelated),Data("keep".utf8))
        // Reopening must never repeat a broad cleanup over future data.
        let later = try await legacy.create()
        try await fresh.clearLegacyCapturesOnce()
        let retained = try await fresh.load(later.captureId)
        XCTAssertEqual(retained.captureId,later.captureId)
    }
    func testNativeCaptureUsesDirectBundleWithoutLegacyFramesOrMandatoryPreview() async throws {
        let repository = CaptureRepository(directory: try directory())
        let native = try await nativeCapture(repository)
        XCTAssertEqual(native.sourceBundleFormat,"house-capture/5")
        XCTAssertTrue(native.frames.isEmpty)
        XCTAssertNil(native.sceneMesh)
        XCTAssertNotNil(native.sourceBundleIntegrity)
        XCTAssertFalse(native.canEvictRawFiles)
        let url = try await repository.sourceBundleURL(native.captureId)
        XCTAssertNotNil(url)
        let preview = await repository.localPreviewURL(native.captureId)
        XCTAssertFalse(FileManager.default.fileExists(atPath: preview.path))
    }
    func testSourceIntegrityRejectsChangedMissingAndAddedFiles() throws {
        let root = try directory(), file = root.appendingPathComponent("original.jpg")
        try Data("original pixels".utf8).write(to: file)
        let seal = try SourceBundleIntegrity.create(at: root)
        try seal.verify(at: root)
        try Data("modified pixels".utf8).write(to: file)
        XCTAssertThrowsError(try seal.verify(at: root))
        try Data("original pixels".utf8).write(to: file)
        let extra = root.appendingPathComponent("extra.jpg")
        try Data("unexpected".utf8).write(to: extra)
        XCTAssertThrowsError(try seal.verify(at: root))
        try FileManager.default.removeItem(at: extra)
        try FileManager.default.removeItem(at: file)
        XCTAssertThrowsError(try seal.verify(at: root))
    }
    func testNativeArchiveIsZIPAndRefusesCorruptEvidence() async throws {
        let repository = CaptureRepository(directory: try directory())
        let native = try await nativeCapture(repository)
        let archive = try await repository.sourceBundleArchive(native.captureId)
        addTeardownBlock { try? FileManager.default.removeItem(at: archive) }
        XCTAssertEqual(try Data(contentsOf: archive).prefix(2),Data([0x50,0x4b]))
        let sourceURL = try await repository.sourceBundleURL(native.captureId)
        let source = try XCTUnwrap(sourceURL)
        try Data("changed".utf8).write(to: source.appendingPathComponent("photo.jpg"))
        do { _ = try await repository.sourceBundleArchive(native.captureId); XCTFail("Corrupt evidence must not be shared as a valid capture") } catch {}
    }
    func testUpstreamBudgetThrottlesInsteadOfKeepingOldPhotoAndTimeCaps() {
        let normal = CaptureBudget(thermal: .nominal, photos: 0, memoryPressure: false)
        XCTAssertEqual(normal.depthInterval,0.2)
        XCTAssertEqual(normal.photoInterval,0.4)
        let large = CaptureBudget(thermal: .nominal, photos: 901, memoryPressure: false)
        XCTAssertEqual(large.photoInterval,1.2)
        XCTAssertEqual(large.depthInterval,0.5)
        let critical = CaptureBudget(thermal: .critical, photos: 1, memoryPressure: false)
        XCTAssertEqual(critical.depthInterval,1)
        XCTAssertFalse(CaptureQuality(percent: 84,walls: 4,photos: 20).ready)
        XCTAssertTrue(CaptureQuality(percent: 85,walls: 4,photos: 20).ready)
    }
    func testFreshNativeCaptureUploadsStableOriginalFilesAndResumesOnlyMissing() async throws {
        let repository = CaptureRepository(directory: try directory())
        let native = try await nativeCapture(repository)
        let upload = try await repository.nativeReconstructionUpload(native.captureId)
        XCTAssertEqual(upload.schemaVersion, 2)
        XCTAssertEqual(upload.format, "house-capture/5")
        XCTAssertEqual(Set(upload.files.map(\.relativePath)), ["manifest.json", "photo.jpg", "integrity.json"])
        for file in upload.files {
            let expected = SHA256.hash(data: Data(file.relativePath.utf8)).map { String(format: "%02x", $0) }.joined()
            XCTAssertEqual(file.id, expected); XCTAssertEqual(file.filename, expected)
        }
        let missing = try XCTUnwrap(upload.files.first { $0.relativePath == "photo.jpg" })
        let base = "/v1/reconstructions/" + native.captureId
        let recorder = ReconstructionRequestRecorder { request in
            if request.url!.path == base && request.httpMethod == "PUT" {
                var body=request.httpBody ?? Data()
                if let stream=request.httpBodyStream {
                    stream.open(); defer { stream.close() }
                    var buffer=[UInt8](repeating:0,count:4096)
                    while stream.hasBytesAvailable {
                        let count=stream.read(&buffer,maxLength:buffer.count)
                        if count<=0 { break };body.append(buffer,count:count)
                    }
                }
                let wire = try XCTUnwrap(JSONSerialization.jsonObject(with:body) as? [String:Any])
                XCTAssertEqual(wire["schema_version"] as? Int, 2)
                XCTAssertNil(wire["frames"]); XCTAssertNil(wire["scene_mesh"])
                return (200, try Wire.encoder().encode(ReconstructionJob(schemaVersion:1,id:native.captureId,state:"uploading",revision:0,stage:"uploading",missingArtifactIds:[missing.id])))
            }
            if request.url!.path == base + "/artifacts/" + missing.id { return (200, Data("{}".utf8)) }
            if request.url!.path == base + "/run" {
                return (200, try Wire.encoder().encode(ReconstructionJob(schemaVersion:1,id:native.captureId,state:"queued",revision:0,stage:"queued",missingArtifactIds:[])))
            }
            return (404, Data())
        }
        let client = ReconstructionClient(baseURL:URL(string:"http://mac.local:8008")!,token:"test-reconstruction-token",session:recorder.session())
        let job = try await client.submit(native.captureId, repository:repository)
        XCTAssertEqual(job.state, "queued")
        XCTAssertEqual(recorder.requests.filter { $0.url!.path.contains("/artifacts/") }.count,1)
        let source = try await repository.sourceBundleURL(native.captureId)!
        try Data("tampered".utf8).write(to:source.appendingPathComponent("photo.jpg"))
        do { _ = try await repository.nativeReconstructionUpload(native.captureId); XCTFail("Changed source bytes must fail before upload") } catch {}
    }
    func testThreeJSNativeAssetsDownloadAndValidateAgainstActualWorker() async throws {
        let environment=ProcessInfo.processInfo.environment
        guard let fixture=environment["RESPACE_TEST_THREEJS_FIXTURE"], let origin=environment["RESPACE_TEST_ORIGIN"] else {
            throw XCTSkip("Opt-in actual native asset integration requires the synthetic Three.js worker fixture")
        }
        let root=URL(fileURLWithPath:fixture), source=root.appendingPathComponent("source")
        let repository=CaptureRepository(directory:try directory())
        var capture=try await repository.create();capture.captureId="native-synthetic"
        try await repository.save(capture)
        try await repository.assignRoom(capture.captureId,roomId:capture.captureId)
        let target=try await repository.createSourceBundle(capture.captureId)
        for file in try FileManager.default.contentsOfDirectory(at:source,includingPropertiesForKeys:nil) {
            try FileManager.default.copyItem(at:file,to:target.appendingPathComponent(file.lastPathComponent))
        }
        let seal=try Data(contentsOf:target.appendingPathComponent("integrity.json"))
        try await repository.complete(capture.captureId,roomData:Data("synthetic measured room".utf8),thumbnailData:nil,sourceIntegrityData:seal)
        let client=ReconstructionClient(baseURL:URL(string:origin)!,token:"synthetic-native-test-token")
        let job=try await client.submit(capture.captureId,repository:repository)
        XCTAssertTrue(job.hasFinalWalkthrough)
        XCTAssertEqual(job.result?.pipeline,"threejs")
        let loadedScene=try await client.sceneURL(capture.captureId,repository:repository)
        let sceneURL=try XCTUnwrap(loadedScene)
        let scene=try Wire.decoder().decode(WalkthroughBundle.self,from:Data(contentsOf:sceneURL))
        XCTAssertTrue(scene.materials.contains { $0.baseColorTexture != nil })
        XCTAssertTrue(scene.entities.contains { $0.id=="curved-chair" })
        let shared=try await client.usdzURL(capture.captureId,repository:repository)
        XCTAssertNotNil(shared)
        var triangleCount=0
        for entity in scene.entities {
            let asset=MDLAsset(url:sceneURL.deletingLastPathComponent().appendingPathComponent(entity.asset));asset.loadTextures()
            let native=SCNScene(mdlAsset:asset)
            var names=Set<String>(),hasUV=false
            native.rootNode.enumerateHierarchy { node,_ in
                if let geometry=node.geometry {
                    triangleCount += geometry.elements.reduce(0) { $0+$1.primitiveCount }
                    names.formUnion(geometry.materials.compactMap(\.name))
                    hasUV = hasUV || !geometry.sources(for:.texcoord).isEmpty
                }
            }
            let bindings=scene.materials.filter { $0.ownerId==entity.id }
            XCTAssertTrue(Set(bindings.map(\.sourceMaterial)).isSubset(of:names),"Native material names must bind exported texture maps")
            if bindings.contains(where: { $0.baseColorTexture != nil }) { XCTAssertTrue(hasUV) }
        }
        XCTAssertEqual(triangleCount,job.result?.generatedTriangleCount)
    }
    func testRoomPlanBuildFailureDoesNotDiscardTheNativeCapture() async throws {
        let repository = CaptureRepository(directory: try directory())
        let capture = try await nativeCapture(repository, layoutAvailable: false)
        XCTAssertNil(capture.roomExport)
        XCTAssertNotNil(capture.sourceLayoutError)
        let rooms = try await repository.localRooms()
        XCTAssertEqual(rooms.map(\.id),[capture.captureId])
        let archive = try await repository.sourceBundleArchive(capture.captureId)
        addTeardownBlock { try? FileManager.default.removeItem(at: archive) }
        XCTAssertEqual(try Data(contentsOf: archive).prefix(2),Data([0x50,0x4b]))
    }
}
