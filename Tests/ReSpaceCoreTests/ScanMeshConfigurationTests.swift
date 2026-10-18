import XCTest
@testable import ReSpaceCore

final class ScanMeshConfigurationTests: XCTestCase {
    private struct Reconstruction: OptionSet {
        let rawValue: UInt
        static let mesh = Self(rawValue: 1)
        static let classifiedMesh = Self(rawValue: 3)
    }

    func testRoomPlanStartupTraceKeepsMeshEnabledWithAdditionalFeatures() {
        // Captured on the iPhone: shared-session startup uses options 25 (1 | 8 | 16).
        // It still provides the mesh capability requested by capture.
        let recordedStartup: [UInt] = [25,1]
        for flags in recordedStartup {
            XCTAssertTrue(ScanMeshConfiguration.isEnabled(Reconstruction(rawValue: flags), mesh: .mesh),
                          "Active mesh capture must survive RoomPlan's additional features (\(flags))")
        }
        XCTAssertTrue(ScanMeshConfiguration.isEnabled(Reconstruction.classifiedMesh, mesh: .mesh))
    }

    func testDisabledOrMissingMeshConfigurationStillStopsCapture() {
        XCTAssertFalse(ScanMeshConfiguration.isEnabled(Reconstruction(rawValue: 0), mesh: .mesh))
        XCTAssertFalse(ScanMeshConfiguration.isEnabled(Reconstruction(rawValue: 24), mesh: .mesh))
        XCTAssertFalse(ScanMeshConfiguration.isEnabled(Optional<Reconstruction>.none, mesh: .mesh))
    }
}
