package com.dincr.data

import java.math.BigDecimal
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JARVIS → Registros (Owner): the timeline and the reconciliation as the app reads them, and the
 * confirm request. Unknown amounts stay null (never 0). iOS: `RecordsTests`. Synthetic data only.
 */
class RecordsTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

    @Test fun theTimelineReadsItsEventsByDayInOrder() {
        val timeline = json.decodeFromString(MoneyTimeline.serializer(), """
            {"status":"OK","start_date":"2026-10-25","end_date":"2026-12-09","opening_available":310000,"ending_available":685100,
             "events":[{"date":"2026-10-28","name":"Cuota A","kind":"debt_payment","amount":50000,"impact":-50000,"projected_balance":260000},
                       {"date":"2026-10-28","name":"Internet","kind":"recurring_expense","amount":24900,"impact":-24900,"projected_balance":235100},
                       {"date":"2026-11-02","name":"Ingreso de salario","kind":"income","amount":450000,"impact":450000,"projected_balance":685100},
                       {"date":"2026-11-30","name":"Meta · Viaje","kind":"goal","amount":400000,"impact":0,"note":"Recordatorio"}],
             "assumptions":["Solo se proyectan ingresos con calendario configurado."]}
        """)
        assertEquals(0, BigDecimal(310_000).compareTo(timeline.openingAvailable))
        assertEquals(listOf("2026-10-28", "2026-11-02", "2026-11-30"), timeline.days.map { it.first })
        assertEquals(listOf("Cuota A", "Internet"), timeline.days[0].second.map { it.name })
        assertNull(timeline.events[3].projectedBalance)
        assertEquals(1, timeline.assumptions.size)
    }

    @Test fun anEmptyOrPartialTimelineIsNotZero() {
        val timeline = json.decodeFromString(MoneyTimeline.serializer(), """{"status":"OK"}""")
        assertNull(timeline.openingAvailable)
        assertNull(timeline.endingAvailable)
        assertTrue(timeline.events.isEmpty())
    }

    @Test fun theReconciliationReadsEachAccountAndTheSummary() {
        val report = json.decodeFromString(Reconciliation.serializer(), """
            {"status":"OK","accounts":[{"account_id":801,"account_name":"Cuenta","last4":"1111","currency":"CRC","expected_balance":290000,
               "real_balance":310000,"difference":20000,"movements_since_balance":4,"status":"needs_review"},
              {"account_id":802,"account_name":"Ahorro","expected_balance":120000,"real_balance":120000,"difference":0,"status":"ok"}],
             "summary":{"accounts":2,"needs_review":1,"unlinked":2,"possible_duplicates":0,"untracked_accounts":1},"note":"Solo detecta."}
        """)
        assertEquals(listOf(801L, 802L), report.accounts.map { it.accountId })
        assertTrue(report.accounts[0].needsReview)
        assertFalse(report.accounts[1].needsReview)
        assertEquals(1, report.summary?.untrackedAccounts)
    }

    @Test fun theConfirmSendsTheBackendsFieldNames() {
        val body = json.encodeToString(ReconciliationConfirmRequest.serializer(), ReconciliationConfirmRequest(BigDecimal(310_000)))
        assertTrue(body, body.contains("\"real_balance\"") && body.contains("\"note\":\"\""))
    }

    @Test fun recordsIsAnAvailableJarvisSection() {
        assertTrue(Jarvis.Section.RECORDS.isAvailable)
    }
}
