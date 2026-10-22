import DincrCore
import DincrDesign
import SwiftUI

/// Cuentas (VIP, `gmail_automation` and `vip_intelligence`; the Owner by role): the second surface of the Email Monitor's
/// review. Banks → accounts (`•••• last4`, currency, Es mía / No es mía) → their movements, read from
/// the SAME candidates with `/vip/gmail/emails?bank=` or `?financial_account_id=` and reviewed with
/// the same endpoints and states. Every screen reloads from the backend when it appears, so a notice
/// accepted here shows confirmed in the Email Monitor and vice versa. No balance is ever shown.
struct AccountsView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        if model.planTier != .vip {
            ScreenScroll(title: tx("Cuentas", "Accounts")) { PlanRequiredView(tier: .vip, feature: tx("Cuentas", "Accounts")) }
        } else if let paused = [OpsFlag.gmailAutomation, .vipIntelligence].first(where: { !model.flags.isEnabled($0) }) {
            // The backend pauses /vip/financial-identity under either switch: a paused state, not an error.
            ScreenScroll(title: tx("Cuentas", "Accounts")) { FeaturePausedView(message: model.flags.message(paused, language: model.language)) }
        } else {
            BankListView()
        }
    }
}

private struct BankListView: View {
    struct Snapshot: Equatable {
        let groups: [BankGroup]
    }

    @Environment(AppModel.self) private var model
    @State private var generation = 0
    @State private var appeared = false
    @State private var declaring = false
    @State private var notice: String?

    var body: some View {
        ScreenScroll(title: tx("Cuentas", "Accounts")) {
            Text(tx("Las cuentas que DINCR detectó en tus avisos bancarios. DINCR no ve saldos ni números completos.",
                    "The accounts DINCR detected in your bank notices. DINCR doesn’t see balances or full numbers."))
                .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
            // An own account no notice came from (the other bank of a transfer): marking it lets
            // DINCR recognise transfers between your accounts instead of offering them as spending.
            Button { declaring = true } label: { Label(tx("Agregar cuenta propia", "Add an own account"), systemImage: "plus.circle") }
                .buttonStyle(.dincrSecondary)
                .accessibilityIdentifier("accounts.declare")
            if let notice { StatusBanner(tone: .info, title: notice, message: "").accessibilityIdentifier("accounts.notice") }
            AsyncContent(load: { () async throws -> Snapshot in
                let service = model.service
                async let identity = service.financialIdentity()
                async let candidates = service.mailCandidates(pendingOnly: false)
                let loaded = try await identity
                let rows = try await candidates
                return Snapshot(groups: BankGroup.make(accounts: loaded.items ?? [], candidates: rows))
            }) { snapshot, _ in
                if snapshot.groups.isEmpty {
                    EmptyStateView(symbol: "building.columns", title: tx("Sin cuentas todavía", "No accounts yet"),
                                   message: tx("Cuando DINCR lea avisos de tus bancos, verás acá las cuentas que mencionan.",
                                               "When DINCR reads your bank notices, you’ll see the accounts they mention here.")) { EmptyView() }
                }
                ForEach(snapshot.groups) { group in
                    NavigationLink { BankDetailView(group: group) } label: { BankRow(group: group) }
                        .buttonStyle(.plain)
                        .dincrCard(padding: DincrSpacing.s3)
                        .accessibilityIdentifier("accounts.bank.\(group.id)")
                }
            }
            .id(generation)
        }
        // Back from a bank: reload, so reviews made elsewhere are reflected.
        .onAppear { if appeared { generation += 1 } else { appeared = true } }
        .sheet(isPresented: $declaring) {
            DeclareOwnAccountForm { message in notice = message; generation += 1 }
        }
    }
}

extension BankGroup {
    /// The detected account's label (`bank_name`) for display; codes are only used to query.
    var title: String { displayName ?? brand?.name ?? tx("Otras instituciones", "Other institutions") }
    /// The fallback glyph for "Otras instituciones".
    var logoBrand: BankBrand { brand ?? BankBrand.describe(nil) }
}

private struct BankRow: View {
    let group: BankGroup

    var body: some View {
        HStack(spacing: DincrSpacing.s3) {
            BankLogo(brand: group.logoBrand, size: 44)
            VStack(alignment: .leading, spacing: 2) {
                Text(group.title).font(DincrFont.body.weight(.semibold)).foregroundStyle(DincrColor.text)
                Text(tx("\(group.accounts.count) \(group.accounts.count == 1 ? "cuenta" : "cuentas")", "\(group.accounts.count) \(group.accounts.count == 1 ? "account" : "accounts")"))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                Text(tx("\(group.movements) movimientos · \(group.pending) por revisar", "\(group.movements) transactions · \(group.pending) to review"))
                    .font(DincrFont.caption).foregroundStyle(group.pending > 0 ? DincrColor.warning : DincrColor.textMuted)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(DincrColor.textMuted).accessibilityHidden(true)
        }
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

/// One bank: its accounts with the ownership answer, and every notice of the bank.
private struct BankDetailView: View {
    let group: BankGroup
    @Environment(AppModel.self) private var model
    @State private var accounts: [FinancialIdentity.Account]
    @State private var error: String?

    init(group: BankGroup) {
        self.group = group
        _accounts = State(initialValue: group.accounts)
    }

    var body: some View {
        ScreenScroll(title: group.title) {
            if let error { ErrorStateView(message: error) }
            SectionHeader(title: tx("Cuentas", "Accounts"))
            ForEach(accounts) { account in
                AccountCard(account: account, set: { ownership in Task { await setOwnership(account, ownership) } })
            }
            SectionHeader(title: tx("Movimientos", "Transactions"))
            CandidateReviewList(identifier: "bank.\(group.id)") {
                // "Otras instituciones" also holds notices linked to an unidentified account, which
                // `?bank=` cannot ask for: read the accounts and the inbox and keep this group's rows
                // (only rows with a candidate: an email row without one is not a movement).
                if group.isOther {
                    let service = model.service
                    async let identity = service.financialIdentity()
                    async let inbox = service.mailCandidates(pendingOnly: false)
                    let loaded = try await identity
                    let rows = try await inbox
                    return BankGroup.rows(of: group.id, accounts: loaded.items ?? [], candidates: rows)
                }
                // Known banks: `?bank=` with the institution CODE(s), never the display label.
                var rows: [MailCandidate] = []
                for code in group.bankCodes {
                    for candidate in try await model.service.mailCandidates(bank: code)
                    where candidate.candidateId != nil && !rows.contains(where: { $0.id == candidate.id }) {
                        rows.append(candidate)
                    }
                }
                return rows
            }
        }
    }

    private func setOwnership(_ account: FinancialIdentity.Account, _ ownership: AccountOwnership) async {
        let epoch = model.currentEpoch
        error = nil
        do {
            try await model.service.setAccountOwnership(id: account.id, ownership)
            // The backend's list is the source of truth: reload this bank's accounts from it.
            let identity = try await model.service.financialIdentity()
            guard epoch == model.currentEpoch else { return }
            let ids = Set(group.accounts.map(\.id))
            accounts = (identity.items ?? []).filter { ids.contains($0.id) }
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardarlo.", "We couldn’t save it."))
        }
    }
}

/// A detected account: masked number, currency and ownership. Opens its own movements.
private struct AccountCard: View {
    let account: FinancialIdentity.Account
    let set: (AccountOwnership) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            NavigationLink { AccountDetailView(account: account) } label: {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(account.accountName ?? tx("Cuenta", "Account")).font(DincrFont.body.weight(.semibold)).foregroundStyle(DincrColor.text)
                        Text([account.maskedNumber, account.currency].compactMap { $0 }.joined(separator: " · "))
                            .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(DincrColor.textMuted).accessibilityHidden(true)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("accounts.account.\(account.id)")
            OwnershipControl(account: account, set: set)
        }
        .dincrCard()
    }
}

/// The ownership answer of an account: Es mía / No es mía / No la reconozco, changeable at any time.
/// Only "Es mía" makes the account an end of a transfer between your accounts.
private struct OwnershipControl: View {
    let account: FinancialIdentity.Account
    let set: (AccountOwnership) -> Void

    var body: some View {
        HStack {
            switch account.ownership {
            case .own?: Label(tx("Es mía", "It’s mine"), systemImage: "checkmark.circle").foregroundStyle(DincrColor.positive)
            case .notMine?: Label(tx("No es mía", "Not mine"), systemImage: "xmark.circle").foregroundStyle(DincrColor.textMuted)
            case .unknown?: Label(tx("No la reconozco", "I don’t recognise it"), systemImage: "questionmark.circle").foregroundStyle(DincrColor.warning)
            case nil:
                Button(tx("Es mía", "It’s mine")) { set(.own) }.buttonStyle(.dincrSecondary)
                    .accessibilityIdentifier("accounts.own.\(account.id)")
                Button(tx("No es mía", "Not mine")) { set(.notMine) }.frame(minHeight: 44)
                    .accessibilityIdentifier("accounts.notMine.\(account.id)")
            }
            Spacer(minLength: 0)
            Menu {
                ForEach(AccountOwnership.allCases, id: \.self) { option in
                    if option != account.ownership { Button(option.title) { set(option) } }
                }
            } label: {
                Text(account.ownership == nil ? tx("Otra opción", "Other option") : tx("Cambiar", "Change")).frame(minHeight: 44)
            }
            .accessibilityIdentifier("accounts.change.\(account.id)")
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("accounts.ownership.\(account.id)")
    }
}

extension AccountOwnership {
    var title: String {
        switch self {
        case .own: tx("Es mía", "It’s mine")
        case .notMine: tx("No es mía", "Not mine")
        case .unknown: tx("No la reconozco", "I don’t recognise it")
        }
    }
}

/// "Agregar cuenta propia": institution, last 4 digits and currency of an own account no notice
/// came from. Only the last 4 digits are asked for (and stored).
private struct DeclareOwnAccountForm: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let onDone: (String) -> Void
    @State private var institution = "bac"
    @State private var institutionName = ""
    @State private var last4 = ""
    @State private var currency = "CRC"
    @State private var displayName = ""
    @State private var error: String?
    @State private var saving = false

    private var declaration: OwnAccountDeclaration {
        OwnAccountDeclaration(institutionCode: institution, institutionName: institutionName, accountLast4: last4,
                              currency: currency, displayName: displayName)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker(tx("Institución", "Institution"), selection: $institution) {
                        Text("BAC").tag("bac")
                        Text("Banco Popular").tag("popular")
                        Text("MultiMoney").tag("multimoney")
                        Text(tx("Otra", "Other")).tag("other")
                    }
                    .accessibilityIdentifier("declare.institution")
                    if institution == "other" {
                        TextField(tx("Nombre de la institución", "Institution name"), text: $institutionName)
                            .accessibilityIdentifier("declare.institutionName")
                    }
                    TextField(tx("Últimos 4 dígitos", "Last 4 digits"), text: $last4)
                        .keyboardType(.numberPad)
                        .onChange(of: last4) { _, value in last4 = String(value.filter(\.isNumber).prefix(4)) }
                        .accessibilityIdentifier("declare.last4")
                    Picker(tx("Moneda", "Currency"), selection: $currency) {
                        Text(tx("Colones", "Colones")).tag("CRC")
                        Text(tx("Dólares", "Dollars")).tag("USD")
                    }
                    .pickerStyle(.segmented)
                    .accessibilityIdentifier("declare.currency")
                    TextField(tx("Nombre (opcional)", "Name (optional)"), text: $displayName)
                } footer: {
                    Text(tx("Solo se guardan los últimos 4 dígitos. DINCR reconocerá las transferencias entre tus cuentas y no las contará como gastos ni ingresos.",
                            "Only the last 4 digits are stored. DINCR will recognise transfers between your accounts and won’t count them as spending or income."))
                }
                if let error { Section { Text(error).foregroundStyle(DincrColor.negative) } }
            }
            .navigationTitle(tx("Cuenta propia", "Own account"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Guardar", "Save")) { Task { await save() } }
                        .disabled(saving || !declaration.isComplete)
                        .accessibilityIdentifier("declare.save")
                }
            }
        }
        .interactiveDismissDisabled(saving)
    }

    private func save() async {
        let epoch = model.currentEpoch
        saving = true; error = nil
        defer { saving = false }
        do {
            try await model.service.declareOwnAccount(declaration)
            onDone(tx("Cuenta propia guardada", "Own account saved"))
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardarla.", "We couldn’t save it."))
        }
    }
}

/// One account's notices (`?financial_account_id=`).
private struct AccountDetailView: View {
    let account: FinancialIdentity.Account
    @Environment(AppModel.self) private var model

    var body: some View {
        ScreenScroll(title: account.accountName ?? tx("Cuenta", "Account")) {
            HStack(spacing: DincrSpacing.s3) {
                BankLogo(brand: account.brand, size: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text(account.brand.name.isEmpty ? tx("Institución", "Institution") : account.brand.name).font(DincrFont.body.weight(.semibold))
                    Text([account.maskedNumber, account.currency].compactMap { $0 }.joined(separator: " · "))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
            }
            .accessibilityElement(children: .combine)
            SectionHeader(title: tx("Movimientos", "Transactions"))
            CandidateReviewList(identifier: "account.\(account.id)") {
                try await model.service.mailCandidates(financialAccountID: account.id)
            }
        }
    }
}
