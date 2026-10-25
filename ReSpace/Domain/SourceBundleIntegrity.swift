import Foundation
import CryptoKit

/// An integrity record around the native export; it changes no camera/image data.
struct SourceBundleIntegrity: Codable, Sendable {
    struct Entry: Codable, Sendable, Equatable {
        var path: String
        var byteLength: Int
        var sha256: String
    }
    var format = "respace-source-integrity/1"
    var files: [Entry]

    static func create(at root: URL) throws -> Self {
        let root = root.standardizedFileURL.resolvingSymlinksInPath()
        guard let enumerator = FileManager.default.enumerator(at: root,
            includingPropertiesForKeys: [.isRegularFileKey,.isSymbolicLinkKey]) else {
            throw ClientError.storage("The source capture cannot be read.")
        }
        var entries: [Entry] = []
        for case let url as URL in enumerator {
            let values = try url.resourceValues(forKeys: [.isRegularFileKey,.isSymbolicLinkKey])
            guard values.isSymbolicLink != true else { throw ClientError.storage("A source capture contains a symbolic link.") }
            guard values.isRegularFile == true,
                  url.standardizedFileURL != root.appendingPathComponent("integrity.json").standardizedFileURL else { continue }
            let resolved = url.standardizedFileURL.resolvingSymlinksInPath()
            guard resolved.path.hasPrefix(root.path+"/") else { throw ClientError.storage("Source file is outside its capture.") }
            let path = String(resolved.path.dropFirst(root.path.count+1))
            let handle = try FileHandle(forReadingFrom: url)
            defer { try? handle.close() }
            var hash = SHA256(), count = 0
            while let data = try handle.read(upToCount: 1024*1024), !data.isEmpty {
                count += data.count; hash.update(data: data)
            }
            entries.append(Entry(path: path, byteLength: count,
                sha256: hash.finalize().map { String(format:"%02x",$0) }.joined()))
        }
        return Self(files: entries.sorted { $0.path < $1.path })
    }
    func verify(at root: URL) throws {
        guard format == "respace-source-integrity/1", !files.isEmpty,
              Set(files.map(\.path)).count == files.count else { throw ClientError.storage("The source integrity record is invalid.") }
        let actual = try Self.create(at: root)
        guard actual.files == files else { throw ClientError.storage("Source scan files are missing or changed. Keep the original capture for recovery.") }
    }
}
