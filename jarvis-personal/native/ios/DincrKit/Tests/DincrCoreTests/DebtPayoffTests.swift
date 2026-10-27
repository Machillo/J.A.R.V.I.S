import Foundation
import Testing
@testable import DincrCore

/// When the debts are expected to be paid off (the backend's debt_payoff.py estimate per debt).
/// The app never calculates a date: the debt-free month is the latest of the backend's, and only
/// when every unpaid debt has one. Android: `DebtPayoffTest`. Synthetic data only.
struct DebtPayoffTests {
    private func debts(_ json: String) throws -> [Debt] {
        try APIClient.decoder.decode([Debt].self, from: Data(json.utf8))
    }

    @Test func theEstimateIsReadFromTheDebtsList() throws {
        let list = try debts("""
        [{"id":1,"remaining_amount":100000,"estimated_payoff_months":12,"estimated_payoff_date":"2027-10-05"},
         {"id":2,"remaining_amount":50000,"estimated_payoff_months":null,"estimated_payoff_date":null},
         {"id":3,"remaining_amount":50000}]
        """)
        #expect(list[0].estimatedPayoffMonths == 12 && list[0].estimatedPayoffDate == "2027-10-05")
        #expect(list[1].estimatedPayoffMonths == nil && list[1].estimatedPayoffDate == nil)
        #expect(list[2].estimatedPayoffDate == nil, "an older server sends nothing: no date")
    }

    @Test func theDebtFreeMonthIsTheLatestWhenEveryUnpaidDebtHasOne() throws {
        let list = try debts("""
        [{"id":1,"remaining_amount":100000,"estimated_payoff_date":"2027-10-05"},
         {"id":2,"remaining_amount":20000,"estimated_payoff_date":"2028-03-01"},
         {"id":3,"remaining_amount":0,"estimated_payoff_months":0}]
        """)
        #expect(DebtPayoff.summary(list) == .init(debtFreeDate: "2028-03-01", unestimated: 0, active: 2))
    }

    @Test func oneUnknownDebtLeavesNoDebtFreeMonthAndIsCounted() throws {
        let list = try debts("""
        [{"id":1,"remaining_amount":100000,"estimated_payoff_date":"2027-10-05"},
         {"id":2,"remaining_amount":20000,"estimated_payoff_date":null}]
        """)
        #expect(DebtPayoff.summary(list) == .init(debtFreeDate: nil, unestimated: 1, active: 2))
    }

    @Test func withNoUnpaidDebtsThereIsNothingToSay() throws {
        #expect(DebtPayoff.summary(try debts(#"[{"id":1,"remaining_amount":0}]"#)).active == 0)
        #expect(DebtPayoff.summary([]).active == 0)
    }

    @Test func theMonthReadsByNameAndYear() {
        #expect(DebtPayoff.monthLabel("2027-10-05", language: .spanish) == "oct 2027")
        #expect(DebtPayoff.monthLabel("2028-03-01", language: .english) == "Mar 2028")
    }
}
