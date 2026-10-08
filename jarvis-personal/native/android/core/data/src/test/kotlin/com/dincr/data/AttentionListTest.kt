package com.dincr.data

import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** "Para atender" (UX-5): presentation rules only, synthetic data. The Swift twin is `AttentionTests`. */
class AttentionListTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }
    private fun center(raw: String) = json.decodeFromString<CommandCenter>(raw)
    private fun advisor(raw: String) = json.decodeFromString<ProactiveAdvisor>(raw)
    private fun alerts(vararg severities: String) =
        severities.mapIndexed { i, s -> """{"severity":"$s","title":"A$i","context":"c$i","action":"Hacé algo"}""" }.joinToString(",")

    // 0 / 1 / 3 / >3

    @Test fun nothingToAttendLeavesTheSectionOut() {
        assertTrue(AttentionList.today(null).isEmpty)
        assertTrue(AttentionList.today(center("{}")).isEmpty)
        assertTrue(AttentionList.today(center("""{"alerts":[],"automation":{"review":0}}""")).isEmpty)
        // A title-less alert says nothing: it is not shown.
        assertTrue(AttentionList.today(center("""{"alerts":[{"severity":"high","title":"  "}]}""")).isEmpty)
    }

    @Test fun oneItemIsShownWithoutSeeAll() {
        val today = AttentionList.today(center("""{"alerts":[${alerts("medium")}]}"""))
        assertEquals(1, today.visible.size); assertFalse(today.showsSeeAll)
    }

    @Test fun exactlyThreeAreShownWithoutSeeAll() {
        val today = AttentionList.today(center("""{"alerts":[${alerts("medium", "high", "medium")}]}"""))
        assertEquals(3, today.visible.size); assertFalse(today.showsSeeAll)
    }

    @Test fun moreThanThreeShowThreeAndSeeAll() {
        val value = center("""{"alerts":[${alerts("medium", "medium", "high", "critical")}],"automation":{"review":2}}""")
        val today = AttentionList.today(value)
        assertEquals(3, today.visible.size); assertTrue(today.showsSeeAll)
        // The full list is the same items, uncapped.
        val all = AttentionList.items(value, null)
        assertEquals(5, all.size)
        assertEquals(today.visible, all.take(3))
    }

    // Order

    @Test fun criticalThenHighThenMediumThenSuccess() {
        val value = center("""{"alerts":[${alerts("medium", "high", "critical")}]}""")
        val advice = advisor("""{"status":"ALERTS","alerts":[{"id":"p","code":"debt_progress","severity":"success","title":"Tu deuda disminuyó","explanation":"e","action":{"label":"Ver","route":"vip-monthly-review"}},{"id":"h","code":"debt_increase","severity":"high","title":"Subió la deuda","explanation":"e","action":{"route":"debts"}}]}""")
        val items = AttentionList.items(value, advice)
        assertEquals(listOf("critical", "high", "high", "medium", "success"), items.map { it.severity })
        // Same severity: command center before the advisor.
        assertEquals(AttentionItem.Source.COMMAND_CENTER, items[1].source)
        assertEquals(AttentionItem.Source.ADVISOR, items[2].source)
        assertEquals(MessageKind.POSITIVE, items.last().kind)
    }

    @Test fun theOwnersCriticalComesBeforeHigh() {
        val items = AttentionList.today(center("""{"alerts":[${alerts("high", "critical")}]}""")).visible
        assertEquals(listOf("critical", "high"), items.map { it.severity })
    }

    @Test fun theOrderIsDeterministicAndKeepsTheBackendsOrderWithinASeverity() {
        val value = center("""{"alerts":[${alerts("medium", "medium", "medium")}]}""")
        val first = AttentionList.items(value, null)
        assertEquals(listOf("A0", "A1", "A2"), first.map { it.title })
        assertEquals(first, AttentionList.items(value, null))
    }

    @Test fun anUnknownSeverityIsNeverDowngraded() {
        assertTrue(AttentionList.rank("critical") < AttentionList.rank("high"))
        assertTrue(AttentionList.rank("high") < AttentionList.rank("medium"))
        assertEquals(AttentionList.rank("medium"), AttentionList.rank("unexpected"))
        assertTrue(AttentionList.rank(null) < AttentionList.rank("success"))
    }

    // Semantics (UX-1)

    @Test fun financialMattersAreAttentionNeverTechnicalErrors() {
        val items = AttentionList.items(center("""{"alerts":[${alerts("critical", "high", "medium")}],"automation":{"review":1}}"""), null)
        assertTrue(items.all { it.kind == MessageKind.ATTENTION })
        assertTrue(items.none { it.kind == MessageKind.TECHNICAL_ERROR })
    }

    @Test fun successIsPositiveAndARecommendationIsAnOpportunity() {
        val advice = advisor("""{"status":"ALERTS","alerts":[{"id":"s","code":"strategy_changed","severity":"medium","title":"DINCR reajustó tu estrategia","explanation":"La prioridad cambió.","action":{"route":"strategy"}},{"id":"m","code":"emergency_milestone_1","severity":"success","title":"Alcanzaste un hito","explanation":"1 mes","action":{"route":"vip-emergency"}}]}""")
        val items = AttentionList.items(null, advice)
        assertEquals(MessageKind.OPPORTUNITY, items.first { it.title.startsWith("DINCR") }.kind)
        assertEquals(MessageKind.POSITIVE, items.first { it.title.startsWith("Alcanzaste") }.kind)
        assertTrue(items.all { it.isChange })   // the advisor reports changes, not the absolute state
    }

    // Sources and duplicates

    @Test fun theAdvisorIsNeverInTodaysThreeButIsInTheFullList() {
        val value = center("""{"alerts":[${alerts("medium")}]}""")
        val advice = advisor("""{"status":"ALERTS","alerts":[{"id":"x","code":"debt_increase","severity":"critical","title":"Subió la deuda","explanation":"e","action":{"route":"debts"}}]}""")
        assertTrue(AttentionList.today(value).visible.none { it.source == AttentionItem.Source.ADVISOR })
        assertEquals(AttentionItem.Source.ADVISOR, AttentionList.items(value, advice).first().source)
    }

    @Test fun pendingNoticesAndTheirAlertAreOneItem() {
        val value = center("""{"alerts":[{"severity":"medium","title":"Movimientos por revisar","context":"Hay 3 movimientos importados sin confirmar.","action":"Revisalos antes de confiar en el cierre mensual."}],"automation":{"review":3}}""")
        val items = AttentionList.items(value, null)
        assertEquals(1, items.size)
        assertEquals(AttentionItem.Source.REVIEW, items[0].source)
        assertEquals(AttentionItem.Destination.REVIEW, items[0].destination)
        assertTrue(items[0].message.startsWith("Hay 3 movimientos"))   // the command center's own words
        val english = center("""{"alerts":[{"severity":"medium","title":"Transactions to review","context":"c"}],"automation":{"review":1}}""")
        assertEquals(1, AttentionList.items(english, null, language = AppLanguage.ENGLISH).size)
    }

    @Test fun pendingNoticesWithoutTheirAlertStillGetOneItem() {
        val items = AttentionList.items(center("""{"automation":{"review":2}}"""), null, language = AppLanguage.SPANISH)
        assertEquals(1, items.size)
        assertEquals(AttentionItem.Destination.REVIEW, items[0].destination)
        assertTrue(items[0].message.contains("2 avisos"))
    }

    @Test fun noPendingNoticesMeansNoReviewItem() {
        val items = AttentionList.items(center("""{"alerts":[{"severity":"medium","title":"Movimientos por revisar","context":"c"}],"automation":{"review":0}}"""), null)
        assertEquals(1, items.size)
        assertNull(items[0].destination)
        assertEquals(AttentionItem.Source.COMMAND_CENTER, items[0].source)
    }

    @Test fun theHealthScoreIsNotAFactInTheList() {
        val advice = advisor("""{"status":"ALERTS","alerts":[{"id":"h","code":"health_score_drop","severity":"high","title":"Bajó tu salud financiera","explanation":"−12 puntos","action":{"route":"situation"}}]}""")
        assertTrue(AttentionList.items(null, advice).isEmpty())
    }

    @Test fun pausedMailAutomationKeepsTheNoticesWithoutALink() {
        val value = center("""{"alerts":[{"severity":"medium","title":"Movimientos por revisar","context":"c"}],"automation":{"review":3}}""")
        val items = AttentionList.items(value, null, mailReviewAvailable = false)
        assertEquals(1, items.size)
        assertEquals(AttentionItem.Source.REVIEW, items[0].source)
        assertNull(items[0].destination)
        assertNull(AttentionList.today(center("""{"automation":{"review":1}}"""), mailReviewAvailable = false).visible.single().destination)
    }

    @Test fun anUnavailableSourceIsNotATechnicalProblem() {
        assertTrue(AttentionList.isUnavailable(ApiError(ApiError.Kind.FEATURE_UNAVAILABLE, 503, message = "x")))
        assertTrue(AttentionList.isUnavailable(ApiError(ApiError.Kind.FORBIDDEN, 403, message = "x")))
        assertTrue(AttentionList.isUnavailable(ApiError(ApiError.Kind.SUBSCRIPTION_REQUIRED, 402, message = "x")))
        assertFalse(AttentionList.isUnavailable(ApiError(ApiError.Kind.SERVER, 500, message = "x")))
        assertFalse(AttentionList.isUnavailable(ApiError(ApiError.Kind.OFFLINE, message = "x")))
        assertFalse(AttentionList.isUnavailable(IllegalStateException()))
    }

    // Destinations

    @Test fun commandCenterFreeTextNeverBecomesALink() {
        val items = AttentionList.items(center("""{"alerts":[{"severity":"high","title":"Saldo bajo","context":"c","action":"Revisá la deuda"}]}"""), null)
        assertNull(items[0].destination)
        assertEquals("c Revisá la deuda", items[0].message)   // kept as words
    }

    @Test fun advisorRoutesOpenTheirRealScreens() {
        assertEquals(AttentionItem.Destination.DEBTS, AttentionList.destination("debts"))
        assertEquals(AttentionItem.Destination.SALVAVIDAS, AttentionList.destination("vip-emergency"))
        assertEquals(AttentionItem.Destination.INCOME_BASE, AttentionList.destination("situation"))  // UX-7: no Situación screen
        assertEquals(AttentionItem.Destination.STRATEGY, AttentionList.destination("strategy"))
        assertEquals(AttentionItem.Destination.MOVEMENTS, AttentionList.destination("finance"))
        assertEquals(AttentionItem.Destination.MONTHLY_REVIEW, AttentionList.destination("/vip-monthly-review"))
    }

    @Test fun destinationsMapToTheSameScreensAsIos() {
        // App routes that exist in MainScaffold; the review item opens the Email Monitor.
        assertEquals(
            mapOf("review" to "mail", "debts" to "debts", "salvavidas" to "salvavidas", "incomeBase" to "incomeBase",
                "strategy" to "strategy", "movements" to "movements", "monthlyReview" to "review"),
            AttentionItem.Destination.entries.associate { it.key to it.route },
        )
    }

    @Test fun anUnknownAdvisorRouteIsShownWithoutALink() {
        assertNull(AttentionList.destination("vip-projections"))
        assertNull(AttentionList.destination(null))
        val advice = advisor("""{"status":"ALERTS","alerts":[{"id":"u","code":"new_code","severity":"medium","title":"Algo nuevo","explanation":"e","action":{"route":"somewhere"}}]}""")
        val items = AttentionList.items(null, advice)
        assertEquals(1, items.size)
        assertNull(items[0].destination)
    }

    // Data and purity

    @Test fun noAmountIsInventedAndTheBackendWordsAreKept() {
        val value = center("""{"alerts":[{"severity":"critical","title":"Este mes tus compromisos superan tus ingresos","context":"Faltan ₡150,000 para cubrir compromisos conocidos.","action":null}]}""")
        assertEquals("Faltan ₡150,000 para cubrir compromisos conocidos.", AttentionList.items(value, null)[0].message)
        // With no alerts (for example an unknown income, #324) nothing is shown: no zero is made up.
        assertTrue(AttentionList.items(center("""{"alerts":[],"safe_to_spend":{"amount":0}}"""), null).isEmpty())
    }

    @Test fun readingTheSourcesOnlySendsGets() = runTest {
        // Hoy and "Ver todas" read the command center and the advisor: GETs only, never a write, a
        // notification or the notifications cron.
        for (role in FakeBackend.Role.entries) {
            val backend = FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP, role = role)
            val api = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, backend, AppLanguage.SPANISH, backoff = {}))
            val before = backend.requests.size
            val items = AttentionList.items(api.commandCenter(), api.proactiveAdvisor(), language = AppLanguage.SPANISH)
            val sent = backend.requests.drop(before)
            assertEquals("$role", listOf("GET", "GET"), sent.map { it.method })
            assertTrue("$role", sent.none { "notification" in it.url })
            // The fixture's four matters, the pending-review alert merged with the mail count.
            assertEquals("$role", 4, items.size)
            assertEquals("$role", 1, items.count { it.destination == AttentionItem.Destination.REVIEW })
            assertEquals("$role", "high", items.first().severity)
        }
    }
}
