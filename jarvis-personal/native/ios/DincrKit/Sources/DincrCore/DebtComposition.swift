import Foundation

/// §15 PR 8 — Patrimonio → Deudas: how the active debts make up what is owed, from the balances
/// kept in Plan → Deudas (`remaining_amount`). Presentation only: nothing is computed but the shares
/// `Composition` allows. A paid debt (balance 0) is left out; a debt whose balance is unknown is kept
/// as unknown, so no share or total is drawn from it (never read as 0). Debts carry no currency of
/// their own: they are the account's base currency. Android: `com.dincr.data.DebtComposition`.
public enum DebtComposition {
    public static func of(_ debts: [Debt]) -> Composition {
        Composition(debts
            .filter { debt in debt.remainingAmount.map { $0 > 0 } ?? true }
            .map { CompositionItem(id: "debt-\($0.id)", label: $0.name ?? "", value: $0.remainingAmount) })
    }
}
