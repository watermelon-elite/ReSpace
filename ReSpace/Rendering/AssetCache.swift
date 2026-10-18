import CryptoKit
import Foundation

actor AssetCache {
    static let shared = AssetCache()
    private var downloads: [String: Task<URL, Error>] = [:]

    func file(for asset: ScanRenderAsset) async throws -> URL {
        guard asset.url.scheme == "https", asset.units == "meters", asset.pivot == "bottom_center", asset.forward == "+z" else {
            throw ClientError.invalidGeometry
        }
        let key = "\(asset.id):\(asset.revision)"
        if let task = downloads[key] { return try await task.value }
        let task = Task<URL, Error> {
            let hash = SHA256.hash(data: Data(key.utf8)).map { String(format: "%02x", $0) }.joined()
            let directory = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("ReSpaceAssets")
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let file = directory.appendingPathComponent(hash).appendingPathExtension("usdz")
            if FileManager.default.fileExists(atPath: file.path) { return file }
            let (temporary, response) = try await URLSession.shared.download(from: asset.url)
            guard let response = response as? HTTPURLResponse, (200..<300).contains(response.statusCode),
                  response.expectedContentLength <= 100_000_000 else { throw ClientError.invalidResponse }
            try FileManager.default.moveItem(at: temporary, to: file)
            return file
        }
        downloads[key] = task
        do { return try await task.value }
        catch { downloads[key] = nil; throw error }
    }
}
