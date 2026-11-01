import DincrCore
import Foundation
import UserNotifications

/// NT-1 — the reminders on the phone (local notifications; no server, no token). Turned on in
/// Perfil → Recordatorios, which asks the system permission. Every time the app becomes active
/// (and right after signing in) it reads the debts, the fixed expenses and the Salvavidas plan,
/// asks `Reminders.plan` which reminders the next weeks need, and replaces the ones it scheduled
/// before. A failed read keeps the reminders already scheduled. Signing out removes them.
/// Android twin: `ReminderScheduler.kt`.
@MainActor
enum ReminderScheduler {
    static let enabledKey = "dincr.reminders"
    private static let prefix = "dincr.reminder."
    private static var center: UNUserNotificationCenter { .current() }

    static var isEnabled: Bool { UserDefaults.standard.bool(forKey: enabledKey) }

    /// Asks the system and turns the reminders on; false when the user declined (they live in Ajustes then).
    static func enable(_ model: AppModel) async -> Bool {
        let granted = (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        UserDefaults.standard.set(granted, forKey: enabledKey)
        if granted { await refresh(model) }
        return granted
    }

    static func disable() async {
        UserDefaults.standard.set(false, forKey: enabledKey)
        await clear()
    }

    static func clear() async {
        let ids = await center.pendingNotificationRequests().map(\.identifier).filter { $0.hasPrefix(prefix) }
        center.removePendingNotificationRequests(withIdentifiers: ids)
    }

    static func refresh(_ model: AppModel) async {
        guard isEnabled, model.phase == .ready, !model.environment.isFixtures else { return }
        guard await center.notificationSettings().authorizationStatus == .authorized else { return }
        let bills: [Reminders.Bill]
        var saving: SalvavidasAutoContribution?
        var blocks: [DebtSavingsBlocks.Block] = []
        do {
            let debts = try await model.service.debts()
            var fixed: [Reminders.Bill] = []
            if model.planTier.rank >= PlanTier.vip.rank {
                if Jarvis.isAvailable(to: model.profile) {
                    fixed = try await model.service.ownerFixedExpenses().compactMap { item in
                        item.dueDay.map { Reminders.Bill(id: "fixed-\(item.id)", kind: .fixed, name: item.name ?? "", amount: item.expectedAmount, day: $0) }
                    }
                } else {
                    fixed = (try await model.service.recurring().items ?? []).compactMap { item in
                        guard item.itemType == "expense", item.isActive != false, (item.frequency ?? "monthly") == "monthly", let day = item.dueDay else { return nil }
                        return Reminders.Bill(id: "fixed-\(item.id)", kind: .fixed, name: item.name ?? "", amount: item.amount, day: day)
                    }
                }
                saving = (try? await model.service.salvavidas())?.autoContribution
                if Jarvis.isAvailable(to: model.profile) { blocks = (try? await model.service.debtSavingsBlocks())?.blocks ?? [] }
            }
            bills = Reminders.bills(debts: debts, fixed: fixed)
        } catch {
            return
        }
        let plan = Reminders.plan(today: Date(), bills: bills, saving: saving, blocks: blocks, format: model.moneyFormat, language: model.language)
        await clear()
        for reminder in plan {
            let content = UNMutableNotificationContent()
            content.title = reminder.title
            content.body = reminder.body
            content.sound = .default
            let trigger = UNCalendarNotificationTrigger(dateMatching: reminder.date, repeats: false)
            try? await center.add(UNNotificationRequest(identifier: reminder.id, content: content, trigger: trigger))
        }
    }
}
