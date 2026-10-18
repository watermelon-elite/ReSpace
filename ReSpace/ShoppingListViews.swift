import SwiftUI

struct ShoppingListView: View {
    let list: ShoppingList

    var body: some View {
        RSPage(title: "Your shopping list", topTitle: list.roomName) {
            Label("Saved on this iPhone · \(list.savedAt.formatted(date: .abbreviated, time: .shortened))", systemImage: "checkmark.circle")
                .font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
            if list.fitPending { RSNotice(message: "Product plan · room fit is still pending.") }
            if list.lines.isEmpty {
                RSSymbol(name: "bag")
                Text("Nothing to buy.").font(ReSpaceStyle.font(22, weight: .semibold))
                Text("No purchases are needed for this \(list.fitPending ? "plan" : "design").").foregroundStyle(ReSpaceStyle.secondary)
            }
            ForEach(list.lines) { line in
                VStack(alignment: .leading, spacing: 8) {
                    Text(line.title).font(ReSpaceStyle.font(18, weight: .semibold))
                    Text(line.merchant).font(ReSpaceStyle.font(14)).foregroundStyle(ReSpaceStyle.secondary)
                    RSKeyValue(title: line.quantity, value: "USD \(line.total)")
                    if line.surplusCount > 0 {
                        Text("\(line.surplusCount) unplaced paid units").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
                    }
                    Link(destination: line.url) {
                        Label("Open at \(line.merchant)", systemImage: "arrow.up.right")
                            .font(ReSpaceStyle.font(14, weight: .medium)).frame(minHeight: 44)
                    }.accessibilityHint("Opens the selected merchant offer")
                }
            }
            RSKeyValue(title: "Total · USD", value: "$\(list.total)")
            if let limit = list.approvedCeiling { RSKeyValue(title: "Approved limit", value: "$\(limit)") }
            Text("Whole packs are included. Existing Objects, tax and shipping are excluded. Saved prices; confirm price and availability with each merchant.")
                .font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
        } footer: {
            if !list.lines.isEmpty {
                ShareLink(item: list.shareText) {
                    Label("Share list", systemImage: "square.and.arrow.up")
                }.buttonStyle(RSButtonStyle())
                Text("Choose Messages to send all the links together.")
                    .font(ReSpaceStyle.font(12)).foregroundStyle(ReSpaceStyle.secondary)
            }
        }
    }
}

struct SavedShoppingListsView: View {
    let store: ShoppingListStore

    var body: some View {
        NavigationStack {
            RSPage(title: "Saved shopping lists") {
                if store.lists.isEmpty {
                    RSSymbol(name: "bag")
                    Text("Your new pieces, all together.").font(ReSpaceStyle.font(22, weight: .semibold))
                    Text("Open a room or design and tap the shopping bag to save its links here.").foregroundStyle(ReSpaceStyle.secondary)
                }
                ForEach(store.lists) { list in
                    NavigationLink { ShoppingListView(list: list) } label: {
                        RSRow(title: list.roomName,
                              subtitle: "\(list.lines.count) \(list.lines.count == 1 ? "purchase" : "purchases") · USD \(list.total) · \(list.savedAt.formatted(date: .abbreviated, time: .omitted))",
                              symbol: "bag")
                    }.buttonStyle(.plain)
                }
            } footer: { EmptyView() }
        }
    }
}
