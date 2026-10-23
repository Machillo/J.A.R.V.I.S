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

    // CONFIRMAR -----------------------------------------------------------------------------------

    private func dashboard() throws -> StrategyDashboard {
        try APIClient.decoder.decode(StrategyDashboard.self, from: Data(#"""
        {"strategy":{"scope":"owner","distribution_source":"manual_amount","allocation_base_amount":254698,
          "allocation_items":[{"key":"ataque_de_deuda","amount":114614.10},{"key":"fondo_de_emergencia","amount":101879.20},
                              {"key":"vida_controlada","amount":38204.70}]},
         "confirmation_plan":{"confirmable":true,"blocking_reasons":[],"steps":[
           {"key":"ataque_de_deuda","amount":114614.10,"action":"debt_extra_payment",
            "targets":[{"debt_id":2,"name":"Tarjeta de ejemplo","amount":60000},{"debt_id":1,"name":"Préstamo de ejemplo","amount":54614.10}]},
           {"key":"fondo_de_emergencia","amount":101879.20,"action":"salvavidas_deposit"},
           {"key":"vida_controlada","amount":38204.70,"action":"not_recorded"}]}}
        """#.utf8))
    }

    @Test func aCalculatedResultCarriesWhatConfirmWouldRecord() throws {
        let answer = try dashboard()
        var form = ExactDistributionForm()
        form.edit("254698")
        form.calculated(for: "254698", answer.strategy, plan: answer.confirmationPlan, key: "confirm-ios-0001")
        #expect(form.canConfirm)
        #expect(form.plan?.steps.map(\.action) == ["debt_extra_payment", "salvavidas_deposit", "not_recorded"])
        #expect(form.plan?.steps.first?.targets.map(\.name) == ["Tarjeta de ejemplo", "Préstamo de ejemplo"])
    }

    @Test func confirmSendsTheReviewedSplitAndIsOfferedOnce() throws {
        let answer = try dashboard()
        var form = ExactDistributionForm()
        form.edit("254698")
        form.calculated(for: "254698", answer.strategy, plan: answer.confirmationPlan, key: "confirm-ios-0002")
        let request = try #require(form.confirmRequest(amount: 254698))
        let body = String(decoding: try APIClient.encoder.encode(request), as: UTF8.self)
        #expect(body.contains(#""confirmation_key":"confirm-ios-0002""#))
        #expect(body.contains(#""expected_items""#) && body.contains(#""currency":"CRC""#))
        #expect(request.expectedItems.map(\.key) == ["ataque_de_deuda", "fondo_de_emergencia", "vida_controlada"])
        form.confirmed(key: "another-key", ExactDistributionConfirmation(status: "applied"))
        #expect(form.canConfirm)  // an answer for another result is ignored
        form.confirmed(key: "confirm-ios-0002", ExactDistributionConfirmation(status: "applied"))
        #expect(!form.canConfirm)
        form.edit("300000")
        #expect(form.confirmationKey == nil && !form.canConfirm)
    }

    @Test func aPlanThatCannotBeRecordedOffersNoConfirm() throws {
        let plan = try APIClient.decoder.decode(ConfirmationPlan.self, from: Data(#"""
        {"confirmable":false,"blocking_reasons":["La parte para deudas es mayor que lo que se debe."],"steps":[]}
        """#.utf8))
        var form = ExactDistributionForm()
        form.edit("1")
        form.calculated(for: "1", try answer(), plan: plan)
        #expect(!form.canConfirm)
        #expect(form.plan?.blockingReasons.count == 1)
    }
}
