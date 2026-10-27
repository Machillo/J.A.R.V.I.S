import Foundation
import Testing
@testable import DincrCore

/// PLN-04 — iOS edits a savings plan as Android does: one PUT with every field (status included),
/// keyed for idempotency, and the plan keeps its id. Android: `GoalsScreens.SavingsPlanForm`.
@Suite struct SavingsPlanEditTests {
    @Test func anEditIsOnePutWithEveryField() async throws {
        let backend = FixtureBackend(latency: .zero, language: .spanish)
        let service = FixtureBackend.service(backend)
        let plan = try #require(try await service.savingsPlans().first)
        let request = SavingsPlanRequest(name: "Viaje", monthlyAmount: 30_000, savedAmount: 90_000,
                                         startDate: "2026-07-01", endDate: "2027-12-01", status: "paused")
        let updated = try await service.updateSavingsPlan(id: plan.id, request, idempotencyKey: "edit-1")
        #expect(updated.id == plan.id)
        #expect(updated.name == "Viaje" && updated.monthlyAmount == 30_000 && updated.savedAmount == 90_000)
        #expect(updated.status == "paused" && updated.endDate == "2027-12-01")
        #expect(try await service.savingsPlans().first { $0.id == plan.id } == updated)

        let sent = try #require(await backend.requests.last { $0.httpMethod == "PUT" })
        #expect(sent.url?.path == "/user-product/savings-plans/\(plan.id)")
        #expect(sent.value(forHTTPHeaderField: "X-Idempotency-Key") == "edit-1")
        let body = try #require(sent.httpBody.flatMap { try JSONSerialization.jsonObject(with: $0) as? [String: Any] })
        #expect(Set(body.keys) == ["name", "monthly_amount", "saved_amount", "start_date", "end_date", "status"])
    }

    @Test func anInvalidEditIsRefusedBeforeTheNetwork() async throws {
        let backend = FixtureBackend(latency: .zero, language: .spanish)
        let service = FixtureBackend.service(backend)
        let before = await backend.requests.count
        let request = SavingsPlanRequest(name: "Viaje", monthlyAmount: 30_000, savedAmount: 0, startDate: "2027-01-01", endDate: "2026-01-01")
        await #expect(throws: (any Error).self) { _ = try await service.updateSavingsPlan(id: 44, request, idempotencyKey: "edit-2") }
        #expect(await backend.requests.count == before)
    }
}
