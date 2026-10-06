import DincrCore
import DincrDesign
import SwiftUI

/// Hoy (UX-6): the four public blocks — Estado de hoy, Para atender, Qué sigue, Accesos rápidos —
/// drawn from `HomeToday`. The public plans and the Owner (below its JARVIS space) share it.
/// Unknown figures are "—" with a "?" that says what DINCR needs and opens the real flow to add it.
struct HomeBlocks: View {
    let home: HomeToday
    var idPrefix = "home"
    var ownerStyle = false
    /// Switches to the Movimientos tab when the screen can (public Hoy); otherwise it is pushed.
    var openMovements: (() -> Void)?
    let reload: () async -> Void
    @State private var editor: EditorRequest?

    var body: some View {
        let links = HomeLinkContext(editor: $editor, openMovements: openMovements)
        VStack(alignment: .leading, spacing: DincrSpacing.s4) {
            HomeStatusCard(status: home.status, idPrefix: idPrefix, ownerStyle: ownerStyle, links: links)
            if let attention = home.attention {
                AttentionSection(today: attention, idPrefix: "\(idPrefix).attention", ownerStyle: ownerStyle)
            }
            HomeNextCard(next: home.next, idPrefix: idPrefix, ownerStyle: ownerStyle, links: links)
            HomeShortcuts(shortcuts: home.shortcuts, idPrefix: idPrefix, ownerStyle: ownerStyle, links: links)
        }
        .sheet(item: $editor) { request in
            MovementEditor(mode: .create, initialKind: request.kind) { _ in Task { await reload() } }
        }
    }
}

/// The movement editor Hoy opens (income to register the month's pay, or any movement).
struct EditorRequest: Identifiable {
    let kind: Movement.Kind
    var id: String { kind.rawValue }
}

struct HomeLinkContext {
    let editor: Binding<EditorRequest?>
    let openMovements: (() -> Void)?
}

/// Opens a destination: the movement editor as a sheet, Movimientos as a tab, the rest pushed.
struct HomeLink<Label: View>: View {
    let destination: HomeDestination
    let links: HomeLinkContext
    @ViewBuilder let label: () -> Label

    var body: some View {
        switch destination {
        case .registerIncome:
            Button { links.editor.wrappedValue = EditorRequest(kind: .income) } label: { label() }.buttonStyle(.plain)
        case .registerMovement:
            Button { links.editor.wrappedValue = EditorRequest(kind: .expense) } label: { label() }.buttonStyle(.plain)
        case .movements where links.openMovements != nil:
            Button { links.openMovements?() } label: { label() }.buttonStyle(.plain)
        default:
            NavigationLink { HomeDestinationView(destination: destination) } label: { label() }.buttonStyle(.plain)
        }
    }
}

/// The screens Hoy opens (navigation only; each keeps its own rules and gates).
struct HomeDestinationView: View {
    let destination: HomeDestination

    var body: some View {
        switch destination {
        case .movements, .registerIncome, .registerMovement: MovementsView()
        case .debts: DebtsView()
        case .goals: GoalsView()
        case .situation: SituationView()
        case .monthPlan: PlanStrategyView()
        }
    }
}

private struct BlockHeader: View {
    let title: String
    let ownerStyle: Bool

    var body: some View {
        if ownerStyle { OwnerSectionHeader(title) } else { SectionHeader(title: title) }
    }
}

// MARK: 1. Estado de hoy

private struct HomeStatusCard: View {
    let status: HomeStatus
    let idPrefix: String
    let ownerStyle: Bool
    let links: HomeLinkContext
    @State private var explains = false
    @Environment(\.moneyFormat) private var format


    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            BlockHeader(title: tx("Estado de hoy", "Today’s status"), ownerStyle: ownerStyle)
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                VStack(alignment: .leading, spacing: DincrSpacing.s1) {
                    Text(headline).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                    if let amount = status.amount {
                        MoneyText(amount, font: DincrFont.displayAmount)
                            .accessibilityIdentifier("\(idPrefix).status.amount")
                    } else {
                        unknown
                    }
                    if status.headline == .safeToSpend {
                        HStack(spacing: DincrSpacing.s1) {
                            Text(tx("Margen del mes", "Monthly margin"))
                            if let margin = status.margin {
                                MoneyText(margin, font: DincrFont.caption.weight(.semibold).monospacedDigit())
                            } else {
                                Text("—")
                            }
                        }
                        .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                        .accessibilityElement(children: .combine)
                    }
                    if let lowest = status.lowestBalance {
                        HStack(spacing: DincrSpacing.s1) {
                            Text(tx("Saldo mínimo previsto (45 días)", "Lowest expected balance (45 days)"))
                            MoneyText(lowest, font: DincrFont.caption.weight(.semibold).monospacedDigit())
                        }
                        .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                        .accessibilityElement(children: .combine)
                    }
                }
                facts
                if let paid = status.debtPaid { line(tx("Pagado a deudas", "Paid to debts"), paid, id: "debtPaid") }
                if let owed = status.debtBalance { line(tx("Deuda pendiente", "Outstanding debt"), owed, id: "debtBalance") }
                if let budget = status.budget {
                    VStack(alignment: .leading, spacing: DincrSpacing.s1) {
                        HStack {
                            Text(tx("Presupuesto restante", "Budget left")).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                            Spacer()
                            MoneyText(budget.remaining, font: DincrFont.bodySmall.weight(.semibold).monospacedDigit())
                        }
                        .accessibilityElement(children: .combine)
                        DincrProgressBar(budget.used, overMeaning: .unfavorable)
                    }
                    .accessibilityIdentifier("\(idPrefix).status.budget")
                }
                if let pending = status.pending {
                    HStack {
                        Text(tx("Próximos pagos conocidos este mes", "Known upcoming payments this month")).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                        Spacer()
                        Text(pendingText(pending)).font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(DincrColor.text)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityIdentifier("\(idPrefix).status.pending")
                }
            }
            .dincrCard()
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("\(idPrefix).status")
    }

    private var headline: String {
        switch status.headline {
        case .monthResult: tx("Resultado del mes", "This month’s result")
        case .safeToSpend: tx("Podés gastar con tranquilidad", "Safe to spend")
        }
    }

    /// Unknown, never ₡0: what DINCR can't calculate yet, and on "?" why and how to give it.
    private var unknown: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            HStack(alignment: .center, spacing: DincrSpacing.s2) {
                Text("—").font(DincrFont.displayAmount).foregroundStyle(DincrColor.text2).accessibilityHidden(true)
                Text(tx("Aún no puedo calcularlo", "I can’t calculate this yet")).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                Spacer(minLength: 0)
                Button { explains.toggle() } label: {
                    Image(systemName: "questionmark.circle").font(.title3).foregroundStyle(DincrColor.tint).frame(minWidth: 44, minHeight: 44)
                }
                .accessibilityLabel(tx("Qué necesita DINCR", "What DINCR needs"))
                .accessibilityIdentifier("\(idPrefix).status.help")
            }
            // .contain: the row's identifier must not replace the "?" button's own.
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("\(idPrefix).status.unknown")
            if explains {
                MissingInputs(missing: status.missing, idPrefix: "\(idPrefix).status", links: links)
            }
        }
    }

    private var facts: some View {
        HStack(alignment: .top, spacing: DincrSpacing.s4) {
            fact(tx("Ingresos", "Income"), status.income, sign: .income, unknown: tx("Sin registrar", "Not recorded"))
            fact(tx("Gastos", "Expenses"), status.expenses, sign: .expense, unknown: tx("Sin registrar", "Not recorded"))
            if status.headline == .safeToSpend {
                fact(tx("Resultado del mes", "Month result"), status.result, sign: .none, unknown: "—")
            }
        }
        .accessibilityIdentifier("\(idPrefix).status.facts")
    }

    private func fact(_ label: String, _ amount: Decimal?, sign: MoneyFormat.Sign, unknown: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            if let amount {
                MoneyText(amount, sign: sign, font: DincrFont.bodySmall.weight(.semibold).monospacedDigit())
            } else {
                Text(unknown).font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(DincrColor.text2)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func line(_ label: String, _ amount: Decimal, id: String) -> some View {
        HStack {
            Text(label).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
            Spacer()
            MoneyText(amount, font: DincrFont.bodySmall.weight(.semibold).monospacedDigit())
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("\(idPrefix).status.\(id)")
    }

    /// Payments the calendar knows of (scheduled from today on): none known is not "none due".
    private func pendingText(_ pending: HomeStatus.Pending) -> String {
        if pending.count == 0 { return tx("Ninguno registrado", "None recorded") }
        let count = pending.count == 1 ? tx("1 pago", "1 payment") : tx("\(pending.count) pagos", "\(pending.count) payments")
        guard let total = pending.total else { return tx("\(count) · monto por confirmar", "\(count) · amount to confirm") }
        return "\(count) · \(format.string(total))"
    }
}

/// Why a figure is unknown and where to give DINCR what it needs (never an estimate).
private struct MissingInputs: View {
    let missing: [HomeInput]
    let idPrefix: String
    let links: HomeLinkContext

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            if missing.isEmpty {
                Text(tx("Aún no tengo suficiente información para calcular esto.", "I don’t have enough information to calculate this yet."))
                    .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
            }
            ForEach(missing, id: \.self) { input in
                VStack(alignment: .leading, spacing: DincrSpacing.s1) {
                    Text(input.explanation).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                    HomeLink(destination: input.destination, links: links) {
                        Text(input.actionTitle).font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(DincrColor.tint).frame(minHeight: 44)
                    }
                    .accessibilityIdentifier("\(idPrefix).missing.\(input.rawValue)")
                }
            }
        }
        .padding(DincrSpacing.s3)
        .background(DincrColor.surface2, in: RoundedRectangle(cornerRadius: DincrRadius.md, style: .continuous))
    }
}

extension HomeInput {
    var explanation: String {
        switch self {
        case .income: tx("DINCR necesita tus ingresos del mes registrados (tu salario o boleta de pago) para calcularlo.",
                         "DINCR needs this month’s income recorded (your salary or pay stub) to calculate it.")
        case .essentialExpenses: tx("Faltan tus gastos esenciales del mes.", "Your essential monthly expenses are missing.")
        case .debtPayments: tx("Una de tus deudas no tiene su cuota mensual.", "One of your debts has no monthly payment.")
        case .savings: tx("Falta tu ahorro disponible o el saldo de una cuenta.", "Your available savings or an account balance is missing.")
        case .emergencyFundTarget: tx("Falta la meta de tu fondo de emergencia.", "Your emergency fund target is missing.")
        case .debtInterestRates: tx("Falta la tasa de interés de una o más deudas. Con todas las tasas, DINCR puede decirte qué deuda atacar primero.",
                                    "The interest rate of one or more debts is missing. With every rate, DINCR can tell you which debt to pay down first.")
        }
    }

    var actionTitle: String {
        switch self {
        case .income: tx("Registrar ingreso", "Record income")
        case .debtPayments, .debtInterestRates: tx("Revisar deudas", "Review debts")
        case .essentialExpenses, .savings, .emergencyFundTarget: tx("Completar mi situación", "Complete my situation")
        }
    }
}

// MARK: 3. Qué sigue

private struct HomeNextCard: View {
    let next: HomeNext
    let idPrefix: String
    let ownerStyle: Bool
    let links: HomeLinkContext


    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            BlockHeader(title: tx("Qué sigue", "What’s next"), ownerStyle: ownerStyle)
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                HStack(alignment: .top, spacing: DincrSpacing.s3) {
                    Image(systemName: symbol).font(.system(size: 18, weight: .medium)).foregroundStyle(DincrColor.tint)
                        .frame(width: 36, height: 36).background(DincrColor.tintContainer, in: RoundedRectangle(cornerRadius: DincrRadius.sm, style: .continuous))
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(title).font(DincrFont.body.weight(.semibold)).foregroundStyle(DincrColor.text)
                        if let detail { Text(detail).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2) }
                        if next.kind == .commitment {
                            if let amount = next.amount {
                                MoneyText(amount, font: DincrFont.bodySmall.weight(.semibold).monospacedDigit())
                            } else {
                                Text(tx("Monto por confirmar", "Amount to confirm")).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                            }
                        }
                    }
                    Spacer(minLength: 0)
                }
                .accessibilityElement(children: .combine)
                if next.kind == .needsInformation, !next.missing.isEmpty {
                    MissingInputs(missing: next.missing, idPrefix: "\(idPrefix).next", links: links)
                } else {
                    HomeLink(destination: next.destination, links: links) {
                        HStack(spacing: DincrSpacing.s1) {
                            Text(actionTitle)
                            Image(systemName: "chevron.right").font(DincrFont.caption).accessibilityHidden(true)
                        }
                        .font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(DincrColor.tint).frame(minHeight: 44)
                    }
                    .accessibilityIdentifier("\(idPrefix).next.action")
                }
                if next.kind == .recommendation { FinancialDisclaimer() }
            }
            .dincrCard()
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("\(idPrefix).next")
    }

    private var symbol: String {
        switch next.kind {
        case .recommendation: "sparkles"
        case .needsInformation: "questionmark.circle"
        case .commitment: "calendar"
        case .registerIncome: "arrow.down.circle"
        case .registerMovement: "plus.circle"
        }
    }

    private var title: String {
        switch next.kind {
        case .recommendation: next.title ?? ""
        case .needsInformation: next.title ?? tx("DINCR necesita más información antes de recomendarte.", "DINCR needs more information before recommending.")
        case .commitment: tx("Próximo pago: \(next.title ?? tx("deuda", "debt"))", "Next payment: \(next.title ?? "debt")")
        case .registerIncome: tx("Registrá tus ingresos del mes", "Record this month’s income")
        case .registerMovement: tx("Mantené tu mes al día", "Keep your month up to date")
        }
    }

    private var detail: String? {
        switch next.kind {
        case .recommendation: next.detail
        case .needsInformation: nil
        case .commitment: next.date.flatMap(Self.day)
        case .registerIncome: tx("Con tu salario o boleta de pago registrados, DINCR puede mostrarte el resultado del mes.",
                                 "With your salary or pay stub recorded, DINCR can show you this month’s result.")
        case .registerMovement: tx("Registrá tus gastos e ingresos para ver tu mes completo.", "Record your expenses and income to see your whole month.")
        }
    }

    private var actionTitle: String {
        switch next.kind {
        case .recommendation: tx("Ver tu plan del mes", "See your plan for the month")
        case .needsInformation: tx("Completar mi situación", "Complete my situation")
        case .commitment: tx("Ver deudas", "See debts")
        case .registerIncome: tx("Registrar ingreso", "Record income")
        case .registerMovement: tx("Registrar movimiento", "Record a transaction")
        }
    }

    private static func day(_ key: String) -> String? {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        guard let date = formatter.date(from: key) else { return nil }
        return JarvisAgendaLabel.day(date, fallback: key)
    }
}

// MARK: 4. Accesos rápidos

private struct HomeShortcuts: View {
    let shortcuts: [HomeShortcut]
    let idPrefix: String
    let ownerStyle: Bool
    let links: HomeLinkContext


    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            BlockHeader(title: tx("Accesos rápidos", "Quick access"), ownerStyle: ownerStyle)
            // Two per row, always built (not lazy): every shortcut exists for VoiceOver and tests.
            VStack(spacing: DincrSpacing.s3) {
                ForEach(Array(stride(from: 0, to: shortcuts.count, by: 2)), id: \.self) { start in
                    HStack(alignment: .top, spacing: DincrSpacing.s3) {
                        ForEach(shortcuts[start..<min(start + 2, shortcuts.count)], id: \.self) { shortcut in
                            HomeLink(destination: shortcut.destination, links: links) { tile(shortcut) }
                                .accessibilityIdentifier(identifier(shortcut))
                        }
                    }
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("\(idPrefix).shortcuts")
    }

    private func tile(_ shortcut: HomeShortcut) -> some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Image(systemName: symbol(shortcut)).font(.system(size: 18, weight: .medium)).foregroundStyle(DincrColor.tint)
                .frame(width: 36, height: 36).background(DincrColor.tintContainer, in: RoundedRectangle(cornerRadius: DincrRadius.sm, style: .continuous))
                .accessibilityHidden(true)
            Text(title(shortcut)).font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(DincrColor.text)
                .multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, minHeight: 88, alignment: .topLeading)
        .dincrCard(padding: DincrSpacing.s3)
        .contentShape(Rectangle())
    }

    /// Debts and goals keep the identifiers the reachability spec names (`home.debts`, `home.goals`).
    private func identifier(_ shortcut: HomeShortcut) -> String {
        switch shortcut {
        case .debts: "\(idPrefix).debts"
        case .goals: "\(idPrefix).goals"
        default: "\(idPrefix).shortcut.\(shortcut.rawValue)"
        }
    }

    private func symbol(_ shortcut: HomeShortcut) -> String {
        switch shortcut {
        case .registerMovement: "plus.circle"
        case .movements: "list.bullet.rectangle"
        case .debts: "creditcard"
        case .goals: "target"
        }
    }

    private func title(_ shortcut: HomeShortcut) -> String {
        switch shortcut {
        case .registerMovement: tx("Registrar movimiento", "Record a transaction")
        case .movements: tx("Movimientos", "Transactions")
        case .debts: tx("Deudas", "Debts")
        case .goals: tx("Metas y ahorro", "Goals and savings")
        }
    }
}
