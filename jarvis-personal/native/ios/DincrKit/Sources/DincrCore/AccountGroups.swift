import Foundation

/// Cuentas: the detected accounts grouped by bank, the second surface of the Email Monitor's review
/// (the same candidates, endpoints and states). It never shows a balance: a detected account's
/// `current_balance` is unknown, not zero, so it is not even decoded. Android twin: `AccountGroups.kt`.
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
    /// The institution codes to ask `/vip/gmail/emails?bank=` with (never empty or `unknown`).
    public let bankCodes: [String]
    /// Notices of this bank (any state) and those still pending, from the shared candidate list.
    public let movements: Int
    public let pending: Int

    public var isOther: Bool { brand == nil }

    /// A usable institution code: trimmed, lowercased; nil when empty or `unknown`.
    public static func code(_ raw: String?) -> String? {
        let value = (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return value.isEmpty || value == "unknown" ? nil : value
    }

    /// The group of a detected account: its institution code, else its label.
    public static func groupID(of account: FinancialIdentity.Account) -> String {
        let brand = BankBrand.identify(Self.code(account.institutionCode)) ?? BankBrand.identify(account.bankName)
        return brand?.id ?? otherID
    }

    /// The group of a notice, from its own `bank` code (unknown, empty or unrecognized → "other").
    public static func groupID(of candidate: MailCandidate) -> String {
        BankBrand.identify(Self.code(candidate.bank))?.id ?? otherID
    }

    /// Whether a notice is listed under this group (the same rule the counts use).
    public func contains(_ candidate: MailCandidate) -> Bool { Self.groupID(of: candidate) == id }

    /// Groups in a stable order: known banks by name, then "Otras instituciones". A bank with notices
    /// but no detected account still gets its group.
    public static func make(accounts: [FinancialIdentity.Account], candidates: [MailCandidate]) -> [BankGroup] {
        var order: [String] = []
        var members: [String: [FinancialIdentity.Account]] = [:]
        var codes: [String: [String]] = [:]
        func note(_ group: String, _ institution: String?) {
            if members[group] == nil { order.append(group); members[group] = [] }
            if let institution, !(codes[group] ?? []).contains(institution) { codes[group, default: []].append(institution) }
        }
        for account in accounts {
            let group = Self.groupID(of: account)
            note(group, Self.code(account.institutionCode) ?? (group == otherID ? nil : group))
            members[group, default: []].append(account)
        }
        for candidate in candidates {
            note(Self.groupID(of: candidate), Self.code(candidate.bank))
        }
        let groups = order.map { group -> BankGroup in
            let brand = group == otherID ? nil : BankBrand.identify(group)
            let own = members[group] ?? []
            let label = own.compactMap { $0.bankName?.trimmingCharacters(in: .whitespacesAndNewlines) }.first { !$0.isEmpty }
            let mine = candidates.filter { Self.groupID(of: $0) == group }
            return BankGroup(id: group, brand: brand, displayName: brand == nil ? nil : (label ?? brand?.name), accounts: own,
                             bankCodes: codes[group] ?? [], movements: mine.count, pending: mine.filter(\.isPending).count)
        }
        return groups.sorted { lhs, rhs in
            if lhs.isOther != rhs.isOther { return !lhs.isOther }
            return (lhs.displayName ?? "").localizedCaseInsensitiveCompare(rhs.displayName ?? "") == .orderedAscending
        }
    }
}
