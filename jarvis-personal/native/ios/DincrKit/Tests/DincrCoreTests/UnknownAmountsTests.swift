import Foundation
import Testing
@testable import DincrCore

/// UNKNOWN ≠ 0 on the planning screens: a goal whose amount saved is unknown has no remainder, no
/// progress and no monthly need computed from 0; a budget category whose limit or amount spent is
/// unknown draws no bar. Android: `UnknownAmountsTest.kt`. Synthetic data.
@Suite struct UnknownAmountsTests {
    private func goal(target: Decimal?, current: Decimal?, status: String? = "active") -> Goal {
        Goal(id: 1, name: "Viaje", targetAmount: target, currentAmount: current, status: status)
    }

    @Test func aGoalsRemainderNeedsBothAmounts() {
        #expect(goal(target: 100_000, current: 30_000).remaining == 70_000)
        #expect(goal(target: 100_000, current: 120_000).remaining == 0, "never negative")
        #expect(goal(target: 100_000, current: nil).remaining == nil, "an unknown amount saved is not 0 saved")
        #expect(goal(target: nil, current: 30_000).remaining == nil)
    }

    @Test func aGoalsProgressNeedsBothAmountsAndAPositiveTarget() {
        #expect(goal(target: 100_000, current: 30_000).progressFraction == 0.3)
        #expect(goal(target: 100_000, current: nil).progressFraction == nil, "no 0 % from an unknown amount saved")
        #expect(goal(target: 0, current: 0).progressFraction == nil)
        #expect(goal(target: nil, current: 30_000).progressFraction == nil)
    }

    @Test func aContributionIsOfferedUntilTheGoalIsReachedEvenWhenTheRemainderIsUnknown() {
        #expect(goal(target: 100_000, current: 30_000).canContribute)
        #expect(goal(target: 100_000, current: nil).canContribute, "unknown does not hide the action")
        #expect(!goal(target: 100_000, current: 100_000).canContribute)
        #expect(!goal(target: 100_000, current: 30_000, status: "completed").canContribute)
    }

    @Test func aBudgetCategoryDrawsUsageOnlyFromKnownAmounts() {
        #expect(Budget.Item(category: "Comida", monthlyLimit: 100_000, spent: 50_000).usage?.fraction == 0.5)
        let over = Budget.Item(category: "Comida", monthlyLimit: 100_000, spent: 120_000).usage
        #expect(over?.isOver == true && over?.fraction == 1.2)
        #expect(Budget.Item(category: "Comida", monthlyLimit: 100_000, spent: nil).usage == nil, "no empty bar from an unknown amount spent")
        #expect(Budget.Item(category: "Comida", monthlyLimit: nil, spent: 50_000).usage == nil)
        #expect(Budget.Item(category: "Comida", monthlyLimit: 0, spent: 50_000).usage == nil, "no division by a zero limit")
    }
}
