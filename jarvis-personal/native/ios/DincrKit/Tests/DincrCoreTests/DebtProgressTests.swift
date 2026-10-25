import Foundation
import Testing
@testable import DincrCore

/// How much of the debts has been paid (original − remaining, the backend's amounts) and the
/// strategy's debt-free date. Unknown ≠ 0: no original amount, no progress; one unknown debt, no
/// total. Android: `DebtProgressTest`. Synthetic data only.
struct DebtProgressTests {
    private func debts(_ json: String) throws -> [Debt] {
        try APIClient.decoder.decode([Debt].self, from: Data(json.utf8))
    }

    @Test func oneDebtPaidAndLeft() throws {
        let debt = try #require(try debts(#"[{"id":1,"total_amount":200000,"remaining_amount":150000}]"#).first)
        let amounts = try #require(DebtProgress.of(debt))
        #expect(amounts.paid == 50_000 && amounts.original == 200_000)
        #expect(amounts.progress.fraction == 0.25)
        #expect(amounts.remainingFraction == 0.75)
    }

    @Test func anUnknownOriginalAmountHasNoProgress() throws {
        let list = try debts(#"[{"id":1,"remaining_amount":150000},{"id":2,"total_amount":0,"remaining_amount":10},{"id":3,"total_amount":100}]"#)
        #expect(list.allSatisfy { DebtProgress.of($0) == nil })
    }

    @Test func theTotalAddsEveryDebtIncludingPaidOnes() throws {
        let list = try debts("""
        [{"id":1,"total_amount":200000,"remaining_amount":150000},
         {"id":2,"total_amount":100000,"remaining_amount":0},
         {"id":3,"total_amount":100000,"remaining_amount":130000}]
        """)
        let total = try #require(DebtProgress.total(list))
        // 50 000 + 100 000 + 0 (a balance above the original is never negative progress).
        #expect(total.paid == 150_000 && total.original == 400_000)
        #expect(total.remainingFraction == 0.625)
    }

    @Test func oneUnknownDebtLeavesNoTotal() throws {
        let list = try debts(#"[{"id":1,"total_amount":200000,"remaining_amount":150000},{"id":2,"remaining_amount":5000}]"#)
        #expect(DebtProgress.total(list) == nil)
        #expect(DebtProgress.total([]) == nil)
    }

    @Test func theStrategyDateComesOnlyFromADashboard() throws {
        let dashboard = try APIClient.decoder.decode(StrategyDashboard.self, from: Data("""
        {"status":"OK","strategy":{"scope":"owner","estimated_debt_free_date":"2028-06-01","months_saved_by_current_extras":3}}
        """.utf8))
        #expect(DebtProgress.strategyDate(.dashboard(dashboard)) == .init(date: "2028-06-01", monthsSaved: 3, needsRates: false))
        let waiting = try APIClient.decoder.decode(StrategyDashboard.self, from: Data("""
        {"status":"OK","strategy":{"scope":"users","estimated_debt_free_date":null,"missing":["debt_interest_rates"]}}
        """.utf8))
        #expect(DebtProgress.strategyDate(.dashboard(waiting)) == .init(date: nil, monthsSaved: nil, needsRates: true))
        #expect(DebtProgress.strategyDate(nil) == nil)
    }
}
