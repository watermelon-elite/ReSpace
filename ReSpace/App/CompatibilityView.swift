import SwiftUI

struct CompatibilityView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 28) {
            Text("ReSpace").font(.system(.title2, design: .serif).weight(.semibold))
            Spacer()
            Image(systemName: "viewfinder").font(.system(size: 66, weight: .ultraLight)).foregroundStyle(ReSpaceTheme.olive)
            Text("A new perspective\non your space.").font(.system(size: 43, weight: .regular, design: .serif)).fixedSize(horizontal: false, vertical: true)
            Text("ReSpace needs a LiDAR-capable iPhone to measure your room.")
                .font(.title3).foregroundStyle(.secondary)
            Text("Use an iPhone 12 Pro or a newer Pro model with iOS 18 or later.")
                .font(.subheadline).foregroundStyle(.secondary)
            Spacer()
            Label("LiDAR iPhone required", systemImage: "iphone.gen3.radiowaves.left.and.right").font(.subheadline.weight(.medium))
        }
        .padding(30).frame(maxWidth: .infinity, alignment: .leading)
        .background(ReSpaceTheme.cream).foregroundStyle(ReSpaceTheme.ink)
    }
}
