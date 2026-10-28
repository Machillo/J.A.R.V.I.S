import Foundation
import Testing
@testable import DincrCore

/// JARVIS → Control de dinero (Owner): `GET /finance/receivables` as the app reads it, and the two
/// write requests. Unknown amounts stay nil (never 0) and a negative amount due is credit.
/// Android: `ReceivablesTest`. Synthetic data only.
struct ReceivablesTests {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try APIClient.decoder.decode(type, from: Data(json.utf8))
    }

    @Test func theReportReadsTheCycleThePeopleAndTheirHistory() throws {
        let report = try decode(ReceivablesReport.self, """
        {"status":"OK","cycle":{"start":"2026-09-21","end":"2026-10-21"},
         "summary":{"total_pending":60000,"carried_pending":20000,"cycle_charges":50000,"cycle_payments":10000,"count_open":2,"people_count":2},
         "items":[{"id":7,"person_name":"Persona A","current_amount_due":25000,"carried_pending":20000,"cycle_charges":15000,
                   "cycle_payments":10000,"status":"partial","is_auto":true,
                   "history":[{"id":1,"entry_type":"payment","amount":10000,"entry_date":"2026-10-10","description":"Efectivo","source_type":"cash_collection"},
                              {"id":2,"entry_type":"charge","amount":15000,"entry_date":"2026-10-04","source_type":"additional_card_auto"}]}]}
        """)
        #expect(report.cycle?.start == "2026-09-21" && report.cycle?.end == "2026-10-21")
        #expect(report.summary?.totalPending == 60_000 && report.summary?.countOpen == 2)
        let person = try #require(report.items.first)
        #expect(person.personName == "Persona A" && person.currentAmountDue == 25_000 && person.status == .partial && person.isAuto)
        #expect(person.history.map(\.isPayment) == [true, false])
        #expect(person.canRecordPayment)
    }

    @Test func unknownAmountsStayUnknownAndCreditIsNotOwed() throws {
        let report = try decode(ReceivablesReport.self, """
        {"items":[{"id":1,"person_name":"Sin datos"},{"id":2,"person_name":"A favor","current_amount_due":-5000,"status":"credit"},
                  {"id":3,"person_name":"Raro","current_amount_due":0,"status":"something_new"}]}
        """)
        #expect(report.summary == nil && report.cycle == nil)
        #expect(report.items[0].currentAmountDue == nil && report.items[0].status == .unknown && report.items[0].history.isEmpty)
        #expect(!report.items[0].canRecordPayment, "an unknown amount due is not a debt to collect")
        #expect(report.items[1].status == .credit && !report.items[1].canRecordPayment)
        #expect(report.items[2].status == .unknown && !report.items[2].canRecordPayment)
    }

    @Test func theWritesSendTheBackendsFieldNames() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        let payment = String(decoding: try encoder.encode(ReceivablePaymentRequest(amount: 10_000, notes: "Efectivo", paymentDate: "2026-10-24")), as: UTF8.self)
        #expect(payment == #"{"amount":10000,"notes":"Efectivo","payment_date":"2026-10-24"}"#)
        let entry = String(decoding: try encoder.encode(ReceivableEntryRequest(personName: "Persona B", amount: 5_000, description: "Almuerzo", entryKind: "loan")), as: UTF8.self)
        #expect(entry == #"{"amount":5000,"description":"Almuerzo","entry_kind":"loan","person_name":"Persona B"}"#)
    }

    @Test func aWriteTheBackendRefusesInTheBodyIsNotSaved() throws {
        #expect(try decode(ReceivableWriteResult.self, #"{"status":"OK","item":{}}"#).succeeded)
        #expect(!(try decode(ReceivableWriteResult.self, #"{"status":"NOT_FOUND","message":"No encontrada"}"#).succeeded))
        #expect(!(try decode(ReceivableWriteResult.self, #"{"status":"DUPLICATE"}"#).succeeded))
    }

    @Test func additionalCardsReadTheCardAndThePerson() throws {
        let list = try decode(AdditionalCardsList.self, """
        {"status":"ok","items":[{"card_last4":"4821","person_name":"Persona A"},{"card_last4":"","person_name":"Sin tarjeta"},
                                {"card_last4":"7310"}]}
        """)
        #expect(list.items.map(\.cardLast4) == ["4821", "7310"], "a row without a card is not a card")
        #expect(list.items[0].personName == "Persona A" && list.items[1].personName == nil)
        #expect(try decode(AdditionalCardsList.self, "{}").items.isEmpty)
        let result = try decode(AdditionalCardResult.self, #"{"status":"ok","settled_purchases":2}"#)
        #expect(result.settledPurchases == 2 && result.releasedPurchases == nil)
    }

    @Test func markingACardSendsThePersonAndOnlyFourDigits() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        let body = String(decoding: try encoder.encode(AdditionalCardRequest(personName: "Persona B")), as: UTF8.self)
        #expect(body == #"{"person_name":"Persona B"}"#)
        #expect(AdditionalCardRequest.last4(" 4821 ") == "4821")
        for wrong in ["482", "48210", "48a1", "", "٤٨٢١"] { #expect(AdditionalCardRequest.last4(wrong) == nil, "\(wrong)") }
    }

    @Test func theOwnerMarksAndUnmarksAnAdditionalCard() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, role: .owner, latency: .zero))
        let before = try await service.additionalCards().items.map(\.cardLast4)
        try await service.saveAdditionalCard(last4: "7310", personName: "Persona C")
        let after = try await service.additionalCards().items
        #expect(Set(after.map(\.cardLast4)) == Set(before + ["7310"]))
        #expect(after.first { $0.cardLast4 == "7310" }?.personName == "Persona C")
        try await service.stopAdditionalCard(last4: "7310")
        #expect(try await service.additionalCards().items.map(\.cardLast4) == before)
        await #expect(throws: APIError.self) { try await service.stopAdditionalCard(last4: "7310") }
    }

    @Test func aRegularAccountCannotReachAdditionalCards() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        await #expect(throws: APIError.self) { try await service.additionalCards() }
    }

    @Test func moneyControlIsAnAvailableJarvisSection() {
        #expect(Jarvis.Section.moneyControl.isAvailable)
    }
}
