import XCTest
@testable import ReSpaceContracts

final class DesignCameraTests: XCTestCase {
    func testCameraStaysInsideRoomAndCannotTunnelThroughFurniture() throws {
        let scene = try JSONDecoder().decode(JSONValue.self, from: Data("""
        {"room":{"floor":{"polygon":[[0,0],[4,0],[4,4],[0,4]]}},"items":[
          {"category":"sofa","placement":{"position":[2,0,2],"size":[2,0.5,1],"yaw":0,"mount":"floor"}}
        ]}
        """.utf8))
        let path=DesignCameraPath(scene:scene)
        XCTAssertNotNil(path.spawn())
        XCTAssertTrue(path.canStand(try XCTUnwrap(path.spawn())))
        XCTAssertFalse(path.canStand([2,2]))
        XCTAssertFalse(path.canStand([0.1,1]))
        let moved=path.move(from:[2,1],delta:[0,2])
        XCTAssertLessThan(moved[1],1.6)
        XCTAssertTrue(path.canStand(moved))
        XCTAssertLessThan(path.move(from:[3.5,1],delta:[2,0])[0],4)
    }
}
