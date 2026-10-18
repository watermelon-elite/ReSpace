import XCTest
import RealityKit
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
@testable import ReSpaceContracts

@MainActor final class RenderAssetTests: XCTestCase {
    private var root: URL { URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent() }
    private func asset() throws -> RenderAsset {
        let manifest = try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: root.appendingPathComponent("assets/manifest.json")))
        return try RenderAsset(XCTUnwrap(manifest["assets"].array.first))
    }
    func testNormalizedAssetUsesSavedAxesAndDimensionedAssetIsNotScaledTwice() throws {
        let normalized = try asset()
        XCTAssertEqual(try normalized.scale(for: [0.7, 0.3, 1.1]), [0.7, 1.1, 0.3])
        var record = normalized.value.object
        record["scaling_mode"] = .string("dimensioned"); record["authored_bounds"] = .array([.number(2), .number(0.5), .number(0.8)])
        let dimensioned = try RenderAsset(.object(record))
        XCTAssertEqual(try dimensioned.scale(for: [2, 0.5, 0.8]), [1, 1, 1])
        XCTAssertThrowsError(try dimensioned.scale(for: [2.2, 0.5, 0.8]))
        XCTAssertFalse(dimensioned.validatesLoadedBounds(minimum: [-1, -0.2, -0.25], maximum: [1, 0.6, 0.25]))
    }
    func testRealLicensedChairLoadsAtSavedDimensionsAndPivot() async throws {
        let asset = try asset()
        let url = root.appendingPathComponent("assets/" + asset.value["path"].text)
        let entity = try await RealityAssetLoader.load(asset, from: url, savedSize: [0.7, 0.3, 1.1])
        let bounds = entity.visualBounds(relativeTo: nil)
        XCTAssertEqual(Double(bounds.extents.x), 0.7, accuracy: 0.005)
        XCTAssertEqual(Double(bounds.extents.y), 1.1, accuracy: 0.005)
        XCTAssertEqual(Double(bounds.extents.z), 0.3, accuracy: 0.005)
        XCTAssertEqual(Double(bounds.min.y), 0, accuracy: 0.005)
        XCTAssertEqual(Double(bounds.center.x), 0, accuracy: 0.005)
        XCTAssertEqual(Double(bounds.center.z), 0, accuracy: 0.005)
    }
    func testRealAssetUpgradePreservesInstanceIdentityPoseAndSelectionMarker() async throws {
        let asset = try asset()
        let model = try await RealityAssetLoader.load(asset, from: root.appendingPathComponent("assets/" + asset.value["path"].text), savedSize: [0.7, 0.3, 1.1])
        let instance = Entity(); instance.name = "i_chair"; instance.position = [2, 1.4, -3]
        instance.orientation = simd_quatf(angle: 0.7, axis: [0, 1, 0])
        let saved = instance.transform
        let fallback = ModelEntity(mesh: .generateBox(size: 1))
        let selection = Entity(); selection.name = "selected"; instance.addChild(fallback); instance.addChild(selection)
        RealityAssetLoader.install(model, in: instance, replacing: [fallback])
        XCTAssertEqual(instance.name, "i_chair"); XCTAssertEqual(instance.transform, saved)
        XCTAssertTrue(selection.parent === instance); XCTAssertTrue(model.parent === instance); XCTAssertNil(fallback.parent)
        XCTAssertEqual(instance.children.count, 2)
    }
    func testMissingTextureReturnsNeutralPanelFallback() async {
        let texture = await RealityAssetLoader.texture(from: root.appendingPathComponent("missing-texture.png"))
        XCTAssertNil(texture)
    }
    func testUnreadableRequestedModelReportsFailureForStandinFallback() async throws {
        let asset = try asset()
        do { _ = try await RealityAssetLoader.load(asset, from: root.appendingPathComponent("missing-model.usdz"), savedSize: [1, 1, 1]); XCTFail("Unreadable asset must not replace the fallback") }
        catch { XCTAssertFalse(error.localizedDescription.isEmpty) }
    }
}

private final class AssetHTTPState: @unchecked Sendable {
    private let lock = NSLock()
    private var bytes = Data()
    private var count = 0
    func reset(_ data: Data) { lock.lock(); defer { lock.unlock() }; bytes = data; count = 0 }
    func response() -> Data { lock.lock(); defer { lock.unlock() }; count += 1; return bytes }
    var requests: Int { lock.lock(); defer { lock.unlock() }; return count }
}
private final class AssetHTTPProtocol: URLProtocol, @unchecked Sendable {
    static let state = AssetHTTPState()
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.state.response())
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

extension RenderAssetTests {
    func testPanelTextureLoadsWithoutInventedCatalogIdentity() async throws {
        let pixels = Data((0..<16).flatMap { _ in [UInt8(200), 120, 60, 255] })
        let provider = try XCTUnwrap(CGDataProvider(data: pixels as CFData))
        let image = try XCTUnwrap(CGImage(width: 4, height: 4, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: 16, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue), provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent))
        let encoded = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(encoded, UTType.png.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, image, nil)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        let png = encoded as Data
        AssetHTTPProtocol.state.reset(png)
        let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [AssetHTTPProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        let folder = URL.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let cache = RenderAssetCache(directory: folder, session: session)
        let file = try await cache.texture(for: .object(["kind": .string("panel"), "texture_url": .string("https://assets.example/art.png")]), baseURL: URL(string: "https://backend.example/v1")!)
        let texture = await RealityAssetLoader.texture(from: file)
        XCTAssertNotNil(texture)
    }
    func testImmutableCacheCoalescesRealFixtureAndRejectsChangedBytes() async throws {
        let source = try asset()
        let bytes = try Data(contentsOf: root.appendingPathComponent("assets/" + source.value["path"].text))
        AssetHTTPProtocol.state.reset(bytes)
        var record = source.value.object; record["url"] = .string("https://assets.example/chair.usdz")
        let requested = try RenderAsset(.object(record))
        let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [AssetHTTPProtocol.self]
        let folder = URL.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        let cache = RenderAssetCache(directory: folder, session: session)
        async let first = cache.file(for: requested, baseURL: URL(string: "https://backend.example/v1")!)
        async let second = cache.file(for: requested, baseURL: URL(string: "https://backend.example/v1")!)
        let files = try await [first, second]
        XCTAssertEqual(files[0], files[1]); XCTAssertEqual(AssetHTTPProtocol.state.requests, 1)
        XCTAssertEqual(try Data(contentsOf: files[0]), bytes)
        let reloaded = RenderAssetCache(directory: folder, session: session)
        _ = try await reloaded.file(for: requested, baseURL: URL(string: "https://backend.example/v1")!)
        XCTAssertEqual(AssetHTTPProtocol.state.requests, 1)
        record["revision"] = .string("changed-revision")
        AssetHTTPProtocol.state.reset(Data(repeating: 0, count: bytes.count))
        do { _ = try await cache.file(for: RenderAsset(.object(record)), baseURL: URL(string: "https://backend.example/v1")!); XCTFail("Changed checksum must preserve fallback") }
        catch { XCTAssertFalse(error.localizedDescription.isEmpty) }
    }
}
