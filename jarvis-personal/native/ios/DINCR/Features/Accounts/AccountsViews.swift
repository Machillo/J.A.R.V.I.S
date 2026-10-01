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

    var body: some View {
        ScreenScroll(title: tx("Cuentas", "Accounts")) {
            Text(tx("Las cuentas que DINCR detectó en tus avisos bancarios. DINCR no ve saldos ni números completos.",
                    "The accounts DINCR detected in your bank notices. DINCR doesn’t see balances or full numbers."))
                .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
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
                AccountCard(account: account, set: { own in Task { await setOwnership(account, own) } })
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

    private func setOwnership(_ account: FinancialIdentity.Account, _ own: Bool) async {
        let epoch = model.currentEpoch
        error = nil
        do {
            try await model.service.setAccountOwnership(id: account.id, own: own)
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
    let set: (Bool) -> Void

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

/// The existing "Es mía / No es mía" answer of the detected accounts.
private struct OwnershipControl: View {
    let account: FinancialIdentity.Account
    let set: (Bool) -> Void

    var body: some View {
        switch account.ownershipStatus {
        case "own": Label(tx("Es mía", "It’s mine"), systemImage: "checkmark.circle").foregroundStyle(DincrColor.positive)
        case "not_mine": Label(tx("No es mía", "Not mine"), systemImage: "xmark.circle").foregroundStyle(DincrColor.textMuted)
        default:
            HStack {
                Button(tx("Es mía", "It’s mine")) { set(true) }.buttonStyle(.dincrSecondary)
                    .accessibilityIdentifier("accounts.own.\(account.id)")
                Button(tx("No es mía", "Not mine")) { set(false) }.frame(minHeight: 44)
                    .accessibilityIdentifier("accounts.notMine.\(account.id)")
            }
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
