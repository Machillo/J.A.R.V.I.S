import Foundation
import Security
import Testing
@testable import DincrCore

/// Release identity and secure-storage guards. They read the app's build settings and sources from
/// the repository, so a change that puts the side-by-side development identity back, moves the
/// OAuth callback, or stores a session outside the Keychain fails here.
@Suite struct IdentityGuardTests {
    /// `.../native/ios` (this file is `.../native/ios/DincrKit/Tests/DincrCoreTests/…`).
    static let iosRoot: URL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()

    static func read(_ path: String) throws -> String {
        try String(contentsOf: iosRoot.appending(path: path), encoding: .utf8)
    }

    /// Every Swift source, build setting and project file of the app and the kit.
    static func appFiles() -> [URL] {
        let roots = ["DINCR", "DincrKit/Sources", "Config", "DINCR.xcodeproj", "DINCRUITests"]
        var files: [URL] = []
        for root in roots {
            let url = iosRoot.appending(path: root)
            guard let walker = FileManager.default.enumerator(at: url, includingPropertiesForKeys: nil) else { continue }
            for case let file as URL in walker where ["swift", "xcconfig", "plist", "pbxproj", "entitlements"].contains(file.pathExtension) {
                files.append(file)
            }
        }
        return files
    }

    @Test func releaseIdentityIsTheStoreApp() throws {
        #expect(AppIdentity.bundleID == "com.dincr.app")
        #expect(AppIdentity.authRedirect == "com.dincr.app://auth/callback")
        #expect(AppIdentity.authCallbackScheme == "com.dincr.app")
        let base = try Self.read("Config/Base.xcconfig")
        let bundle = base.split(separator: "\n").first { $0.hasPrefix("PRODUCT_BUNDLE_IDENTIFIER") }
        #expect(bundle?.split(separator: "=").last?.trimmingCharacters(in: .whitespaces) == AppIdentity.bundleID)
        // The build number must stay above the Capacitor app's so the native build is an update.
        let build = base.split(separator: "\n").first { $0.hasPrefix("CURRENT_PROJECT_VERSION") }
        let number = Int(build?.split(separator: "=").last?.trimmingCharacters(in: .whitespaces) ?? "") ?? 0
        #expect(number > 36)
    }

    @Test func noSideBySideIdentityOrCallbackRemains() throws {
        let files = Self.appFiles()
        #expect(files.count > 20, "the guard must actually see the app sources")
        for file in files {
            let text = try String(contentsOf: file, encoding: .utf8)
            #expect(!text.contains("nativedev"), "\(file.lastPathComponent) still references the development identity")
        }
    }

    @Test func sessionsNeverTouchUserDefaults() throws {
        for file in Self.appFiles() where file.pathExtension == "swift" {
            let lines = try String(contentsOf: file, encoding: .utf8).split(separator: "\n")
            for line in lines where line.contains("UserDefaults") || line.contains("AppStorage") {
                let lower = line.lowercased()
                #expect(!["token", "session", "refresh", "verifier", "password"].contains { lower.contains($0) },
                        "\(file.lastPathComponent): sensitive value near UserDefaults: \(line)")
            }
        }
    }

    @Test func keychainItemIsDeviceOnlyAndNotSynchronized() {
        let item = KeychainSessionStore().item(data: Data("x".utf8))
        #expect(item[kSecAttrAccessible as String] as? String == kSecAttrAccessibleWhenUnlockedThisDeviceOnly as String)
        #expect(item[kSecAttrSynchronizable as String] as? Bool == false)
        #expect(item[kSecClass as String] as? String == kSecClassGenericPassword as String)
    }
}
