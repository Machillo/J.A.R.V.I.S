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
        // store-sample.json: the backend engines' output for the STORE fixture (a byte copy of the Android
        // resource; backend/tests/test_store_sample_engine.py writes and checks both).
        .target(name: "DincrCore", resources: [.copy("Resources/store-sample.json")]),
        .target(name: "DincrDesign", dependencies: ["DincrCore"]),
        .testTarget(name: "DincrCoreTests", dependencies: ["DincrCore"], resources: [.copy("Fixtures")]),
    ]
)
