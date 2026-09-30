package com.dincr.data

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JARVIS chat (J1): the `/jarvis/chat` contract, the tolerant reply reader and the session's
 * conversation (sending, errors, retry, confirmation, reset). The Swift twin is `JarvisChatTests`.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class JarvisChatTest {
    private val json = Json { ignoreUnknownKeys = true }
    private fun read(body: String) = JarvisChatReply.from(json.parseToJsonElement(body))

    /** A send stand-in the test answers by hand, to observe the conversation while a message is out. */
    private class ManualReplies {
        val sent = mutableListOf<String>()
        val waiting = ArrayDeque<CompletableDeferred<JarvisChatReply>>()
        suspend fun send(text: String): JarvisChatReply {
            sent += text
            return CompletableDeferred<JarvisChatReply>().also { waiting += it }.await()
        }
        fun answer(reply: JarvisChatReply) = waiting.removeFirst().complete(reply)
        fun fail(error: Throwable) = waiting.removeFirst().completeExceptionally(error)
    }

    private fun fixture(role: FakeBackend.Role = FakeBackend.Role.OWNER, plan: PlanTier = PlanTier.FREE) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, plan, role = role), AppLanguage.SPANISH, backoff = {}))

    // --- Contract --------------------------------------------------------------------------------

    @Test fun theRequestIsTheOwnersMessage() {
        assertEquals("""{"message":"Hoy hice 3 horas extra"}""", Json.encodeToString(JarvisChatRequest("Hoy hice 3 horas extra")))
    }

    @Test fun aChangeToConfirmIsRecognized() {
        val reply = read("""{"message":"Voy a guardar esta evento de planilla:\n- horas: 3.0\n¿Confirmo y guardo? Responde sí o no.","intent":"create_payroll_event",
            "action_type":"create_payroll_event","status":"PENDING","pending":true,"source":"local_direct_payroll_guard","data":{"id":1,"current_field":"confirm","payload":{"hours":3.0}}}""")!!
        assertTrue(reply.awaitsConfirmation && reply.pending)
        assertEquals("create_payroll_event", reply.actionType)
        assertEquals("PENDING", reply.status)
    }

    @Test fun aQuestionForAMissingFieldIsNotAConfirmation() {
        assertFalse(read("""{"message":"¿Cuál es la cuota mensual?","status":"PENDING","pending":true,"data":{"current_field":"monthly_payment"}}""")!!.awaitsConfirmation)
    }

    @Test fun unexpectedShapesAroundTheMessageAreIgnored() {
        // `data` changes with every intent (object, list, null), `entity` can be text or an object,
        // and some answers carry extra keys: none of that may break the chat.
        listOf(
            """{"message":"Hola","data":[1,2,3]}""",
            """{"message":"Hola","data":null,"entity":{"scope":"all"},"budget":null,"confidence":0.9}""",
            """{"message":"Hola","pending":"yes","status":7,"intent":null}""",
            """{"message":"Hola","pending":true,"data":{"current_field":5}}""",
        ).forEach { body ->
            val reply = read(body)!!
            assertEquals(body, "Hola", reply.message)
            assertFalse(body, reply.awaitsConfirmation)
        }
    }

    @Test fun anAnswerWithoutAMessageIsNotAReply() {
        listOf("{}", """{"message":"   "}""", """{"message":null,"status":"OK"}""", "[]", """"texto"""", """{"message":5}""").forEach { assertNull(it, read(it)) }
    }

    // --- Conversation ----------------------------------------------------------------------------

    @Test fun aMessageShowsWhileSendingThenTheAnswer() = runTest {
        val replies = ManualReplies()
        val chat = JarvisChatSession(replies::send)
        val sending = launch { chat.submit("  ¿Cuál es mi deuda más alta?  ") }
        runCurrent()
        assertTrue(chat.state.value.sending)
        assertEquals(listOf("¿Cuál es mi deuda más alta?"), chat.state.value.messages.map { it.text })
        assertEquals(JarvisChatSession.Delivery.Sending, chat.state.value.messages.single().delivery)
        // One message at a time.
        assertFalse(chat.submit("otra pregunta"))
        replies.answer(JarvisChatReply("Tu deuda más alta es la tarjeta."))
        sending.join()
        val state = chat.state.value
        assertFalse(state.sending)
        assertEquals(listOf(JarvisChatSession.Author.OWNER, JarvisChatSession.Author.JARVIS), state.messages.map { it.author })
        assertTrue(state.messages.all { it.delivery == JarvisChatSession.Delivery.Sent })
        assertEquals(listOf("¿Cuál es mi deuda más alta?"), replies.sent)
        // Empty messages are never sent.
        assertFalse(chat.submit("   "))
    }

    @Test fun aFailedMessageStaysWithARetry() = runTest {
        val replies = ManualReplies()
        val chat = JarvisChatSession(replies::send)
        val first = launch { chat.submit("Hoy hice 3 horas extra") }
        runCurrent()
        replies.fail(ApiError(ApiError.Kind.OFFLINE, message = "Sin conexión."))
        first.join()
        val failed = chat.state.value.messages.single()  // no answer was invented
        assertEquals(JarvisChatSession.Delivery.Failed("Sin conexión."), failed.delivery)
        assertTrue(chat.state.value.canRetry(failed))

        val again = launch { chat.retry(failed.id) }
        runCurrent()
        assertEquals(JarvisChatSession.Delivery.Sending, chat.state.value.messages.single().delivery)
        replies.answer(JarvisChatReply("Listo."))
        again.join()
        assertTrue(chat.state.value.messages.all { it.delivery == JarvisChatSession.Delivery.Sent })
        assertEquals(listOf("Hoy hice 3 horas extra", "Hoy hice 3 horas extra"), replies.sent)
    }

    @Test fun anUnexpectedErrorStillLeavesARetry() = runTest {
        val chat = JarvisChatSession({ throw IllegalStateException("broken") }, { AppLanguage.SPANISH })
        chat.submit("hola")
        val failed = chat.state.value.messages.single()
        assertTrue((failed.delivery as JarvisChatSession.Delivery.Failed).reason.isNotBlank())
        assertTrue(chat.state.value.canRetry(failed))
    }

    @Test fun aChangeIsSavedOnlyWithConfirmar() = runTest {
        val replies = ManualReplies()
        val chat = JarvisChatSession(replies::send)
        // Nothing is waiting: Confirmar and Cancelar send nothing.
        chat.confirm()
        chat.cancel()
        assertTrue(replies.sent.isEmpty())

        val ask = launch { chat.submit("Hoy hice 3 horas extra") }
        runCurrent()
        replies.answer(JarvisChatReply("¿Confirmo y guardo?", pending = true, awaitsConfirmation = true))
        ask.join()
        assertTrue(chat.state.value.awaitingConfirmation)

        val confirm = launch { chat.confirm() }
        runCurrent()
        assertFalse(chat.state.value.awaitingConfirmation)  // answered: the buttons go away
        replies.answer(JarvisChatReply("Señor, OT registrado."))
        confirm.join()
        assertEquals(listOf("Hoy hice 3 horas extra", "sí"), replies.sent)
        assertFalse(chat.state.value.awaitingConfirmation)
    }

    @Test fun cancelarAnswersNo() = runTest {
        val replies = ManualReplies()
        val chat = JarvisChatSession(replies::send)
        val ask = launch { chat.submit("bono de 50 mil") }
        runCurrent()
        replies.answer(JarvisChatReply("¿Confirmo y guardo?", pending = true, awaitsConfirmation = true))
        ask.join()
        val cancel = launch { chat.cancel() }
        runCurrent()
        replies.answer(JarvisChatReply("Listo, cancelé el registro."))
        cancel.join()
        assertEquals("no", replies.sent.last())
    }

    @Test fun resetForgetsTheConversationAndLateAnswers() = runTest {
        // Sign-out or another identity: nothing of the previous conversation survives.
        val replies = ManualReplies()
        val chat = JarvisChatSession(replies::send)
        val late = launch { chat.submit("¿Qué tengo en la agenda?") }
        runCurrent()
        chat.reset()
        assertTrue(chat.state.value.messages.isEmpty() && !chat.state.value.sending)
        replies.answer(JarvisChatReply("Tu agenda…"))
        late.join()
        assertTrue(chat.state.value.messages.isEmpty())
    }

    @Test fun theSessionKeepsItsLatestMessages() = runTest {
        val chat = JarvisChatSession({ JarvisChatReply("respuesta a $it") })
        repeat(40) { chat.submit("mensaje ${it + 1}") }
        assertEquals(JarvisChatSession.HISTORY_LIMIT, chat.state.value.messages.size)
        assertEquals("respuesta a mensaje 40", chat.state.value.messages.last().text)
    }

    // --- Fake backend (what the UI tests run against) --------------------------------------------

    @Test fun theFakeChatAnswersTheOwnerAndAdminOnly() = runTest {
        val owner = fixture()
        assertTrue(owner.jarvisChat("Hoy hice 3 horas extra").awaitsConfirmation)
        assertTrue("registrado" in owner.jarvisChat("sí").message)
        assertFalse(owner.jarvisChat("¿Cuál es mi deuda más alta?").awaitsConfirmation)
        fixture(FakeBackend.Role.ADMIN).jarvisChat("hola")

        PlanTier.entries.forEach { plan ->
            val error = runCatching { fixture(FakeBackend.Role.USER, plan).jarvisChat("hola") }.exceptionOrNull() as ApiError
            assertEquals(ApiError.Kind.FORBIDDEN, error.kind)
        }
        assertEquals(ApiError.Kind.DECODING, (runCatching { owner.jarvisChat("respuesta rara") }.exceptionOrNull() as ApiError).kind)
        assertEquals(ApiError.Kind.SERVER, (runCatching { owner.jarvisChat("falla") }.exceptionOrNull() as ApiError).kind)
    }
}
