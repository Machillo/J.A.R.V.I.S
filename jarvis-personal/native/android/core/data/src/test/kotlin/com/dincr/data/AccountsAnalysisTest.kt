package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Cuentas (the second surface of the mail review), bank identification and the Owner's
 * "Análisis financiero". The fake keeps ONE candidate store, as the backend does.
 */
class AccountsAnalysisTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    private fun fixture(plan: PlanTier = PlanTier.VIP, role: FakeBackend.Role = FakeBackend.Role.USER) =
        FakeBackend(FakeBackend.Scenario.POPULATED, plan, role = role).let { it to DincrApi(ApiClient("https://fixtures.invalid", { "t" }, it, AppLanguage.SPANISH, backoff = {})) }

    private suspend fun status(block: suspend () -> Unit): Int = try { block(); 200 } catch (error: ApiError) { error.status }

    @Test fun banksAreIdentifiedLikeTheWebApp() {
        assertEquals("bac", BankBranding.identify("BAC Credomatic")?.id)
        assertEquals("bac", BankBranding.identify("credomatic")?.id)
        assertEquals("bn", BankBranding.identify("Banco Nacional de Costa Rica")?.id)
        assertEquals("bcr", BankBranding.identify("Banco de Costa Rica")?.id)
        assertEquals("bn", BankBranding.identify("BNCR")?.id)
        assertEquals("davibank", BankBranding.identify("scotiabank")?.id)
        assertEquals("popular", BankBranding.identify("Banco Popular")?.id)
        assertEquals("multimoney", BankBranding.identify("Multi Money")?.id)
        assertEquals("promerica", BankBranding.identifyInText("Notificación de Banco Promerica")?.id)
        assertNull(BankBranding.identify("unknown"))
        assertNull(BankBranding.identify(""))
        assertNull(BankBranding.identify("Cooperativa de ejemplo"))
        // Every known bank has one of the historical assets; nothing else gets a logo.
        assertTrue(BankBranding.KNOWN.all { it.hasLogo })
        val fallback = BankBranding.describe(null, "Cooperativa de ejemplo")
        assertFalse(fallback.known || fallback.hasLogo)
        assertEquals("CE", fallback.short)
        assertEquals("?", BankBranding.describe(null, null).short)
    }

    @Test fun onboardingKeepsTheStoredInstitutionIds() {
        val list = BankBranding.onboardingInstitutions(AppLanguage.SPANISH)
        assertEquals(listOf("bac", "bn", "bcr", "popular", "davivienda", "scotiabank", "promerica", "multimoney"), list.map { it.id })
        // DAVIbank keeps the historical id scotiabank, with the DAVIbank logo.
        assertEquals("davibank", list.first { it.id == "scotiabank" }.logoId)
        assertTrue(list.all { BankBranding.identify(it.logoId)?.hasLogo == true })
    }

    @Test fun accountsAreGroupedByInstitutionCodeWithoutBalances() = runTest {
        val (_, api) = fixture()
        val groups = Accounts.group(api.financialIdentity().items, api.mailCandidates(pendingOnly = false))
        assertEquals(listOf("bac", "multimoney", "popular", Accounts.OTHER), groups.map { it.key })
        val bac = groups.first { it.key == "bac" }
        assertEquals(1, bac.accounts.size)
        assertEquals(2, bac.movements)
        assertEquals(2, bac.pending)
        assertEquals("the code, never the label", listOf("bac"), bac.bankQueries)
        // A known bank without a detected account still has its group.
        val multimoney = groups.first { it.key == "multimoney" }
        assertTrue(multimoney.accounts.isEmpty())
        assertEquals(1, multimoney.movements)
        val other = groups.last()
        assertNull("an unknown institution has no identity (fallback logo)", other.bank)
        assertEquals(listOf("cooperativa_ejemplo"), other.bankQueries)
        assertEquals(0, other.pending)
        assertEquals("•••• 1234", Accounts.maskedLabel(bac.accounts.single()))
        assertNull(Accounts.maskedLabel(FinancialIdentity.Account(9)))
        assertEquals("•••• 6789", Accounts.maskedLabel(FinancialIdentity.Account(9, accountLast4 = "123456789")))
    }

    @Test fun aBankWhoseLabelDiffersFromItsCodeListsItsMovements() = runTest {
        val (backend, api) = fixture()
        val identity = api.financialIdentity().items
        val popular = Accounts.group(identity, api.mailCandidates(pendingOnly = false)).first { it.key == "popular" }
        // The account says "Banco Popular"; the candidates say "popular": grouped together, queried by code.
        assertEquals("Banco Popular", popular.accounts.single().bankName)
        assertEquals(listOf("popular"), popular.bankQueries)
        val movements = Accounts.merge(popular.bankQueries.map { api.mailCandidates(bank = it) })
        assertTrue(backend.requests.last().url.contains("bank=popular"))
        assertEquals(listOf(23L), movements.map { it.candidateId })
        // Querying by the label finds nothing: the label is for display only.
        assertTrue(api.mailCandidates(bank = "Banco Popular").isEmpty())
    }

    @Test fun bothSurfacesShareOneCandidateStore() = runTest {
        val (backend, api) = fixture()
        // Cuentas: the bank and account filters reach the same endpoint as Email Monitor.
        val byBank = api.mailCandidates(bank = "bac")
        assertTrue(backend.requests.last().url.contains("/user-product/vip/gmail/emails?status=&bank=bac"))
        assertEquals(listOf(21L, 22L), byBank.map { it.candidateId })
        val byAccount = api.mailCandidates(financialAccountId = 2)
        assertTrue(backend.requests.last().url.contains("financial_account_id=2"))
        assertEquals(listOf(23L), byAccount.map { it.candidateId })
        assertEquals("transfer_in", byAccount.single().bankMovement)
        assertEquals("income", byAccount.single().financialEffect)

        // Accept in Cuentas → Correos (the whole inbox) shows it confirmed and no longer pending.
        assertEquals("confirmed", api.acceptCandidate(21).status)
        assertEquals("confirmed", api.mailCandidates(pendingOnly = false).first { it.candidateId == 21L }.reviewStatus)
        assertTrue(api.mailCandidates(pendingOnly = true).none { it.candidateId == 21L })
        // Reject in Correos → Cuentas shows it rejected.
        assertEquals("rejected", api.rejectCandidate(23).status)
        assertEquals("rejected", api.mailCandidates(financialAccountId = 2).single().reviewStatus)

        // Accepting twice never records a second movement: the backend answers already_reviewed.
        val before = api.movements().size
        val again = api.acceptCandidate(21)
        assertEquals(true, again.alreadyReviewed)
        assertEquals(before, api.movements().size)
        assertEquals(1, api.movements().count { it.description == "Compra en supermercado" && it.origin == "transaction" })
    }

    @Test fun ownershipIsTheExistingAction() = runTest {
        val (_, api) = fixture()
        api.setAccountOwnership(1, own = true)
        assertEquals("own", api.financialIdentity().items.first { it.id == 1L }.ownershipStatus)
        // A detected account never carries a balance in the native model.
        assertFalse(FinancialIdentity.Account::class.java.declaredFields.any { it.name.contains("balance", ignoreCase = true) })
    }

    @Test fun candidateRowsDecodeTheNewFields() {
        val row = json.decodeFromString<MailCandidate>("""{"candidate_id":7,"bank":"BAC","financial_account_id":3,"bank_movement":null,"financial_effect":"expense","extra":1}""")
        assertEquals(3L, row.financialAccountId)
        assertNull(row.bankMovement)
        assertEquals("expense", row.financialEffect)
    }

    @Test fun ownerAnalysisIsOwnerOnlyAndReadsTheThreeEndpoints() = runTest {
        val (_, user) = fixture(PlanTier.VIP)
        assertEquals(403, status { user.transactionAnalysis() })
        assertEquals(403, status { user.netWorth() })
        assertEquals(403, status { user.financialEngine() })
        val (backend, owner) = fixture(PlanTier.FREE, FakeBackend.Role.OWNER)
        val analysis = owner.transactionAnalysis()
        val netWorth = owner.netWorth()
        val engine = owner.financialEngine()
        assertEquals(listOf("/transactions/analysis/summary", "/finance/net-worth", "/finance/engine"),
            backend.requests.takeLast(3).map { it.url.substringAfter("fixtures.invalid").substringBefore("?") })
        assertEquals(6, analysis.monthlyFlow.size)
        assertTrue(analysis.spendingBreakdown!!.categories.isNotEmpty())
        assertEquals(analysis.monthlyFlow.map { it.month }, analysis.expensesByMonth.map { it.month })
        assertTrue(netWorth.netWorth != null && netWorth.assets?.assetsTotal != null)
        assertEquals("stable", engine.health?.level)
        assertTrue(Jarvis.Section.ANALYSIS.isAvailable)
    }

    @Test fun analysisDecodingIsTolerant() {
        val engine = json.decodeFromString<FinancialEngineReport>("""{"status":"OK","health":{"score":54.5,"level":"stable","components":{}},
            "forecast":{"status":"OK","projected_end_balance":-1200.5,"alert":{"level":"high","message":"m"}},"debts":{"status":"EMPTY","recommended":null},
            "emergency_fund":{"current":0,"monthly_base":0},"recommendations":["a"],"reconciliation":{"status":"DATA_REQUIRED"}}""")
        assertEquals(0, BigDecimal("-1200.5").compareTo(engine.forecast?.projectedEndBalance))
        assertNull(engine.debts?.recommended)
        val worth = json.decodeFromString<NetWorthReport>("""{"assets":{"savings":[],"assets_total":0},"liabilities":{"debt_total":10},"net_worth":-10,"change":{"amount":0,"percentage":null},"ratios":{}}""")
        assertNull(worth.change?.percentage)
    }
}
