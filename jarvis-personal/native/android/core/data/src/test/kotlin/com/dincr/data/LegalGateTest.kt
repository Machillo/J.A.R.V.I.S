package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * SEC-01 — the server's legal gate answers 403 `legal_acceptance_required` (`auth/legal.py`). The
 * client keeps that code so the app can bring back the acceptance screen, and the fake backend used
 * by the UI tests behaves like the server. The Swift twin is `LegalGateTests`.
 */
class LegalGateTest {
    private fun api(backend: FakeBackend) = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, backend, AppLanguage.SPANISH, backoff = {}))

    private suspend fun refused(block: suspend () -> Unit): ApiError {
        try { block() } catch (error: ApiError) { return error }
        fail("expected the legal gate"); throw IllegalStateException()
    }

    @Test fun theGatesCodeReachesTheApp() {
        val body = """{"detail":{"code":"legal_acceptance_required","message":"Antes de continuar, aceptá los Términos y la Política de Privacidad vigentes."}}"""
        val error = ApiError.from(403, body, AppLanguage.SPANISH, null)
        assertEquals(ApiError.LEGAL_ACCEPTANCE_REQUIRED_CODE, error.code)
        assertTrue(error.message.startsWith("Antes de continuar"))
    }

    @Test fun afterTheTermsChangeWritesWaitForAcceptanceAndReadsDoNot() = runTest {
        val backend = FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.FREE)
        val api = api(backend)
        val debt = api.debts().first().id
        backend.legalLapses = true
        assertTrue("reads are not held back", api.debts().isNotEmpty())
        assertEquals(403, refused { api.payDebt(debt, BigDecimal("1000"), "pay-1") }.status)
        val legal = api.me().legal!!
        assertEquals("the identity asks for acceptance again", true, legal.required)
        assertEquals(ApiError.LEGAL_ACCEPTANCE_REQUIRED_CODE, refused { api.payDebt(debt, BigDecimal("1000"), "pay-2") }.code)

        api.acceptLegal(LegalAcceptRequest(true, true, legal.termsVersion.orEmpty(), legal.privacyVersion.orEmpty()))
        assertFalse(api.me().legal!!.required == true)
        api.payDebt(debt, BigDecimal("1000"), "pay-3")
    }

    @Test fun withoutTheLapseNothingChanges() = runTest {
        val backend = FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.FREE)
        val api = api(backend)
        api.payDebt(api.debts().first().id, BigDecimal("1000"), "pay-1")
        assertFalse(api.me().legal!!.required == true)
    }
}
