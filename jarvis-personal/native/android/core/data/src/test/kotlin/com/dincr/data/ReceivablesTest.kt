package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JARVIS → Control de dinero (Owner): `GET /finance/receivables` as the app reads it, and the two
 * write requests. Unknown amounts stay null (never 0) and a negative amount due is credit.
 * iOS: `ReceivablesTests`. Synthetic data only.
 */
class ReceivablesTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

    @Test fun theReportReadsTheCycleThePeopleAndTheirHistory() {
        val report = json.decodeFromString(ReceivablesReport.serializer(), """
            {"status":"OK","cycle":{"start":"2026-09-21","end":"2026-10-21"},
             "summary":{"total_pending":60000,"carried_pending":20000,"cycle_charges":50000,"cycle_payments":10000,"count_open":2,"people_count":2},
             "items":[{"id":7,"person_name":"Persona A","current_amount_due":25000,"carried_pending":20000,"cycle_charges":15000,
                       "cycle_payments":10000,"status":"partial","is_auto":true,
                       "history":[{"id":1,"entry_type":"payment","amount":10000,"entry_date":"2026-10-10","description":"Efectivo","source_type":"cash_collection"},
                                  {"id":2,"entry_type":"charge","amount":15000,"entry_date":"2026-10-04","source_type":"additional_card_auto"}]}]}
        """)
        assertEquals("2026-09-21", report.cycle?.start)
        assertEquals(0, BigDecimal(60_000).compareTo(report.summary?.totalPending))
        assertEquals(2, report.summary?.countOpen)
        val person = report.items.single()
        assertEquals("Persona A", person.personName)
        assertEquals(0, BigDecimal(25_000).compareTo(person.currentAmountDue))
        assertEquals(Receivable.Status.PARTIAL, person.status)
        assertTrue(person.isAuto)
        assertEquals(listOf(true, false), person.history.map { it.isPayment })
        assertTrue(person.canRecordPayment)
    }

    @Test fun unknownAmountsStayUnknownAndCreditIsNotOwed() {
        val report = json.decodeFromString(ReceivablesReport.serializer(), """
            {"items":[{"id":1,"person_name":"Sin datos"},{"id":2,"person_name":"A favor","current_amount_due":-5000,"status":"credit"},
                      {"id":3,"person_name":"Raro","current_amount_due":0,"status":"something_new"}]}
        """)
        assertNull(report.summary)
        assertNull(report.items[0].currentAmountDue)
        assertEquals(Receivable.Status.UNKNOWN, report.items[0].status)
        assertFalse("an unknown amount due is not a debt to collect", report.items[0].canRecordPayment)
        assertEquals(Receivable.Status.CREDIT, report.items[1].status)
        assertFalse(report.items[1].canRecordPayment)
        assertEquals(Receivable.Status.UNKNOWN, report.items[2].status)
    }

    @Test fun theWritesSendTheBackendsFieldNames() {
        val payment = json.encodeToString(ReceivablePaymentRequest.serializer(), ReceivablePaymentRequest(BigDecimal(10_000), paymentDate = "2026-10-24"))
        assertTrue(payment, payment.contains("\"amount\"") && payment.contains("\"payment_date\":\"2026-10-24\""))
        val entry = json.encodeToString(ReceivableEntryRequest.serializer(), ReceivableEntryRequest("Persona B", BigDecimal(5_000), "Almuerzo", "loan"))
        assertTrue(entry, entry.contains("\"person_name\":\"Persona B\"") && entry.contains("\"entry_kind\":\"loan\"") && entry.contains("\"description\":\"Almuerzo\""))
    }

    @Test fun aWriteTheBackendRefusesInTheBodyIsNotSaved() {
        assertTrue(json.decodeFromString(ReceivableWriteResult.serializer(), """{"status":"OK","item":{}}""").succeeded)
        assertFalse(json.decodeFromString(ReceivableWriteResult.serializer(), """{"status":"NOT_FOUND","message":"No encontrada"}""").succeeded)
        assertFalse(json.decodeFromString(ReceivableWriteResult.serializer(), """{"status":"DUPLICATE"}""").succeeded)
    }

    @Test fun additionalCardsReadTheCardAndThePerson() {
        val list = json.decodeFromString(AdditionalCards.serializer(), """
            {"status":"ok","items":[{"card_last4":"4821","person_name":"Persona A"},{"card_last4":"","person_name":"Sin tarjeta"},
                                    {"card_last4":"7310"}]}
        """)
        assertEquals(listOf("4821", "7310"), list.items.map { it.cardLast4 })
        assertEquals("Persona A", list.items[0].personName)
        assertNull(list.items[1].personName)
        assertTrue(json.decodeFromString(AdditionalCards.serializer(), "{}").items.isEmpty())
        val result = json.decodeFromString(AdditionalCardResult.serializer(), """{"status":"ok","settled_purchases":2}""")
        assertEquals(2, result.settledPurchases)
        assertNull(result.releasedPurchases)
    }

    @Test fun markingACardSendsThePersonAndOnlyFourDigits() {
        assertEquals("""{"person_name":"Persona B"}""", json.encodeToString(AdditionalCardRequest.serializer(), AdditionalCardRequest("Persona B")))
        assertEquals("4821", AdditionalCardRequest.last4(" 4821 "))
        listOf("482", "48210", "48a1", "", "٤٨٢١").forEach { assertNull(it, AdditionalCardRequest.last4(it)) }
    }

    private fun api(role: FakeBackend.Role, plan: PlanTier = PlanTier.VIP) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, plan, role = role), AppLanguage.SPANISH, backoff = {}))

    @Test fun theOwnerMarksAndUnmarksAnAdditionalCard() = runBlocking {
        val api = api(FakeBackend.Role.OWNER)
        val before = api.additionalCards().items.map { it.cardLast4 }
        api.saveAdditionalCard("7310", "Persona C")
        val after = api.additionalCards().items
        assertEquals((before + "7310").toSet(), after.map { it.cardLast4 }.toSet())
        assertEquals("Persona C", after.first { it.cardLast4 == "7310" }.personName)
        api.stopAdditionalCard("7310")
        assertEquals(before, api.additionalCards().items.map { it.cardLast4 })
        assertThrows(ApiError::class.java) { runBlocking { api.stopAdditionalCard("7310") } }
        Unit
    }

    @Test fun aRegularAccountCannotReachAdditionalCards() = runBlocking {
        assertThrows(ApiError::class.java) { runBlocking { api(FakeBackend.Role.USER).additionalCards() } }
        Unit
    }

    @Test fun moneyControlIsAnAvailableJarvisSection() {
        assertTrue(Jarvis.Section.MONEY_CONTROL.isAvailable)
    }
}
