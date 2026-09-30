package com.dincr.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull

/** Body of `POST /jarvis/chat` (Owner): one message, in the Owner's own words. */
@Serializable
data class JarvisChatRequest(val message: String)

/**
 * The JARVIS engine's answer to one message (`backend/ai/jarvis_engine.process_message`).
 *
 * The backend sends an untyped dict whose `data` changes with every intent: only `message` is
 * required, the rest is read defensively and anything else is ignored. A change the chat
 * understood (a payroll event, a bonus, an event, a memory, a fixed expense…) comes back with
 * `pending: true` and `data.current_field == "confirm"`: it is saved only if the Owner answers "sí"
 * ([awaitsConfirmation]). iOS twin: `JarvisChat.swift`.
 */
data class JarvisChatReply(
    val message: String,
    val intent: String? = null,
    val status: String? = null,
    val pending: Boolean = false,
    val actionType: String? = null,
    /** JARVIS showed what it will save and waits for "sí" / "no". */
    val awaitsConfirmation: Boolean = false,
) {
    companion object {
        /** The reply in [element], or null when it has no message to show (an unexpected answer). */
        fun from(element: JsonElement): JarvisChatReply? {
            val body = element as? JsonObject ?: return null
            fun text(from: JsonObject?, key: String) = (from?.get(key) as? JsonPrimitive)?.takeIf { it.isString }?.content
            val message = text(body, "message")?.takeIf { it.isNotBlank() } ?: return null
            val pending = (body["pending"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull ?: false
            val field = text(body["data"] as? JsonObject, "current_field")
            return JarvisChatReply(message, text(body, "intent"), text(body, "status"), pending, text(body, "action_type"), pending && field == "confirm")
        }
    }
}

/**
 * One JARVIS conversation, kept only for the signed-in session: nothing is stored on the device or
 * the server (the web Owner app kept its chat the same way). Messages go out one at a time, in
 * order; a message that could not be sent stays in the list with a retry. iOS: `JarvisChatSession`.
 */
class JarvisChatSession(
    private val send: suspend (String) -> JarvisChatReply,
    private val language: () -> AppLanguage = { AppLanguage.current() },
) {
    enum class Author { OWNER, JARVIS }

    sealed interface Delivery {
        data object Sending : Delivery
        data object Sent : Delivery
        data class Failed(val reason: String) : Delivery
    }

    data class Message(val id: Long, val author: Author, val text: String, val delivery: Delivery, val awaitsConfirmation: Boolean = false)

    data class State(val messages: List<Message> = emptyList(), val sending: Boolean = false) {
        /** JARVIS's last message waits for "sí" / "no" and nothing is on its way. */
        val awaitingConfirmation: Boolean
            get() = !sending && messages.lastOrNull()?.let { it.author == Author.JARVIS && it.awaitsConfirmation } == true

        /** Whether a failed message can be sent again (only the latest one: messages stay in order). */
        fun canRetry(message: Message) = !sending && message.delivery is Delivery.Failed && messages.lastOrNull()?.id == message.id
    }

    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()
    private var nextId = 1L
    /** Bumped by [reset]: an answer to an earlier session is dropped. */
    private var generation = 0

    /** Sends one message; empty text, or a message while another is on its way, is ignored. */
    suspend fun submit(text: String): Boolean {
        val clean = text.trim()
        if (clean.isEmpty() || _state.value.sending) return false
        val id = append(Author.OWNER, clean, Delivery.Sending)
        deliver(id, clean)
        return true
    }

    suspend fun confirm() { if (_state.value.awaitingConfirmation) submit(CONFIRM_WORD) }
    suspend fun cancel() { if (_state.value.awaitingConfirmation) submit(CANCEL_WORD) }

    suspend fun retry(id: Long) {
        val message = _state.value.messages.firstOrNull { it.id == id } ?: return
        if (!_state.value.canRetry(message)) return
        change(id) { it.copy(delivery = Delivery.Sending) }
        deliver(id, message.text)
    }

    /** Sign-out or another identity: the conversation is gone. */
    fun reset() {
        generation += 1
        _state.value = State()
    }

    private suspend fun deliver(id: Long, text: String) {
        val session = generation
        // Any question JARVIS asked is answered (or set aside) by this message.
        _state.update { state -> state.copy(sending = true, messages = state.messages.map { if (it.awaitsConfirmation) it.copy(awaitsConfirmation = false) else it }) }
        val outcome = runCatching { send(text) }
        if (session != generation) return
        _state.update { it.copy(sending = false) }
        outcome.fold(
            onSuccess = { reply ->
                change(id) { it.copy(delivery = Delivery.Sent) }
                append(Author.JARVIS, reply.message, Delivery.Sent, reply.awaitsConfirmation)
            },
            onFailure = { error ->
                if (error is kotlinx.coroutines.CancellationException) throw error
                val reason = (error as? ApiError)?.message
                    ?: language().pick("No pudimos enviar el mensaje. Intentá de nuevo.", "We couldn’t send the message. Please try again.")
                change(id) { it.copy(delivery = Delivery.Failed(reason)) }
            },
        )
    }

    private fun append(author: Author, text: String, delivery: Delivery, awaitsConfirmation: Boolean = false): Long {
        val id = nextId++
        _state.update { state -> state.copy(messages = (state.messages + Message(id, author, text, delivery, awaitsConfirmation)).takeLast(HISTORY_LIMIT)) }
        return id
    }

    private fun change(id: Long, transform: (Message) -> Message) {
        _state.update { state -> state.copy(messages = state.messages.map { if (it.id == id) transform(it) else it }) }
    }

    companion object {
        /** The answers to a pending change (backend `action_flow.YES_WORDS` / `NO_WORDS`). */
        const val CONFIRM_WORD = "sí"
        const val CANCEL_WORD = "no"
        /** The oldest messages leave the list past this many (the session only). */
        const val HISTORY_LIMIT = 60
    }
}
