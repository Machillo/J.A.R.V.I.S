import Foundation
import Testing
@testable import DincrCore

struct DebtOrderTests {
    let debts = [
        Debt(id: 1, name: "A", remainingAmount: 300, interestRate: 20, interestRateKnown: true),
        Debt(id: 2, name: "B", remainingAmount: nil, interestRate: 0, interestRateKnown: false),
        Debt(id: 3, name: "C", remainingAmount: 900, interestRate: 35, interestRateKnown: true),
        Debt(id: 4, name: "D", remainingAmount: 100, interestRate: nil, interestRateKnown: nil),
    ]

    @Test func savedKeepsTheOrder() { #expect(DebtOrder.saved.sorted(debts).map(\.id) == [1, 2, 3, 4]) }

    @Test func balanceEitherWayAndUnknownLast() {
        #expect(DebtOrder.balanceHigh.sorted(debts).map(\.id) == [3, 1, 4, 2])
        #expect(DebtOrder.balanceLow.sorted(debts).map(\.id) == [4, 1, 3, 2])
    }

    @Test func anUnknownRateIsNeverZero() {
        // B's stored 0 is not a known rate: it goes last both ways, with D (no rate).
        #expect(DebtOrder.rateHigh.sorted(debts).map(\.id) == [3, 1, 2, 4])
        #expect(DebtOrder.rateLow.sorted(debts).map(\.id) == [1, 3, 2, 4])
    }
}
