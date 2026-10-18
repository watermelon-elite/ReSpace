import XCTest
@testable import ReSpaceCore

final class ScanColorProjectionTests: XCTestCase {
    func testSensorProjectionUsesARKitForwardAndImageYAxis() throws {
        let intrinsics: [Float] = [600, 600, 640, 480]
        XCTAssertEqual(ScanColorProjection.pixel(cameraPoint: [0, 0, -2], intrinsics: intrinsics, width: 1280, height: 960), [640, 480])
        XCTAssertEqual(ScanColorProjection.pixel(cameraPoint: [1, 1, -2], intrinsics: intrinsics, width: 1280, height: 960), [940, 180])
        // Resizing the JPEG and intrinsics together must preserve normalized image coordinates.
        XCTAssertEqual(ScanColorProjection.pixel(cameraPoint: [1, 1, -2], intrinsics: [300, 300, 320, 240], width: 640, height: 480), [470, 90])
    }

    func testRejectsBehindCameraOutsideImageAndInvalidCalibration() {
        let k: [Float] = [600, 600, 640, 480]
        for point: [Float] in [[0, 0, 2], [0, 0, 0], [10, 0, -1], [0, 10, -1], [.nan, 0, -1]] {
            XCTAssertNil(ScanColorProjection.pixel(cameraPoint: point, intrinsics: k, width: 1280, height: 960))
        }
        XCTAssertNil(ScanColorProjection.pixel(cameraPoint: [0, 0, -1], intrinsics: [0, 600, 640, 480], width: 1280, height: 960))
        XCTAssertNil(ScanColorProjection.pixel(cameraPoint: [], intrinsics: k, width: 1280, height: 960))
    }
}
