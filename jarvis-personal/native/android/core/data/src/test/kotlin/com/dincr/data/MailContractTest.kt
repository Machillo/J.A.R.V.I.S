package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The mail endpoints as FastAPI really answers them (`backend/user_product/gmail_service.py`,
 * `models.py`). The payloads are synthetic but keep the server's shape, so a model that drifts
 * from the contract fails here instead of on a device.
 */
class MailContractTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    /** A [DincrApi] whose every call is answered with [body], as the server would answer it. */
    private fun serving(body: String) = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, { HttpResponse(200, body) }, AppLanguage.SPANISH, backoff = {}))

    /** `list_gmail_emails`: an envelope, not a bare list. */
    @Test fun candidatesDecodeFromTheServerEnvelope() = runTest {
        val body = """{"status":"ok","items":[
            {"email_id":7,"sender":"avisos@banco.test","subject":"Compra","received_at":"2026-09-01T10:00:00Z","bank":"Banco de ejemplo",
             "email_status":"parsed","parse_reason":"Aviso procesado.","candidate_id":11,"transaction_id":null,"transaction_date":"2026-09-01",
             "description":"Supermercado","amount":15300.0,"currency":"CRC","original_amount":null,"original_currency":null,
             "account_base_currency":"CRC","transaction_type":"expense","movement_direction":"out","movement_kind":"purchase",
             "category":"Comida","confidence":0.97,"review_status":"pending","source_type":"email","is_internal_transfer":false,
             "related_candidate_id":null,"resolution_reason":"possible_cross_source_match"},
            {"email_id":8,"sender":"avisos@banco.test","subject":"Otro","email_status":"ignored","parse_reason":"No es un aviso financiero.",
             "candidate_id":null,"amount":null,"currency":null,"review_status":null}
        ]}"""
        val items = serving(body).mailCandidates(pendingOnly = false)
        assertEquals(2, items.size)
        assertEquals(11L, items[0].candidateId)
        assertEquals(0, BigDecimal("15300").compareTo(items[0].amount))
        assertTrue(items[0].isPending)
        assertNull("an email without a candidate still decodes", items[1].candidateId)
    }

    /** `sync_current_gmail`: `failed_connections` lists the ids of the mailboxes that failed. */
    @Test fun syncDecodesTheFailedConnectionIds() = runTest {
        val partial = serving(
            """{"status":"partial","connections":2,"failed_connections":[3],"scan_scope":"year_to_date","initial_scan_complete":true,
                "found":4,"auto_saved":0,"pending":2,"payroll_reports":0,"duplicates":1}""").syncMail()
        assertEquals(listOf(3L), partial.failedConnections)
        assertEquals(4, partial.found)
        val ok = serving("""{"status":"ok","connections":1,"failed_connections":[],"found":0,"pending":0}""").syncMail()
        assertEquals(emptyList<Long>(), ok.failedConnections)
    }
}
