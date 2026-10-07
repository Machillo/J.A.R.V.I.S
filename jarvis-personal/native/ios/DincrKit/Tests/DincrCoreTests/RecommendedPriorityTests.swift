import Foundation
import Testing
@testable import DincrCore

/// UX-8 — "Recomendación de DINCR" reads the engines' own priority and why, never a new rule.
/// Android twin: `RecommendedPriorityTest.kt`. Synthetic data.
@Suite struct RecommendedPriorityTests {
    private func basic(_ json: String) throws -> PlanStrategy { .basic(try APIClient.decoder.decode(Strategy.self, from: Data(json.utf8))) }
    private func dashboard(_ json: String) throws -> PlanStrategy { .dashboard(try APIClient.decoder.decode(StrategyDashboard.self, from: Data(json.utf8))) }

    @Test func basicShowsTheEnginesPriorityAndItsOwnReason() throws {
        let priority = try #require(RecommendedPriority.of(try basic(#"{"status":"healthy","priority":"debt","recommendation":"Cubrí tus compromisos y dirigí el excedente a Tarjeta."}"#), language: .spanish))
        #expect(priority.title == "Pagar deudas" && priority.why == "Cubrí tus compromisos y dirigí el excedente a Tarjeta.")
    }

    @Test func basicWithoutIncomeOrWithAnUnknownCodeShowsNothing() throws {
        #expect(RecommendedPriority.of(try basic(#"{"status":"needs_income","priority":"income","recommendation":"Registrá tus ingresos."}"#)) == nil)
        #expect(RecommendedPriority.of(try basic(#"{"status":"healthy","priority":"something_new"}"#)) == nil)
    }

    @Test func aCriticalBasicMonthKeepsItsMessageOnce() throws {
        let priority = try #require(RecommendedPriority.of(try basic(#"{"status":"critical","priority":"stabilize","recommendation":"Tus compromisos superan el ingreso."}"#), language: .spanish))
        #expect(priority.title == "Estabilizar tu mes" && priority.why == nil)
    }

    @Test func vipShowsTheDashboardPriorityTitleAndDetail() throws {
        let priority = try #require(RecommendedPriority.of(try dashboard(#"""
        {"strategy":{"scope":"users","status":"healthy","priority":{"kind":"debt","title":"Atacar deuda: Tarjeta","detail":"El sobrante destinado a deuda se concentra primero en esta obligación."}}}
        """#)))
        #expect(priority.title == "Atacar deuda: Tarjeta" && priority.why?.hasPrefix("El sobrante") == true)
    }

    @Test func vipWithoutIncomeOrPriorityShowsNothing() throws {
        #expect(RecommendedPriority.of(try dashboard(#"{"strategy":{"scope":"users","status":"needs_income","priority":{"kind":"cash","title":"X"}}}"#)) == nil)
        #expect(RecommendedPriority.of(try dashboard(#"{"strategy":{"scope":"users","status":"healthy"}}"#)) == nil)
    }
}
