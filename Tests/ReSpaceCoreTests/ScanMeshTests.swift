import Foundation
import XCTest
@testable import ReSpaceCore

final class ScanMeshTests: XCTestCase {
    private func floats(_ values: [Float]) -> Data {
        var result = Data(); values.forEach { result.appendScanFloat($0) }; return result
    }
    private func indices(_ values: [UInt32]) -> Data {
        var result = Data(); values.forEach { result.appendScanUInt32($0) }; return result
    }
    private func anchor() -> ScanMeshAnchor {
        ScanMeshAnchor(id: "anchor", transform: [0,0,-1,0, 0,1,0,0, 1,0,0,0, 2,3,4,1],
            vertexCount: 3, triangleCount: 1,
            positions: floats([0,0,0, 1,0,0, 0,1,0]), normals: floats([0,0,1, 0,0,1, 0,0,1]),
            triangles: indices([0,1,2]))
    }
    private func mesh(_ anchor: ScanMeshAnchor) -> ScanMeshSnapshot {
        ScanMeshSnapshot(captureId: "capture", timestamp: 12, anchors: [anchor])
    }

    func testMetricAnchorCoordinatesSurviveRoundTripWithoutFitting() throws {
        let original = mesh(anchor())
        let compact = try original.anchors[0].removingUnreferencedVertices()
        XCTAssertEqual(compact.positions, original.anchors[0].positions)
        XCTAssertEqual(compact.normals, original.anchors[0].normals)
        XCTAssertEqual(compact.triangles, original.anchors[0].triangles)
        let restored = try ScanMeshSnapshot.decode(original.encoded(), captureId: "capture")
        let a = try XCTUnwrap(restored.anchors.first)
        XCTAssertEqual(a.positions, original.anchors[0].positions)
        XCTAssertEqual(a.triangles, original.anchors[0].triangles)
        XCTAssertEqual(a.worldPosition(at: 0), SIMD3(2,3,4))
        XCTAssertEqual(a.worldPosition(at: 1), SIMD3(2,3,3))
        XCTAssertEqual(a.worldPosition(at: 2), SIMD3(2,4,4))
        XCTAssertEqual(a.worldNormal(at: 1), SIMD3(1,0,0))
        let delta = a.worldPosition(at: 1) - a.worldPosition(at: 0)
        XCTAssertEqual(sqrt(delta.x*delta.x + delta.y*delta.y + delta.z*delta.z), 1, accuracy: 0.00001)
        XCTAssertThrowsError(try ScanMeshSnapshot.decode(original.encoded(), captureId: "another capture"))
    }

    func testCaptureCompactsUnusedNaNNormalsWithoutChangingAnyTriangle() throws {
        // The device returned NaN normals only for slots that no face referenced.
        var sparse = anchor()
        sparse.vertexCount = 6; sparse.triangleCount = 2
        sparse.positions = floats([9,9,9, 0,0,0, 1,0,0, 8,8,8, 0,1,0, 7,7,7])
        sparse.normals = floats([.nan,.nan,.nan, 0,0,1, 0,0,1, .nan,.nan,.nan, 0,0,1, .nan,.nan,.nan])
        sparse.triangles = indices([4,1,2, 2,1,4])
        XCTAssertThrowsError(try sparse.validate()) // persisted snapshots remain strict

        let compact = try sparse.removingUnreferencedVertices()
        XCTAssertEqual(compact.vertexCount, 3)
        XCTAssertEqual(compact.triangleCount, sparse.triangleCount)
        XCTAssertEqual(compact.id, sparse.id)
        XCTAssertEqual(compact.transform, sparse.transform)
        XCTAssertEqual(compact.triangles, indices([2,0,1, 1,0,2]))
        for index in 0..<(sparse.triangleCount * 3) {
            let before = Int(sparse.triangles.scanUInt32(at: index))
            let after = Int(compact.triangles.scanUInt32(at: index))
            XCTAssertEqual(compact.worldPosition(at: after), sparse.worldPosition(at: before))
            XCTAssertEqual(compact.worldNormal(at: after), sparse.worldNormal(at: before))
        }
        let restored = try ScanMeshSnapshot.decode(mesh(compact).encoded(), captureId: "capture")
        XCTAssertEqual(restored.anchors[0].positions, compact.positions)
        XCTAssertEqual(restored.anchors[0].normals, compact.normals)
        XCTAssertEqual(restored.anchors[0].triangles, compact.triangles)
    }

    func testRejectsInvalidGeometryAndNonRigidTransforms() {
        var scaled = anchor(); scaled.transform[0] = 2
        var reflected = anchor(); reflected.transform[1] = 0; reflected.transform[2] = 1
        var badIndex = anchor(); badIndex.triangles = indices([0,1,3])
        var truncated = anchor(); truncated.positions.removeLast()
        var nonfinite = anchor(); nonfinite.positions = floats([.nan,0,0, 1,0,0, 0,1,0])
        var badNormal = anchor(); badNormal.normals = floats([0,0,1, .nan,.nan,.nan, 0,0,1])
        var overLimit = anchor(); overLimit.vertexCount = ScanMeshSnapshot.maximumVertices + 1
        for invalid in [scaled,reflected,badIndex,truncated,nonfinite,badNormal,overLimit] {
            XCTAssertThrowsError(try mesh(invalid).validate(for: "capture"))
            XCTAssertThrowsError(try invalid.removingUnreferencedVertices())
        }
        var duplicate = mesh(anchor()); duplicate.anchors.append(anchor())
        XCTAssertThrowsError(try duplicate.validate(for: "capture"))
        XCTAssertThrowsError(try ScanMeshSnapshot(captureId: "capture", timestamp: 1, anchors: []).validate(for: "capture"))
    }

    func testDepthRejectsForegroundOcclusionInvalidDepthAndLowConfidence() throws {
        var metadata = FrameMetadata(id: "frame", captureId: "capture", timestamp: 1, width: 100, height: 100,
            intrinsics: [50,50,50,50], cameraToScanTransform: [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1])
        metadata.depthWidth = 2; metadata.depthHeight = 2; metadata.depthFormat = "float16_le_meters"
        metadata.confidenceWidth = 2; metadata.confidenceHeight = 2; metadata.confidenceFormat = "uint8_arkit"
        var depth = Data()
        for value: Float in [2,1,.nan,2] {
            var bits = Float16(value).bitPattern.littleEndian
            withUnsafeBytes(of: &bits) { depth.append(contentsOf: $0) }
        }
        let registered = try XCTUnwrap(RegisteredScanDepth(metadata: metadata, depth: depth, confidence: Data([2,2,2,0])))
        XCTAssertTrue(registered.seesSurface(u: 0.25, v: 0.25, cameraDepth: 2.02))
        XCTAssertFalse(registered.seesSurface(u: 0.75, v: 0.25, cameraDepth: 2)) // foreground at 1 m
        XCTAssertFalse(registered.seesSurface(u: 0.25, v: 0.75, cameraDepth: 2)) // nonfinite
        XCTAssertFalse(registered.seesSurface(u: 0.75, v: 0.75, cameraDepth: 2)) // low confidence
        XCTAssertFalse(registered.seesSurface(u: 1, v: 0.25, cameraDepth: 2))
        XCTAssertFalse(registered.seesSurface(u: 0.25, v: 0.25, cameraDepth: .nan))
        XCTAssertNil(RegisteredScanDepth(metadata: metadata, depth: Data(), confidence: nil))
    }

    func testMeasuredMeshIsRetainedAndIntegrityCheckedAfterReopening() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let repository = CaptureRepository(directory: root)
        let capture = try await repository.create()
        try await repository.assignRoom(capture.captureId, roomId: capture.captureId)
        let data = try ScanMeshSnapshot(captureId: capture.captureId, timestamp: 1, anchors: [anchor()]).encoded()
        try await repository.complete(capture.captureId, roomData: Data("room".utf8), thumbnailData: nil, sceneMeshData: data)
        let preview = await repository.localPreviewURL(capture.captureId)
        try Data("preview".utf8).write(to: preview)
        try await repository.saveLocalRoom(capture.captureId, objectCount: 1)
        let reopened = CaptureRepository(directory: root)
        let manifest = try await reopened.load(capture.captureId)
        let artifact = try XCTUnwrap(manifest.sceneMesh)
        let retained = try await reopened.bytes(artifact, captureId: capture.captureId)
        XCTAssertEqual(retained, data)
        XCTAssertEqual(manifest.state, "local_saved")
        XCTAssertTrue(manifest.allArtifacts.contains(artifact))
        XCTAssertFalse(manifest.canEvictRawFiles)
        let corrupted = preview.deletingLastPathComponent().appendingPathComponent(artifact.filename)
        try Data("damaged".utf8).write(to: corrupted)
        do { _ = try await reopened.bytes(artifact, captureId: capture.captureId); XCTFail("Damaged mesh must fail") }
        catch { XCTAssertTrue(error is ClientError) }
    }

    func testLegacyManifestWithoutMeshStillDecodes() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let repository = CaptureRepository(directory: root)
        let capture = try await repository.create()
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Wire.encoder().encode(capture)) as? [String: Any])
        object.removeValue(forKey: "scene_mesh")
        let legacy = try Wire.decoder().decode(CaptureManifest.self, from: JSONSerialization.data(withJSONObject: object))
        XCTAssertNil(legacy.sceneMesh)
    }
}
