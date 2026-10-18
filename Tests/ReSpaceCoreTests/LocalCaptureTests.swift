import Foundation
import XCTest
@testable import ReSpaceCore

final class LocalCaptureTests: XCTestCase {
    private func directory() -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }

    func testLocalRoomSurvivesReopeningWithoutClaimingBackendStorage() async throws {
        let root = directory()
        let repository = CaptureRepository(directory: root)
        let capture = try await repository.create()
        try await repository.assignRoom(capture.captureId, roomId: capture.captureId)
        let raw = Data("raw RoomPlan export".utf8)
        try await repository.complete(capture.captureId, roomData: raw, thumbnailData: nil)
        let preview = await repository.localPreviewURL(capture.captureId)
        // Persistence tests treat the native USDZ exporter output as opaque bytes.
        try Data("USDZ output".utf8).write(to: preview)
        try await repository.saveLocalRoom(capture.captureId, objectCount: 3)

        let reopened = CaptureRepository(directory: root)
        let saved = try await reopened.localRooms()
        XCTAssertEqual(saved.map(\.id), [capture.captureId])
        XCTAssertEqual(saved.first?.objectCount, 3)
        let manifest = try await reopened.load(capture.captureId)
        XCTAssertEqual(manifest.state, "local_saved")
        XCTAssertFalse(manifest.canEvictRawFiles)
        XCTAssertTrue(manifest.acknowledgments.isEmpty)
        XCTAssertNil(manifest.scanToRoomTransform)
        let retained = try await reopened.bytes(XCTUnwrap(manifest.roomExport), captureId: capture.captureId)
        XCTAssertEqual(retained, raw)

        let creationName = try await reopened.backendCreationName(capture.captureId)
        try await reopened.renameLocalRoom(capture.captureId, name: "  Living room  ")
        let renamed = try await reopened.localRoom(capture.captureId)
        XCTAssertEqual(renamed.name, "Living room")
        let replayName = try await reopened.backendCreationName(capture.captureId)
        XCTAssertEqual(replayName, creationName, "A retry must retain the original room-creation payload after a rename.")
        try await reopened.linkBackend(capture.captureId, roomId: "backend-room", captureId: "backend-capture")
        let linked = try await CaptureRepository(directory: root).localRoom(capture.captureId)
        XCTAssertEqual(linked.backendRoomId, "backend-room")
        XCTAssertEqual(linked.backendCaptureId, "backend-capture")
        let linkedManifest = try await reopened.load(capture.captureId)
        XCTAssertFalse(linkedManifest.canEvictRawFiles)

        try await reopened.removeCapture(capture.captureId)
        let remaining = try await reopened.manifests()
        XCTAssertTrue(remaining.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: preview.path))
    }

    func testMissingPreviewKeepsCompletedScanRecoverable() async throws {
        let repository = CaptureRepository(directory: directory())
        let capture = try await repository.create()
        try await repository.assignRoom(capture.captureId, roomId: capture.captureId)
        try await repository.complete(capture.captureId, roomData: Data("room".utf8), thumbnailData: nil)
        do {
            try await repository.saveLocalRoom(capture.captureId, objectCount: 0)
            XCTFail("Saving without an exported model must fail")
        } catch { XCTAssertTrue(error is ClientError) }
        let manifest = try await repository.load(capture.captureId)
        XCTAssertEqual(manifest.state, "completed")
        let rooms = try await repository.localRooms()
        XCTAssertTrue(rooms.isEmpty)
    }

    @MainActor func testLocalModeUsesSeparateStorageAndSkipsBackendBootstrap() async throws {
        let root = directory()
        let local = WorkspaceStore(configuration: AppConfiguration(serviceURL: nil, appKey: "", storageURL: root), deviceId: "test")
        let remote = WorkspaceStore(configuration: AppConfiguration(serviceURL: nil, appKey: "", storageURL: root,
                                                                    localCaptureEnabled: false), deviceId: "test")
        XCTAssertTrue(local.localCaptureEnabled)
        XCTAssertFalse(remote.localCaptureEnabled)
        _ = try await local.captures.create()
        _ = try await remote.captures.create()
        await local.bootstrap()
        XCTAssertNil(local.listError)
        let localCaptures = try await local.captures.manifests()
        let remoteCaptures = try await remote.captures.manifests()
        XCTAssertEqual(localCaptures.count, 1)
        XCTAssertEqual(remoteCaptures.count, 1)
        XCTAssertNotEqual(localCaptures.first?.captureId, remoteCaptures.first?.captureId)
    }
}
