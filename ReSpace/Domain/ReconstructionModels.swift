import Foundation

enum ReconstructionServiceError: Error, LocalizedError, Sendable {
    case http(Int, String?)

    var errorDescription: String? {
        switch self {
        case .http(401, _), .http(403, _):
            return "The reconstruction service rejected the token. Check the app’s reconstruction token against the Mac service."
        case .http(404, _):
            return "The reconstruction job or file was not found. Send the saved scan again."
        case .http(422, let detail):
            return "The reconstruction service rejected the scan (422)." + (detail.map { " \($0)" } ?? "")
        case .http(let status, let detail):
            return "The reconstruction service returned \(status)." + (detail.map { " \($0)" } ?? " Try again when the Mac service is available.")
        }
    }
}

struct ReconstructionAsset: Codable, Sendable {
    var filename: String
    var byteLength: Int
    var sha256: String

    func validate() throws {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_.-"))
        guard !filename.isEmpty, filename.count <= 128, !filename.contains(".."),
              filename.unicodeScalars.allSatisfy({ allowed.contains($0) }),
              byteLength > 0, byteLength <= 128 * 1024 * 1024,
              sha256.count == 64, sha256.allSatisfy({ $0.isHexDigit && !$0.isUppercase }) else {
            throw ClientError.invalidResponse
        }
    }
}

struct ReconstructionResult: Codable, Sendable {
    var revision: Int
    var status: String
    var modelFilename: String
    var assets: [ReconstructionAsset]
    var needsReview: Bool
    var error: String?
    var coordinateSystem: String
    var qualityFilename: String
    var generationModel: String? = nil
    var generatedTriangleCount: Int? = nil
    var sceneFilename: String? = nil
    var sceneSchemaVersion: Int? = nil

    var isAIGenerated: Bool { ["gpt-6-astra", "gpt-6-sol"].contains(generationModel ?? "") }
    var isWalkthrough: Bool { status == "succeeded" && sceneSchemaVersion == 2 && sceneFilename != nil }

    func validate() throws {
        guard revision > 0, coordinateSystem == "arkit_scan_meters_y_up",
              generatedTriangleCount.map({ (0...200000).contains($0) }) ?? true,
              ["succeeded", "partially_processed"].contains(status),
              (1...512).contains(assets.count), Set(assets.map(\.filename)).count == assets.count,
              assets.contains(where: { $0.filename == modelFilename }), modelFilename.hasSuffix(".obj"),
              assets.contains(where: { $0.filename == qualityFilename }),
              assets.reduce(0, { $0 + $1.byteLength }) <= 512 * 1024 * 1024 else { throw ClientError.invalidResponse }
        try assets.forEach { try $0.validate() }
        if sceneFilename != nil || sceneSchemaVersion != nil {
            guard isWalkthrough, let name=sceneFilename, WalkthroughBundle.safeName(name), name.hasSuffix(".json"),
                  let scene=assets.first(where: { $0.filename==name }), scene.byteLength<=8*1024*1024 else { throw ClientError.invalidResponse }
        }
    }
}

struct ReconstructionJob: Codable, Sendable {
    var schemaVersion: Int
    var id: String
    var state: String
    var revision: Int
    var stage: String
    var error: String?
    var result: ReconstructionResult?
    var missingArtifactIds: [String]
    var generationId: String? = nil

    var isRunning: Bool { ["queued", "running"].contains(state) }
    var canRetry: Bool {
        ["failed", "partially_processed"].contains(state) || (state == "succeeded" && result?.isAIGenerated != true && result?.isWalkthrough != true)
    }
    var hasFinalWalkthrough: Bool { state == "succeeded" && result?.isWalkthrough == true && result?.revision == revision }

    var stageDescription: String {
        switch stage {
        case "astra_selecting_evidence": return "Selecting scan photos…"
        case "astra_generating_scene": return "AI is generating your room…"
        case "astra_inventory": return "Identifying room contents…"
        case "astra_baking_photos": return "Applying captured photo textures…"
        case "astra_validating_geometry": return "Building and checking the AI model…"
        default:
            if stage.hasPrefix("astra_batch:") {
                return "Building objects · " + stage.replacingOccurrences(of:"astra_batch:",with:"")
            }
            if stage.hasPrefix("astra_detail:") {
                return "Adding object detail · " + stage.replacingOccurrences(of:"astra_detail:",with:"")
            }
            return stage.replacingOccurrences(of: "_", with: " ")
        }
    }

    func validate(captureId: String) throws {
        guard schemaVersion == 1, id == captureId,
              ["uploading", "queued", "running", "failed", "partially_processed", "succeeded"].contains(state) else {
            throw ClientError.invalidResponse
        }
        if let result { try result.validate() }
    }
}

struct ReconstructionReceipt: Codable, Sendable {
    var origin: String
    var job: ReconstructionJob?
    var downloadedRevision: Int?
    var pendingRestartId: String? = nil
}
