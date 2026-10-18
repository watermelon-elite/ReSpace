import Foundation
import CryptoKit

actor RenderAssetCache {
    static let shared = RenderAssetCache()
    private let directory: URL
    private let session: URLSession
    private var downloads: [String: Task<URL, Error>] = [:]
    init(directory: URL = URL.cachesDirectory.appendingPathComponent("ReSpaceAssets"), session: URLSession = .shared) { self.directory = directory; self.session = session }
    func file(for asset: RenderAsset, baseURL: URL) async throws -> URL {
        let path = asset.value["asset_url"].string ?? asset.value["url"].text
        guard let url = URL(string: path, relativeTo: baseURL.appendingPathComponent("", isDirectory: true))?.absoluteURL, url.scheme == "https", url.host != nil, !path.isEmpty else { throw ContractError.invalid("Render asset URL is unavailable.") }
        let identity = asset.id + "/" + asset.revision
        let key = SHA256.hash(data: Data(identity.utf8)).map { String(format: "%02x", $0) }.joined()
        let file = directory.appendingPathComponent(key).appendingPathExtension("usdz")
        if FileManager.default.fileExists(atPath: file.path) {
            try validate(Data(contentsOf: file), asset: asset)
            return file
        }
        if let download = downloads[key] { let file = try await download.value; try validate(Data(contentsOf: file), asset: asset); return file }
        let download = Task { try await fetch(url, to: file, asset: asset) }
        downloads[key] = download
        defer { downloads.removeValue(forKey: key) }
        return try await download.value
    }
    func texture(for descriptor: JSONValue, baseURL: URL) async throws -> URL {
        let path = descriptor["texture_url"].text
        guard !path.isEmpty, let url = URL(string: path, relativeTo: baseURL.appendingPathComponent("", isDirectory: true))?.absoluteURL, url.scheme == "https", url.host != nil else { throw ContractError.invalid("Panel texture URL is unavailable.") }
        let identity = descriptor["asset_id"].text + "/" + descriptor["asset_revision"].text + "/" + url.absoluteString
        let key = SHA256.hash(data: Data(identity.utf8)).map { String(format: "%02x", $0) }.joined()
        let file = directory.appendingPathComponent(key).appendingPathExtension("png")
        if FileManager.default.fileExists(atPath: file.path) { return file }
        let (data, response) = try await session.data(for: URLRequest(url: url, timeoutInterval: 30))
        guard let response = response as? HTTPURLResponse, response.statusCode == 200, !data.isEmpty, data.count <= 16_000_000 else { throw ContractError.invalid("Panel texture download failed.") }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try data.write(to: file, options: .atomic)
        return file
    }
    private func fetch(_ url: URL, to file: URL, asset: RenderAsset) async throws -> URL {
        let (data, response) = try await session.data(for: URLRequest(url: url, timeoutInterval: 30))
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { throw ContractError.invalid("Render asset download failed.") }
        try validate(data, asset: asset)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try data.write(to: file, options: .atomic)
        return file
    }
    private func validate(_ data: Data, asset: RenderAsset) throws {
        guard !data.isEmpty, data.count <= 16_000_000 else { throw ContractError.invalid("Render asset is empty or exceeds the download limit.") }
        if let count = asset.value["byte_count"].number, count != Double(data.count) { throw ContractError.invalid("Immutable asset byte count changed.") }
        if let checksum = asset.value["sha256"].string, SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined() != checksum { throw ContractError.invalid("Immutable asset checksum changed.") }
    }
}
