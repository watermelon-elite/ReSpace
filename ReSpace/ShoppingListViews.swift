import SwiftUI

struct ShoppingListView: View {
    let list: ShoppingList
    @State private var showShare = false

    var body: some View {
        RSPage(title: "Shopping list", topTitle: list.roomName) {
            if list.fitPending {
                Text("Room fit not yet checked").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
            }
            if list.lines.isEmpty {
                RSSymbol(name: "bag")
                Text("Nothing to buy.").font(ReSpaceStyle.font(22, weight: .semibold))
            }
            VStack(spacing: 0) {
                ForEach(list.lines) { line in
                    Link(destination: line.url) {
                        HStack(alignment: .top, spacing: 16) {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(line.title).font(ReSpaceStyle.font(17, weight: .medium))
                                Text(line.merchant).font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
                                if line.packCount > 1 || line.suppliedCount > 1 {
                                    Text(line.quantity).font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
                                }
                                if line.surplusCount > 0 {
                                    Text("Includes \(line.surplusCount) extra \(line.surplusCount == 1 ? "item" : "items")")
                                        .font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
                                }
                            }.frame(maxWidth: .infinity, alignment: .leading)
                            Text("$\(line.total)").font(ReSpaceStyle.font(17, weight: .semibold)).fixedSize()
                            Image(systemName: "arrow.up.right").font(.system(size: 13)).padding(.top, 4)
                        }.foregroundStyle(ReSpaceStyle.ink).padding(.vertical, 20).frame(minHeight: 44)
                    }.accessibilityHint("Opens the product at \(line.merchant)")
                    Divider().overlay(ReSpaceStyle.line)
                }
                HStack {
                    Text("Total · USD").font(ReSpaceStyle.font(14)).foregroundStyle(ReSpaceStyle.secondary)
                    Spacer()
                    Text("$\(list.total)").font(ReSpaceStyle.font(24, weight: .semibold))
                }.padding(.top, 24)
                Text("Tax & shipping extra.").font(ReSpaceStyle.font(12)).foregroundStyle(ReSpaceStyle.secondary)
                    .frame(maxWidth: .infinity, alignment: .trailing).padding(.top, 6)
            }
            DisclosureGroup {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Saved \(list.savedAt.formatted(date: .abbreviated, time: .shortened))")
                    if let limit = list.approvedCeiling { Text("Budget limit · $\(limit)") }
                    ForEach(list.lines) { line in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(line.title).fontWeight(.medium)
                            Text(line.quantity)
                        }
                    }
                    Text("Saved prices for new purchases. Check current price and availability with the retailer.")
                }.frame(maxWidth: .infinity, alignment: .leading).padding(.top, 12)
            } label: {
                Text("Details").frame(minHeight: 44)
            }.font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
        } footer: {
            if !list.lines.isEmpty {
                Button { showShare = true } label: {
                    Label("Share list", systemImage: "square.and.arrow.up")
                }.buttonStyle(RSButtonStyle())
            }
        }
        .sheet(isPresented: $showShare) { ShoppingShareView(list: list) }
    }
}

struct SavedShoppingListsView: View {
    let lists: [ShoppingList]

    var body: some View {
        NavigationStack {
            RSPage(title: "Shopping lists") {
                if lists.isEmpty {
                    RSSymbol(name: "bag")
                    Text("No saved lists yet.").font(ReSpaceStyle.font(22, weight: .semibold))
                    Text("Tap the bag in a room to save its products.").foregroundStyle(ReSpaceStyle.secondary)
                }
                ForEach(lists) { list in
                    NavigationLink { ShoppingListView(list: list) } label: {
                        RSRow(title: list.roomName,
                              subtitle: "\(list.lines.count) \(list.lines.count == 1 ? "product" : "products") · $\(list.total)",
                              symbol: "bag")
                    }.buttonStyle(.plain)
                }
            } footer: { EmptyView() }
        }
    }
}

#if DEBUG
#Preview("Shopping list") { UIDemoPreview(.shopping) }
#endif
