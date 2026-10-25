import Foundation

struct NativeReconstructionFile: Codable, Sendable {
    var id: String
    var type = "native_source"
    var filename: String
    var relativePath: String
    var byteLength: Int
    var sha256: String
}
struct NativeReconstructionUpload: Codable, Sendable {
    var schemaVersion = 2
    var captureId: String
    var state: String
    var format = "house-capture/5"
    var files: [NativeReconstructionFile]
}
