import Foundation

/// Structured server error details may contain candidates, geometry, or revision records.
indirect enum ScanJSONValue: Codable, Sendable, Equatable {
    case string(String), number(Double), bool(Bool), array([ScanJSONValue]), object([String: ScanJSONValue]), null
    init(from decoder: any Decoder) throws {
        let value = try decoder.singleValueContainer()
        if value.decodeNil() { self = .null }
        else if let boolean = try? value.decode(Bool.self) { self = .bool(boolean) }
        else if let number = try? value.decode(Double.self) { self = .number(number) }
        else if let string = try? value.decode(String.self) { self = .string(string) }
        else if let array = try? value.decode([ScanJSONValue].self) { self = .array(array) }
        else { self = .object(try value.decode([String: ScanJSONValue].self)) }
    }
    func encode(to encoder: any Encoder) throws {
        var value = encoder.singleValueContainer()
        switch self {
        case .string(let string): try value.encode(string)
        case .number(let number): try value.encode(number)
        case .bool(let bool): try value.encode(bool)
        case .array(let array): try value.encode(array)
        case .object(let object): try value.encode(object)
        case .null: try value.encodeNil()
        }
    }
}
