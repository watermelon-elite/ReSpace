import Foundation

/// Display only, bound to an explicit scene ID. Never written into a design or a request.
enum DemoShoppingPresentation {
    static func product(for item: SceneItem) -> ProductPresentation {
        ProductPresentation(id: "demo:\(item.id)", title: "Demo \(item.label.lowercased())",
                            store: "Example retailer", priceText: "Demo price · $89.00", isDemo: true,
                            alternatives: [
                                ProductAlternative(id: "demo:\(item.id):1", title: "Demo alternative one", store: "Example retailer", priceText: "Demo price · $69.00"),
                                ProductAlternative(id: "demo:\(item.id):2", title: "Demo alternative two", store: "Example retailer", priceText: "Demo price · $109.00")
                            ])
    }
}
