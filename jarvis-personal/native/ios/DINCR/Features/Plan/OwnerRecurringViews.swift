import DincrCore
import DincrDesign
import SwiftUI

// The Owner's recurring automation (backend finance/recurring_automation.py): a recurring income
// recorded on its date, and the next incomes and debt installments. Shown only when `/auth/me`
// says owner; the backend refuses everyone else (403) whatever the app shows.

/// Owner-only fields of the recurring form: record the income automatically from a next date.
struct OwnerAutomationSection: View {
    @Binding var auto: Bool
    @Binding var next: Date
    @Binding var hasStart: Bool
    @Binding var start: Date

    var body: some View {
        Section {
            Toggle(tx("Registrar en su fecha", "Record on its date"), isOn: $auto)
                .accessibilityIdentifier("recurring.autoRecord")
            if auto {
                DatePicker(tx("Próxima fecha", "Next date"), selection: $next, in: Calendar.current.startOfDay(for: .now)..., displayedComponents: .date)
                Toggle(tx("Indicar desde cuándo", "Set a start date"), isOn: $hasStart)
                if hasStart { DatePicker(tx("Desde", "Since"), selection: $start, displayedComponents: .date) }
            }
        } footer: {
            Text(tx("DINCR lo anota como ingreso una vez por fecha. No mueve dinero.", "DINCR records it as income once per date. It never moves money."))
        }
    }
}

/// The Owner's next recurring incomes and debt installments: expected ones are never shown as paid.
struct OwnerUpcomingSection: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        AsyncContent(load: { try await model.service.recurringUpcoming() }) { upcoming, _ in
            let incomes = upcoming.incomes ?? [], installments = upcoming.installments ?? []
            if !incomes.isEmpty || !installments.isEmpty {
                VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                    Text(tx("Próximos ingresos y cuotas", "Upcoming income and instalments")).font(DincrFont.body.weight(.semibold))
                    ForEach(Array(incomes.enumerated()), id: \.offset) { _, entry in row(entry, income: true) }
                    ForEach(Array(installments.enumerated()), id: \.offset) { _, entry in row(entry, income: false) }
                }
                .dincrCard()
            }
        }
    }

    private func row(_ entry: RecurringUpcoming.Entry, income: Bool) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.name ?? "")
                Text([entry.dueDate, Self.status(entry.status, income: income)].compactMap { $0 }.joined(separator: " · "))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
            Spacer()
            MoneyText(entry.amount, sign: income && !entry.isExpected ? .income : .expense)
        }
        .accessibilityElement(children: .combine)
    }

    static func status(_ status: String?, income: Bool) -> String? {
        switch status {
        case "expected": income ? tx("Previsto", "Expected") : tx("Pendiente", "Pending")
        case "recorded": tx("Registrado", "Recorded")
        case "already_recorded": tx("Ya estaba registrado", "Already recorded")
        case "paid": tx("Cuota registrada", "Instalment recorded")
        default: nil
        }
    }
}
