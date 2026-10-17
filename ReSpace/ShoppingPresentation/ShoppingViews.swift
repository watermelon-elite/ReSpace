import SwiftUI

struct ItemPresentationCard: View {
    let item: SceneItem
    let selected: Bool
    let select: () -> Void
    private var presentation: ProductPresentation? {
        item.product ?? (item.origin == .new ? DemoShoppingPresentation.product(for: item) : nil)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button(action: select) {
                HStack(alignment: .top, spacing: 14) {
                    ProductImage(url: presentation?.imageUrl, category: item.category).frame(width: 74, height: 80).clipShape(RoundedRectangle(cornerRadius: 12))
                    VStack(alignment: .leading, spacing: 6) {
                        Text(item.label).font(.headline).foregroundStyle(ReSpaceTheme.ink)
                        if let product = presentation {
                            Text(product.isDemo ? "Demo product · \(product.store)" : product.store).font(.caption).foregroundStyle(.secondary)
                            if let price = product.priceText { Text(price).font(.subheadline).foregroundStyle(ReSpaceTheme.ink) }
                        } else {
                            Text(item.isGhost ? "Removed existing furniture" : "Existing furniture").font(.caption).foregroundStyle(.secondary)
                            Text(item.planningState.label).font(.caption).foregroundStyle(ReSpaceTheme.olive)
                        }
                    }
                    Spacer(minLength: 0)
                    if selected { Image(systemName: "checkmark.circle.fill").foregroundStyle(ReSpaceTheme.olive) }
                }
            }.buttonStyle(.plain)
            if let reason = item.reason { Text("Why: \(reason)").font(.caption).foregroundStyle(.secondary) }
            if let product = presentation {
                NavigationLink { ProductDetailView(product: product, sceneItemLabel: item.label) } label: {
                    Label("View product & alternatives", systemImage: "arrow.up.right").font(.caption.weight(.medium))
                }
            }
        }.padding(14).background(ReSpaceTheme.surface, in: RoundedRectangle(cornerRadius: 18))
            .overlay(RoundedRectangle(cornerRadius: 18).stroke(selected ? ReSpaceTheme.olive : .clear, lineWidth: 1.5))
    }
}

struct ProductDetailView: View {
    let product: ProductPresentation
    let sceneItemLabel: String
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                ProductImage(url: product.imageUrl, category: "product").frame(height: 260).clipShape(RoundedRectangle(cornerRadius: 24))
                Text(product.title).font(.system(.largeTitle, design: .serif))
                Text(product.store).foregroundStyle(.secondary)
                if let price = product.priceText { Text(price).font(.title3) }
                StatusBanner(text: product.isDemo ? "Demo merchandise for shopping navigation. It does not identify the measured model \(sceneItemLabel)." : "Product information supplied by the room service. Shopping actions are unavailable in this build.")
                Button {} label: { Label("Buy · unavailable", systemImage: "bag").frame(maxWidth: .infinity).padding() }
                    .buttonStyle(.bordered).disabled(true)
                if !product.alternatives.isEmpty {
                    Text("Explore alternatives").font(.system(.title2, design: .serif))
                    Text("Preview only. Alternatives do not replace items in your design.").font(.caption).foregroundStyle(.secondary)
                    ForEach(product.alternatives) { alternative in
                        NavigationLink {
                            AlternativeDetailView(product: alternative)
                        } label: {
                            HStack(spacing: 14) {
                                ProductImage(url: alternative.imageUrl, category: "product").frame(width: 64, height: 64).clipShape(RoundedRectangle(cornerRadius: 12))
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(alternative.title).font(.headline)
                                    Text(alternative.store).font(.caption).foregroundStyle(.secondary)
                                    if let price = alternative.priceText { Text(price).font(.caption) }
                                }
                                Spacer(); Image(systemName: "chevron.right")
                            }.padding(14).background(ReSpaceTheme.surface, in: RoundedRectangle(cornerRadius: 16))
                        }.buttonStyle(.plain)
                    }
                }
            }.padding(24)
        }.background(ReSpaceTheme.cream).navigationTitle("Product details").navigationBarTitleDisplayMode(.inline)
    }
}

private struct AlternativeDetailView: View {
    let product: ProductAlternative
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                ProductImage(url: product.imageUrl, category: "product").frame(height: 260).clipShape(RoundedRectangle(cornerRadius: 24))
                Text(product.title).font(.system(.largeTitle, design: .serif))
                Text(product.store).foregroundStyle(.secondary)
                if let price = product.priceText { Text(price).font(.title3) }
                StatusBanner(text: "Demo alternative · preview only. Your room, total, and design history stay as supplied by the room service.")
                Button("Buy · unavailable") {}.buttonStyle(.bordered).disabled(true)
            }.padding(24)
        }.background(ReSpaceTheme.cream).navigationTitle("Alternative").navigationBarTitleDisplayMode(.inline)
    }
}

private struct ProductImage: View {
    let url: URL?
    let category: String
    var body: some View {
        AsyncImage(url: url) { phase in
            if let image = phase.image { image.resizable().scaledToFit().padding(8) }
            else {
                ZStack {
                    ReSpaceTheme.olive.opacity(0.07)
                    VStack(spacing: 6) {
                        Image(systemName: "cube.transparent").font(.title2)
                        Text("Placeholder image").font(.system(size: 9)).multilineTextAlignment(.center)
                    }.foregroundStyle(ReSpaceTheme.olive)
                }
            }
        }
    }
}
