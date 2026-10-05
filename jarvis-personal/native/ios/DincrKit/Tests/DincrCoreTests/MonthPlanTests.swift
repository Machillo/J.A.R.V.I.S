import Foundation
import Testing
@testable import DincrCore

/// "Tu plan del mes" (UX-3) is a reading of the strategy answer, never a new calculation. Android
/// checks the same rules in `MonthPlanTest.kt`; plan gating stays `StrategySource`
/// (`PlanAccountsTests.strategySourceFollowsTheServerRoleAndPlan`).
@Suite struct MonthPlanTests {
    private func basic(_ json: String) throws -> PlanStrategy {
        .basic(try APIClient.decoder.decode(Strategy.self, from: Data(json.utf8)))
    }

    private func dashboard(_ strategy: String?) throws -> PlanStrategy {
        let body = strategy.map { #"{"status":"OK","title":"T","content":"C","strategy":\#($0)}"# } ?? #"{"status":"OK","content":"Sin datos"}"#
        return .dashboard(try APIClient.decoder.decode(StrategyDashboard.self, from: Data(body.utf8)))
    }

    // MARK: Complete data

    @Test func basicPlanReadsTheMarginItsSplitAndTheRecommendation() throws {
        let plan = MonthPlan(try basic(#"""
            {"status":"tight","strategic_margin":214000,"recommendation":"Destiná ₡100.000 a la tarjeta.",
             "allocations":[{"bucket":"emergency","label":"Fondo de emergencia","amount":60000},
                            {"bucket":"debt_extra","label":"Extra a la tarjeta","amount":100000},
                            {"bucket":"flex","label":"Libre","amount":54000}],"income_source":"observed"}
            """#))
        #expect(plan.kind == .basic)
        #expect(plan.base == 214_000)
        #expect(plan.parts.map(\.label) == ["Fondo de emergencia", "Extra a la tarjeta", "Libre"])
        #expect(plan.parts.map(\.amount) == [60_000, 100_000, 54_000])
        #expect(plan.headline == "Destiná ₡100.000 a la tarjeta.")
        #expect(plan.usesObservedIncome && !plan.isCritical && !plan.needsIncome)
        #expect(plan.showsComposition)                     // 60.000 + 100.000 + 54.000 = 214.000
        #expect(plan.composition.total == 214_000)
    }

    @Test func dashboardPlanReadsTheSurplusItsSplitAndThePriority() throws {
        let plan = MonthPlan(try dashboard(#"""
            {"scope":"users","status":"controlled","objective":"Modo ataque de deuda.",
             "priority":{"kind":"debt","title":"Atacar deuda: Tarjeta","detail":"Primero esta obligación."},
             "allocation_base_amount":458000,
             "allocation_items":[{"key":"ataque_de_deuda","percentage":50.0,"amount":229000,"target_name":"Tarjeta"},
                                 {"key":"fondo_de_emergencia","percentage":35.0,"amount":160300},
                                 {"key":"vida_controlada","percentage":15.0,"amount":68700}]}
            """#), language: .spanish)
        #expect(plan.kind == .users)
        #expect(plan.base == 458_000)
        #expect(plan.parts.map(\.label) == ["Ataque de deuda · Tarjeta", "Salvavidas", "Vida controlada"])
        #expect(plan.parts.map(\.percentage) == [50, 35, 15])
        #expect(plan.headline == "Atacar deuda: Tarjeta")      // the priority first, the objective after
        #expect(plan.showsComposition)
    }

    @Test func theOwnerAnswerIsReadAsTheOwnerPlan() throws {
        let plan = MonthPlan(try dashboard(#"{"scope":"owner","status":"controlled","objective":"O","allocation_base_amount":100,"allocation_items":[{"key":"inversion","amount":100}]}"#))
        #expect(plan.kind == .owner)
        #expect(plan.headline == "O")
    }

    // MARK: Partial and unknown data

    @Test func partsThatLeaveMoneyUnassignedAreListedNotDrawnAsAWhole() throws {
        let plan = MonthPlan(try basic(#"{"strategic_margin":200000,"allocations":[{"bucket":"debt_extra","label":"Extra","amount":140000},{"bucket":"emergency","label":"Fondo","amount":40000}]}"#))
        #expect(plan.parts.count == 2)
        #expect(!plan.showsComposition)                    // 180.000 of 200.000: the backend left 20.000 unassigned
        #expect(plan.base == 200_000)                      // the margin is shown as sent, not replaced by the sum
    }

    @Test func anUnknownAmountIsNeverZero() throws {
        let plan = MonthPlan(try dashboard(#"{"scope":"users","allocation_base_amount":300,"allocation_items":[{"key":"inversion","amount":300},{"key":"fondo_de_emergencia"}]}"#))
        #expect(plan.parts.last?.amount == nil)
        #expect(plan.parts.last?.percentage == nil)
        #expect(!plan.showsComposition)
        #expect(plan.composition.status == .partial)
        #expect(plan.composition.unknown.count == 1)
    }

    @Test func anUnknownAmountToPlanIsNeverZeroAndDrawsNoWhole() throws {
        let plan = MonthPlan(try dashboard(#"{"scope":"users","allocation_items":[{"key":"inversion","amount":300}]}"#))
        #expect(plan.base == nil)
        #expect(!plan.showsComposition)
        let empty = MonthPlan(try basic(#"{"status":"tight"}"#))
        #expect(empty.base == nil && empty.parts.isEmpty && !empty.showsComposition)
    }

    @Test func aMissingDashboardStrategyIsNotAPlan() throws {
        let plan = MonthPlan(try dashboard(nil))
        #expect(plan.base == nil && plan.parts.isEmpty && plan.headline == "Sin datos")
        #expect(!plan.needsIncome && !plan.showsComposition)
    }

    @Test func noIncomeAndCriticalAnswersAreRecognized() throws {
        #expect(MonthPlan(try basic(#"{"status":"needs_income"}"#)).needsIncome)
        #expect(MonthPlan(try dashboard(#"{"scope":"users","status":"needs_income"}"#)).needsIncome)
        #expect(MonthPlan(try basic(#"{"status":"critical","recommendation":"R"}"#)).isCritical)
        #expect(MonthPlan(try dashboard(#"{"scope":"users","status":"critical"}"#)).isCritical)
    }

    /// The plan reads the backend's figures as they are: rebuilding it never changes them, and the
    /// parts carry no currency of their own (they are never mixed with another one).
    @Test func readingThePlanNeverChangesTheFigures() throws {
        let strategy = try basic(#"{"strategic_margin":100.5,"allocations":[{"bucket":"a","label":"A","amount":100.5}]}"#)
        let first = MonthPlan(strategy), second = MonthPlan(strategy)
        #expect(first == second)
        #expect(first.base == Decimal(string: "100.5"))
        #expect(first.composition.currency == nil)
    }

    // MARK: Unknown savings in the detail

    @Test func unknownUsersSavingsAreNeverZeroInThePlan() throws {
        let unknown = try APIClient.decoder.decode(DashboardStrategy.self, from: Data(#"""
            {"scope":"users","emergency_fund":{"current":0},"salvavidas":{"scope":"users","current_amount":null,"current_amount_known":false}}
            """#.utf8))
        #expect(!unknown.emergencyKnown)
        let known = try APIClient.decoder.decode(DashboardStrategy.self, from: Data(#"{"scope":"users","emergency_fund":{"current":120000},"salvavidas":{"current_amount_known":true}}"#.utf8))
        #expect(known.emergencyKnown)
        let owner = try APIClient.decoder.decode(DashboardStrategy.self, from: Data(#"{"scope":"owner","emergency_fund":{"current":5000},"salvavidas":{"current_amount_known":false}}"#.utf8))
        #expect(owner.emergencyKnown)
        let missing = try APIClient.decoder.decode(DashboardStrategy.self, from: Data(#"{"scope":"users","emergency_fund":{"monthly_base":1}}"#.utf8))
        #expect(!missing.emergencyKnown)
    }
}
