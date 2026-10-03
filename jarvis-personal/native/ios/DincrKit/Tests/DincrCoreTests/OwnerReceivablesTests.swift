import Foundation
import Testing
@testable import DincrCore

/// JARVIS · Control de dinero: the Owner's cuentas por cobrar. Only the Owner reaches them, through
/// the read-only route; unknown figures stay unknown. Android: `ReceivablesTest.kt`.
@Suite struct OwnerReceivablesTests {
    @Test func moneyControlIsPortedNextToTheOtherSections() {
        #expect(Jarvis.Section.allCases.filter(\.isAvailable) == [.chat, .calendar, .moneyControl, .analysis])
        // Still restoring: memory, strategy, money, wealth and records.
        #expect(Jarvis.Section.allCases.filter { !$0.isAvailable } == [.memory, .strategy, .money, .wealth, .records])
    }

    @Test func theAppReadsTheReadOnlyRouteWithAGet() async throws {
        let body = #"{"status":"OK","cycle":{"start":"2026-09-21","end":"2026-10-21"},"items":[{"id":7,"person_name":"Persona","status":"partial","current_amount_due":2000,"carried_pending":3000,"cycle_charges":0,"cycle_payments":1000,"history":[{"id":1,"entry_type":"payment","amount":1000,"description":"Abono","entry_date":"2026-09-25"}]}],"summary":{"total_pending":2000,"people_count":1}}"#
        let transport = RoutedTransport(["/finance/receivables/view": body])
        let api = DincrService(client: APIClient(baseURL: URL(string: "https://api.example.test")!, tokens: CountingTokens(), transport: transport, language: .spanish, backoff: { _ in }))
        let report = try await api.receivables()
        // Never the web route, which syncs and stores on every read.
        #expect(transport.requests.map { $0.url!.path } == ["/finance/receivables/view"])
        #expect(transport.requests.allSatisfy { $0.httpMethod == "GET" })
        #expect(report.summary?.totalPending == 2000 && report.summary?.peopleCount == 1)
        let item = try #require(report.items.first)
        #expect(item.personName == "Persona" && item.currentAmountDue == 2000 && item.carriedPending == 3000)
        #expect(item.history.first?.isPayment == true && item.history.first?.amount == 1000)
    }

    @Test func unknownFiguresAreNeverZero() throws {
        let report = try PlanAccountsTests.decode(ReceivablesReport.self,
            #"{"items":[{"id":3,"person_name":null,"current_amount_due":null,"carried_pending":"n/a","history":[{"id":9,"amount":null}]}],"summary":{"total_pending":null}}"#)
        #expect(report.summary?.totalPending == nil)
        let item = try #require(report.items.first)
        #expect(item.currentAmountDue == nil && item.carriedPending == nil && item.cycleCharges == nil)
        #expect(item.history.first?.amount == nil)
        // A body without items is an empty list, not an error.
        #expect(try PlanAccountsTests.decode(ReceivablesReport.self, #"{"status":"OK"}"#).items.isEmpty)
    }

    @Test func onlyTheOwnerReachesThem() async throws {
        for plan in [PlanTier.free, .basic, .vip] {
            let user = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: plan, latency: .zero))
            do {
                _ = try await user.receivables()
                Issue.record("a \(plan) user must not reach the Owner's receivables")
            } catch let error as APIError {
                #expect(error.status == 403)
            }
        }
        let owner = try await FixtureBackend.service(FixtureBackend(scenario: .populated, role: .owner, latency: .zero)).receivables()
        #expect(owner.items.count == 2 && owner.summary?.totalPending == 85_000)
    }
}
