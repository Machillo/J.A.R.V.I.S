import Foundation
import Testing
@testable import DincrCore

/// §15 PR 8 — the debt composition in Patrimonio reads Plan → Deudas' balances as they are: active
/// debts only, an unknown balance never drawn as 0. Android: `DebtCompositionTest.kt`. Synthetic data.
@Suite struct DebtCompositionTests {
    private func debt(_ id: Int, _ name: String, _ remaining: Decimal?) -> Debt { Debt(id: id, name: name, remainingAmount: remaining) }

    @Test func activeDebtsMakeUpWhatIsOwedInTheirOrder() {
        let composition = DebtComposition.of([debt(1, "Tarjeta", 480_000), debt(2, "Préstamo", 520_000)])
        #expect(composition.status == .complete)
        #expect(composition.segments.map(\.label) == ["Tarjeta", "Préstamo"])
        #expect(composition.segments.map { (($0.share ?? -1) * 100).rounded() } == [48, 52])
        #expect(composition.total == 1_000_000)
    }

    @Test func aPaidDebtIsNotPartOfIt() {
        let composition = DebtComposition.of([debt(1, "Tarjeta", 300_000), debt(2, "Pagada", 0)])
        #expect(composition.segments.map(\.label) == ["Tarjeta"])
    }

    @Test func anUnknownBalanceIsNeverZeroAndBlocksSharesAndTotal() {
        let composition = DebtComposition.of([debt(1, "Tarjeta", 300_000), debt(2, "Sin saldo", nil)])
        #expect(composition.status == .partial)
        #expect(composition.total == nil)
        #expect(composition.segments.allSatisfy { $0.share == nil })
        #expect(composition.unknown.map(\.label) == ["Sin saldo"])
    }

    @Test func noActiveDebtIsAnEmptyComposition() {
        #expect(DebtComposition.of([]).status == .empty)
        #expect(DebtComposition.of([debt(1, "Pagada", 0)]).status == .empty)
    }

    @Test func theFixtureDebtsAreDrawable() async throws {
        let debts = try await FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .free, latency: .zero)).debts()
        #expect(!debts.isEmpty)
        #expect(DebtComposition.of(debts).status == .complete)
    }
}
