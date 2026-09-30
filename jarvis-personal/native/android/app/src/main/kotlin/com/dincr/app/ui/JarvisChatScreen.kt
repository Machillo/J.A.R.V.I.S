package com.dincr.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.Send
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.JarvisChatSession
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.generated.DincrRadius
import com.dincr.design.generated.DincrSpacing

/**
 * JARVIS chat (recovery roadmap J1): the Owner talks to JARVIS in plain words and gets the engine's
 * answer (`POST /jarvis/chat`). A change JARVIS understood is shown first and saved only on
 * Confirmar (the backend waits for "sí"). The conversation lives for the session only, like the web
 * Owner app's. iOS: `JarvisChatView`.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun JarvisChatScreen(model: AppModel, nav: Navigator) {
    val chat by model.jarvisChat.state.collectAsStateWithLifecycle()
    var draft by rememberSaveable { mutableStateOf("") }
    val list = rememberLazyListState()
    val canSend = !chat.sending && draft.isNotBlank()
    val send = {
        if (canSend) {
            model.sendToJarvis(draft)
            draft = ""
        }
    }
    LaunchedEffect(chat.messages.size, chat.sending, chat.awaitingConfirmation) {
        val last = list.layoutInfo.totalItemsCount - 1
        if (last >= 0) list.animateScrollToItem(last)
    }
    BackHandler(onBack = nav::back)
    Column(Modifier.fillMaxSize().background(Dincr.colors.bg).imePadding()) {
        TopAppBar(
            title = { Text(tx("Chat", "Chat"), style = MaterialTheme.typography.titleLarge, modifier = Modifier.semantics { heading() }) },
            navigationIcon = {
                IconButton(onClick = nav::back, modifier = Modifier.size(48.dp)) {
                    Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = tx("Volver", "Back"))
                }
            },
            colors = TopAppBarDefaults.topAppBarColors(containerColor = Dincr.colors.bg, titleContentColor = Dincr.colors.text, navigationIconContentColor = Dincr.colors.text),
        )
        LazyColumn(
            state = list,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(DincrSpacing.s4),
            verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            if (chat.messages.isEmpty()) item { ChatIntro() }
            items(chat.messages, key = { it.id }) { message ->
                MessageBubble(message, chat.canRetry(message)) { model.retryJarvisMessage(message.id) }
            }
            if (chat.sending) item { Thinking() }
            if (chat.awaitingConfirmation) item {
                Row(Modifier.widthIn(max = ContentMaxWidth).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                    OutlinedButton({ model.cancelJarvisChange() }, Modifier.weight(1f).heightIn(min = 52.dp).testTag("jarvis.chat.cancel")) {
                        Text(tx("Cancelar", "Cancel"), color = Dincr.colors.tint)
                    }
                    DincrPrimaryButton(tx("Confirmar", "Confirm"), { model.confirmJarvisChange() }, Modifier.weight(1f).testTag("jarvis.chat.confirm"))
                }
            }
        }
        Row(
            Modifier.fillMaxWidth().background(Dincr.colors.bg).padding(horizontal = DincrSpacing.s4, vertical = DincrSpacing.s2),
            verticalAlignment = Alignment.Bottom,
            horizontalArrangement = Arrangement.Center,
        ) {
            OutlinedTextField(
                value = draft, onValueChange = { draft = it },
                placeholder = { Text(tx("Escribile a JARVIS", "Message JARVIS")) },
                maxLines = 5,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Default),
                shape = RoundedCornerShape(DincrRadius.lg),
                colors = OutlinedTextFieldDefaults.colors(unfocusedBorderColor = Dincr.colors.fieldBorder, focusedBorderColor = Dincr.colors.tint),
                modifier = Modifier.weight(1f).widthIn(max = ContentMaxWidth).testTag("jarvis.chat.input"),
            )
            IconButton(onClick = send, enabled = canSend, modifier = Modifier.size(52.dp).testTag("jarvis.chat.send")) {
                Icon(Icons.AutoMirrored.Rounded.Send, contentDescription = tx("Enviar", "Send"),
                    tint = if (canSend) Dincr.colors.tint else Dincr.colors.textMuted)
            }
        }
    }
}

@Composable
private fun ChatIntro() {
    Box(Modifier.widthIn(max = ContentMaxWidth).fillMaxWidth().testTag("jarvis.chat.empty")) {
        DincrCard {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2), modifier = Modifier.semantics(mergeDescendants = true) {}) {
                Text(tx("Hablale a JARVIS como siempre", "Talk to JARVIS as usual"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                Text(tx("Preguntá por tus deudas, tu estrategia o tu agenda, o contale lo que pasó: “Hoy hice 3 horas extra”. Antes de guardar algo, JARVIS te muestra qué va a registrar.",
                    "Ask about your debts, your strategy or your calendar, or tell it what happened: “Today I did 3 hours of overtime”. Before saving anything, JARVIS shows you what it will record."),
                    style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
            }
        }
    }
}

@Composable
private fun Thinking() {
    Row(
        Modifier.widthIn(max = ContentMaxWidth).fillMaxWidth().testTag("jarvis.chat.sending").semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite },
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s2),
    ) {
        CircularProgressIndicator(Modifier.size(20.dp), color = Dincr.colors.tint, strokeWidth = 2.dp)
        Text(tx("JARVIS está pensando…", "JARVIS is thinking…"), style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
    }
}

/** One message: the Owner's on the right in the brand color, JARVIS's on the left on a card. */
@Composable
private fun MessageBubble(message: JarvisChatSession.Message, canRetry: Boolean, onRetry: () -> Unit) {
    val fromOwner = message.author == JarvisChatSession.Author.OWNER
    Column(
        Modifier.widthIn(max = ContentMaxWidth).fillMaxWidth()
            .padding(start = if (fromOwner) DincrSpacing.s8 else 0.dp, end = if (fromOwner) 0.dp else DincrSpacing.s8),
        horizontalAlignment = if (fromOwner) Alignment.End else Alignment.Start,
        verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1),
    ) {
        val speaker = if (fromOwner) tx("Vos", "You") else "JARVIS"
        SelectionContainer {
            Text(
                message.text,
                style = MaterialTheme.typography.bodyLarge,
                color = if (fromOwner) Dincr.colors.onTint else Dincr.colors.text,
                modifier = Modifier
                    .background(if (fromOwner) Dincr.colors.tint else Dincr.colors.surface, RoundedCornerShape(DincrRadius.lg))
                    .padding(horizontal = DincrSpacing.s3, vertical = DincrSpacing.s2)
                    .testTag(if (fromOwner) "jarvis.chat.owner" else "jarvis.chat.reply")
                    .semantics { contentDescription = "$speaker: ${message.text}" },
            )
        }
        val delivery = message.delivery
        if (delivery is JarvisChatSession.Delivery.Failed) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s2), modifier = Modifier.testTag("jarvis.chat.failed")) {
                Icon(Icons.Rounded.ErrorOutline, contentDescription = null, tint = Dincr.colors.negative, modifier = Modifier.size(18.dp))
                Text(delivery.reason, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.negative)
                if (canRetry) TextButton(onRetry, Modifier.heightIn(min = 48.dp).testTag("jarvis.chat.retry")) {
                    Text(tx("Reintentar", "Retry"), color = Dincr.colors.tint)
                }
            }
        }
    }
}
