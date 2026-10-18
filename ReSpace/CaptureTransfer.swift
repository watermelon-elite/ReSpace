import Foundation
import CryptoKit
import ImageIO

/// Converts retained reconstruction evidence to the existing planning API contract.
/// The original full-resolution photos, half-depth and mesh stay in CaptureRepository.
enum CaptureTransfer {
    static func indices(count: Int) -> [Int] {
        guard count > 0 else { return [] }
        let selected = min(count, 40)
        if selected == 1 { return [0] }
        return (0..<selected).map { $0 * (count - 1) / (selected - 1) }
    }

    static func descriptor(id: String, captureID: String, frameID: String? = nil, kind: String, format: String, data: Data) -> JSONValue {
        .object(["artifact_id": .string(id), "capture_id": .string(captureID), "frame_id": frameID.map(JSONValue.string) ?? .null,
                 "kind": .string(kind), "format": .string(format), "byte_length": .number(Double(data.count)),
                 "checksum": .string(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined())])
    }

    static func frame(metadata: JSONValue, parts: [String: Data], captureID: String, index: Int) throws -> (JSONValue, [String: Data]) {
        let intrinsics = metadata["intrinsics"].numbers
        let transform = metadata["camera_to_scan_transform"].numbers
        guard (0..<40).contains(index), metadata["orientation"].text == "sensor", intrinsics.count == 4,
              intrinsics.allSatisfy(\.isFinite), intrinsics[0] > 0, intrinsics[1] > 0,
              transform.count == 16, transform.allSatisfy(\.isFinite),
              let jpeg = parts["jpeg"], let source = CGImageSourceCreateWithData(jpeg as CFData, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let originalWidth = properties[kCGImagePropertyPixelWidth] as? Int,
              let originalHeight = properties[kCGImagePropertyPixelHeight] as? Int,
              originalWidth == metadata["width"].int, originalHeight == metadata["height"].int,
              originalWidth > 0, originalHeight > 0,
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true,
                    kCGImageSourceThumbnailMaxPixelSize: min(1280, max(originalWidth, originalHeight)),
                    kCGImageSourceCreateThumbnailWithTransform: false] as CFDictionary) else {
            throw ContractError.invalid("The saved frame has invalid image calibration.")
        }
        let output = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(output, "public.jpeg" as CFString, 1, nil) else {
            throw ContractError.invalid("Could not prepare a planning photo.")
        }
        CGImageDestinationAddImage(destination, image, [kCGImageDestinationLossyCompressionQuality: 0.7] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw ContractError.invalid("Could not encode a planning photo.") }
        let id = metadata["id"].text
        let sx = Double(image.width) / Double(originalWidth), sy = Double(image.height) / Double(originalHeight)
        var converted = ["jpeg": output as Data]
        var meta: [String: JSONValue] = ["schema_version": .number(1), "operation_id": .string(id), "capture_id": .string(captureID),
            "frame_id": .string(id), "idx": .number(Double(index)), "w": .number(Double(image.width)), "h": .number(Double(image.height)),
            "timestamp": metadata["timestamp"], "timestamp_source": .string("ar_session_seconds"), "orientation": .string("sensor_landscape"),
            "transform": metadata["camera_to_scan_transform"], "intrinsics": .object(["fx": .number(intrinsics[0] * sx), "fy": .number(intrinsics[1] * sy),
                "cx": .number(intrinsics[2] * sx), "cy": .number(intrinsics[3] * sy)])]
        if let depth = parts["depth"] {
            let w = metadata["depth_width"].int, h = metadata["depth_height"].int
            guard (1...4096).contains(w), (1...4096).contains(h), metadata["depth_format"].text == "float16_le_meters", depth.count == w * h * 2 else {
                throw ContractError.invalid("The saved depth dimensions or format are invalid.")
            }
            var fullDepth = Data(capacity: w * h * 4)
            for offset in stride(from: 0, to: depth.count, by: 2) {
                let bits = UInt16(depth[offset]) | UInt16(depth[offset + 1]) << 8
                var value = Float(Float16(bitPattern: bits)).bitPattern.littleEndian
                withUnsafeBytes(of: &value) { fullDepth.append(contentsOf: $0) }
            }
            converted["depth"] = fullDepth
            meta["depth_w"] = .number(Double(w)); meta["depth_h"] = .number(Double(h)); meta["depth_format"] = .string("float32_le_m")
            if let confidence = parts["confidence"] {
                guard metadata["confidence_width"].int == w, metadata["confidence_height"].int == h,
                      metadata["confidence_format"].text == "uint8_arkit", confidence.count == w * h, confidence.allSatisfy({ $0 <= 2 }) else {
                    throw ContractError.invalid("The saved confidence map does not match its depth.")
                }
                converted["confidence"] = confidence; meta["confidence_format"] = .string("uint8")
            }
        } else if parts["confidence"] != nil { throw ContractError.invalid("A confidence map requires its original depth.") }
        meta["artifacts"] = .array(converted.keys.sorted().map { kind in
            var record = descriptor(id: "\(id)_\(kind)", captureID: captureID, frameID: id, kind: kind,
                format: kind == "jpeg" ? "image/jpeg" : kind == "depth" ? "float32_le_m" : "uint8", data: converted[kind]!).object
            record["w"] = meta[kind == "jpeg" ? "w" : "depth_w"]; record["h"] = meta[kind == "jpeg" ? "h" : "depth_h"]
            record["orientation"] = .string("sensor_landscape")
            return .object(record)
        })
        return (.object(meta), converted)
    }
}
