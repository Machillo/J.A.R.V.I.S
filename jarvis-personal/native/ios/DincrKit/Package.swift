// swift-tools-version: 6.0
// DincrKit: everything in the DINCR iOS app that is not a screen.
// - DincrCore: models, API client, auth session, formatting, fixtures. No UI.
// - DincrDesign: DINCR 2.0 tokens (generated from /DESIGN.md) and shared components.
// Business rules stay in the FastAPI backend; nothing here computes financial results.
import PackageDescription

let package = Package(
    name: "DincrKit",
    defaultLocalization: "es",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "DincrCore", targets: ["DincrCore"]),
        .library(name: "DincrDesign", targets: ["DincrDesign"]),
    ],
    targets: [
        .target(name: "DincrCore"),
        .target(name: "DincrDesign", dependencies: ["DincrCore"]),
        .testTarget(name: "DincrCoreTests", dependencies: ["DincrCore"], resources: [.copy("Fixtures")]),
    ]
)
