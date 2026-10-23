import Foundation
import Testing
@testable import DincrCore

/// The Owner's exact-amount form: a result never outlives the amount it was calculated from.
/// Android: OwnerExactDistributionTest (ExactDistributionForm).
struct ExactDistributionFormTests {
    private func answer() throws -> DashboardStrategy {
        try APIClient.decoder.decode(DashboardStrategy.self, from: Data(#"""
        {"scope":"owner","distribution_source":"manual_amount","allocation_base_amount":250000,
         "distribution_formula":{"manual_available":250000,"surplus":250000}}
        """#.utf8))
    }

    @Test func editingTheAmountDropsTheResultOfThePreviousOne() throws {
        let strategy = try answer()
        var form = ExactDistributionForm()
        form.edit("250000")
        form.calculated(for: "250000", strategy)
        #expect(form.result == strategy)
        #expect(form.result?.isManualAmount == true)
        form.edit("300000")
        #expect(form.result == nil)
        #expect(form.amountText == "300000")
        form.error = "x"
        form.edit("1")
        #expect(form.error == nil)
    }

    @Test func aLateAnswerForAnEarlierAmountIsIgnored() throws {
        var form = ExactDistributionForm()
        form.edit("300000")
        form.calculated(for: "250000", try answer())
        #expect(form.result == nil)
        #expect(form.amountText == "300000")
    }

    @Test func theExactFormulaListsOnlyTheTypedAmountAndTheSurplus() throws {
        let lines = try answer().distributionFormula?.lines.map(\.key)
        #expect(lines == ["manual_available", "surplus"])
    }
}
