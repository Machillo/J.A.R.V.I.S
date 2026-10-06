import Foundation
import Testing
@testable import DincrCore

/// A debt's unknown interest rate is not 0% (debts.interest_rate_known): the edit form starts an
/// unknown rate empty, an edit confirms the rate only when the user touched it, and VIP asks for the
/// missing rates (`debt_interest_rates`) instead of naming a debt. Android twin:
/// `DebtInterestRateTest.kt`. Synthetic data.
@Suite struct DebtInterestRateTests {
    private func debt(_ json: String) throws -> Debt { try APIClient.decoder.decode(Debt.self, from: Data(json.utf8)) }

    @Test func anUnknownRateStartsEmptyNeverZero() throws {
        #expect(try debt(#"{"id":1,"remaining_amount":1000,"interest_rate":0,"interest_rate_known":false}"#).rateForEditing == nil)
        #expect(try debt(#"{"id":1,"remaining_amount":1000,"interest_rate":0,"interest_rate_known":true}"#).rateForEditing == 0)
        #expect(try debt(#"{"id":1,"remaining_amount":1000,"interest_rate":24,"interest_rate_known":true}"#).rateForEditing == 24)
        // An older server (no flag): the stored rate as before.
        #expect(try debt(#"{"id":1,"remaining_amount":1000,"interest_rate":18}"#).rateForEditing == 18)
    }

    @Test func anEditConfirmsTheRateOnlyWhenTheUserTouchedIt() throws {
        #expect(!DebtRequest.rateConfirmed(initial: "", current: ""))
        #expect(!DebtRequest.rateConfirmed(initial: "24", current: " 24 "))
        #expect(DebtRequest.rateConfirmed(initial: "", current: "0"))       // an unknown rate typed as 0%
        #expect(DebtRequest.rateConfirmed(initial: "24", current: "21"))
        #expect(DebtRequest.rateConfirmed(initial: "24", current: ""))      // cleared
    }

    @Test func theConfirmationIsSentOnlyWhenSet() throws {
        let edit = DebtRequest(name: "Tarjeta", remainingAmount: 1000, totalAmount: nil, monthlyPayment: nil, interestRate: 0, interestRateConfirmed: true)
        let body = String(decoding: try APIClient.encoder.encode(edit), as: UTF8.self)
        #expect(body.contains(#""interest_rate_confirmed":true"#) && body.contains(#""interest_rate":0"#))
        let create = DebtRequest(name: "Tarjeta", remainingAmount: 1000, totalAmount: nil, monthlyPayment: nil)
        #expect(!String(decoding: try APIClient.encoder.encode(create), as: UTF8.self).contains("interest_rate"))  // no rate: unknown
    }

    @Test func vipAsksForTheMissingRatesInsteadOfNamingADebt() throws {
        let center = try APIClient.decoder.decode(CommandCenter.self, from: Data(#"""
        {"safe_to_spend":{"amount":118000,"monthly_margin":214000,"next_45_days_minimum":96000,"missing":[]},
         "director":{"priority":"debt","headline":"Completá las tasas de interés para saber qué deuda atacar primero","missing":["debt_interest_rates"]},
         "alerts":[]}
        """#.utf8))
        let home = HomeToday.vip(center, budget: nil, calendar: nil, debts: [])
        #expect(home.status.amount == 118000)  // safe to spend doesn't use rates
        #expect(home.next.kind == .needsInformation && home.next.missing == [.debtInterestRates])
        #expect(home.next.destination == .debts)
        #expect(HomeInput.debtInterestRates.destination == .debts)
    }

    @Test func theVipPlanCarriesBasicsWarningAndTheMissingCode() throws {
        let plan = try APIClient.decoder.decode(DashboardStrategy.self, from: Data(#"""
        {"scope":"users","warnings":["Falta la tasa de interés de 1 deuda; la prioridad usa los datos disponibles."],"missing":["debt_interest_rates"]}
        """#.utf8))
        #expect(plan.warnings?.first?.hasPrefix("Falta la tasa de interés") == true)
        #expect(plan.needsDebtRates)
        let complete = try APIClient.decoder.decode(DashboardStrategy.self, from: Data(#"{"scope":"users","warnings":[],"missing":[]}"#.utf8))
        #expect(!complete.needsDebtRates)
    }
}
