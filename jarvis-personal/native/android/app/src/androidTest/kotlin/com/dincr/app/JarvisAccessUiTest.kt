package com.dincr.app

import android.content.Intent
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
 * JARVIS role matrix on the FakeBackend (roadmap J0): only the Owner's role in `/auth/me` opens
 * JARVIS; Free, Basic, VIP and admin never see it, and the Owner keeps every DINCR screen. The
 * fake server's role comes from the `dincrRole` extra (debug fixtures only). iOS: `JarvisAccessUITests`.
 */
class JarvisAccessUiTest {
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

    private fun present(text: String, substring: Boolean = false) =
        compose.onAllNodes(hasText(text, substring = substring), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()

    private fun waitForText(text: String, substring: Boolean = false) {
        try {
            compose.waitUntil(15_000) { compose.mainClock.advanceTimeBy(100); present(text, substring) }
        } catch (error: Throwable) {
            runCatching { compose.onAllNodes(isRoot()).printToLog("DINCR-UI") }
            throw AssertionError("timed out waiting for \"$text\"", error)
        }
    }

    private fun click(text: String) {
        waitForText(text)
        val node = compose.onAllNodesWithText(text).onFirst()
        runCatching { node.performScrollTo() }
        node.performClick()
    }

    /** Opens the Profile tab and waits until its rows are there. */
    private fun openProfile() {
        waitForText(tx("Hoy", "Today"))
        compose.onAllNodesWithText(tx("Perfil", "Profile")).onFirst().performClick()
        waitForText(tx("Mi situación financiera", "My financial situation"))
    }

    @Test fun ownerGetsJarvisOnTopOfDincr() {
        launch(role = "owner")
        openProfile()
        // The Owner keeps DINCR: every tab, and VIP screens such as the financial emails.
        listOf(tx("Hoy", "Today"), tx("Movimientos", "Transactions"), "Plan", "DINCR", tx("Perfil", "Profile")).forEach { assertTrue(it, present(it)) }
        assertTrue(present(tx("Correos financieros", "Financial emails")))
        click("JARVIS")
        click(tx("Chat", "Chat"))
        // Nothing is ported yet: the section says so and shows no sample content.
        waitForText(tx("Esta función todavía no está disponible en la app.", "This feature isn’t available in the app yet."), substring = true)
    }

    @Test fun freeBasicAndVipNeverSeeJarvis() {
        listOf("free", "basic", "vip").forEach { plan ->
            launch(plan = plan)
            openProfile()
            assertTrue(plan, !present("JARVIS"))
        }
    }

    @Test fun adminGetsNeitherThePublicAppNorJarvis() {
        launch(role = "admin", plan = "vip")
        waitForText(tx("Esta cuenta usa DINCR Owner", "This account uses DINCR Owner"))
        assertTrue(!present("JARVIS"))
        assertTrue(!present(tx("Movimientos", "Transactions")))
    }

    @Test fun theRoleIsReadFromTheServerOnEveryLaunch() {
        // Nothing about the Owner survives on the device: the next session's /auth/me decides.
        launch(role = "owner")
        openProfile()
        assertTrue(present("JARVIS"))
        launch(plan = "vip")
        openProfile()
        assertTrue(!present("JARVIS"))
    }
}
