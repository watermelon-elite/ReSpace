import Foundation

public enum JSONValue: Codable, Equatable, Hashable, Sendable {
    public func hash(into hasher: inout Hasher) {
        switch self {
        case .object(let values): hasher.combine(0); for key in values.keys.sorted() { hasher.combine(key); hasher.combine(values[key]) }
        case .array(let values): hasher.combine(1); hasher.combine(values)
        case .string(let value): hasher.combine(2); hasher.combine(value)
        case .number(let value): hasher.combine(3); hasher.combine(value)
        case .bool(let value): hasher.combine(4); hasher.combine(value)
        case .null: hasher.combine(5)
        }
    }
    case object([String: JSONValue]), array([JSONValue]), string(String), number(Double), bool(Bool), null
    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode([JSONValue].self) { self = .array(v) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .object(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }
    public subscript(_ key: String) -> JSONValue { if case .object(let v) = self { return v[key] ?? .null }; return .null }
    public var string: String? { if case .string(let v) = self { return v }; return nil }
    public var number: Double? { if case .number(let v) = self { return v }; return nil }
    public var bool: Bool? { if case .bool(let v) = self { return v }; return nil }
    public var array: [JSONValue] { if case .array(let v) = self { return v }; return [] }
    public var object: [String: JSONValue] { if case .object(let v) = self { return v }; return [:] }
    public var text: String { string ?? "" }
    public var int: Int { number.flatMap(Int.init(exactly:)) ?? 0 }
    public var numbers: [Double] { array.compactMap(\.number) }
    public func data() throws -> Data { let e = JSONEncoder(); e.outputFormatting = [.sortedKeys]; return try e.encode(self) }
}

public enum ContractError: LocalizedError {
    case invalid(String)
    public var errorDescription: String? { if case .invalid(let v) = self { return v }; return nil }
}

public struct Placement: Equatable, Sendable {
    public let position: [Double]
    public let size: [Double]
    public let yaw: Double
    public let mount: String
    public init(_ value: JSONValue) throws {
        position = value["position"].numbers; size = value["size"].numbers
        guard position.count == 3, size.count == 3, position.allSatisfy(\.isFinite), size.allSatisfy({ $0.isFinite && $0 > 0 }), let angle = value["yaw"].number, angle.isFinite, let m = value["mount"].string, ["floor", "wall", "ceiling", "object", "item", "support", "tabletop"].contains(m) else { throw ContractError.invalid("Invalid placement; the room cannot be rendered safely.") }
        yaw = angle; mount = m
    }
}

public struct IntentDraft: Codable, Equatable, Sendable {
    public var intent = "add"
    public var styles = ["match"]
    public var budget = ""
    public var text = ""
    public init() {}
    public static func validBudget(_ value: String) -> Bool {
        guard value.range(of: #"^[0-9]+(?:\.[0-9]{1,2})?$"#, options: .regularExpression) != nil, let amount = Decimal(string: value, locale: Locale(identifier: "en_US_POSIX")) else { return false }
        return amount > 0
    }
    public mutating func toggleStyle(_ style: String) {
        if style == "match" { styles = ["match"]; return }
        styles.removeAll { $0 == "match" }
        if styles.contains(style) { styles.removeAll { $0 == style } } else { styles.append(style) }
        if styles.isEmpty { styles = ["match"] }
    }
}

public struct SamplingGate: Sendable {
    public private(set) var count = 0
    private var lastTime: Double?
    private var lastPosition: [Double] = []
    private var lastForward: [Double] = []
    public init() {}
    public mutating func accept(time: Double, position: [Double], forward: [Double], trackingNormal: Bool) -> Bool {
        guard trackingNormal, count < 40, position.count == 3, forward.count == 3 else { return false }
        if let lastTime {
            let dt = time - lastTime
            guard dt > 0 else { return false }
            let distance = sqrt(zip(position, lastPosition).map { pow($0 - $1, 2) }.reduce(0, +))
            let dot = zip(forward, lastForward).map(*).reduce(0, +)
            let turn = acos(min(1, max(-1, dot)))
            guard distance / dt <= 0.3, dt >= 1.5 || distance >= 0.5 || turn >= 20 * .pi / 180 else { return false }
        }
        lastTime = time; lastPosition = position; lastForward = forward; count += 1
        return true
    }
}

public struct PendingRequest: Codable, Sendable {
    public let operationID: String
    public let roomID: String?
    public let path: String
    public let method: String
    public let body: JSONValue
    public init(path: String, method: String = "POST", roomID: String?, body: [String: JSONValue]) {
        operationID = body["operation_id"]?.string ?? UUID().uuidString
        self.roomID = roomID; self.path = path; self.method = method
        var payload = body; payload["schema_version"] = .number(1); payload["operation_id"] = .string(operationID)
        self.body = .object(payload)
    }
}

public struct SavedDesign: Sendable {
    public let value: JSONValue
    public let items: [JSONValue]
    public init(envelope: JSONValue) throws {
        guard envelope["schema_version"].int == 1 else { throw ContractError.invalid("Unsupported design schema.") }
        let value = envelope["design"]
        guard let id = value["design_id"].string, !id.isEmpty, value["scene"]["design_id"].text == id, value["scene"]["room"]["floor"]["polygon"].array.count >= 3 else { throw ContractError.invalid("Saved design is missing its immutable identity or measured room.") }
        let items = value["scene"]["items"].array
        var identities = Set<String>()
        for item in items {
            guard let id = item["id"].string, identities.insert(id).inserted else { throw ContractError.invalid("Saved design Item identities are invalid.") }
            _ = try Placement(item["placement"])
            if item["status"].text == "removed", item["origin"].text == "existing" { _ = try Placement(item["last_valid_placement"]) }
            if let selection = item["selection_id"].string { _ = try ProductChoice(value["scene"]["selections"][selection]) }
        }
        self.value = value; self.items = items
    }
}

public struct ProductChoice: Sendable {
    public let value: JSONValue
    public let exactOfferURL: URL
    public init(_ value: JSONValue) throws {
        let offer = value["offer"]
        guard let variant = value["variant_id"].string, offer["variant_id"].text == variant,
              value["dimensions"].numbers.count == 3, value["dimensions"].numbers.allSatisfy({ $0.isFinite && $0 > 0 }),
              value["dimension_evidence"]["variant_id"].text == variant, value["dimension_evidence"]["outcome"].text == "verified", value["dimension_evidence"]["dimensions"] == value["dimensions"],
              let price = offer["price"].string, IntentDraft.validBudget(price), offer["currency"].text == "USD",
              !offer["checked_at"].text.isEmpty, let url = URL(string: offer["product_url"].text), url.scheme == "https", url.host != nil else { throw ContractError.invalid("This Product is missing its exact offer or verified dimensions.") }
        self.value = value; exactOfferURL = url
    }
}

public struct RoomRecord: Sendable {
    public let value: JSONValue
    public init(_ value: JSONValue) throws {
        guard !value["room_id"].text.isEmpty, !value["name"].text.isEmpty,
              value["metadata_revision"].number != nil, value["active_revision"].number != nil,
              !value["latest_capture_id"].text.isEmpty, !value["capture_state"].text.isEmpty else { throw ContractError.invalid("The backend returned an incomplete Room record.") }
        self.value = value
    }
}

public enum SceneItems {
    public static func visible(in scene: JSONValue, showGhosts: Bool) -> [JSONValue] {
        scene["items"].array.filter { $0["status"].text != "removed" || ($0["origin"].text == "existing" && showGhosts) }
    }
}

public enum ProductOptions {
    public static func choices(selected: JSONValue, search: JSONValue) -> [JSONValue] {
        var seen = Set<String>()
        return ([selected] + search["prior_displayed_choices"].array + search["displayed_choices"].array).filter { choice in
            guard (try? ProductChoice(choice)) != nil else { return false }
            return seen.insert(choice["variant_id"].text).inserted
        }
    }
}

public struct NumericQuestion: Sendable {
    private let minimum: Double?
    private let maximum: Double?
    private let step: Double
    public init(_ question: JSONValue) {
        minimum = question["numeric_min"].number
        maximum = question["numeric_max"].number
        step = question["numeric_step"].number ?? 1
    }
    public var initialValue: Double {
        let start = minimum ?? 0
        if let maximum, start > maximum, step.isFinite, step > 0 { return start + floor((maximum - start) / step) * step }
        return start
    }
    public func isValid(_ value: Double) -> Bool {
        guard value.isFinite, step.isFinite, step > 0, value >= (minimum ?? -.infinity), value <= (maximum ?? .infinity) else { return false }
        let steps = (value - (minimum ?? 0)) / step
        return steps.isFinite && abs(steps - steps.rounded()) < 1e-8
    }
    public func next(_ value: Double, direction: Int) -> Double? {
        guard isValid(value) else { return nil }
        let base = minimum ?? 0
        let result = base + (((value - base) / step).rounded() + Double(direction)) * step
        return isValid(result) ? result : nil
    }
}
