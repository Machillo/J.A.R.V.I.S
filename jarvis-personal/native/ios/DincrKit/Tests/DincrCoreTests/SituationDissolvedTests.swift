import Foundation
import Testing
@testable import DincrCore

/// UX-7 — there is no separate Situación screen: each declared figure has its home. Missing essential
/// expenses and the advisor's old "situation" route open Plan → Ingresos y base; missing savings and
/// emergency-fund target open Metas y ahorro (Tus ahorros). Android twin:
/// `SituationDissolvedTest.kt`. Synthetic data.
@Suite struct SituationDissolvedTests {
    @Test func noDestinationIsTheRetiredScreen() {
        #expect(!HomeDestination.allCases.map(\.rawValue).contains("situation"))
        #expect(!AttentionItem.Destination.allCases.map(\.rawValue).contains("situation"))
        #expect(HomeDestination.allCases.contains(.incomeBase) && AttentionItem.Destination.allCases.contains(.incomeBase))
    }

    @Test func missingFiguresAndTheOldRouteOpenIngresosYBase() {
        #expect(HomeInput.essentialExpenses.destination == .incomeBase)
        #expect([HomeInput.savings, .emergencyFundTarget].allSatisfy { $0.destination == .goals })
        #expect(AttentionList.destination(advisorRoute: "situation") == .incomeBase)
    }

    @Test func ingresosYBaseIsAPlanRowForEveryPlan() {
        #expect(PlanHubItem.allCases.contains(.incomeBase))
        #expect(PlanHubItem.incomeBase.minimum == .free && PlanHubItem.incomeBase.killSwitch == nil)
    }
}
