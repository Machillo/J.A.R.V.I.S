package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * The native RC's data layer: mail returns, conversion preview, contract checks, flags, plans and
 * the fake backend's parity with FastAPI semantics. The Swift twin is `NativeRcTests`.
 */
class NativeRcTest {
    private fun d(value: String) = BigDecimal(value)
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
    private val schemes = setOf("com.dincr.app", "com.finva.app")

    // --- Mail connection return ----------------------------------------------------------------

    @Test fun mailReturnParsesOnlyTheExactDeepLink() {
        val ok = MailReturn.parse("com.finva.app://gmail/callback?gmail=authorized&flow=f1&completion=c1&ret=r1", schemes)
        assertNotNull(ok)
        assertEquals(MailReturn.Provider.GMAIL, ok!!.provider)
        assertTrue(ok.isAuthorized)
        assertEquals("gmail:authorized:f1:r1", ok.key)
        val outlook = MailReturn.parse("com.dincr.app://gmail/callback?microsoft=authorized&flow=f2&completion=c2&ret=r2", schemes)
        assertEquals(MailReturn.Provider.MICROSOFT, outlook?.provider)
        val denied = MailReturn.parse("com.dincr.app://gmail/callback?gmail=denied&ret=r3", schemes)
        assertFalse(denied!!.isAuthorized)
        for (hostile in listOf(
            "https://evil.example/gmail/callback?gmail=authorized&flow=f&completion=c",
            "com.dincr.app.evil://gmail/callback?gmail=authorized&flow=f&completion=c",
            "com.dincr.app://gmail.evil/callback?gmail=authorized&flow=f&completion=c",
            "com.dincr.app://gmail/callbackX?gmail=authorized&flow=f&completion=c",
            "com.dincr.app://user@gmail/callback?gmail=authorized&flow=f&completion=c",
            "com.dincr.app://gmail:99/callback?gmail=authorized&flow=f&completion=c",
            "com.dincr.app://gmail/callback?gmail=authorized&flow=f&completion=c#x",
            "com.dincr.app://gmail/callback?gmail=authorized&gmail=denied&flow=f&completion=c",
            "com.dincr.app://gmail/callback?gmail=authorized&microsoft=authorized&flow=f&completion=c",
            "com.dincr.app://gmail/callback?flow=f&completion=c",
            "com.dincr.app://gmail/callback?gmail=authorized&flow=f&flow=g&completion=c",
            "not a url",
        )) assertNull(hostile, MailReturn.parse(hostile, schemes))
        assertFalse("an authorized return without a completion code is not redeemable",
            MailReturn.parse("com.dincr.app://gmail/callback?gmail=authorized&flow=f", schemes)!!.isAuthorized)
    }

    @Test fun handledReturnsAreRememberedOnceAndBounded() {
        val handled = HandledReturns(capacity = 3)
        listOf("a", "b", "b", "c", "d").forEach(handled::add)
        assertEquals(listOf("b", "c", "d"), handled.snapshot)
        assertTrue(handled.contains("d"))
        assertFalse(handled.contains("a"))
        assertEquals(listOf("c", "d"), HandledReturns(listOf("a", "b", "c", "d"), capacity = 2).snapshot)
    }

    // --- Conversion preview matches the backend arithmetic -------------------------------------

    @Test fun conversionPreviewMatchesTheBackend() {
        assertEquals(d("5075.00"), ConversionPreview.baseAmount(d("10"), "USD", "CRC", d("507.5")))
        assertEquals(d("5056.29"), ConversionPreview.baseAmount(d("9.99"), "USD", "CRC", d("506.135")))
        assertEquals(d("19.70"), ConversionPreview.baseAmount(d("10000"), "CRC", "USD", d("507.5")))
        // Rate rounded to 6 decimals first, then half-up to cents.
        assertEquals(d("0.01"), ConversionPreview.baseAmount(d("0.01"), "USD", "CRC", d("1.0000004")))
        assertNull(ConversionPreview.baseAmount(d("10"), "USD", "CRC", d("0.0000004")))
        assertNull(ConversionPreview.baseAmount(d("10"), "USD", "CRC", null))
        assertNull(ConversionPreview.baseAmount(d("10"), "EUR", "CRC", d("600")))
        assertEquals(d("10.00"), ConversionPreview.baseAmount(d("10"), "CRC", "CRC", d("1")))
    }

    @Test fun latestUserRateComesOnlyFromManualEntries() {
        val rows = listOf(
            Movement("expense:1", 1, "expense", "2026-09-01", "a", d("5000"), "expense", exchangeRate = d("500"), originalAmount = d("10"), originalCurrency = "USD"),
            Movement("salary:2", 2, "salary", "2026-09-05", "b", d("5100"), "income", exchangeRate = d("510"), originalAmount = d("10"), originalCurrency = "USD"),
            Movement("transaction:3", 3, "transaction", "2026-09-09", "mail", d("5200"), "expense", exchangeRate = d("520"), originalAmount = d("10"), originalCurrency = "USD"),
        )
        assertEquals(d("510"), ConversionPreview.latestUserRate(rows))
        assertNull(ConversionPreview.latestUserRate(emptyList()))
    }

    // --- Currency rows: which can be edited, and how -------------------------------------------

    @Test fun manualCurrencyRowsAreEditableWithTheirOwnRate() {
        fun row(origin: String, extra: String) = json.decodeFromString<Movement>(
            """{"movement_id":"$origin:1","origin":"$origin","transaction_date":"2026-09-01","amount":5075,"transaction_type":"expense","editable":true$extra}""")
        val full = ""","original_amount":10,"original_currency":"USD","exchange_rate":507.5"""
        val usd = listOf("CRC", "USD")
        assertTrue(row("expense", full).isCurrencyEditable(usd))
        assertTrue(row("salary", full).canEdit(usd))
        assertFalse("no longer converted by this backend", row("expense", full).isCurrencyEditable(listOf("CRC")))
        assertFalse("mail transactions stay read-only", row("transaction", full).canEdit(usd))
        assertFalse("partial data", row("expense", ""","original_currency":"USD","exchange_rate":507.5""").canEdit(usd))
        assertFalse("no rate", row("expense", ""","original_amount":10,"original_currency":"USD"""").canEdit(usd))
        assertTrue("plain rows", row("expense", "").canEdit(usd))
        assertTrue(row("expense", "").acceptsCurrency)
        assertFalse(row("transaction", "").acceptsCurrency)
    }

    @Test fun baseEditsCarryNoCurrencyAndForeignEditsCarryTheRate() {
        val base = json.parseToJsonElement(json.encodeToString(MovementUpdate.serializer(), MovementUpdate("2026-09-01", "x", d("1"), "expense", "Otros"))).toString()
        assertFalse(base, base.contains("currency") || base.contains("exchange_rate"))
        val foreign = json.parseToJsonElement(json.encodeToString(MovementUpdate.serializer(), MovementUpdate("2026-09-01", "x", d("10"), "expense", "Otros", "", "USD", d("507.5")))).toString()
        assertTrue(foreign, foreign.contains("\"currency\":\"USD\"") && foreign.contains("\"exchange_rate\":507.5"))
    }

    // --- Mail candidates: native currency and what the user can do -----------------------------

    @Test fun candidatesUseTheNoticeCurrency() {
        val usd = MailCandidate(candidateId = 1, amount = d("12700"), currency = "CRC", originalAmount = d("25"), originalCurrency = "USD", accountBaseCurrency = "CRC", reviewStatus = "pending")
        assertEquals("USD", usd.nativeCurrency)
        assertEquals(d("25"), usd.nativeAmount)
        assertTrue(usd.needsRate)
        assertFalse(usd.cannotConvert)
        val plain = MailCandidate(candidateId = 2, amount = d("15300"), currency = "CRC", accountBaseCurrency = "CRC", reviewStatus = "pending")
        assertEquals("CRC", plain.nativeCurrency)
        assertFalse(plain.needsRate)
        val euro = MailCandidate(candidateId = 3, amount = d("40"), currency = "EUR", accountBaseCurrency = "CRC")
        assertTrue(euro.cannotConvert)
        assertFalse(euro.needsRate)
    }

    // --- Contract checks before sending --------------------------------------------------------

    @Test fun writesOutsideTheContractFailLocally() {
        fun rejected(block: () -> Unit) = try { block(); fail("must be rejected") } catch (e: ApiError) { assertEquals(ApiError.Kind.VALIDATION, e.kind) }
        val ok = DebtRequest("Tarjeta", "credit_card", d("1000"), d("2000"), d("100"), d("36.5"), 12, 15, "2026-10-15")
        ok.checked()
        rejected { ok.copy(remainingAmount = d("10000000000.00")).checked() }
        rejected { ok.copy(monthlyPayment = d("1.001")).checked() }
        rejected { ok.copy(interestRate = d("10000")).checked() }
        rejected { ok.copy(termMonths = 0).checked() }
        rejected { ok.copy(paymentDay = 32).checked() }
        rejected { ok.copy(nextPaymentDate = "2026-02-30").checked() }
        rejected { ok.copy(nextPaymentDate = "15/10/2026").checked() }
        rejected { ok.copy(totalAmount = d("500")).checked() }
        rejected { ok.copy(name = " ").checked() }
        val goal = GoalRequest("Viaje", d("100000"), d("0"), "2027-01-01", "high")
        goal.checked()
        rejected { goal.copy(targetAmount = BigDecimal.ZERO).checked() }
        rejected { goal.copy(priority = "urgentísima").checked() }
        rejected { goal.copy(status = "archived").checked() }
        rejected { GoalContribution(d("1"), "ayer").checked() }
        val plan = SavingsPlanRequest("Ahorro", d("10000"), d("0"), "2026-10-01", "2027-10-01")
        plan.checked()
        rejected { plan.copy(endDate = "2026-09-01").checked() }
        val correction = CandidateCorrection("2026-09-01", "Compra", d("25"), "expense", "Compras", d("507.5"))
        correction.checked()
        rejected { correction.copy(exchangeRate = d("100001")).checked() }
        rejected { correction.copy(exchangeRate = d("0.0000001")).checked() }
        rejected { correction.copy(transactionType = "transfer").checked() }
        rejected { correction.copy(category = "").checked() }
    }

    @Test fun ratesAndInterestParseWithinTheirColumns() {
        val dc = MoneyFormat.Separators.DOT_COMMA
        assertEquals(d("507.5"), ExchangeRateInput.parse("507,5", dc))
        assertEquals(d("0.000001"), ExchangeRateInput.parse("0,000001", dc))
        assertNull(ExchangeRateInput.parse("0,0000001", dc))
        assertEquals(d("100000"), ExchangeRateInput.parse("100.000", dc))
        assertNull(ExchangeRateInput.parse("100.000,01", dc))
        assertNull(ExchangeRateInput.parse("0", dc))
        assertEquals(d("9999.9999"), InterestRateInput.parse("9.999,9999", dc))
        assertEquals(BigDecimal.ZERO, InterestRateInput.parse("0", dc)?.stripTrailingZeros()?.let { if (it.signum() == 0) BigDecimal.ZERO else it })
        assertNull(InterestRateInput.parse("10.000", dc))
        assertEquals(15, WholeNumberInput.parse(" 15 ", 1..31))
        assertNull(WholeNumberInput.parse("32", 1..31))
        assertNull(WholeNumberInput.parse("1e1", 1..31))
        assertNull(WholeNumberInput.parse("-1", 1..31))
        assertTrue(IsoDate.isValid("2028-02-29"))
        assertFalse(IsoDate.isValid("2027-02-29"))
        assertFalse(IsoDate.isValid("2027-2-9"))
        assertEquals(BigDecimal.ZERO.compareTo(AmountInput.parseZeroOrMore("0", dc)), 0)
        assertNull(AmountInput.parseZeroOrMore("", dc))
    }

    // --- Flags, plans, release policy ----------------------------------------------------------

    @Test fun unknownFlagsUseTheBackendSafeDefaults() {
        val none = FeatureFlags()
        assertFalse(none.isEnabled(OpsFlag.FINANCIAL_WRITES))
        assertFalse(none.isEnabled(OpsFlag.GMAIL_AUTOMATION))
        assertFalse(none.isEnabled(OpsFlag.STORE_BILLING))
        assertTrue(none.isEnabled(OpsFlag.VIP_INTELLIGENCE))
        assertTrue(none.isEnabled(OpsFlag.ADVANCED_REPORTS))
        val loaded = json.decodeFromString<FeatureFlags>("""{"flags":[{"flag_key":"financial_writes","enabled":true},{"flag_key":"vip_intelligence","enabled":false,"disabled_message_es":"Pausa"}]}""")
        assertTrue(loaded.isEnabled(OpsFlag.FINANCIAL_WRITES))
        assertFalse(loaded.isEnabled(OpsFlag.VIP_INTELLIGENCE))
        assertEquals("Pausa", loaded.message(OpsFlag.VIP_INTELLIGENCE, AppLanguage.SPANISH))
    }

    @Test fun planGatingMatchesTheBackendMinimums() {
        assertTrue(PlanTier.FREE.allows(Feature.DEBTS))
        assertFalse(PlanTier.FREE.allows(Feature.STRATEGY_BASIC))
        assertTrue(PlanTier.BASIC.allows(Feature.GUIDED_BUDGET))
        assertFalse(PlanTier.BASIC.allows(Feature.GMAIL_AUTOMATION))
        assertTrue(PlanTier.VIP.allows(Feature.STRATEGY_VIP))
        assertEquals(PlanTier.FREE, PlanTier.from(null))
        assertEquals(PlanTier.FREE, PlanTier.from("owner"))
        assertEquals(PlanTier.VIP, PlanTier.from("VIP"))
    }

    @Test fun releasePolicyIsOnlyBindingWhenActive() {
        assertFalse(json.decodeFromString<ReleasePolicy>("""{"status":"current","required":false,"active":false}""").isRequired)
        assertTrue(json.decodeFromString<ReleasePolicy>("""{"status":"required","required":true,"active":true}""").isRequired)
        assertFalse("inactive policies never block", json.decodeFromString<ReleasePolicy>("""{"status":"required","required":true,"active":false}""").isRequired)
        assertTrue(json.decodeFromString<ReleasePolicy>("""{"status":"optional","active":true}""").isOptional)
    }

    @Test fun appLockPolicyNeedsFiveMinutesAway() {
        assertFalse(AppLockPolicy.shouldLock(true, null, 1_000_000))
        assertFalse(AppLockPolicy.shouldLock(true, 0, AppLockPolicy.TIMEOUT_MS - 1))
        assertTrue(AppLockPolicy.shouldLock(true, 0, AppLockPolicy.TIMEOUT_MS))
        assertFalse(AppLockPolicy.shouldLock(false, 0, AppLockPolicy.TIMEOUT_MS * 10))
        assertFalse("a clock that goes back never locks by itself", AppLockPolicy.shouldLock(true, 10_000, 5_000))
    }

    @Test fun idempotencyKeysMatchTheBackendPattern() {
        repeat(20) { assertTrue(Regex("^[A-Za-z0-9_-]{8,80}$").matches(IdempotencyKey.new())) }
        assertEquals(100, (1..100).map { IdempotencyKey.new() }.toSet().size)
    }

    // --- Transport: kill switches and public calls ---------------------------------------------

    @Test fun killSwitchIsNotRetriedAndCarriesItsFeature() = runTest {
        var calls = 0
        val client = ApiClient("https://api.example.test", { "t" }, { calls += 1; HttpResponse(503, """{"detail":"Pausa","code":"feature_temporarily_unavailable","feature":"gmail_automation"}""") }, AppLanguage.SPANISH, backoff = {})
        try { DincrApi(client).mailStatus(); fail() } catch (e: ApiError) {
            assertEquals(ApiError.Kind.FEATURE_UNAVAILABLE, e.kind)
            assertEquals("gmail_automation", e.feature)
            assertEquals("Pausa", e.message)
        }
        assertEquals("a deliberate pause is not retried", 1, calls)
        var other = 0
        val flaky = ApiClient("https://api.example.test", { "t" }, { other += 1; HttpResponse(503, "{}") }, AppLanguage.SPANISH, backoff = {})
        try { DincrApi(flaky).mailStatus(); fail() } catch (_: ApiError) {}
        assertEquals("an ordinary 503 on a GET is retried twice", 3, other)
    }

    @Test fun releasePolicyIsPublicAndCarriesTheVersion() = runTest {
        val requests = mutableListOf<HttpRequest>()
        val client = ApiClient("https://api.example.test", { error("no token needed") }, { requests += it; HttpResponse(200, """{"status":"current","active":false}""") }, AppLanguage.SPANISH, backoff = {})
        DincrApi(client).releasePolicy("2.0.0-rc.1")
        assertNull(requests.single().headers["Authorization"])
        assertTrue(requests.single().url.endsWith("/product-ops/release-policy?platform=android&version=2.0.0-rc.1"))
    }

    @Test fun eventsOutsideTheAllowListAreNeverSent() = runTest {
        val requests = mutableListOf<HttpRequest>()
        val api = DincrApi(ApiClient("https://api.example.test", { "t" }, { requests += it; HttpResponse(200, """{"status":"recorded"}""") }, AppLanguage.SPANISH, backoff = {}))
        api.recordEvent(ProductEvent("salvavidas_saved", "x"))
        assertTrue(requests.isEmpty())
        api.recordEvent(ProductEvent("dashboard_opened", "home"))
        assertEquals(1, requests.size)
    }

    // --- Fake backend follows FastAPI semantics ------------------------------------------------

    private fun fake(plan: PlanTier = PlanTier.FREE, scenario: FakeBackend.Scenario = FakeBackend.Scenario.POPULATED) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(scenario, plan), AppLanguage.SPANISH, backoff = {}))

    @Test fun fakeBackendEnforcesPlansLikeTheServer() = runTest {
        val free = fake(PlanTier.FREE)
        try { free.budget(); fail() } catch (e: ApiError) { assertEquals(ApiError.Kind.FORBIDDEN, e.kind) }
        try { free.updateDebt(1, DebtRequest("x", remainingAmount = d("1")), "key-12345678"); fail() } catch (e: ApiError) { assertEquals(403, e.status) }
        try { fake(PlanTier.BASIC).mailStatus(); fail() } catch (e: ApiError) { assertEquals(403, e.status) }
        assertNotNull(fake(PlanTier.VIP).commandCenter().safeToSpend)
    }

    @Test fun fakeBackendCandidateReviewFollowsAlreadyReviewed() = runTest {
        val vip = fake(PlanTier.VIP)
        val pending = vip.mailCandidates(true)
        val crc = pending.first { !it.needsRate }
        assertEquals("confirmed", vip.acceptCandidate(crc.candidateId!!).status)
        assertEquals(true, vip.acceptCandidate(crc.candidateId!!).alreadyReviewed)
        val usd = pending.first { it.needsRate }
        try { vip.acceptCandidate(usd.candidateId!!); fail("a foreign notice needs the user's rate") } catch (e: ApiError) { assertEquals(422, e.status) }
        assertEquals("confirmed", vip.correctCandidate(usd.candidateId!!, CandidateCorrection("2026-09-01", "Tienda", d("25"), "expense", "Compras", d("507.5"))).status)
    }

    @Test fun fakeBackendConvertsAndClearsCurrencyLikeTheServer() = runTest {
        val api = fake()
        api.create(MovementKind.EXPENSE, EntryCreate(d("10"), "USD", "Compras", "2026-09-01", "USD", d("507.5")), "key-usd-0001")
        val row = api.movements().first { it.description == "USD" }
        assertEquals(0, d("5075").compareTo(row.amount))
        assertEquals("USD", row.originalCurrency)
        try { api.create(MovementKind.EXPENSE, EntryCreate(d("10"), "sin tasa", "Compras", "2026-09-01", "USD", null), "key-usd-0002"); fail() } catch (e: ApiError) { assertEquals(422, e.status) }
        api.update(row.movementId, MovementUpdate("2026-09-01", "USD", d("5075"), "expense", "Compras"))
        val cleared = api.movements().first { it.movementId == row.movementId }
        assertNull("a base-currency edit clears the original data, as the backend does", cleared.originalCurrency)
    }
}
