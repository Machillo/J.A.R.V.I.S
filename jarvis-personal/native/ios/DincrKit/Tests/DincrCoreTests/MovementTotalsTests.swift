import DincrCore
import Foundation
import Testing

@Suite struct MovementTotalsTests {
    private func row(_ id: String, _ amount: Decimal, _ type: Movement.Kind, countsIn: String? = nil) -> Movement {
        var row = Movement(movementId: id, transactionDate: "2026-11-02", description: id, amount: amount, transactionType: type, category: nil)
        row.countsIn = countsIn
        return row
    }

    @Test func aPublicPlanAddsUpIncomeAndExpenses() {
        let totals = MovementTotals([row("a", 100, .income), row("b", 30, .expense), row("c", 20, .expense)])
        #expect(totals.income == 100 && totals.expenses == 50 && totals.debtPaid == nil && totals.result == 50)
    }

    @Test func noRowOfAKindIsUnknownNeverZero() {
        let totals = MovementTotals([row("b", 30, .expense)])
        #expect(totals.income == nil && totals.expenses == 30 && totals.result == nil)
    }

    @Test func theOwnersRowsCountAsHisLedgerSays() {
        let totals = MovementTotals([
            row("salary", 100, .income, countsIn: "income"), row("card", 40, .expense, countsIn: "expenses"),
            row("back", 5, .income, countsIn: "refunds"), row("loan", 10, .expense, countsIn: "debt_payments"),
            row("own", 900, .expense, countsIn: "not_counted"), row("lent", 70, .income, countsIn: "other_inflows"),
        ])
        #expect(totals.income == 100 && totals.expenses == 35 && totals.debtPaid == 10 && totals.result == 55)
    }

    @Test func refundsNeverTakeSpendingBelowZero() {
        #expect(MovementTotals([row("back", 5, .income, countsIn: "refunds")]).expenses == 0)
    }
}
