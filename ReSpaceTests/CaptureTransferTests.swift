import XCTest
import ImageIO
@testable import ReSpaceContracts

final class CaptureTransferTests: XCTestCase {
    private func fixture() throws -> (JSONValue, [String: Data]) {
        let context = try XCTUnwrap(CGContext(data: nil, width: 2560, height: 1440, bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        let image = try XCTUnwrap(context.makeImage())
        let bytes = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(bytes, "public.jpeg" as CFString, 1, nil))
        CGImageDestinationAddImage(destination, image, nil)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        let meta: JSONValue = .object(["id": .string("frame-test"), "orientation": .string("sensor"), "timestamp": .number(12),
            "width": .number(2560), "height": .number(1440), "intrinsics": .array([2000, 2000, 1280, 720].map(JSONValue.number)),
            "camera_to_scan_transform": .array([1,0,0,0,0,1,0,0,0,0,1,0,0,1.5,0,1].map(JSONValue.number)),
            "depth_width": .number(2), "depth_height": .number(2), "depth_format": .string("float16_le_meters"),
            "confidence_width": .number(2), "confidence_height": .number(2), "confidence_format": .string("uint8_arkit")])
        var depth = Data()
        for value: Float16 in [1, 2, 0.5, 4] {
            var bits = value.bitPattern.littleEndian
            withUnsafeBytes(of: &bits) { depth.append(contentsOf: $0) }
        }
        return (meta, ["jpeg": bytes as Data, "depth": depth, "confidence": Data([2, 1, 0, 2])])
    }

    func testConversionPreservesCalibrationPoseDepthAndOriginalEvidence() throws {
        let (input, parts) = try fixture()
        let (meta, converted) = try CaptureTransfer.frame(metadata: input, parts: parts, captureID: "capture-test", index: 0)
        XCTAssertEqual(meta["w"].int, 1280); XCTAssertEqual(meta["h"].int, 720)
        XCTAssertEqual(meta["intrinsics"]["fx"].number, 1000)
        XCTAssertEqual(meta["intrinsics"]["cy"].number, 360)
        XCTAssertEqual(meta["transform"], input["camera_to_scan_transform"])
        XCTAssertEqual(meta["orientation"].text, "sensor_landscape")
        let depth = try XCTUnwrap(converted["depth"])
        let values = stride(from: 0, to: depth.count, by: 4).map { offset -> Float in
            let bits = (0..<4).reduce(UInt32(0)) { $0 | UInt32(depth[offset + $1]) << ($1 * 8) }
            return Float(bitPattern: bits)
        }
        XCTAssertEqual(values, [1, 2, 0.5, 4])
        XCTAssertEqual(parts["depth"]?.count, 8)
        XCTAssertEqual(converted["confidence"], parts["confidence"])
        XCTAssertEqual(meta["artifacts"].array.count, 3)
        // Export actual Swift conversion output for the cross-language API smoke check.
        if let path = ProcessInfo.processInfo.environment["RESPACE_CAPTURE_TRANSFER_FIXTURE"] {
            let folder = URL(fileURLWithPath: path)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            try meta.data().write(to: folder.appendingPathComponent("meta.json"))
            for (kind, data) in converted { try data.write(to: folder.appendingPathComponent(kind)) }
        }
    }

    func testSampleSpansEntireCaptureAndRespectsBackendCap() {
        XCTAssertEqual(CaptureTransfer.indices(count: 0), [])
        XCTAssertEqual(CaptureTransfer.indices(count: 1), [0])
        let indices = CaptureTransfer.indices(count: 240)
        XCTAssertEqual(indices.count, 40); XCTAssertEqual(Set(indices).count, 40)
        XCTAssertEqual(indices.first, 0); XCTAssertEqual(indices.last, 239)
        XCTAssertEqual(CaptureTransfer.indices(count: 3), [0, 1, 2])
    }

    func testCorruptDepthAndUncalibratedEvidenceAreRejected() throws {
        var (meta, parts) = try fixture()
        parts["depth"] = Data([0])
        XCTAssertThrowsError(try CaptureTransfer.frame(metadata: meta, parts: parts, captureID: "capture-test", index: 0))
        parts.removeValue(forKey: "depth"); parts.removeValue(forKey: "confidence")
        meta = .object(meta.object.merging(["orientation": .string("portrait")]) { _, new in new })
        XCTAssertThrowsError(try CaptureTransfer.frame(metadata: meta, parts: parts, captureID: "capture-test", index: 0))
    }
}
