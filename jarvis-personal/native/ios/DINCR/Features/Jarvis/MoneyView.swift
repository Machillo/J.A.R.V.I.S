import DincrCore
import DincrDesign
import SwiftUI

/// JARVIS → Mi dinero (Owner only): the current cycle (expected and received income, the statement
/// period's spending, debt payments, goal reserves and the real balance) and the Owner's accounts
/// with their balances. Opening it only reads; saving or removing an account is an explicit Owner
/// command. The cycle and the accounts load independently: one failing never hides the other.
/// Every amount is the backend's. Android: `MoneyScreen`.
struct MoneyView: View {
    /// The account form: a new account, or a new balance for an existing one.
    enum FormMode: Identifiable {
        case create
        case update(AccountBalances.Account)
        var id: String {
            switch self {
            case .create: "create"
            case .update(let account): "update.\(account.id)"
            }
        }
    }

    @Environment(AppModel.self) private var model
    @State private var form: FormMode?
    @State private var removing: AccountBalances.Account?
    @State private var notice: String?
    @State private var accountsToken = 0

    var body: some View {
        ScreenScroll(title: tx("Mi dinero", "My money")) {
            if let notice { StatusBanner(tone: .info, title: notice, message: "").accessibilityIdentifier("money.notice") }
            AsyncContent(fallback: tx("No pudimos cargar tu ciclo.", "We couldn’t load your cycle."),
                         load: { try await model.service.cycleReport() }) { report, _ in
                CycleCard(report: report)
            }
            AsyncContent(fallback: tx("No pudimos cargar tus cuentas.", "We couldn’t load your accounts."),
                         load: { try await model.service.accountBalances() }) { balances, _ in
                AccountsContent(balances: balances, update: { form = .update($0) }, remove: { removing = $0 })
            }
            .id(accountsToken)
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { form = .create } label: { Image(systemName: "plus") }
                    .accessibilityLabel(tx("Nueva cuenta", "New account"))
                    .accessibilityIdentifier("money.add")
            }
        }
        .sheet(item: $form) { mode in
            AccountForm(mode: mode) { done($0) }
        }
        .confirmationDialog(tx("¿Quitar «\(removing?.accountName ?? "")» de tus cuentas?", "Remove “\(removing?.accountName ?? "")” from your accounts?"),
                            isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }), titleVisibility: .visible) {
            Button(tx("Quitar", "Remove"), role: .destructive) { if let account = removing { Task { await remove(account) } } }
            Button(tx("Cancelar", "Cancel"), role: .cancel) {}
        } message: {
            Text(tx("Deja de sumar en tu dinero. Sus movimientos no se borran.", "It stops counting in your money. Its movements aren’t deleted."))
        }
    }

    private func done(_ message: String) {
        notice = message
        accountsToken += 1
    }

    private func remove(_ account: AccountBalances.Account) async {
        guard let id = account.accountId else { return }
        let epoch = model.currentEpoch
        do {
            try await model.service.removeAccountBalance(id: id)
            done(tx("Cuenta quitada", "Account removed"))
        } catch {
            notice = model.message(for: error, epoch: epoch, fallback: tx("No pudimos quitarla. Revisá tus cuentas antes de intentar de nuevo.", "We couldn’t remove it. Check your accounts before trying again."))
        }
    }
}

/// "Tu ciclo": the income cycle and the statement period, as the backend computed them.
private struct CycleCard: View {
    let report: CycleReport

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(tx("Tu ciclo", "Your cycle")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
            if let start = report.cycle?.start, let end = report.cycle?.end {
                Text(tx("Ciclo: \(Day.label(start)) – \(Day.label(end))", "Cycle: \(Day.label(start)) – \(Day.label(end))"))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
            if let start = report.expenseCycle?.start, let end = report.expenseCycle?.end {
                Text(tx("Estado de cuenta: \(Day.label(start)) – \(Day.label(end))", "Statement: \(Day.label(start)) – \(Day.label(end))"))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
            FigureRow(label: tx("Ingresos esperados", "Expected income"), amount: report.income?.expectedTotal)
            FigureRow(label: tx("Ingresos recibidos", "Income received"), amount: report.income?.receivedFromTransactions)
            if let pending = report.income?.pendingProjection, pending > 0 {
                FigureRow(label: tx("Por recibir", "Still to come"), amount: pending)
            }
            FigureRow(label: tx("Gastos del período", "Spending this period"), amount: report.expenses?.spendingOnly)
            FigureRow(label: tx("Pagos de deudas", "Debt payments"), amount: report.expenses?.debtPayments)
            if let reserved = report.goals?.reservedCurrentPeriod, reserved > 0 {
                FigureRow(label: tx("Reservado para metas", "Set aside for goals"), amount: reserved)
            }
            FigureRow(label: tx("Saldo real", "Real balance"), amount: report.cashflow?.realBalance)
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("money.cycle")
    }
}

/// "Tus cuentas": the total that counts and one row per account.
private struct AccountsContent: View {
    let balances: AccountBalances
    let update: (AccountBalances.Account) -> Void
    let remove: (AccountBalances.Account) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(tx("Tus cuentas", "Your accounts")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
            FigureRow(label: tx("Total", "Total"), amount: balances.totalRealBalance, currency: balances.currency)
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("money.accounts")

        if balances.items.isEmpty {
            EmptyStateView(symbol: "building.columns", title: tx("Sin cuentas", "No accounts"),
                           message: tx("Con «+» agregás una cuenta y su saldo.", "Use “+” to add an account and its balance.")) { EmptyView() }
        }
        ForEach(balances.items) { account in
            AccountRow(account: account, update: { update(account) }, remove: { remove(account) })
        }
    }
}

private struct AccountRow: View {
    let account: AccountBalances.Account
    let update: () -> Void
    let remove: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text([account.accountName ?? tx("Cuenta", "Account"), account.accountLast4.map { "••\($0)" }].compactMap { $0 }.joined(separator: " "))
                        .font(DincrFont.body.weight(.semibold))
                    if let bank = account.bankName, !bank.isEmpty {
                        Text(bank).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                    }
                }
                Spacer()
                MoneyText(account.balance, currency: account.currency)
            }
            .accessibilityElement(children: .combine)
            if let asOf = account.balanceAsOf {
                Text(tx("Al \(Day.label(asOf))", "As of \(Day.label(asOf))")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
            if !account.includeInNetWorth {
                Text(tx("No suma a tu patrimonio", "Doesn’t count toward your net worth")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
            if account.isEditable {
                HStack(spacing: DincrSpacing.s2) {
                    Button(tx("Actualizar saldo", "Update balance"), action: update)
                        .buttonStyle(.dincrSecondary)
                        .accessibilityIdentifier("money.edit.\(account.id)")
                    Button(tx("Quitar", "Remove"), role: .destructive, action: remove)
                        .font(DincrFont.label).foregroundStyle(DincrColor.negative)
                        .accessibilityIdentifier("money.delete.\(account.id)")
                }
            }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("money.account.\(account.id)")
    }
}

/// "Nueva cuenta" / "Actualizar saldo": the account and the balance the Owner checked. An update keeps
/// the account's name and last 4 digits (they identify it). Saved once (disabled while it is sent),
/// never retried on its own.
private struct AccountForm: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let mode: MoneyView.FormMode
    let onDone: (String) -> Void
    @State private var name = ""
    @State private var bank = ""
    @State private var last4 = ""
    @State private var balance = ""
    @State private var currency = "CRC"
    @State private var type = "checking"
    @State private var includeInNetWorth = true
    @State private var error: String?
    @State private var saving = false

    private var existing: AccountBalances.Account? {
        switch mode {
        case .create: nil
        case .update(let account): account
        }
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(tx("Nombre de la cuenta", "Account name"), text: $name)
                        .disabled(existing != nil)
                        .accessibilityIdentifier("money.form.name")
                    TextField(tx("Banco (opcional)", "Bank (optional)"), text: $bank).accessibilityIdentifier("money.form.bank")
                    TextField(tx("Últimos 4 dígitos (opcional)", "Last 4 digits (optional)"), text: $last4)
                        .keyboardType(.numberPad)
                        .disabled(existing != nil)
                        .accessibilityIdentifier("money.form.last4")
                }
                Section {
                    TextField(tx("Saldo de hoy", "Today’s balance"), text: $balance).keyboardType(.decimalPad).accessibilityIdentifier("money.form.balance")
                    if let shown = existing?.balance {
                        Text(tx("Saldo que DINCR muestra: \(model.moneyFormat.string(shown, currency: existing?.currency))",
                                "Balance DINCR shows: \(model.moneyFormat.string(shown, currency: existing?.currency))"))
                            .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                    }
                    Picker(tx("Moneda", "Currency"), selection: $currency) {
                        ForEach(AccountBalanceRequest.currencies, id: \.self) { Text($0).tag($0) }
                    }
                    Picker(tx("Tipo", "Type"), selection: $type) {
                        ForEach(AccountBalanceRequest.accountTypes, id: \.self) { Text(Self.typeLabel($0)).tag($0) }
                    }
                    Toggle(tx("Suma a mi patrimonio", "Counts toward my net worth"), isOn: $includeInNetWorth)
                    if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
                }
            }
            .navigationTitle(existing == nil ? tx("Nueva cuenta", "New account") : tx("Actualizar saldo", "Update balance"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Guardar", "Save")) { Task { await submit() } }.disabled(saving).accessibilityIdentifier("money.form.save")
                }
            }
        }
        .interactiveDismissDisabled(saving)
        .onAppear(perform: prefill)
    }

    static func typeLabel(_ type: String) -> String {
        switch type {
        case "checking": tx("Cuenta corriente", "Checking")
        case "savings": tx("Ahorro", "Savings")
        case "credit_card": tx("Tarjeta de crédito", "Credit card")
        case "cash": tx("Efectivo", "Cash")
        default: tx("Otra", "Other")
        }
    }

    /// An update starts from the account as it is; the balance stays empty so the Owner writes the one
    /// checked today instead of confirming a figure DINCR calculated.
    private func prefill() {
        guard let account = existing else { return }
        name = account.accountName ?? ""
        bank = account.bankName ?? ""
        last4 = account.accountLast4 ?? ""
        if let value = account.currency?.uppercased(), AccountBalanceRequest.currencies.contains(value) { currency = value }
        if let value = account.accountType, AccountBalanceRequest.accountTypes.contains(value) { type = value }
        includeInNetWorth = account.includeInNetWorth
    }

    private func submit() async {
        guard !saving else { return }
        let accountName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let digits = last4.trimmingCharacters(in: .whitespaces)
        guard !accountName.isEmpty else { error = tx("Escribí el nombre de la cuenta.", "Enter the account name."); return }
        guard AccountBalanceRequest.isValidLast4(digits) else { error = tx("Los últimos dígitos son 4 números, o dejalo vacío.", "The last digits are 4 numbers, or leave it empty."); return }
        // The balance is never guessed: an empty or invalid field is not sent. 0 is a real balance.
        guard let amount = AmountInput.parseZeroOrMore(balance, separators: model.moneyFormat.separators) else {
            let example = model.moneyFormat.inputText(18_450)
            error = tx("Escribí el saldo, por ejemplo \(example).", "Enter the balance, for example \(example).")
            return
        }
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            try await model.service.saveAccountBalance(AccountBalanceRequest(
                accountName: accountName, currentBalance: amount, bankName: bank.trimmingCharacters(in: .whitespaces), accountLast4: digits,
                currency: currency, accountType: type, includeInNetWorth: includeInNetWorth))
            onDone(tx("Cuenta guardada", "Account saved"))
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardarla. Revisá tus cuentas antes de intentar de nuevo.", "We couldn’t save it. Check your accounts before trying again."))
        }
    }
}
