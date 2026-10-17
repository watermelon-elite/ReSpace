import Foundation

struct MultipartBody: Sendable {
    let boundary: String
    private(set) var data = Data()
    var contentType: String { "multipart/form-data; boundary=\(boundary)" }

    init(boundary: String = "ReSpace-\(UUID().uuidString)") { self.boundary = boundary }

    mutating func append(name: String, filename: String? = nil, type: String, bytes: Data) {
        data.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"".utf8))
        if let filename { data.append(Data("; filename=\"\(filename)\"".utf8)) }
        data.append(Data("\r\nContent-Type: \(type)\r\n\r\n".utf8))
        data.append(bytes)
        data.append(Data("\r\n".utf8))
    }
    mutating func finish() { data.append(Data("--\(boundary)--\r\n".utf8)) }
}
