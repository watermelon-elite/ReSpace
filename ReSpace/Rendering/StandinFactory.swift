import RealityKit
import UIKit

@MainActor enum StandinFactory {
    static func make(category: String, size: [Float], tint: String?) -> Entity {
        let root = Entity()
        let color = UIColor(hex: tint) ?? UIColor(red: 0.59, green: 0.65, blue: 0.57, alpha: 1)
        func part(_ dimensions: SIMD3<Float>, at position: SIMD3<Float>, color override: UIColor? = nil) {
            let model = ModelEntity(mesh: .generateBox(size: dimensions, cornerRadius: 0.025),
                                    materials: [SimpleMaterial(color: override ?? color, roughness: 0.85, isMetallic: false)])
            model.position = position; root.addChild(model)
        }
        switch category {
        case "sofa", "bed":
            part([1, 0.45, 1], at: [0, 0.225, 0])
            part([1, 0.55, 0.15], at: [0, 0.725, -0.425])
            if category == "sofa" {
                part([0.12, 0.3, 1], at: [-0.44, 0.6, 0])
                part([0.12, 0.3, 1], at: [0.44, 0.6, 0])
            }
        case "chair", "stool", "table", "coffee_table", "desk":
            let isChair = category == "chair"
            let top: Float = isChair ? 0.45 : 0.95
            part([1, 0.1, 1], at: [0, top, 0])
            for x: Float in [-0.4, 0.4] { for z: Float in [-0.4, 0.4] { part([0.08, top, 0.08], at: [x, top / 2, z]) } }
            if isChair { part([1, 0.5, 0.12], at: [0, 0.75, -0.44]) }
        case "plant":
            part([0.55, 0.35, 0.55], at: [0, 0.175, 0], color: .brown)
            part([1, 0.65, 1], at: [0, 0.675, 0], color: .systemGreen)
        case "lamp", "floor_lamp":
            part([0.6, 0.06, 0.6], at: [0, 0.03, 0])
            part([0.06, 0.75, 0.06], at: [0, 0.4, 0])
            part([1, 0.25, 1], at: [0, 0.875, 0], color: .init(red: 0.95, green: 0.87, blue: 0.68, alpha: 1))
        default: part([1, 1, 1], at: [0, 0.5, 0])
        }
        root.scale = [size[0], size[2], size[1]]
        return root
    }
}

extension UIColor {
    convenience init?(hex: String?) {
        guard let hex else { return nil }
        let text = hex.hasPrefix("#") ? String(hex.dropFirst()) : hex
        guard text.count == 6, let value = UInt32(text, radix: 16) else { return nil }
        self.init(red: CGFloat((value >> 16) & 255) / 255, green: CGFloat((value >> 8) & 255) / 255,
                  blue: CGFloat(value & 255) / 255, alpha: 1)
    }
}
