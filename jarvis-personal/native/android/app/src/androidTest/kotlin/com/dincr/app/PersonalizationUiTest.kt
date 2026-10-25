package com.dincr.app

import android.content.Intent
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.printToLog
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * APP-1 — Personalización on the FakeBackend: the Owner opens it, changes a palette, saves and
 * restores the defaults; Free, Basic and VIP never see it and keep the device's Apariencia choice.
 * The server gate is proven in backend/user_product/test_appearance.py.
 */
class PersonalizationUiTest {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun launch(role: String? = null, plan: String = "free") {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
    }

    private fun present(text: String) = compose.onAllNodes(hasText(text), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()

    private fun tagged(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()

    private fun waitFor(what: String, condition: () -> Boolean) {
        try {
            compose.waitUntil(15_000) { compose.mainClock.advanceTimeBy(100); condition() }
        } catch (error: Throwable) {
            runCatching { compose.onAllNodes(isRoot()).printToLog("DINCR-UI") }
            throw AssertionError("timed out waiting for $what", error)
        }
    }

    private fun click(text: String) {
        waitFor("\"$text\"") { present(text) }
        val node = compose.onAllNodesWithText(text).onFirst()
        runCatching { node.performScrollTo() }
        node.performClick()
    }

    private fun openProfile() {
        waitFor("Hoy") { present(tx("Hoy", "Today")) }
        compose.onAllNodesWithText(tx("Perfil", "Profile")).onFirst().performClick()
        waitFor("Perfil") { present(tx("Ajustes de cuenta", "Account settings")) }
    }

    @Test fun theOwnerChangesSavesAndRestoresItsAppearance() {
        launch(role = "owner")
        openProfile()
        assertTrue(tagged("profile.appearance"))
        click(tx("Personalización", "Personalization"))
        waitFor("the preview") { tagged("appearance.preview") }
        assertTrue("nothing to save yet", present(tx("Guardado", "Saved")))
        click(tx("Arena", "Sand"))
        waitFor("a pending change") { present(tx("Guardar cambios", "Save changes")) }
        assertTrue(present(tx("Descartar cambios", "Discard changes")))
        click(tx("Guardar cambios", "Save changes"))
        waitFor("the saved state") { present(tx("Guardado", "Saved")) && present(tx("Restaurar valores predeterminados", "Restore defaults")) }
        click(tx("Restaurar valores predeterminados", "Restore defaults"))
        click(tx("Restaurar", "Restore"))
        waitFor("the defaults again") { !present(tx("Restaurar valores predeterminados", "Restore defaults")) && present(tx("Guardado", "Saved")) }
    }

    @Test fun freeBasicAndVipNeverSeePersonalization() {
        listOf("free", "basic", "vip").forEach { plan ->
            launch(plan = plan)
            openProfile()
            assertTrue(plan, !tagged("profile.appearance") && !present(tx("Personalización", "Personalization")))
            click(tx("Ajustes de cuenta", "Account settings"))
            // Their theme stays the device's own Automático / Claro / Oscuro choice, as before.
            waitFor("$plan appearance choice") { present(tx("Automático", "Automatic")) && present(tx("Oscuro", "Dark")) }
            assertTrue(plan, !present(tx("Personalización", "Personalization")))
        }
    }
}
