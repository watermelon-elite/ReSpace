import Foundation

enum ClientError: Error, LocalizedError, Sendable {
    case unconfigured, invalidResponse, invalidGeometry, unsupportedSchema, storage(String)
    case http(Int)
    var errorDescription: String? {
        switch self {
        case .unconfigured: "The room service is not configured. Add its HTTPS address and app key in the app configuration."
        case .invalidResponse: "The room service returned an unreadable response. Your saved room has been preserved."
        case .invalidGeometry: "The room service returned incomplete geometry. Refresh the room or rescan."
        case .unsupportedSchema: "This room service uses an unsupported contract version."
        case .storage(let reason): "Couldn’t retain your data: \(reason)"
        case .http(let code): "The room service is unavailable (\(code)). Try again."
        }
    }
}

enum Wire {
    static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }
    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }
}

struct APIRequest: Codable, Sendable, Equatable {
    var method: String
    var path: String
    var body: Data?
    var identity: String?
    var contentType: String = "application/json"

    static func json<T: Encodable>(method: String = "POST", path: String,
                                   identity: String, body: T) throws -> APIRequest {
        APIRequest(method: method, path: path, body: try Wire.encoder().encode(body), identity: identity)
    }
}

protocol HTTPTransport: Sendable {
    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse)
}
struct SessionTransport: HTTPTransport {
    let session: URLSession
    init() {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 60
        configuration.timeoutIntervalForResource = 90
        session = URLSession(configuration: configuration)
    }
    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw ClientError.invalidResponse }
        return (data, response)
    }
}

actor ScanAPIClient {
    private let baseURL: URL?
    private let appKey: String
    private let deviceId: String
    private let transport: any HTTPTransport

    init(baseURL: URL?, appKey: String, deviceId: String, transport: any HTTPTransport = SessionTransport()) {
        self.baseURL = baseURL
        self.appKey = appKey
        self.deviceId = deviceId
        self.transport = transport
    }

    func execute<T: Decodable & Sendable>(_ request: APIRequest, as: T.Type = T.self) async throws -> T {
        guard let baseURL, baseURL.scheme == "https", !appKey.isEmpty else { throw ClientError.unconfigured }
        guard let url = URL(string: request.path, relativeTo: baseURL.appendingPathComponent("v1/")) else {
            throw ClientError.invalidResponse
        }
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = request.method
        urlRequest.httpBody = request.body
        urlRequest.setValue(request.contentType, forHTTPHeaderField: "Content-Type")
        urlRequest.setValue("application/json", forHTTPHeaderField: "Accept")
        urlRequest.setValue(deviceId, forHTTPHeaderField: "X-Device-Id")
        urlRequest.setValue(appKey, forHTTPHeaderField: "X-App-Key")
        if let identity = request.identity { urlRequest.setValue(identity, forHTTPHeaderField: "Idempotency-Key") }
        let (data, response) = try await transport.data(for: urlRequest)
        guard (200..<300).contains(response.statusCode) else {
            if let error = try? Wire.decoder().decode(APIErrorEnvelope.self, from: data) { throw error }
            if response.statusCode == 501 {
                throw APIErrorEnvelope(code: "unavailable_capability", message: "This capability is not available from the room service yet.", retryable: false)
            }
            throw ClientError.http(response.statusCode)
        }
        do { return try Wire.decoder().decode(T.self, from: data) }
        catch { throw ClientError.invalidResponse }
    }

    func get<T: Decodable & Sendable>(_ path: String, as: T.Type = T.self) async throws -> T {
        try await execute(APIRequest(method: "GET", path: path), as: T.self)
    }

    func room(_ id: String) async throws -> ScanRoomRecord {
        let record: ScanRoomRecord = try await get("rooms/\(Self.segment(id))")
        guard record.schemaVersion == 1 else { throw ClientError.unsupportedSchema }
        if let snapshot = record.snapshot { try snapshot.validateGeometry() }
        return record
    }
    func design(_ id: String) async throws -> DesignVersion {
        let design: DesignVersion = try await get("designs/\(Self.segment(id))")
        guard design.schemaVersion == 1 else { throw ClientError.unsupportedSchema }
        try design.validateGeometry()
        return design
    }
    func snapshot(roomId: String, id: String) async throws -> RoomSnapshot {
        let snapshot: RoomSnapshot = try await get("rooms/\(Self.segment(roomId))/snapshots/\(Self.segment(id))")
        try snapshot.validateGeometry()
        return snapshot
    }
    func lookup(_ id: String) async throws -> RoomOperation? {
        do {
            let operation: RoomOperation = try await get("operations/\(Self.segment(id))")
            guard operation.schemaVersion == 1 else { throw ClientError.unsupportedSchema }
            guard operation.id == id else { throw ClientError.invalidResponse }
            return operation
        } catch let error as APIErrorEnvelope where error.code == "unknown_operation" {
            return nil
        }
    }
    nonisolated static func segment(_ id: String) -> String {
        id.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ""
    }
}
