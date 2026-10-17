import Foundation
import Security

struct AppConfiguration {
    let serviceURL: URL?
    let appKey: String
    let storageURL: URL

    static func load() throws -> AppConfiguration {
        let rawURL = Bundle.main.object(forInfoDictionaryKey: "ReSpaceServiceURL") as? String ?? ""
        let key = Bundle.main.object(forInfoDictionaryKey: "ReSpaceAppKey") as? String ?? ""
        let support = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                                 appropriateFor: nil, create: true)
        let storage = support.appendingPathComponent("ReSpace", isDirectory: true)
        try FileManager.default.createDirectory(at: storage, withIntermediateDirectories: true)
        var resource = storage
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try resource.setResourceValues(values)
        return AppConfiguration(serviceURL: URL(string: rawURL), appKey: key, storageURL: storage)
    }
}

enum DeviceIdentity {
    static func load() throws -> String {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                    kSecAttrService as String: "com.Somei.ReSpace.device",
                                    kSecAttrAccount as String: "device-id"]
        var read = query
        read[kSecReturnData as String] = true
        read[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(read as CFDictionary, &result)
        if status == errSecSuccess, let data = result as? Data, let id = String(data: data, encoding: .utf8) { return id }
        guard status == errSecItemNotFound else { throw ClientError.storage("Device identity could not be read (\(status)).") }
        let id = UUID().uuidString
        var write = query
        write[kSecValueData as String] = Data(id.utf8)
        write[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let writeStatus = SecItemAdd(write as CFDictionary, nil)
        guard writeStatus == errSecSuccess else { throw ClientError.storage("Device identity could not be saved (\(writeStatus)).") }
        return id
    }
}
