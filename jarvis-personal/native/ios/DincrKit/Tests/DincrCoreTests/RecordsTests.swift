import Foundation
import Testing
@testable import DincrCore

/// JARVIS → Registros (Owner): the timeline and the reconciliation as the app reads them, and the
/// confirm request. Unknown amounts stay nil (never 0). Android: `RecordsTest`. Synthetic data only.
struct RecordsTests {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try APIClient.decoder.decode(type, from: Data(json.utf8))
    }

    @Test func theTimelineReadsItsEventsByDayInOrder() throws {
        let timeline = try decode(MoneyTimeline.self, """
        {"status":"OK","start_date":"2026-10-25","end_date":"2026-12-09","opening_available":310000,"ending_available":685100,
         "events":[{"date":"2026-10-28","name":"Cuota A","kind":"debt_payment","amount":50000,"impact":-50000,"projected_balance":260000},
                   {"date":"2026-10-28","name":"Internet","kind":"recurring_expense","amount":24900,"impact":-24900,"projected_balance":235100},
                   {"date":"2026-11-02","name":"Ingreso de salario","kind":"income","amount":450000,"impact":450000,"projected_balance":685100},
                   {"date":"2026-11-30","name":"Meta · Viaje","kind":"goal","amount":400000,"impact":0,"note":"Recordatorio"}],
         "assumptions":["Solo se proyectan ingresos con calendario configurado."]}
        """)
        #expect(timeline.openingAvailable == 310_000 && timeline.endingAvailable == 685_100)
        #expect(timeline.days.map(\.date) == ["2026-10-28", "2026-11-02", "2026-11-30"])
        #expect(timeline.days[0].events.map(\.name) == ["Cuota A", "Internet"])
        #expect(timeline.events[3].projectedBalance == nil && timeline.events[3].note == "Recordatorio")
        #expect(timeline.assumptions.count == 1)
    }

    @Test func anEmptyOrPartialTimelineIsNotZero() throws {
        let timeline = try decode(MoneyTimeline.self, #"{"status":"OK"}"#)
        #expect(timeline.openingAvailable == nil && timeline.endingAvailable == nil && timeline.events.isEmpty)
    }

    @Test func theReconciliationReadsEachAccountAndTheSummary() throws {
        let report = try decode(Reconciliation.self, """
        {"status":"OK","accounts":[{"account_id":801,"account_name":"Cuenta","last4":"1111","currency":"CRC","expected_balance":290000,
           "real_balance":310000,"difference":20000,"movements_since_balance":4,"status":"needs_review"},
          {"account_id":802,"account_name":"Ahorro","expected_balance":120000,"real_balance":120000,"difference":0,"status":"ok"}],
         "summary":{"accounts":2,"needs_review":1,"unlinked":2,"possible_duplicates":0,"untracked_accounts":1},"note":"Solo detecta."}
        """)
        #expect(report.accounts.map(\.accountId) == [801, 802])
        #expect(report.accounts[0].needsReview && !report.accounts[1].needsReview)
        #expect(report.accounts[0].difference == 20_000)
        #expect(report.summary?.needsReview == 1 && report.summary?.untrackedAccounts == 1)
    }

    @Test func theConfirmSendsTheBackendsFieldNames() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        let body = String(decoding: try encoder.encode(ReconciliationConfirmRequest(realBalance: 310_000)), as: UTF8.self)
        #expect(body == #"{"note":"","real_balance":310000}"#)
    }

    @Test func recordsIsAnAvailableJarvisSection() {
        #expect(Jarvis.Section.records.isAvailable)
    }
}
