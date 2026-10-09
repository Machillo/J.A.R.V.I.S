package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelectable
import androidx.compose.ui.test.isSelected
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeDown
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import com.dincr.data.FakeBackend
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * B17 — pull to refresh on Plan, Patrimonio and Perfil, as Hoy and Movimientos already had: the pull
 * reads the identity, the switches and (Patrimonio) the debts again, each once;
 * every plan keeps its rows and its locks; a refresh that fails keeps the screen and says so in the
 * app-wide notice; the navigation stays where it was; TalkBack gets the same refresh as an action
 * on the tab's title. iOS twin: `PullToRefreshUITests`. FakeBackend only; `dincrRefreshFails` makes
 * the identity read again fail like an unreachable server.
 */
class PullToRefreshUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    private fun launch(plan: String = "free", role: String? = null, refreshFails: Boolean = false) {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
            .putExtra("dincrRefreshFails", refreshFails)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
        waitUntil("Hoy") { tagged(if (role == "owner") "owner.home" else "home.today") }
    }

    @After fun close() { scenario?.close() }

    private val failureNotice get() = tx("No pudimos actualizar. Seguís viendo la información anterior.", "We couldn’t refresh. You’re still seeing the previous information.")
    private val refreshAction get() = tx("Actualizar", "Refresh")
    private val planTab get() = tx("Plan", "Plan")
    private val wealthTab get() = tx("Patrimonio", "Wealth")
    private val profileTab get() = tx("Perfil", "Profile")

    private fun count(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes().size
    private fun present(text: String) = count(text) > 0
    private fun tagged(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun waitUntil(what: String, condition: () -> Boolean) {
        repeat(150) { if (condition()) return; Thread.sleep(100); compose.waitForIdle() }
        throw AssertionError("timed out waiting for $what")
    }
    private fun tab(text: String) {
        waitUntil("tab $text") { compose.onAllNodes(hasText(text) and isSelectable()).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodes(hasText(text) and isSelectable()).onFirst().performSemanticsAction(SemanticsActions.OnClick)
        compose.waitForIdle()
    }
    private fun click(text: String) {
        waitUntil("\"$text\"") { present(text) }
        val node = compose.onAllNodes(hasText(text) and hasClickAction()).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun selectedTab(): String? = compose.onAllNodes(isSelectable() and isSelected()).fetchSemanticsNodes()
        .firstNotNullOfOrNull { node -> node.config.getOrNull(SemanticsProperties.Text)?.joinToString("") { it.text } }

    /** The reads the fake server answered (GET only), from the activity's own model. */
    private fun reads(path: String): Int {
        compose.waitForIdle()
        var backend: FakeBackend? = null
        scenario!!.onActivity { backend = ViewModelProvider(it)[AppModel::class.java].fixtureBackend }
        return backend!!.requests.toList().count { it.method == "GET" && it.url.substringBefore("?").endsWith(path) }
    }

    /** The gesture itself: a swipe down on the tab. */
    private fun pull() {
        waitUntil("the refreshable tab") { tagged("tab.refresh") }
        compose.onAllNodes(hasTestTag("tab.refresh")).onFirst().performTouchInput { swipeDown() }
        compose.waitForIdle()
    }

    /** Pulls and checks the identity was read again, the same rows and locks are there and nothing failed. */
    private fun pullKeeping(rows: List<String>, locks: List<String>, context: String) {
        rows.forEach { waitUntil("$context: $it") { present(it) } }
        val counts = (rows + locks).map(::count)
        val identity = reads("/auth/me")
        val flags = reads("/product-ops/feature-flags")
        pull()
        waitUntil("$context: the identity read again") { reads("/auth/me") == identity + 1 }
        Thread.sleep(300)
        assertEquals("$context: the switches read once", flags + 1, reads("/product-ops/feature-flags"))
        assertEquals("$context: rows or locks changed", counts, (rows + locks).map(::count))
        assertFalse("$context: a successful refresh says nothing", present(failureNotice))
    }

    @Test fun everyPlanPullsPlanPatrimonioAndPerfilAndKeepsItsRowsAndLocks() {
        val locks = listOf(tx("Disponible desde Basic", "Available from Basic"), tx("Disponible desde VIP", "Available from VIP"))
        for ((plan, role) in listOf("free" to null, "basic" to null, "vip" to null, "vip" to "owner")) {
            val context = role ?: plan
            launch(plan, role)
            tab(planTab)
            waitUntil("$context: Plan") { present(tx("Ingresos y base", "Income and base")) }
            assertEquals("$context: Tu plan del mes", plan == "free", present(locks[0]))
            pullKeeping(listOf(tx("Aguinaldo", "Aguinaldo"), tx("Tu plan del mes", "Your plan for the month"), tx("Ingresos y base", "Income and base")), locks, "$context Plan")
            assertEquals("$context: still on Plan", planTab, selectedTab())

            tab(wealthTab)
            waitUntil("$context: debts") { tagged("wealth.debts.composition") }
            assertEquals("$context: Cuentas", plan != "vip", present(locks[1]))
            val debts = reads("/user-product/finance/debts")
            pullKeeping(listOf(tx("Cuentas", "Accounts"), tx("Conexiones de correo", "Mail connections")), locks, "$context Patrimonio")
            assertEquals("$context: the debts read again, once", debts + 1, reads("/user-product/finance/debts"))
            assertTrue("$context: the debts after the refresh", tagged("wealth.debts.composition"))

            tab(profileTab)
            pullKeeping(listOf(tx("Suscripción", "Subscription"), tx("Seguridad", "Security")), locks, "$context Perfil")
            assertEquals("$context: JARVIS only for the Owner", role == "owner", present("JARVIS"))
        }
    }

    @Test fun aFailedRefreshKeepsTheScreenAndSaysSoInTheNotice() {
        launch("vip", refreshFails = true)
        tab(wealthTab)
        waitUntil("debts") { tagged("wealth.debts.composition") }
        pull()
        waitUntil("the failure notice") { present(failureNotice) }
        assertTrue("the debts stay", tagged("wealth.debts.composition"))
        assertTrue("the plan's rows stay", present(tx("Bancos y cuentas detectados en tus avisos", "Banks and accounts found in your notices")))
        assertEquals("no error screen replaces the app", wealthTab, selectedTab())

        // The notice stays up while TalkBack-style timeouts apply, so each tab proves its own failed read.
        for ((name, row) in listOf(planTab to tx("Ingresos y base", "Income and base"), profileTab to tx("Seguridad", "Security"))) {
            tab(name)
            waitUntil(row) { present(row) }
            val before = reads("/auth/me")
            pull()
            waitUntil("$name: the identity read again") { reads("/auth/me") > before }
            waitUntil("$name: the failure notice") { present(failureNotice) }
            assertTrue("$name: the screen stays", present(row))
            assertEquals(name, selectedTab())
        }
    }

    @Test fun aRefreshKeepsTheNavigationOfEveryTab() {
        launch()
        tab(profileTab)
        click(tx("Suscripción", "Subscription"))
        waitUntil("Suscripción") { present(tx("Suscripción actual", "Current subscription")) }
        tab(planTab)
        pull()
        tab(profileTab)
        waitUntil("Perfil is still on Suscripción") { present(tx("Suscripción actual", "Current subscription")) }
    }

    @Test fun talkBackRefreshesFromTheTitleAndEachSourceIsReadOnce() {
        launch("vip")
        tab(wealthTab)
        waitUntil("debts") { tagged("wealth.debts.composition") }
        val action = SemanticsMatcher("has the refresh action") { node ->
            node.config.getOrNull(SemanticsActions.CustomActions)?.any { it.label == refreshAction } == true
        }
        waitUntil("the refresh action") { compose.onAllNodes(action).fetchSemanticsNodes().isNotEmpty() }
        val title = compose.onAllNodes(action).onFirst().fetchSemanticsNode()
        assertTrue("the action sits on the title, a heading", title.config.getOrNull(SemanticsProperties.Heading) != null)
        val sources = listOf("/auth/me", "/product-ops/feature-flags", "/user-product/finance/debts")
        val before = sources.map(::reads)
        compose.runOnIdle { title.config[SemanticsActions.CustomActions].first { it.label == refreshAction }.action() }
        waitUntil("the identity read again") { reads("/auth/me") > before[0] }
        Thread.sleep(500)
        assertEquals("one read of each source, no repeats", before.map { it + 1 }, sources.map(::reads))
        assertTrue(tagged("wealth.debts.composition"))
    }

    @Test fun hoyAndMovimientosStillRefresh() {
        launch()
        val identity = reads("/auth/me")
        val home = reads("/user-product/free/dashboard")
        compose.onRoot().performTouchInput { swipeDown(startY = height * 0.3f, endY = height * 0.9f) }
        waitUntil("Hoy read again") { reads("/user-product/free/dashboard") > home }
        assertEquals("Hoy keeps its own refresh (no identity read)", identity, reads("/auth/me"))
        compose.waitForIdle()
        waitUntil("Hoy after the refresh") { tagged("home.today") }
        tab(tx("Movimientos", "Transactions"))
        waitUntil("a movement") { present("Supermercado") }
        val movements = reads("/user-product/free/movements")
        compose.onRoot().performTouchInput { swipeDown(startY = height * 0.3f, endY = height * 0.9f) }
        waitUntil("Movimientos read again") { reads("/user-product/free/movements") > movements }
        waitUntil("Movimientos after the refresh") { present("Supermercado") }
        assertFalse(present(failureNotice))
    }
}
