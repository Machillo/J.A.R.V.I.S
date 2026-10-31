import Foundation

// WE-2 — Patrimonio (VIP and the Owner): what you have and what you owe
// (`GET /user-product/vip/wealth`). The backend counts every part; net worth is nil while any
// part is unknown (named in `unknown`), never computed as if it were 0. Android twin: `Wealth.kt`.

public struct Wealth: Decodable, Sendable, Equatable {
    public struct Item: Decodable, Sendable, Equatable {
        public let name: String?
        public let amount: Decimal?
        public let currency: String?
        public let originalAmount: Decimal?

        public init(name: String?, amount: Decimal?, currency: String? = nil, originalAmount: Decimal? = nil) {
            self.name = name; self.amount = amount; self.currency = currency; self.originalAmount = originalAmount
        }
    }

    public struct Assets: Decodable, Sendable, Equatable {
        public let accounts: [Item]?
        public let salvavidas: Item?
        public let investments: [Item]?
        public let total: Decimal?
    }

    public struct Liabilities: Decodable, Sendable, Equatable {
        public let debts: [Item]?
        public let accounts: [Item]?
        public let total: Decimal?
    }

    public let assets: Assets?
    public let liabilities: Liabilities?
    public let netWorth: Decimal?
    public let complete: Bool?
    public let unknown: [String]?

    /// What you have, in the order the screen lists it: accounts, the Salvavidas, investments.
    public var owned: [Item] {
        (assets?.accounts ?? []) + (assets?.salvavidas.map { [$0] } ?? []) + (assets?.investments ?? [])
    }

    /// What you owe: the debts (one line with their total) and any overdrawn account.
    public func owed(language: AppLanguage = .current) -> [Item] {
        let debts = liabilities?.debts ?? []
        let debtLine: [Item] = debts.isEmpty ? [] : [Item(name: language.pick("Deudas", "Debts"),
                                                          amount: debts.contains { $0.amount == nil } ? nil : debts.reduce(Decimal(0)) { $0 + ($1.amount ?? 0) })]
        return debtLine + (liabilities?.accounts ?? [])
    }

    /// "Falta el saldo de: X, Y." when net worth cannot be known yet; nil when it is complete.
    public func missingNotice(language: AppLanguage = .current) -> String? {
        guard let unknown, !unknown.isEmpty else { return nil }
        return language.pick("Falta el saldo de: \(unknown.joined(separator: ", ")). Cuando lo tengamos, te mostramos tu patrimonio neto.",
                             "Missing the balance of: \(unknown.joined(separator: ", ")). Once we have it, we show your net worth.")
    }
}

extension DincrService {
    /// VIP and the Owner. A read: it never writes.
    public func wealth() async throws -> Wealth { try await client.get("/user-product/vip/wealth") }
}
