import XCTest
@testable import ReSpaceContracts

final class BackendURLPolicyTests: XCTestCase {
    func testHTTPSAndCredentials() {
        XCTAssertTrue(BackendURLPolicy.allows(URL(string: "https://backend.example")!))
        for value in ["https://user:password@backend.example", "file:///tmp/room", "http://backend.example", "http://8.8.8.8", "http://localhost.attacker.example"] {
            XCTAssertFalse(BackendURLPolicy.allows(URL(string: value)!), value)
        }
    }
    func testLocalHTTPIsDebugOnly() {
        for value in ["http://localhost:8000", "http://127.0.0.1:8000", "http://[::1]:8000", "http://10.0.0.3:8000", "http://172.16.0.3:8000", "http://192.168.1.3:8000", "http://respace.local:8000"] {
            #if DEBUG
            XCTAssertTrue(BackendURLPolicy.allows(URL(string: value)!), value)
            #else
            XCTAssertFalse(BackendURLPolicy.allows(URL(string: value)!), value)
            #endif
        }
        for value in ["http://172.15.0.3", "http://172.32.0.3", "http://192.169.1.3", "http://10.0.0.256", "http://10.a.0.0.1", "http://010.0.0.1", "http://10.+0.0.1"] {
            XCTAssertFalse(BackendURLPolicy.allows(URL(string: value)!), value)
        }
    }
    func testPrivateMediaAndCredentialsStayOnTheConfiguredOrigin() {
        let base = URL(string: "https://backend.example/v1")!
        XCTAssertTrue(BackendURLPolicy.sameOrigin(URL(string: "https://backend.example:443/v1/media/one")!, base))
        for value in ["https://backend.example:444/v1/media/one", "http://backend.example/v1/media/one", "https://other.example/v1/media/one", "https://user@backend.example/v1/media/one"] {
            XCTAssertFalse(BackendURLPolicy.sameOrigin(URL(string: value)!, base), value)
        }
    }
    func testPublicAssetsCanUseHTTPSAndLocalHTTPStaysOnBackendOrigin() {
        let local = URL(string: "http://127.0.0.1:8000/v1")!
        XCTAssertTrue(BackendURLPolicy.allowsAsset(URL(string: "https://assets.example/chair.usdz")!, from: local))
        XCTAssertFalse(BackendURLPolicy.allowsAsset(URL(string: "http://192.168.1.3:8000/chair.usdz")!, from: local))
        #if DEBUG
        XCTAssertTrue(BackendURLPolicy.allowsAsset(URL(string: "http://127.0.0.1:8000/chair.usdz")!, from: local))
        #else
        XCTAssertFalse(BackendURLPolicy.allowsAsset(URL(string: "http://127.0.0.1:8000/chair.usdz")!, from: local))
        #endif
    }
}
