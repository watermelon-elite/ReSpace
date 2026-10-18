import SwiftUI

func productOffer(_ product: JSONValue) -> JSONValue { product["offer"] == .null ? product["chosen_offer"] : product["offer"] }
func productPrice(_ product: JSONValue) -> String { let offer = productOffer(product); return offer["price"].string ?? offer["price"]["amount"].text }
func productTitle(_ product: JSONValue) -> String { product["title"].string ?? product["variant"]["title"].text }

struct ProductImage: View {
    let product: JSONValue
    var body: some View {
        ZStack {
            ReSpaceStyle.canvas
            if let source = product["variant"]["image_references"].array.first?.string, URL(string: source)?.scheme == nil,
               let image = UIImage(named: source) {
                Image(uiImage: image).resizable().scaledToFit()
            } else if let source = product["variant"]["image_references"].array.first?.string, let url = URL(string: source) {
                AsyncImage(url: url) { phase in
                    if let image = phase.image { image.resizable().scaledToFit() }
                    else if phase.error != nil { Image(systemName: "photo").foregroundStyle(ReSpaceStyle.secondary).accessibilityLabel("Product image unavailable") }
                    else { ProgressView() }
                }
            } else { Image(systemName: "photo").font(.system(size: 28, weight: .light)).foregroundStyle(ReSpaceStyle.secondary).accessibilityLabel("No Product image") }
        }.accessibilityLabel(productTitle(product))
    }
}

struct ProductSummary: View {
    let product: JSONValue
    var body: some View {
        HStack(alignment: .center, spacing: 16) {
            ProductImage(product: product).frame(width: 76, height: 88).clipShape(RoundedRectangle(cornerRadius: 16))
            VStack(alignment: .leading, spacing: 6) {
                Text(productTitle(product)).font(ReSpaceStyle.font(16, weight: .semibold))
                Text("$\(productPrice(product))").font(ReSpaceStyle.font(15, weight: .medium))
                Text(productOffer(product)["merchant"].string ?? productOffer(product)["merchant_id"].text).font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading)
        }.foregroundStyle(ReSpaceStyle.ink)
    }
}

/// Selected context for a Product tapped in the room: price and the exact offer handoff, with details one tap away.
struct ProductSelectionCard: View {
    let product: JSONValue
    var status = "New in this design"
    let onDetails: () -> Void
    let onClose: () -> Void
    @Environment(\.openURL) private var openURL
    private var merchant: String { productOffer(product)["merchant"].string ?? "merchant" }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 14) {
                ProductImage(product: product).frame(width: 72, height: 72).clipShape(RoundedRectangle(cornerRadius: 14))
                VStack(alignment: .leading, spacing: 4) {
                    Text(status).font(ReSpaceStyle.font(12, weight: .medium)).foregroundStyle(ReSpaceStyle.purple)
                    Text(productTitle(product)).font(ReSpaceStyle.font(16, weight: .semibold)).lineLimit(2)
                    if let variant = product["variant"]["variant_label"].string {
                        Text(variant).font(ReSpaceStyle.font(12)).foregroundStyle(ReSpaceStyle.secondary).lineLimit(1)
                    }
                    Text("$\(productPrice(product)) · \(merchant)").font(ReSpaceStyle.font(15, weight: .semibold)).padding(.top, 2)
                }.frame(maxWidth: .infinity, alignment: .leading)
                RSIconButton(symbol: "xmark", label: "Clear selection", action: onClose)
            }
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) { buttons }
                VStack(spacing: 8) { buttons }
            }
        }
        .padding(16).background(.white, in: RoundedRectangle(cornerRadius: 24))
        .overlay { RoundedRectangle(cornerRadius: 24).stroke(ReSpaceStyle.line, lineWidth: 1).allowsHitTesting(false) }
        .shadow(color: .black.opacity(0.08), radius: 16, y: 6)
        .accessibilityElement(children: .contain)
    }
    @ViewBuilder private var buttons: some View {
        Button("Details", action: onDetails).buttonStyle(RSButtonStyle(kind: .secondary, compact: true)).fixedSize()
        if let choice = try? ProductChoice(product) {
            Button("Buy at \(merchant)") { openURL(choice.exactOfferURL) }
                .buttonStyle(RSButtonStyle(compact: true)).lineLimit(1)
                .accessibilityHint("Opens the exact offer on \(choice.exactOfferURL.host ?? merchant)")
        }
    }
}

struct ProductDetail: View {
    let app: AppModel
    let product: JSONValue
    let searchID: String?
    let canSwap: Bool
    var startWithAlternatives = false
    var onFindMore: (() -> Void)? = nil
    let onPreview: (JSONValue, String) -> Void
    @Environment(\.openURL) private var openURL
    @Environment(\.dismiss) private var dismiss
    @State private var search: JSONValue = .null
    @State private var error: String?
    @State private var page = "detail"
    @State private var option: JSONValue = .null
    @State private var loading = false
    var offer: JSONValue { productOffer(product) }
    var choices: [JSONValue] { ProductOptions.choices(selected: product, search: search) }
    var effectiveSearchID: String? { searchID ?? product["search_id"].string }
    private var title: String { page == "evidence" || page == "option" ? "Product evidence" : page == "alternatives" ? "Try another look." : productTitle(product) }
    var body: some View {
        NavigationStack {
            RSPage(title: title, back: { if page == "detail" || (startWithAlternatives && page == "alternatives") { dismiss() } else { page = page == "option" ? "alternatives" : "detail" } }) {
                switch page {
                case "evidence": ProductEvidence(product: product)
                case "option": ProductEvidence(product: option, pending: true)
                case "alternatives": alternatives
                default: detailContent
                }
            } footer: {
                switch page {
                case "evidence": Button("Back to Product") { page = "detail" }.buttonStyle(RSButtonStyle(kind: .secondary))
                case "option":
                    if let search = effectiveSearchID { Button("Preview this Product") { onPreview(option, search) }.buttonStyle(RSButtonStyle()).disabled(!canSwap) }
                    Button("Back to options") { page = "alternatives" }.buttonStyle(RSButtonStyle(kind: .quiet))
                case "alternatives":
                    if let onFindMore { Button("Find more options", action: onFindMore).buttonStyle(RSButtonStyle(kind: .secondary)).disabled(!canSwap) }
                default:
                    if let selected = try? ProductChoice(product) {
                        Button("Buy at \(offer["merchant"].string ?? "merchant")") { openURL(selected.exactOfferURL) }.buttonStyle(RSButtonStyle())
                    }
                }
            }
        }
        .onAppear { if startWithAlternatives { page = "alternatives" } }
        .task(id: effectiveSearchID) {
            search = .null; error = nil
            if let id = effectiveSearchID, let client = app.client {
                loading = true
                defer { loading = false }
                do {
                    let result = try await client.request("searches/\(id)")["search"]
                    if !Task.isCancelled, id == effectiveSearchID { search = result }
                }
                catch { if !Task.isCancelled { self.error = "Current alternatives unavailable: \(error.localizedDescription). Saved selection retained." } }
            }
        }
    }
    private var detailContent: some View {
        VStack(alignment: .leading, spacing: 24) {
            ProductImage(product: product).frame(height: 280).clipShape(RoundedRectangle(cornerRadius: 28))
            HStack(alignment: .firstTextBaseline) {
                Text(offer["merchant"].string ?? offer["merchant_id"].text).font(ReSpaceStyle.font(14)).foregroundStyle(ReSpaceStyle.secondary)
                Spacer()
                Text("$\(productPrice(product))").font(ReSpaceStyle.font(24, weight: .semibold))
            }
            if let variant = product["variant"]["variant_label"].string { Text(variant).font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary) }
            if !product["reason"].text.isEmpty { Text(product["reason"].text).font(ReSpaceStyle.font(16)).foregroundStyle(ReSpaceStyle.secondary) }
            VStack(spacing: 0) {
                Button { page = "evidence" } label: { RSRow(title: "Measurements & evidence", subtitle: "Exact variant and offer details", symbol: "doc.text") }
                Button { page = "alternatives" } label: { RSRow(title: "See alternatives", subtitle: "Keep this choice until a swap is saved", symbol: "arrow.triangle.2.circlepath") }
            }.buttonStyle(.plain)
        }
    }
    @ViewBuilder private var alternatives: some View {
        Text("Saved: \(productTitle(product)) · $\(productPrice(product))").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
        if loading { ProgressView("Checking alternatives…").font(ReSpaceStyle.font(14)).padding(.vertical, 24) }
        if let error { RSNotice(message: error, isError: true) }
        let alternatives = choices.filter { $0["variant_id"].text != product["variant_id"].text }
        ForEach(alternatives, id: \.self) { choice in
            Button { option = choice; page = "option" } label: {
                VStack(alignment: .leading, spacing: 12) {
                    ProductSummary(product: choice)
                    Text(choice["dimensions"].numbers.map { String(format: "%.1f", $0 * 100) }.joined(separator: " × ") + " cm")
                        .font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
                    Text("Preview · fit pending").font(ReSpaceStyle.font(12)).foregroundStyle(ReSpaceStyle.secondary)
                }.padding(16).background(.white, in: RoundedRectangle(cornerRadius: 20))
                    .overlay { RoundedRectangle(cornerRadius: 20).stroke(ReSpaceStyle.line, lineWidth: 1) }
            }.buttonStyle(.plain)
        }
        if !loading && alternatives.isEmpty {
            RSSymbol(name: "bag")
            Text("No more options yet.").font(ReSpaceStyle.font(22, weight: .semibold))
            Text("No other eligible Products are available for this selection. Your saved choice stays in place.").foregroundStyle(ReSpaceStyle.secondary)
        }
    }
}

struct ProductEvidence: View {
    let product: JSONValue
    var pending = false
    private var offer: JSONValue { productOffer(product) }
    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            ProductSummary(product: product)
            HStack(alignment: .top, spacing: 16) {
                ForEach(Array(["Width", "Depth", "Height"].enumerated()), id: \.offset) { index, name in
                    let assumed = product["dimension_evidence"]["assumed_axes"][name.lowercased()].number != nil
                    VStack(alignment: .leading, spacing: 8) {
                        Text(name).font(ReSpaceStyle.font(12)).foregroundStyle(ReSpaceStyle.secondary)
                        Text(assumed ? "Not published" : product["dimensions"].numbers.indices.contains(index) ? String(format: "%.1f cm", product["dimensions"].numbers[index] * 100) : "Unavailable")
                            .font(ReSpaceStyle.font(15, weight: .medium))
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }
            }.padding(.vertical, 16)
                .overlay(alignment: .top) { Rectangle().fill(ReSpaceStyle.line).frame(height: 1) }
                .overlay(alignment: .bottom) { Rectangle().fill(ReSpaceStyle.line).frame(height: 1) }
            VStack(spacing: 0) {
                if let url = URL(string: product["dimension_evidence"]["source_url"].text), ["https", "http"].contains(url.scheme ?? "") {
                    Link(destination: url) { RSKeyValue(title: "Dimension source", value: url.host ?? "Exact variant listing") }.foregroundStyle(ReSpaceStyle.purple)
                }
                RSKeyValue(title: "Dimensions checked", value: checkedDate(product["dimension_evidence"]["verified_at"].text))
                RSKeyValue(title: "Offer checked", value: checkedDate(offer["checked_at"].text))
                RSKeyValue(title: "Offer", value: "$\(productPrice(product))")
                RSKeyValue(title: "Placement", value: pending || product["fit_state"].text == "pending" ? "Fit pending" : "Validated in saved design")
            }
            if !product["verification_warnings"].array.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(product["verification_warnings"].array, id: \.self) { warning in
                        Text(warning.text).font(ReSpaceStyle.font(14)).foregroundStyle(ReSpaceStyle.secondary)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            DisclosureGroup("Why this Product") {
                VStack(alignment: .leading, spacing: 16) {
                    ForEach(["practical", "style", "value", "overall"], id: \.self) { component in
                        if let score = product["scores"][component].number {
                            RSKeyValue(title: component.capitalized, value: String(format: "%.1f / 100", score))
                            if !product["reasons"][component].text.isEmpty { Text(product["reasons"][component].text).font(ReSpaceStyle.font(14)) }
                        }
                    }
                    Text("Scores are judgments, not probabilities.").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
                    ForEach(product["dimension_evidence"]["original_measurements"].array, id: \.self) { measurement in
                        Text("\(measurement["axis"].text) · \(measurement["label"].text): \(measurement["value"].string ?? measurement["value"].number.map(String.init(describing:)) ?? "") \(measurement["unit"].text)").font(ReSpaceStyle.font(13))
                    }
                    let uncertainty = product["uncertainty"].string ?? product["uncertainty"].array.compactMap(\.string).joined(separator: "\n")
                    if !uncertainty.isEmpty { Text(uncertainty).font(ReSpaceStyle.font(14)) }
                    Text("Selected variant: \(product["variant_id"].text)").font(ReSpaceStyle.font(12)).foregroundStyle(ReSpaceStyle.secondary)
                }.padding(.top, 12)
            }.font(ReSpaceStyle.font(14))
            if !product["offers"].array.isEmpty {
                DisclosureGroup("Merchant offers for this variant") {
                    ForEach(product["offers"].array, id: \.self) { offer in
                        VStack(alignment: .leading, spacing: 8) {
                            RSKeyValue(title: offer["merchant"].text, value: "USD \(offer["price"].string ?? offer["price"]["amount"].text)")
                            if let url = URL(string: offer["product_url"].text), ["http", "https"].contains(url.scheme ?? "") { Link("Open exact offer", destination: url).frame(minHeight: 44) }
                        }
                    }
                }.font(ReSpaceStyle.font(14))
            }
            Text("Representative model; verified measurements determine its size.").font(ReSpaceStyle.font(12)).foregroundStyle(ReSpaceStyle.secondary)
        }
    }
    private func checkedDate(_ raw: String) -> String {
        let parser = ISO8601DateFormatter(); parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return (parser.date(from: raw) ?? ISO8601DateFormatter().date(from: raw))?.formatted(date: .abbreviated, time: .shortened) ?? (raw.isEmpty ? "Unavailable" : raw)
    }
}

struct OptionEvidence: View {
    let choice: JSONValue
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        RSPage(title: "Product evidence") { ProductEvidence(product: choice, pending: true) } footer: {
            Button("Back to options") { dismiss() }.buttonStyle(RSButtonStyle(kind: .secondary))
        }
    }
}

extension JSONValue: Identifiable { public var id: String { (try? String(data: data(), encoding: .utf8)) ?? "" } }

#if DEBUG
#Preview("Product") { UIDemoPreview(.product) }
#endif
