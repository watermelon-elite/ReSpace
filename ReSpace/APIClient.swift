import Foundation
import Security
import Observation

struct APIError: LocalizedError {
    let code: String
    let message: String
    let retryable: Bool
    var errorDescription: String? { message }
}

struct APIClient {
    let baseURL: URL
    let deviceID: String
    func request(_ path: String, method: String = "GET", body: JSONValue? = nil, data: Data? = nil, contentType: String? = nil) async throws -> JSONValue {
        guard var components = URLComponents(url: URL(string: path, relativeTo: baseURL.appendingPathComponent("", isDirectory: true))!.absoluteURL, resolvingAgainstBaseURL: false) else { throw ContractError.invalid("Invalid backend path.") }
        if method == "DELETE", let id = body?["operation_id"].string { components.queryItems = (components.queryItems ?? []) + [URLQueryItem(name: "operation_id", value: id)] }
        guard let url = components.url else { throw ContractError.invalid("Invalid backend URL.") }
        guard url.scheme == "https" else { throw ContractError.invalid("Configure an HTTPS backend URL.") }
        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = method
        request.setValue(deviceID, forHTTPHeaderField: "X-Device-Id")
        request.setValue(contentType ?? "application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try body?.data() ?? data
        let (responseData, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw ContractError.invalid("No HTTP response.") }
        let document = try JSONDecoder().decode(JSONValue.self, from: responseData)
        guard (200...299).contains(http.statusCode) else {
            let error = document["error"] == .null ? document : document["error"]
            throw APIError(code: error["code"].text, message: error["message"].string ?? "Request failed (\(http.statusCode)).", retryable: error["retryable"].bool ?? false)
        }
        guard document["schema_version"].int == 1 else { throw ContractError.invalid("Unsupported server schema.") }
        return document
    }
}

@MainActor @Observable final class AppModel {
    var backend = UserDefaults.standard.string(forKey: "backendURL") ?? ""
    var rooms: [JSONValue] = []
    var error: String?
    var busy = false
    private var recoveryBlocked = false
    var pending: [PendingRequest] = []
    private(set) var deviceID = ""
    private(set) var disk = FileManager.default.temporaryDirectory
    init() {
        do {
            deviceID = try Self.installationID()
            disk = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("ReSpace", isDirectory: true)
            try FileManager.default.createDirectory(at: disk, withIntermediateDirectories: true)
            let queue = disk.appendingPathComponent("requests.json")
            if FileManager.default.fileExists(atPath: queue.path) { pending = try JSONDecoder().decode([PendingRequest].self, from: Data(contentsOf: queue)) }
        } catch { recoveryBlocked = true; self.error = "Local request recovery is unavailable: \(error.localizedDescription)" }
    }
    var client: APIClient? {
        guard !recoveryBlocked, !deviceID.isEmpty, let url = URL(string: backend), url.scheme == "https", url.host != nil else { return nil }
        return APIClient(baseURL: url.appendingPathComponent("v1"), deviceID: deviceID)
    }
    func saveBackend() { UserDefaults.standard.set(backend, forKey: "backendURL") }
    func refresh() async {
        guard let client else { return }
        do {
            var path = "rooms"; var values: [JSONValue] = []
            repeat {
                let result = try await client.request(path)
                values += result["rooms"].array
                if let cursor = result["next_cursor"].string, !cursor.isEmpty { path = "rooms?cursor=\(cursor.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? cursor)" } else { break }
            } while true
            for value in values { _ = try RoomRecord(value) }
            rooms = values; error = nil
        } catch { self.error = error.localizedDescription }
    }
    func recoverPending() async {
        for request in pending { do { _ = try await reconcile(request) } catch { self.error = "Request remains unconfirmed: \(error.localizedDescription)" } }
    }
    func persistPending() throws {
        try JSONEncoder().encode(pending).write(to: disk.appendingPathComponent("requests.json"), options: [.atomic, .completeFileProtectionUnlessOpen])
    }
    func submit(_ request: PendingRequest) async throws -> JSONValue {
        guard let client else { throw ContractError.invalid("Configure the backend before continuing.") }
        if let existing = pending.first(where: { $0.operationID == request.operationID }), existing.path != request.path || existing.body != request.body { throw ContractError.invalid("This Room has an unresolved request. Reconcile its original payload before sending another action.") }
        if !pending.contains(where: { $0.operationID == request.operationID }) { pending.append(request); try persistPending() }
        do {
            let result = try await client.request(request.path, method: request.method, body: request.body)
            if result["deletion"]["state"].text != "pending" { pending.removeAll { $0.operationID == request.operationID }; try persistPending() }
            return result
        } catch let error as APIError {
            if !error.retryable { pending.removeAll { $0.operationID == request.operationID }; try persistPending() }
            throw error
        }
    }
    func reconcile(_ request: PendingRequest) async throws -> JSONValue {
        guard let client else { throw ContractError.invalid("Backend unavailable.") }
        do {
            let result = try await client.request("operations/\(request.operationID)")
            let operation = result["operation"]
            if request.path.hasSuffix("/answers"), !operation["answer_history"].array.contains(where: { $0["reply_id"] == request.body["reply_id"] }) { return try await submit(request) }
            if request.path.hasSuffix("/cancel"), operation["state"].text != "cancelled" { return try await submit(request) }
            if request.path.hasSuffix("/dismiss-clarification"), operation["pending_question"] != .null { return try await submit(request) }
            pending.removeAll { $0.operationID == request.operationID }; try persistPending(); return result
        } catch let error as APIError where error.code == "unknown_operation" { return try await submit(request) }
    }
    static func installationID() throws -> String {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "com.Somei.ReSpace.installation", kSecAttrAccount as String: "device"]
        var lookup = query; lookup[kSecReturnData as String] = true
        var result: CFTypeRef?
        let status = SecItemCopyMatching(lookup as CFDictionary, &result)
        if status == errSecSuccess, let data = result as? Data, let value = String(data: data, encoding: .utf8) { return value }
        guard status == errSecItemNotFound else { throw ContractError.invalid("Keychain installation identity is unavailable (\(status)).") }
        let id = UUID().uuidString
        var item = query; item[kSecValueData as String] = Data(id.utf8); item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else { throw ContractError.invalid("Could not persist installation identity.") }
        return id
    }
}

extension APIClient {
    func media(_ path: String) async throws -> Data {
        guard let url = URL(string: path, relativeTo: baseURL.appendingPathComponent("", isDirectory: true))?.absoluteURL, url.scheme == "https", url.host == baseURL.host else { throw ContractError.invalid("Private media must use this backend.") }
        var request = URLRequest(url: url, timeoutInterval: 30); request.setValue(deviceID, forHTTPHeaderField: "X-Device-Id")
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { throw ContractError.invalid("Private capture image is unavailable.") }
        return data
    }
}
