import DincrCore
import DincrDesign
import SwiftUI

// How the Owner's figures read (Owner information clarity): the month's figures with what each one
// means, the period they cover, whether the month is complete, and the figures the ledger reports
// apart. Every amount is the backend's. Android: OwnerMonthViews.kt and StrategyScreens.kt.

/// A one-line explanation under an Owner figure.
struct OwnerCaption: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
    }
}

/// "Ciclo: 6 oct – 5 nov": the dates the Owner's figures cover; nothing when the backend does not know them.
struct OwnerPeriodNote: View {
    let label: String
    let period: DatePeriod?
    var body: some View {
        if let start = period?.start, let end = period?.end {
            OwnerCaption("\(label): \(Day.label(start)) – \(Day.label(end))")
        }
    }
}

/// The Owner's month in Movimientos → Resumen del mes (backend owner_ledger). Shown only when the
/// answer is the Owner's ledger (`MonthlySummary.isOwnerLedger`).
struct OwnerMonthSummary: View {
    let summary: MonthlySummary
    @Environment(\.moneyFormat) private var format

    var body: some View {
        OwnerCaption(tx("Mes calendario, del primer al último día. Solo cuenta dinero que ya se movió.",
                        "The calendar month, first to last day. Only money that already moved counts."))
        if summary.complete == false {
            DincrMessage(.attention, title: tx("Este mes todavía no está completo", "This month isn’t complete yet"),
                         message: (summary.incompleteReasons ?? []).map {
                             OwnerReading.incompleteReason($0, pendingMail: summary.pendingMailCount, unclassified: summary.unclassifiedCount)
                         }.joined(separator: "\n"))
        } else {
            // Nothing recorded is unknown, not a verified zero; a month in progress can still change.
            switch OwnerReading.monthState(summary, currentMonth: Self.currentMonth) {
            case .noMovements:
                OwnerCaption(tx("No hay movimientos registrados en este mes: las cifras en cero significan que no hay registros, no que se confirmó que no hubo dinero.",
                                "No movements recorded this month: the zero figures mean there are no records, not that no money moved."))
            case .inProgress:
                OwnerCaption(tx("Mes en curso: hasta hoy no quedan avisos sin revisar ni movimientos sin clasificar. Las cifras cambian hasta que termine el mes.",
                                "Month in progress: so far no notices are left to review and no movements to classify. The figures change until the month ends."))
            case .closed:
                OwnerCaption(tx("Mes completo: no quedan avisos sin revisar ni movimientos sin clasificar.",
                                "Complete month: no notices left to review and no movements to classify."))
            }
        }
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            FigureRow(label: tx("Ingresos recibidos", "Income received"), amount: summary.income, sign: .income)
            OwnerCaption(tx("Depósitos y salario neto que entraron este mes.", "Deposits and net salary that came in this month."))
            FigureRow(label: tx("Gastos", "Spending"), amount: summary.expenses, sign: .expense)
            OwnerCaption(refundNote)
            FigureRow(label: tx("Pagos de deuda", "Debt payments"), amount: summary.debtPaid)
            OwnerCaption(tx("Cuotas y abonos pagados a tus deudas.", "Instalments and extra payments made to your debts."))
            FigureRow(label: tx("Resultado del mes", "Result of the month"), amount: summary.balance)
            OwnerCaption(tx("Ingresos recibidos menos gastos y pagos de deuda.", "Income received minus spending and debt payments."))
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("summary.owner.month")

        if Self.positive(summary.otherInflows) {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Otro dinero que entró (no es ingreso)", "Other money in (not income)"))
                if Self.positive(summary.loanReceived) { FigureRow(label: tx("Préstamos recibidos", "Loans received"), amount: summary.loanReceived) }
                if Self.positive(summary.receivablePayments) { FigureRow(label: tx("Cobros de dinero que te debían", "Money owed to you, collected"), amount: summary.receivablePayments) }
                if Self.positive(summary.assetSaleProceeds) { FigureRow(label: tx("Ventas de bienes", "Sales of things you owned"), amount: summary.assetSaleProceeds) }
                FigureRow(label: tx("Resultado contando ese dinero", "Result including that money"), amount: summary.cashFlow)
                OwnerCaption(tx("Entró a tus cuentas pero no lo ganaste: por eso no suma a tus ingresos.",
                                "It came into your accounts but you didn’t earn it, so it doesn’t add to your income."))
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("summary.owner.otherInflows")
        }

        if let payroll = summary.payrollAccrued, OwnerReading.hasPayroll(payroll) {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Nómina bruta registrada (aparte)", "Gross payroll recorded (apart)"))
                if let value = payroll.overtimeGross, value != 0 { FigureRow(label: tx("Horas extra (bruto)", "Overtime (gross)"), amount: value) }
                if let value = payroll.vghGross, value != 0 { FigureRow(label: tx("Rebajos por vacaciones u otros (VGH, bruto)", "Leave deductions (VGH, gross)"), amount: value) }
                if let value = payroll.bonusesGross, value != 0 { FigureRow(label: tx("Bonos (bruto)", "Bonuses (gross)"), amount: value) }
                OwnerCaption(tx("Montos antes de cargas sociales e impuestos. Ese dinero llega dentro del depósito del salario, por eso no se suma otra vez a tus ingresos.",
                                "Amounts before social charges and taxes. That money arrives inside the salary deposit, so it isn’t added to your income again."))
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("summary.owner.payroll")
        }

        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            FigureRow(label: tx("Ahorrado", "Saved"), amount: summary.savings)
            OwnerCaption(tx("Ahorros: lo que anotaste en Ingresos y base; no es el saldo de una cuenta.",
                            "Savings: what you entered in Income and base; not an account balance."))
        }
        .dincrCard()
    }

    private var refundNote: String {
        if let gross = summary.grossExpenses, let refunds = summary.refunds, refunds > 0, refunds <= gross {
            return tx("Gastos de \(format.string(gross)) menos reembolsos de \(format.string(refunds)).",
                      "Spending of \(format.string(gross)) minus refunds of \(format.string(refunds)).")
        }
        return tx("Compras y pagos del mes, ya restados los reembolsos.", "Purchases and payments of the month, refunds already taken out.")
    }

    private static func positive(_ value: Decimal?) -> Bool { (value ?? 0) > 0 }

    private static var currentMonth: String {
        let parts = Calendar.current.dateComponents([.year, .month], from: Date())
        return String(format: "%04d-%02d", parts.year ?? 0, parts.month ?? 0)
    }
}

/// What the income and spending bars mean and which months are not complete yet (backend owner_ledger).
struct OwnerFlowNotes: View {
    let flow: [TransactionAnalysis.MonthPoint]
    /// The months the chart shows: only those are listed as incomplete.
    let charted: [String]
    var body: some View {
        OwnerCaption(tx("Por mes calendario. Ingresos: dinero recibido. Gastos: ya restados los reembolsos. Préstamos, cobros y ventas no cuentan como ingreso.",
                        "By calendar month. Income: money received. Spending: refunds already taken out. Loans, collections and sales don’t count as income."))
        let incomplete = OwnerReading.incompleteMonths(flow).filter { charted.contains($0) }
        if !incomplete.isEmpty {
            OwnerCaption(tx("Meses todavía incompletos: ", "Months not complete yet: ") + incomplete.map { OwnerReading.monthLabel($0) }.joined(separator: ", ") +
                         tx(" (avisos sin revisar, movimientos sin clasificar o nómina sin el depósito del salario).",
                            " (notices not reviewed, movements not classified or payroll without the salary deposit)."))
                .accessibilityIdentifier("jarvis.analysis.incomplete")
        }
    }
}
