import Foundation

enum SourceCaptureStorage {
    struct RawRoomArchive {
        var filename: String?
        var warning: String?
    }

    static func archiveRawRoom<T: Encodable>(_ value: T, to url: URL) throws -> RawRoomArchive {
        let data: Data
        do { data = try JSONEncoder().encode(value) }
        catch EncodingError.invalidValue(_, let context) {
            // RoomPlan can refuse to serialize its opaque recovery data even though
            // RoomBuilder can still process the original in-memory capture.
            return RawRoomArchive(warning: "RoomPlan raw recovery data unavailable: \(context.debugDescription)")
        }
        // Keep disk errors fatal. Only the optional framework encoding can be absent.
        try saving(url) { try data.write(to: url, options: .atomic) }
        return RawRoomArchive(filename: url.lastPathComponent)
    }

    static func writeJSON<T: Encodable>(_ value: T, to url: URL, prettyPrinted: Bool = false) throws {
        try saving(url) {
            let encoder = JSONEncoder()
            if prettyPrinted { encoder.outputFormatting = [.prettyPrinted] }
            try encoder.encode(value).write(to: url, options: .atomic)
        }
    }

    static func saving<T>(_ url: URL, operation: () throws -> T) throws -> T {
        do { return try operation() }
        catch { throw failure(error, at: url) }
    }

    static func failure(_ error: Error, at url: URL) -> ClientError {
        let file = url.deletingLastPathComponent().lastPathComponent + "/" + url.lastPathComponent
        if case EncodingError.invalidValue(_, let context) = error {
            if context.codingPath.isEmpty {
                return .storage("Could not save \(file): \(context.debugDescription)")
            }
            let field = context.codingPath.reduce("") { path, key in
                if let index = key.intValue { return path + "[\(index)]" }
                return path.isEmpty ? key.stringValue : path + "." + key.stringValue
            }
            return .storage("Could not save \(file): invalid capture value at \(field.isEmpty ? "root" : field).")
        }
        return .storage("Could not save \(file): \(error.localizedDescription)")
    }
}
