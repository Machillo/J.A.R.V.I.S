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
 * JARVIS chat (J1) on the FakeBackend, whose scripted chat shows a payroll change for "horas extra",
 * fails for "falla" and answers anything else plainly. Only the Owner reaches the chat
 * (`JarvisAccessUiTest` covers the other roles). iOS: `JarvisChatUITests`.
 */
class JarvisChatUiTest {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun launchOwner(skipLogin: Boolean = true) {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", skipLogin).putExtra("dincrLatencyMs", 0L)
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

    private fun openChat() {
        waitUntil("home") { present(tx("Hoy", "Today")) }
        compose.onAllNodesWithText(tx("Perfil", "Profile")).onFirst().performClick()
        click("JARVIS")
        click(tx("Chat", "Chat"))
        waitUntil("chat input") { tagged("jarvis.chat.input") }
    }

    private fun send(text: String) {
        compose.onNodeWithTag("jarvis.chat.input").performTextInput(text)
        compose.onNodeWithTag("jarvis.chat.send").performClick()
    }

    @Test fun ownerAsksAndGetsAnAnswer() {
        launchOwner()
        openChat()
        assertTrue(tagged("jarvis.chat.empty"))
        send("¿Cuál es mi deuda más alta?")
        waitUntil("the answer") { present("Señor, esto es una respuesta de ejemplo.") }
        assertTrue(present("¿Cuál es mi deuda más alta?"))
        assertTrue("a plain answer asks for nothing", !tagged("jarvis.chat.confirm"))
    }

    @Test fun aChangeIsShownFirstAndSavedOnConfirm() {
        launchOwner()
        openChat()
        send("Hoy hice 3 horas extra")
        waitUntil("the confirmation") { tagged("jarvis.chat.confirm") }
        assertTrue(tagged("jarvis.chat.cancel"))
        assertTrue("the amount is shown before saving", present("₡9,000.00", substring = true))
        compose.onNodeWithTag("jarvis.chat.confirm").performClick()
        waitUntil("the saved reply") { present("Señor, OT registrado", substring = true) }
        assertTrue(!tagged("jarvis.chat.confirm"))
    }

    @Test fun cancelSavesNothing() {
        launchOwner()
        openChat()
        send("Hoy hice 3 horas extra")
        waitUntil("the confirmation") { tagged("jarvis.chat.cancel") }
        compose.onNodeWithTag("jarvis.chat.cancel").performClick()
        waitUntil("the cancellation") { present("Listo, cancelé el registro. No guardé nada.") }
    }

    @Test fun aFailedMessageOffersRetryAndTheChatStaysUsable() {
        launchOwner()
        openChat()
        send("esto falla")
        waitUntil("the retry") { tagged("jarvis.chat.retry") }
        assertTrue(tagged("jarvis.chat.failed"))
        send("hola")
        waitUntil("the answer") { present("Señor, esto es una respuesta de ejemplo.") }
    }

    @Test fun anUnexpectedAnswerDoesNotCrash() {
        launchOwner()
        openChat()
        send("respuesta rara")
        waitUntil("the error") { tagged("jarvis.chat.failed") }
        assertTrue(tagged("jarvis.chat.input"))
    }

    @Test fun signingOutForgetsTheConversation() {
        launchOwner(skipLogin = false)
        waitUntil("login") { tagged("login.google") }
        compose.onNodeWithTag("login.google").performClick()
        openChat()
        send("hola")
        waitUntil("the answer") { present("Señor, esto es una respuesta de ejemplo.") }
        // Back to the Profile hub (chat → JARVIS → Profile), sign out and in again: the chat starts empty.
        repeat(2) {
            waitUntil("the back button") { compose.onAllNodesWithContentDescription(tx("Volver", "Back")).fetchSemanticsNodes().isNotEmpty() }
            compose.onAllNodesWithContentDescription(tx("Volver", "Back")).onFirst().performClick()
            compose.mainClock.advanceTimeBy(500)
        }
        click(tx("Cerrar sesión", "Sign out"))
        waitUntil("the sign-out dialog") { compose.onAllNodesWithText(tx("Cerrar sesión", "Sign out")).fetchSemanticsNodes().size > 1 }
        compose.onAllNodesWithText(tx("Cerrar sesión", "Sign out"))[1].performClick()
        waitUntil("login") { tagged("login.google") }
        compose.onNodeWithTag("login.google").performClick()
        openChat()
        assertTrue(tagged("jarvis.chat.empty"))
        assertTrue(!present("hola"))
    }
}
