// swift-tools-version: 6.0
import PackageDescription

// Separate libraries preserve both sets of wire contracts and their original test seams.
let contractSources = ["CaptureTransfer.swift", "Ollo.swift", "Contracts.swift", "ShoppingList.swift", "RenderAssets.swift", "RealityAssetLoader.swift"]
let appSources = ["UIDemo.swift", "DesignSystem.swift", "IntentViews.swift", "OperationViews.swift", "ProductViews.swift",
                  "ShoppingListViews.swift", "ShoppingShareView.swift", "ContentView.swift", "ImportedRoomView.swift", "ReSpaceApp.swift",
                  "APIClient.swift", "Capture.swift", "RoomViews.swift", "DesignView.swift", "RoomScene.swift", "ScanIntegration.swift"]
let resources = ["Preview Content", "Assets.xcassets", "Resources"]
let package = Package(
    name: "ReSpaceMergedCore",
    platforms: [.macOS(.v15), .iOS(.v18)],
    products: [
        .library(name: "ReSpaceContracts", targets: ["ReSpaceContracts"]),
        .library(name: "ReSpaceCore", targets: ["ReSpaceCore"])
    ],
    targets: [
        .target(name: "ReSpaceContracts", path: "ReSpace",
                exclude: appSources + resources + ["App", "Capture", "Domain", "Networking", "Persistence", "Rooms", "Design", "Rendering", "ShoppingPresentation"],
                sources: contractSources),
        .testTarget(name: "ReSpaceContractsTests", dependencies: ["ReSpaceContracts"], path: "ReSpaceTests"),
        .target(name: "ReSpaceCore", path: "ReSpace",
                exclude: contractSources + appSources + resources + ["App/CompatibilityView.swift", "App/ReSpaceTheme.swift", "App/NetworkRecoveryMonitor.swift",
                    "Rooms", "Design", "Rendering", "ShoppingPresentation", "Capture/CaptureController.swift", "Capture/CaptureScreen.swift", "Capture/FrameEncoder.swift", "Capture/SceneMeshEncoder.swift"],
                sources: ["Domain", "Networking", "Persistence", "Capture/CaptureRepository.swift", "App/AppConfiguration.swift", "App/WorkspaceStore.swift"]),
        .testTarget(name: "ReSpaceCoreTests", dependencies: ["ReSpaceCore"], path: "Tests/ReSpaceCoreTests", resources: [.copy("Fixtures")])
    ],
    swiftLanguageModes: [.v5]
)
