package com.dincr.app

import android.content.Intent
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.printToLog
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * JARVIS agenda (J2) on the FakeBackend: the Owner's upcoming events (POPULATED: two), the empty state,
 * "Agendar con JARVIS", and an event confirmed in the chat reaching the agenda. Other roles never reach
 * JARVIS (`JarvisAccessUiTest`). iOS: `JarvisAgendaUITests`.
 */
class JarvisAgendaUiTest {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun launchOwner(fixture: String = "POPULATED") {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", fixture).putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L)
            .putExtra("dincrPlan", "free").putExtra("dincrRole", "owner")
        scenario = ActivityScenario.launch(intent)
    }

    private fun present(text: String, substring: Boolean = false) =
        compose.onAllNodes(hasText(text, substring = substring), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()

    private fun tagged(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()

    private fun waitUntil(what: String, condition: () -> Boolean) {
        try {
            compose.waitUntil(15_000) { compose.mainClock.advanceTimeBy(100); condition() }
        } catch (error: Throwable) {
            runCatching { compose.onAllNodes(isRoot()).printToLog("DINCR-UI") }
            throw AssertionError("timed out waiting for $what", error)
        }
    }

    private fun click(text: String) {
        waitUntil("\"$text\"") { present(text) }
        val node = compose.onAllNodesWithText(text).onFirst()
        runCatching { node.performScrollTo() }
        node.performClick()
    }

    private fun openAgenda() {
        waitUntil("home") { present(tx("Hoy", "Today")) }
        compose.onAllNodesWithText(tx("Perfil", "Profile")).onFirst().performClick()
        click("JARVIS")
        click(tx("Agenda", "Calendar"))
    }

    @Test fun ownerSeesTheUpcomingEvents() {
        launchOwner()
        openAgenda()
        waitUntil("the events") { present("Reunión con el contador") }
        assertTrue(present("Cita médica"))
        assertTrue(present("10:00"))
        assertTrue(tagged("jarvis.agenda.schedule"))
    }

    @Test fun anEmptyAgendaSaysSoAndOffersJarvis() {
        launchOwner("EMPTY")
        openAgenda()
        waitUntil("the empty state") { tagged("jarvis.agenda.empty") }
        assertTrue(present(tx("No hay compromisos próximos", "No upcoming commitments")))
        compose.onNodeWithTag("jarvis.agenda.schedule").performClick()
        waitUntil("the chat") { tagged("jarvis.chat.input") }
    }

    @Test fun anEventConfirmedInTheChatReachesTheAgenda() {
        launchOwner()
        openAgenda()
        waitUntil("the events") { present("Reunión con el contador") }
        assertTrue(!present("dentista"))
        compose.onNodeWithTag("jarvis.agenda.schedule").performClick()
        waitUntil("the chat") { tagged("jarvis.chat.input") }
        compose.onNodeWithTag("jarvis.chat.input").performTextInput("Agendá dentista el 10 de octubre a las 3pm")
        compose.onNodeWithTag("jarvis.chat.send").performClick()
        waitUntil("the confirmation") { tagged("jarvis.chat.confirm") }
        compose.onNodeWithTag("jarvis.chat.confirm").performClick()
        waitUntil("the saved reply") { present("Guardé en calendario", substring = true) }
        // Back to the agenda: it reloads and shows the confirmed event.
        compose.onAllNodesWithContentDescription(tx("Volver", "Back")).onFirst().performClick()
        waitUntil("the new event") { present("dentista") }
        assertTrue(present("15:00"))
    }
}
