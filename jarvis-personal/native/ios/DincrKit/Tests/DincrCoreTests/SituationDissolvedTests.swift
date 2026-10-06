import Foundation
import Testing
@testable import DincrCore

/// UX-7 — there is no separate Situación screen: each declared figure has its home. Hoy's missing
/// figures and the advisor's old "situation" route open Plan → Ingresos y base; the VIP priority keeps
/// exactly the backend's codes, with "no preference" stored as null. Android twin:
/// `SituationDissolvedTest.kt`. Synthetic data.
@Suite struct SituationDissolvedTests {
    @Test func noDestinationIsTheRetiredScreen() {
        #expect(!HomeDestination.allCases.map(\.rawValue).contains("situation"))
        #expect(!AttentionItem.Destination.allCases.map(\.rawValue).contains("situation"))
        #expect(HomeDestination.allCases.contains(.incomeBase) && AttentionItem.Destination.allCases.contains(.incomeBase))
    }

    @Test func missingFiguresAndTheOldRouteOpenIngresosYBase() {
        #expect([HomeInput.essentialExpenses, .savings, .emergencyFundTarget].allSatisfy { $0.destination == .incomeBase })
        #expect(AttentionList.destination(advisorRoute: "situation") == .incomeBase)
    }

    @Test func thePriorityChoicesAreTheBackendCodesWithNoPreferenceAsNull() {
        #expect(StrategyPreference.choices.map { $0?.rawValue } == [nil, "debt", "emergency", "goals", "balanced"])
    }

    @Test func ingresosYBaseIsAPlanRowForEveryPlan() {
        #expect(PlanHubItem.allCases.contains(.incomeBase))
        #expect(PlanHubItem.incomeBase.minimum == .free && PlanHubItem.incomeBase.killSwitch == nil)
    }
}
