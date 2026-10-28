import Foundation
import Security

/// The "Atajos de iPhone" credential: the limited token the backend issued (`dsc_…`) and the account
/// it was issued to. It can only send purchases and bank notices to the review inbox; it never opens a
/// session. The account id lets the app forget a token that belongs to someone else (account switch).
public struct ShortcutCredential: Codable, Sendable, Equatable {
    public let token: String
    public let accountID: Int

    public init(token: String, accountID: Int) { self.token = token; self.accountID = accountID }

    /// The backend's shape: `dsc_` followed by URL-safe characters. Anything else is never stored or sent.
    public static func isValidToken(_ token: String) -> Bool {
        guard token.hasPrefix("dsc_"), token.count > 4, token.count <= 512 else { return false }
        return token.dropFirst(4).unicodeScalars.allSatisfy { scalar in
            scalar.isASCII && (CharacterSet.alphanumerics.contains(scalar) || scalar == "-" || scalar == "_")
        }
    }
}

/// Where the shortcut token lives on this device.
public protocol ShortcutTokenStore: Sendable {
    func read() -> ShortcutCredential?
    func save(_ credential: ShortcutCredential)
    func clear()
}

extension ShortcutTokenStore {
    public var isLinked: Bool { read() != nil }
}

/// Keychain storage. Unlike the session (`KeychainSessionStore`, readable only while unlocked), the
/// shortcut token is readable after the first unlock since boot: an automation runs the intent in the
/// background with the iPhone locked. Never synced to iCloud, never restored to another device
/// (pinned by `ShortcutTokenStoreTests`).
public struct KeychainShortcutTokenStore: ShortcutTokenStore {
    let service: String
    let account = "shortcut-token"

    public init(service: String = "com.dincr.app.shortcuts") { self.service = service }

    private var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account]
    }

    public func read() -> ShortcutCredential? {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(request as CFDictionary, &item) == errSecSuccess, let data = item as? Data,
              let credential = try? JSONDecoder().decode(ShortcutCredential.self, from: data),
              ShortcutCredential.isValidToken(credential.token) else { return nil }
        return credential
    }

    public func save(_ credential: ShortcutCredential) {
        guard ShortcutCredential.isValidToken(credential.token), let data = try? JSONEncoder().encode(credential) else { return }
        SecItemDelete(query as CFDictionary)
        SecItemAdd(item(data: data) as CFDictionary, nil)
    }

    /// The stored item: readable after the first unlock (background automations), this device only.
    func item(data: Data) -> [String: Any] {
        var item = query
        item[kSecValueData as String] = data
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        item[kSecAttrSynchronizable as String] = false
        return item
    }

    public func clear() { SecItemDelete(query as CFDictionary) }
}

/// Fixtures and tests: nothing leaves memory.
public final class InMemoryShortcutTokenStore: ShortcutTokenStore, @unchecked Sendable {
    private let lock = NSLock()
    private var credential: ShortcutCredential?
    public init(_ credential: ShortcutCredential? = nil) { self.credential = credential }
    public func read() -> ShortcutCredential? { lock.withLock { credential } }
    public func save(_ credential: ShortcutCredential) {
        guard ShortcutCredential.isValidToken(credential.token) else { return }
        lock.withLock { self.credential = credential }
    }
    public func clear() { lock.withLock { credential = nil } }
}
