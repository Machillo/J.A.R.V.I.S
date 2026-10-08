package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelectable
import androidx.compose.ui.test.isSelected
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * §15 PR 6 — Movimientos → Por revisar: VIP and the Owner review the detected bank notices in the
 * existing mail screen (the same as Perfil's). A pending notice is not a movement until it is
 * confirmed; then it appears in the list. Free and Basic see the entry locked and it opens
 * Suscripción. The five tabs and Análisis stay. iOS twin: `MovementsReviewUITests`.
 */
class MovementsReviewUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    private fun launch(plan: String = "free", role: String? = null) {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
        tab(tx("Movimientos", "Transactions"))
        waitUntil("Movimientos") { tagged("movements.analysis") }
    }

    @After fun close() { scenario?.close() }

    private fun present(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun tagged(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun waitUntil(what: String, condition: () -> Boolean) {
        repeat(150) { if (condition()) return; Thread.sleep(100); compose.waitForIdle() }
        throw AssertionError("timed out waiting for $what")
    }
    private fun tab(text: String) {
        waitUntil("tab $text") { compose.onAllNodes(hasText(text) and isSelectable()).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodes(hasText(text) and isSelectable()).onFirst().performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun clickTag(tag: String) {
        waitUntil(tag) { tagged(tag) }
        val node = compose.onAllNodes(hasTestTag(tag) and hasClickAction()).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun click(text: String) {
        waitUntil("\"$text\"") { present(text) }
        val node = compose.onAllNodes(hasText(text) and hasClickAction()).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun back() { scenario?.onActivity { it.onBackPressedDispatcher.onBackPressed() }; compose.waitForIdle() }
    private fun selectedTab(): String? = compose.onAllNodes(isSelectable() and isSelected()).fetchSemanticsNodes()
        .firstNotNullOfOrNull { node -> node.config.getOrNull(SemanticsProperties.Text)?.joinToString("") { it.text } }

    private val locked get() = tx("Disponible desde VIP", "Available from VIP")

    @Test fun freeAndBasicSeePorRevisarLockedAndItOpensSuscripcion() {
        for (plan in listOf("free", "basic")) {
            launch(plan)
            waitUntil("locked ($plan)") { present(locked) }
            clickTag("movements.review")
            waitUntil("Suscripción ($plan)") { present(tx("Suscripción actual", "Current subscription")) }
            assertFalse(present("Compra en supermercado"))
        }
    }

    @Test fun vipReviewsANoticeAndOnlyThenItIsAMovement() {
        launch("vip")
        assertFalse("not locked", present(locked))
        assertFalse("a pending notice is not a movement", present("Compra en supermercado"))
        clickTag("movements.review")
        waitUntil("the notice") { present("Compra en supermercado") }
        click(tx("Confirmar", "Confirm"))
        waitUntil("saved") { present(tx("Movimiento guardado.", "Transaction saved.")) }
        // Opened from Movimientos, the review keeps Movimientos selected.
        assertEquals(tx("Movimientos", "Transactions"), selectedTab())
        back()
        waitUntil("the confirmed notice is now a movement") { present("Compra en supermercado") }
        assertTrue(tagged("movements.analysis"))
    }

    @Test fun theOwnerReviewsTooAndKeepsJarvis() {
        // The fixture seeds the connected mailbox for a VIP launch; the Owner reaches it by role.
        launch("vip", role = "owner")
        assertFalse(present(locked))
        clickTag("movements.review")
        waitUntil("the notice") { present("Compra en supermercado") }
        back()
        tab(tx("Perfil", "Profile"))
        waitUntil("JARVIS") { present("JARVIS") }
    }
}
