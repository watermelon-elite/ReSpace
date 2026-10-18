// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "ReSpaceContracts", platforms: [.macOS(.v14)], products: [.library(name: "ReSpaceContracts", targets: ["ReSpaceContracts"])], targets: [.target(name: "ReSpaceContracts", path: "ReSpace", exclude: ["Assets.xcassets", "ContentView.swift", "ReSpaceApp.swift", "APIClient.swift", "Capture.swift", "RoomViews.swift", "DesignView.swift", "RoomScene.swift"], sources: ["Contracts.swift"]), .testTarget(name: "ReSpaceContractsTests", dependencies: ["ReSpaceContracts"], path: "ReSpaceTests")])
