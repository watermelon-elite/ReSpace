import Foundation

extension FrameUploadResult {
    func validateStorage(for frame: CaptureFrame) throws {
        guard schemaVersion == 1 else { throw ClientError.unsupportedSchema }
        guard frame.artifacts.allSatisfy({ artifact in
            acknowledgments.contains { receipt in
                receipt.artifactId == artifact.id && receipt.durable &&
                receipt.byteLength == artifact.byteLength && receipt.sha256 == artifact.sha256
            }
        }) else {
            throw APIErrorEnvelope(code: "incomplete_storage_ack", message: "The room service has not confirmed storage of every scan artifact.", retryable: true)
        }
    }
}
