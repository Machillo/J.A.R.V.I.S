import Foundation
import Testing
@testable import DincrCore

/// Plan → Gastos fijos (FX-1): the Owner's `/finance/fixed-expenses` rows decode, the request sends
/// only the fields the form edits (every N months, monthly frequency), the form's checks, and the
/// fixture keeps the backend's access rule and "remove = deactivate". Synthetic figures only.
/// Android: `FixedExpenseTest.kt`.
@Suite struct FixedExpenseTests {
    @Test func rowsDecodeAndCostPerMonth() throws {
        let json = #"[{"id":1,"name":"Internet de ejemplo","category":"Servicios","expected_amount":24900.0,"currency":"CRC","frequency":"monthly","interval_months":1,"due_day":8,"is_active":true,"aliases":[]},{"id":2,"name":"Seguro de ejemplo","expected_amount":60000,"interval_months":2,"due_day":null}]"#
        let rows = try APIClient.decoder.decode([OwnerFixedExpense].self, from: Data(json.utf8))
        #expect(rows.map(\.id) == [1, 2])
        #expect(rows[0].expectedAmount == 24_900 && rows[0].dueDay == 8)
        #expect(rows[1].monthlyAmount == 30_000)
        #expect(OwnerFixedExpense.intervalLabel(1, language: .spanish) == "Cada mes")
        #expect(OwnerFixedExpense.intervalLabel(2, language: .spanish) == "Cada 2 meses")
    }

    @Test func theRequestSendsOnlyWhatTheFormEdits() throws {
        let request = OwnerFixedExpenseRequest(name: "Gimnasio de ejemplo", category: "Salud", expectedAmount: Decimal(string: "25000.50")!, intervalMonths: 1, dueDay: nil)
        let body = try JSONSerialization.jsonObject(with: APIClient.encoder.encode(request)) as! [String: Any]
        #expect(Set(body.keys) == ["name", "category", "expected_amount", "frequency", "interval_months"])
        #expect(body["frequency"] as? String == "monthly")
        #expect((body["expected_amount"] as? NSNumber)?.decimalValue == Decimal(string: "25000.5"))
    }

    @Test func theFormRefusesWhatTheBackendWouldStoreWrong() {
        #expect(OwnerFixedExpenseRequest.problem(name: " ", amount: 1, intervalMonths: 1, dueDay: nil, language: .spanish) == "Escribí un nombre.")
        #expect(OwnerFixedExpenseRequest.problem(name: "A", amount: 0, intervalMonths: 1, dueDay: nil, language: .spanish) != nil)
        #expect(OwnerFixedExpenseRequest.problem(name: "A", amount: 1, intervalMonths: 5, dueDay: nil, language: .spanish) != nil)
        #expect(OwnerFixedExpenseRequest.problem(name: "A", amount: 1, intervalMonths: 1, dueDay: 32, language: .spanish) == "El día va de 1 a 31.")
        #expect(OwnerFixedExpenseRequest.problem(name: "A", amount: 1, intervalMonths: 12, dueDay: 31, language: .spanish) == nil)
    }

    @Test func theFixtureIsTheOwnersAloneAndRemovingDeactivates() async throws {
        let vip = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        await #expect(throws: APIError.self) { try await vip.ownerFixedExpenses() }
        let owner = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, role: .owner, latency: .zero))
        let before = try await owner.ownerFixedExpenses()
        let first = try #require(before.first)
        try await owner.removeOwnerFixedExpense(id: first.id)
        try await owner.createOwnerFixedExpense(OwnerFixedExpenseRequest(name: "Agua de ejemplo", category: "Servicios", expectedAmount: 9_000, intervalMonths: 1, dueDay: 3))
        let after = try await owner.ownerFixedExpenses()
        #expect(!after.contains { $0.id == first.id })
        #expect(after.contains { $0.name == "Agua de ejemplo" && $0.expectedAmount == 9_000 && $0.dueDay == 3 })
        #expect(after.count == before.count)
    }
}
