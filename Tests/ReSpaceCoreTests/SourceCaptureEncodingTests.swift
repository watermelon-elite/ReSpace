import Foundation
import XCTest
@testable import ReSpaceCore

final class SourceCaptureEncodingTests: XCTestCase {
    private struct UnencodableRawRoom: Encodable {
        func encode(to encoder: Encoder) throws {
            throw EncodingError.invalidValue(self, .init(codingPath: [], debugDescription: "Invalid data"))
        }
    }
    private let transform: [Float] = [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]
    private let intrinsics: [Float] = [1000,0,0, 0,1000,0, 960,720,1]

    private func photo(camera: CameraState?) -> PhotoRecord {
        PhotoRecord(file: "photos/0000.jpg", room: 0, timestamp: 1, width: 1920, height: 1440,
                    transform: transform, intrinsics: intrinsics, tracking: "normal", manual: false,
                    exposure: 1.0/60, blurPixels: 1, pass: "scan", highRes: false, camera: camera)
    }

    func testPhotoIndexOmitsUnavailableCameraMeasurements() throws {
        for value in [Double.nan, .infinity, -.infinity] {
            let camera = CameraState(iso: Float(value), shutter: value, exposureOffset: Float(value),
                                     whiteBalance: [1, Float(value), 1], whiteBalanceLocked: true,
                                     ambientIntensity: Float(value), colorTemperature: Float(value))
            let data = try JSONEncoder().encode([photo(camera: camera)])
            let wire = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [[String: Any]])
            let savedCamera = try XCTUnwrap(wire.first?["camera"] as? [String: Any])
            XCTAssertEqual(Set(savedCamera.keys), ["whiteBalanceLocked"])
            let saved = try JSONDecoder().decode([PhotoRecord].self, from: data)[0]
            XCTAssertEqual(saved.transform, transform)
            XCTAssertEqual(saved.intrinsics, intrinsics)
            XCTAssertEqual(saved.exposure, 1.0/60)
        }
    }

    func testDepthIndexUsesSameCameraEncoding() throws {
        let camera = CameraState(shutter: .nan, exposureOffset: -.infinity)
        let record = SourceDepthRecord(file: "depth/00000.f16z", confidence: "depth/00000.conf",
                                       camera: camera, room: 0, timestamp: 1, width: 256, height: 192,
                                       transform: transform, intrinsics: intrinsics)
        let data = try JSONEncoder().encode([record])
        let saved = try JSONDecoder().decode([SourceDepthRecord].self, from: data)[0]
        XCTAssertNil(saved.camera?.shutter)
        XCTAssertNil(saved.camera?.exposureOffset)
        XCTAssertEqual(saved.transform, transform)
        XCTAssertEqual(saved.intrinsics, intrinsics)
    }

    func testPhotoIndexOmitsUnavailableExposureAndBlur() throws {
        for value in [Double.nan, .infinity, -.infinity] {
            var record = photo(camera: nil)
            record.exposure = value
            record.blurPixels = Float(value)
            let data = try JSONEncoder().encode([record])
            let saved = try JSONDecoder().decode([PhotoRecord].self, from: data)[0]
            XCTAssertNil(saved.exposure)
            XCTAssertNil(saved.blurPixels)
        }
    }

    func testAvailableMeasurementsSurviveRoundTrip() throws {
        let camera = CameraState(iso: 100, shutter: 1.0/60, exposureOffset: 0,
                                 whiteBalance: [1.1, 1, 1.2], whiteBalanceLocked: true,
                                 ambientIntensity: 1000, colorTemperature: 6500)
        let record = photo(camera: camera)
        let data = try JSONEncoder().encode([record])
        let saved = try JSONDecoder().decode([PhotoRecord].self, from: data)[0]
        XCTAssertEqual(saved.camera?.iso, camera.iso)
        XCTAssertEqual(saved.camera?.shutter, camera.shutter)
        XCTAssertEqual(saved.camera?.exposureOffset, camera.exposureOffset)
        XCTAssertEqual(saved.camera?.whiteBalance, camera.whiteBalance)
        XCTAssertEqual(saved.camera?.whiteBalanceLocked, camera.whiteBalanceLocked)
        XCTAssertEqual(saved.camera?.ambientIntensity, camera.ambientIntensity)
        XCTAssertEqual(saved.camera?.colorTemperature, camera.colorTemperature)
        XCTAssertEqual(saved.exposure, record.exposure)
        XCTAssertEqual(saved.blurPixels, record.blurPixels)
        XCTAssertEqual(saved.transform, record.transform)
        XCTAssertEqual(saved.intrinsics, record.intrinsics)
    }

    func testRequiredCalibrationStillRejectsInvalidNumbers() throws {
        var record = photo(camera: nil)
        record.transform[12] = .nan
        XCTAssertThrowsError(try JSONEncoder().encode([record]))
        record.transform = transform
        record.intrinsics[0] = .infinity
        XCTAssertThrowsError(try JSONEncoder().encode([record]))
    }

    func testFinalizationWritesIndexesAndReportsRequiredFieldWithoutReplacingSavedData() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        for folder in ["photos", "depth"] {
            try FileManager.default.createDirectory(at: root.appendingPathComponent(folder), withIntermediateDirectories: true)
        }
        let camera = CameraState(shutter: .nan, exposureOffset: -.infinity)
        let photos = root.appendingPathComponent("photos/photos.json")
        let depth = root.appendingPathComponent("depth/frames.json")
        let record = photo(camera: camera)
        try SourceCaptureStorage.writeJSON([record], to: photos)
        try SourceCaptureStorage.writeJSON([
            SourceDepthRecord(file: "depth/00000.f16z", confidence: "depth/00000.conf", camera: camera,
                              room: 0, timestamp: 1, width: 256, height: 192,
                              transform: transform, intrinsics: intrinsics)
        ], to: depth, prettyPrinted: true)
        let photoBytes = try Data(contentsOf: photos)
        XCTAssertEqual(try JSONDecoder().decode([PhotoRecord].self, from: photoBytes)[0].transform, transform)
        XCTAssertEqual(try JSONDecoder().decode([SourceDepthRecord].self, from: Data(contentsOf: depth))[0].intrinsics, intrinsics)

        var invalid = record
        invalid.transform[12] = .nan
        XCTAssertThrowsError(try SourceCaptureStorage.writeJSON([invalid], to: photos)) { error in
            XCTAssertTrue(error.localizedDescription.contains("photos/photos.json"))
            XCTAssertTrue(error.localizedDescription.contains("[0].transform[12]"))
        }
        XCTAssertEqual(try Data(contentsOf: photos), photoBytes)
    }

    func testWriteFailureNamesTheFile() {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("photos.json")
        XCTAssertThrowsError(try SourceCaptureStorage.writeJSON([photo(camera: nil)], to: url)) { error in
            XCTAssertTrue(error.localizedDescription.contains("photos.json"))
        }
    }

    func testRawRoomEncodingFailureDoesNotThrowOrClaimAnArchive() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let url = root.appendingPathComponent("room-0-data.json")
        let archive = try SourceCaptureStorage.archiveRawRoom(UnencodableRawRoom(), to: url)
        XCTAssertNil(archive.filename)
        XCTAssertTrue(archive.warning?.contains("Invalid data") == true)
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }

    func testRawRoomArchivePreservesEncodableDataAndStorageFailuresStillThrow() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let url = root.appendingPathComponent("room-0-data.json")
        let bytes = Data("opaque raw capture".utf8)
        let archive = try SourceCaptureStorage.archiveRawRoom(bytes, to: url)
        XCTAssertEqual(archive.filename, "room-0-data.json")
        XCTAssertNil(archive.warning)
        XCTAssertEqual(try JSONDecoder().decode(Data.self, from: Data(contentsOf: url)), bytes)
        XCTAssertThrowsError(try SourceCaptureStorage.archiveRawRoom(bytes, to: root.appendingPathComponent("missing/room-0-data.json")))
    }
}
