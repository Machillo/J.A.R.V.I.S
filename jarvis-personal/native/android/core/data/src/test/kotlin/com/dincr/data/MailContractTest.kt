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

    @Test fun disabledConnectionsAreHidden() {
        val status = json.decodeFromString<MailStatus>(
            """{"connected":true,"connections":[{"id":1,"google_email":"a@correo.test","status":"active"},
                {"id":2,"google_email":"b@correo.test","status":"disabled"},{"id":3,"google_email":"c@correo.test","status":"error"}]}""")
        assertEquals(listOf(1L, 3L), status.visibleConnections.map { it.id })
    }

    /** `MailConnectRequest`: the app language travels with the history scope. */
    @Test fun connectBodySendsTheAppLanguage() {
        for ((language, tag) in listOf(AppLanguage.SPANISH to "es", AppLanguage.ENGLISH to "en")) {
            val body = json.parseToJsonElement(json.encodeToString(MailConnectRequest.serializer(), MailConnectRequest("current_month", language.tag))).jsonObject
            assertEquals("current_month", body["import_scope"]?.jsonPrimitive?.content)
            assertEquals(tag, body["locale"]?.jsonPrimitive?.content)
        }
    }

    /** `candidate_currency.transaction_amounts`: a missing base currency is CRC. */
    @Test fun aMissingBaseCurrencyIsColones() {
        val usd = MailCandidate(candidateId = 1, amount = BigDecimal("25"), currency = "USD", accountBaseCurrency = null, reviewStatus = "pending")
        assertTrue(usd.needsRate)
        assertFalse(usd.cannotConvert)
        val crc = MailCandidate(candidateId = 2, amount = BigDecimal("100"), currency = "CRC", accountBaseCurrency = null, reviewStatus = "pending")
        assertFalse(crc.needsRate)
        assertFalse(crc.cannotConvert)
        val euro = MailCandidate(candidateId = 3, amount = BigDecimal("40"), currency = "EUR", accountBaseCurrency = null, reviewStatus = "pending")
        assertTrue(euro.cannotConvert)
    }

    /** Raw `resolution_reason` codes never reach the user; only the known ones become a note. */
    @Test fun resolutionReasonsMapToNotesNotCodes() {
        fun note(reason: String?, internal: Boolean? = null) = MailCandidate(candidateId = 1, resolutionReason = reason, isInternalTransfer = internal).resolutionNote
        assertEquals(MailCandidate.ResolutionNote.POSSIBLE_MATCH, note("possible_cross_source_match"))
        assertEquals(MailCandidate.ResolutionNote.PAIRED_OWN_TRANSFER, note("paired_owned_transfer", true))
        assertEquals(MailCandidate.ResolutionNote.OWN_ACCOUNTS, note("confirmed_owned_endpoints", true))
        assertNull(note("same_semantic_movement"))
        assertNull(note("legacy_owner_import"))
        assertNull(note(null))
    }

    /** The fake answers with the server's shapes, so the app's own flows exercise the real decoders. */
    @Test fun fakeBackendAnswersWithTheServerShapes() = runTest {
        val api = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP), AppLanguage.SPANISH, backoff = {}))
        assertTrue(api.mailCandidates(pendingOnly = true).isNotEmpty())
        assertTrue(api.syncMail().failedConnections.isEmpty())
        val status = api.mailStatus()
        assertTrue("the fake keeps a disabled row, as the server does", status.connections.any { it.status == "disabled" })
        assertTrue(status.visibleConnections.none { it.status == "disabled" })
    }
}
