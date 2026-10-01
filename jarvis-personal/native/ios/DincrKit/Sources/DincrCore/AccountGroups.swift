import Foundation

/// Cuentas: the detected accounts grouped by bank, the second surface of the Email Monitor's review
/// (the same candidates, endpoints and states). It never shows a balance: a detected account's
/// `current_balance` is unknown, not zero, so it is not even decoded. Android twin: `Accounts.kt`
/// (same rule, same order: the same input gives the same groups).
///
/// Banks are keyed by the institution CODE, never by the display label: a candidate's `bank` holds
/// the parser's code (`bac`, `popular`, `multimoney`) while a detected account holds a label in
/// `bank_name` ("BAC", "Banco Popular") and the code in `institution_code`
/// (`financial_identity._institution_label`). `/vip/gmail/emails?bank=` matches the candidate's
/// stored value, so it is always asked with codes; labels are only displayed.
public struct BankGroup: Sendable, Equatable, Identifiable {
    /// The id of the group of banks DINCR does not recognize ("Otras instituciones").
    public static let otherID = "other"

    public let id: String
    /// Nil for "Otras instituciones" (the screen shows the fallback glyph and that title).
    public let brand: BankBrand?
    /// The label to show: the detected account's `bank_name` when there is one, else the brand's name.
    public let displayName: String?
    public let accounts: [FinancialIdentity.Account]
    /// The `bank=` filters of `/vip/gmail/emails`: the candidates' own `bank` and the accounts'
    /// `institution_code` (trimmed, non-empty, once each); never `bank_name`.
    public let bankCodes: [String]
    /// Notices of this bank (any state) and those still pending, from the shared candidate list.
    public let movements: Int
    public let pending: Int

    public var isOther: Bool { brand == nil }

    /// The group of a detected account: its `institution_code`; its `bank_name` only without a code.
    public static func groupID(of account: FinancialIdentity.Account) -> String {
        let code = account.institutionCode?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let brand = code.isEmpty ? BankBrand.identify(account.bankName) : BankBrand.identify(code)
        return brand?.id ?? otherID
    }

    /// The group of a notice: its own `bank` code when DINCR identifies it; else the bank of the
    /// detected account it is linked to; else "Otras instituciones" when it names some institution.
    /// Nil (no bank, no account): it is only in the Email Monitor.
    public static func groupID(of candidate: MailCandidate, accounts: [FinancialIdentity.Account]) -> String? {
        if let known = BankBrand.identify(candidate.bank) { return known.id }
        if let linked = candidate.financialAccountId, let account = accounts.first(where: { $0.id == linked }) { return groupID(of: account) }
        let bank = candidate.bank?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return bank.isEmpty ? nil : otherID
    }

    /// The movements a group lists: notices with a candidate (an email row without one is not a movement).
    public static func rows(of group: String, accounts: [FinancialIdentity.Account], candidates: [MailCandidate]) -> [MailCandidate] {
        candidates.filter { $0.candidateId != nil && groupID(of: $0, accounts: accounts) == group }
    }

    /// Known banks in their historical order (`BankBrand.identities`, the web app's), then "Otras
    /// instituciones". A known bank with notices but no detected account still gets its group.
    public static func make(accounts: [FinancialIdentity.Account], candidates: [MailCandidate]) -> [BankGroup] {
        var byAccount: [String: [FinancialIdentity.Account]] = [:]
        for account in accounts { byAccount[groupID(of: account), default: []].append(account) }
        var byCandidate: [String: [MailCandidate]] = [:]
        for candidate in candidates {
            if let group = groupID(of: candidate, accounts: accounts) { byCandidate[group, default: []].append(candidate) }
        }
        let order = BankBrand.identities.map(\.id) + [otherID]
        return order.filter { byAccount[$0] != nil || byCandidate[$0] != nil }.map { group -> BankGroup in
            let own = byAccount[group] ?? []
            let mine = byCandidate[group] ?? []
            var codes: [String] = []
            for raw in mine.map(\.bank) + own.map(\.institutionCode) {
                let code = raw?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                if !code.isEmpty, !codes.contains(where: { $0.lowercased() == code.lowercased() }) { codes.append(code) }
            }
            let brand = group == otherID ? nil : BankBrand.identify(group)
            let label = own.compactMap { $0.bankName?.trimmingCharacters(in: .whitespacesAndNewlines) }.first { !$0.isEmpty }
            return BankGroup(id: group, brand: brand, displayName: brand == nil ? nil : (label ?? brand?.name), accounts: own,
                             bankCodes: codes, movements: mine.count, pending: mine.filter(\.isPending).count)
        }
    }
}
