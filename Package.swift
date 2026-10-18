// swift-tools-version: 6.0
import PackageDescription

// Portable tests for the actual client core, without adding targets to the shared Xcode project.
let package = Package(
    name: "ReSpaceClientCore",
    platforms: [.macOS(.v14), .iOS(.v18)],
    products: [.library(name: "ReSpaceCore", targets: ["ReSpaceCore"])],
    targets: [
        .target(name: "ReSpaceCore", path: "ReSpace",
                exclude: ["App/CompatibilityView.swift", "App/ReSpaceTheme.swift", "App/NetworkRecoveryMonitor.swift", "Assets.xcassets", "ContentView.swift", "ReSpaceApp.swift", "Rooms", "Design", "Rendering", "ShoppingPresentation", "Capture/CaptureController.swift", "Capture/CaptureScreen.swift", "Capture/FrameEncoder.swift", "Capture/SceneMeshEncoder.swift"],
                sources: ["Domain", "Networking", "Persistence", "Capture/CaptureRepository.swift", "App/AppConfiguration.swift", "App/WorkspaceStore.swift"]),
        .testTarget(name: "ReSpaceCoreTests", dependencies: ["ReSpaceCore"], path: "Tests/ReSpaceCoreTests",
                    resources: [.copy("Fixtures")])
    ],
    swiftLanguageModes: [.v5]
)
