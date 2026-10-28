import AppIntents
import DincrCore
import Observation

/// Where the system leaves a quick action until the app can act on it. `DINCRApp` forwards it to
/// `AppModel.pendingRoute`, which only the signed-in, unlocked shell consumes: a shortcut never
/// opens anything behind the lock screen, a gate or the sign-in.
@MainActor @Observable
final class QuickActionInbox {
    static let shared = QuickActionInbox()
    private(set) var pending: QuickAction?

    func request(_ action: QuickAction) { pending = action }

    /// The pending action, once: the caller now owns it.
    func take() -> QuickAction? {
        defer { pending = nil }
        return pending
    }
}

/// "Añadir gasto": opens DINCR on the movement editor for a new expense. It writes nothing; the
/// user saves. Available in Shortcuts and Siri, and assignable to Back Tap (Settings > Accessibility
/// > Touch > Back Tap) by tapping the back of the iPhone.
struct AddExpenseIntent: AppIntent {
    static let title: LocalizedStringResource = "Añadir gasto"
    static let description = IntentDescription("Abre DINCR listo para registrar un gasto.")
    static let openAppWhenRun = true

    @MainActor
    func perform() async throws -> some IntentResult {
        QuickActionInbox.shared.request(.newExpense)
        return .result()
    }
}

struct DincrShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: AddExpenseIntent(),
            phrases: [
                "Añadir gasto en \(.applicationName)",
                "Agregar un gasto en \(.applicationName)",
                "Add an expense in \(.applicationName)",
            ],
            shortTitle: "Añadir gasto",
            systemImageName: "plus.circle"
        )
        // Atajos de iPhone (ShortcutIntents.swift): background sends for Shortcuts automations.
        AppShortcut(
            intent: RegisterApplePayPurchaseIntent(),
            phrases: [
                "Registrar compra en \(.applicationName)",
                "Register a purchase in \(.applicationName)",
            ],
            shortTitle: "Registrar compra",
            systemImageName: "creditcard"
        )
        AppShortcut(
            intent: SendBankMessageIntent(),
            phrases: [
                "Enviar aviso bancario a \(.applicationName)",
                "Send a bank notice to \(.applicationName)",
            ],
            shortTitle: "Enviar aviso bancario",
            systemImageName: "message"
        )
    }
}
