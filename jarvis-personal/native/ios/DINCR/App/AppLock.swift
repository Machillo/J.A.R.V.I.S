import DincrCore
import Foundation
import LocalAuthentication
import Observation

/// A12/A13/G6 — local app lock with Face ID / Touch ID or the device passcode. It locks when the
/// app opens and after five minutes in the background (Capacitor `appLock.js`). The setting is per
/// DINCR account on this device; nothing about it leaves the device, and it guards the screens,
/// not the session (the Keychain session is protected by the device itself).
@MainActor @Observable
final class AppLock {
    enum Availability: Equatable { case biometrics(String), passcodeOnly, unavailable }

    private(set) var locked = false
    private(set) var isEnabled = false
    private var userID: Int?
    /// ContinuousClock keeps counting while the device sleeps (systemUptime does not), so a phone
    /// locked for an hour counts as an hour away; it cannot be moved by changing the wall clock.
    private var backgroundedAt: ContinuousClock.Instant?
    private let defaults = UserDefaults.standard

    private var enabledKey: String? { userID.map { "dincr.appLock.enabled.\($0)" } }
    private var offeredKey: String? { userID.map { "dincr.appLock.offered.\($0)" } }

    /// Whether the one-time offer to turn it on was already shown to this account (A12).
    var wasOffered: Bool { offeredKey.map { defaults.bool(forKey: $0) } ?? true }

    func markOffered() { if let offeredKey { defaults.set(true, forKey: offeredKey) } }

    var availability: Availability {
        let context = LAContext()
        var error: NSError?
        if context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) {
            switch context.biometryType {
            case .faceID: return .biometrics("Face ID")
            case .touchID: return .biometrics("Touch ID")
            case .opticID: return .biometrics("Optic ID")
            default: return .passcodeOnly
            }
        }
        return LAContext().canEvaluatePolicy(.deviceOwnerAuthentication, error: nil) ? .passcodeOnly : .unavailable
    }

    /// A signed-in account became ready: lock at launch if this account turned the lock on.
    func attach(userID: Int) {
        self.userID = userID
        isEnabled = enabledKey.map { defaults.bool(forKey: $0) } ?? false
        // A lock that can no longer be opened (the passcode was removed) turns itself off instead of
        // trapping the user; the device has no lock to protect it with anyway.
        if isEnabled, availability == .unavailable {
            isEnabled = false
            if let enabledKey { defaults.set(false, forKey: enabledKey) }
        }
        locked = isEnabled
    }

    func detach() {
        userID = nil
        isEnabled = false
        locked = false
        backgroundedAt = nil
    }

    func onBackground() { backgroundedAt = ContinuousClock.now }

    func onForeground() {
        if let backgroundedAt {
            let away = backgroundedAt.duration(to: .now).components
            let seconds = TimeInterval(away.seconds) + TimeInterval(away.attoseconds) / 1e18
            if AppLockPolicy.shouldLock(enabled: isEnabled, backgroundedAt: 0, now: seconds) { locked = true }
        }
        backgroundedAt = nil
    }

    /// Turning the lock on requires a successful authentication first, so the user can unlock.
    func setEnabled(_ enabled: Bool) async -> String? {
        if enabled, let failure = await authenticate(reason: AppLanguage.current.pick("Activá el bloqueo de DINCR", "Turn on the DINCR lock")) {
            return failure
        }
        isEnabled = enabled
        if let enabledKey { defaults.set(enabled, forKey: enabledKey) }
        return nil
    }

    func unlock() async -> String? {
        let failure = await authenticate(reason: AppLanguage.current.pick("Desbloqueá DINCR", "Unlock DINCR"))
        if failure == nil { locked = false }
        return failure
    }

    func lockNow() { if isEnabled { locked = true } }

    /// nil on success; otherwise a message (cancel is not an error worth a message).
    private func authenticate(reason: String) async -> String? {
        let context = LAContext()
        context.localizedCancelTitle = AppLanguage.current.pick("Cancelar", "Cancel")
        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else {
            return AppLanguage.current.pick("Configurá un código o biometría en tu iPhone para usar el bloqueo.", "Set up a passcode or biometrics on your iPhone to use the lock.")
        }
        // Completion API with a continuation: LAContext is not Sendable, so it never crosses actors.
        let code: LAError.Code? = await withCheckedContinuation { continuation in
            context.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { success, error in
                continuation.resume(returning: success ? nil : ((error as? LAError)?.code ?? .authenticationFailed))
            }
        }
        switch code {
        case nil: return nil
        case .userCancel?, .appCancel?, .systemCancel?: return ""
        case .biometryLockout?: return AppLanguage.current.pick("La biometría está bloqueada. Usá el código de tu iPhone.", "Biometrics are locked. Use your iPhone passcode.")
        default: return AppLanguage.current.pick("No pudimos verificar tu identidad. Intentá de nuevo.", "We couldn’t verify it’s you. Please try again.")
        }
    }
}

/// G8 — the JSON export is written to a temporary file for the share sheet and removed at launch,
/// sign-out and account deletion, so no copy outlives the session that made it.
enum DataExport {
    static var directory: URL { FileManager.default.temporaryDirectory.appending(path: "dincr-export", directoryHint: .isDirectory) }

    static func write(_ data: Data) throws -> URL {
        clear()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appending(path: "dincr-datos.json")
        try data.write(to: file, options: [.atomic, .completeFileProtection])
        return file
    }

    static func clear() { try? FileManager.default.removeItem(at: directory) }
}
