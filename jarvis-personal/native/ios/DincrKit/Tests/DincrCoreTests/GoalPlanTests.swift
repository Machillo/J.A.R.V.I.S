import Foundation
import Testing
@testable import DincrCore

/// GO-1 — each goal says what it takes: per month to its date and, with a known normal month, how
/// long with what is left. Android: `GoalPlanTest.kt`. Synthetic data.
@Suite struct GoalPlanTests {
    private let calendar = Calendar(identifier: .gregorian)
    private let colones = MoneyFormat(currency: "CRC", separators: .dotComma)
    private var today: Date { calendar.date(from: DateComponents(year: 2026, month: 11, day: 15))! }
    private func goal(target: Decimal? = 1_200_000, saved: Decimal? = 200_000, date: String? = nil, status: String = "active") -> Goal {
        Goal(id: 1, name: "Viaje", targetAmount: target, currentAmount: saved, targetDate: date, status: status)
    }

    @Test func perMonthToItsDateCountingThisMonth() {
        // 1 000 000 left; November 2026 → October 2027 is 11 months.
        #expect(GoalPlan.monthlyNeeded(goal(date: "2027-10-01"), today: today) == Decimal(string: "90909.09"))
        #expect(GoalPlan.lines(goal(date: "2027-10-01"), today: today, normalLeft: nil, format: colones, language: .spanish)
                == ["Para llegar en oct 2027 necesitás ₡90.909 por mes."])
    }

    @Test func aDateThisMonthNeedsEverythingNow() {
        #expect(GoalPlan.monthlyNeeded(goal(date: "2026-11-30"), today: today) == 1_000_000)
    }

    @Test func aPastDateAsksToChangeIt() {
        #expect(GoalPlan.monthlyNeeded(goal(date: "2026-09-01"), today: today) == nil)
        #expect(GoalPlan.lines(goal(date: "2026-09-01"), today: today, normalLeft: nil, format: colones, language: .spanish)
                == ["La fecha ya pasó y te faltan ₡1.000.000. Cambiala para recalcular."])
    }

    @Test func withoutADateItAsksForOneAndWithANormalMonthItSaysHowLong() {
        #expect(GoalPlan.lines(goal(), today: today, normalLeft: 300_000, format: colones, language: .spanish)
                == ["Poné una fecha para saber cuánto guardar por mes.",
                    "Con lo que te sobra en un mes normal (₡300.000) llegás en 4 meses."])
        #expect(GoalPlan.lines(goal(), today: today, normalLeft: -50_000, format: colones, language: .spanish).last
                == "Hoy no te sobra plata en un mes normal: primero hay que liberar algo.")
    }

    @Test func aReachedGoalSaysSoAndAnUnknownAmountSavedSaysNothing() {
        #expect(GoalPlan.lines(goal(saved: 1_200_000), today: today, normalLeft: 1, format: colones, language: .spanish) == ["¡Meta cumplida!"])
        #expect(GoalPlan.lines(goal(saved: nil, date: "2027-01-01"), today: today, normalLeft: 1, format: colones).isEmpty)
    }
}
