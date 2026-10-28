package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AdditionalCard
import com.dincr.data.AdditionalCardRequest
import com.dincr.data.AuthException
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.generated.DincrSpacing
import kotlinx.coroutines.launch

/**
 * JARVIS → Control de dinero → "Tarjetas adicionales" (Owner only): the cards billed to the Owner
 * but carried by someone else. A purchase on one of them is that person's debt (it shows up under
 * them above), never the Owner's expense. Opening it only reads; adding or removing a card is an
 * explicit Owner command, sent once. iOS: `AdditionalCardsSection`.
 */
@Composable
fun AdditionalCardsSection(model: AppModel, onChanged: (String) -> Unit) {
    val cards = rememberLoad(model, fallback = tx("No pudimos cargar tus tarjetas adicionales.", "We couldn’t load your additional cards.")) {
        model.api.additionalCards()
    }
    var adding by remember { mutableStateOf(false) }
    var removing by remember { mutableStateOf<AdditionalCard?>(null) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    DincrCard(Modifier.testTag("money.cards")) {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(tx("Tarjetas adicionales", "Additional cards"), style = MaterialTheme.typography.titleMedium,
                    color = Dincr.colors.text, modifier = Modifier.weight(1f))
                TextButton({ adding = true }, modifier = Modifier.heightIn(min = 48.dp).testTag("money.cards.add")) {
                    Text(tx("Agregar", "Add"), color = Dincr.colors.tint)
                }
            }
            Caption(tx("Lo que se compre con estas tarjetas se le cobra a esa persona y no cuenta como gasto tuyo.",
                "Purchases with these cards are charged to that person and don’t count as your spending."))
            LoadContent(cards, rows = 1) { list ->
                Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                    if (list.items.isEmpty()) {
                        Text(tx("Todavía no marcaste ninguna.", "You haven’t marked any yet."), style = MaterialTheme.typography.bodyMedium,
                            color = Dincr.colors.text2, modifier = Modifier.testTag("money.cards.empty"))
                    }
                    list.items.forEach { card ->
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.testTag("money.cards.card.${card.cardLast4}")) {
                            Column(Modifier.weight(1f)) {
                                Text("•••• ${card.cardLast4}", style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text)
                                Caption(card.personName ?: tx("Persona", "Person"))
                            }
                            TextButton({ removing = card }, modifier = Modifier.heightIn(min = 48.dp).testTag("money.cards.remove.${card.cardLast4}")) {
                                Text(tx("Quitar", "Remove"), color = Dincr.colors.negative)
                            }
                        }
                    }
                }
            }
            error?.let { Text(it, color = Dincr.colors.negative, style = MaterialTheme.typography.bodySmall) }
        }
    }
    if (adding) AdditionalCardDialog(model, onDismiss = { adding = false }) { message ->
        adding = false; cards.reload(); onChanged(message)
    }
    removing?.let { card ->
        ConfirmDialog(tx("¿Quitar esta tarjeta adicional?", "Remove this additional card?"),
            tx("Sus compras vuelven a «Por revisar» para que decidás. No se borra nada.",
                "Its purchases go back to “To review” for you to decide. Nothing is deleted."),
            tx("Quitar", "Remove"), busy = busy, onDismiss = { removing = null }, onConfirm = {
                busy = true; error = null
                scope.launch {
                    model.load(tx("No pudimos quitarla.", "We couldn’t remove it.")) { model.api.stopAdditionalCard(card.cardLast4) }
                        .fold({
                            cards.reload()
                            onChanged(tx("Tarjeta •••• ${card.cardLast4} ya no es adicional", "Card •••• ${card.cardLast4} is no longer additional"))
                        }, { if (it !is AuthException.SignedOut) error = it.message })
                    busy = false; removing = null
                }
            })
    }
}

/** "Agregar tarjeta adicional": the card's last 4 digits and who carries it. Sent once. */
@Composable
private fun AdditionalCardDialog(model: AppModel, onDismiss: () -> Unit, onSaved: (String) -> Unit) {
    var last4 by remember { mutableStateOf("") }
    var person by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(tx("Tarjeta adicional", "Additional card")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                FormField(tx("Últimos 4 dígitos", "Last 4 digits"), last4, { last4 = it; error = null }, keyboard = KeyboardType.NumberPassword,
                    modifier = Modifier.testTag("money.cards.last4"))
                FormField(tx("Quién la usa", "Who uses it"), person, { person = it; error = null }, modifier = Modifier.testTag("money.cards.person"))
                Caption(tx("Las compras pendientes de esta tarjeta pasan a lo que esa persona te debe.",
                    "This card’s pending purchases become what that person owes you."))
                error?.let { Text(it, color = Dincr.colors.negative, style = MaterialTheme.typography.bodySmall) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, modifier = Modifier.testTag("money.cards.save"), onClick = {
                val digits = AdditionalCardRequest.last4(last4)
                val name = person.trim()
                when {
                    digits == null -> error = tx("Escribí los últimos 4 dígitos de la tarjeta.", "Enter the card’s last 4 digits.")
                    name.isEmpty() -> error = tx("Escribí quién usa la tarjeta.", "Enter who uses the card.")
                    else -> {
                        busy = true
                        scope.launch {
                            model.load(tx("No pudimos guardarla. Revisá la lista antes de intentar de nuevo.", "We couldn’t save it. Check the list before trying again.")) {
                                model.api.saveAdditionalCard(digits, name)
                            }.fold({ result ->
                                val settled = result.settledPurchases ?: 0
                                onSaved(if (settled > 0) tx("Tarjeta guardada · $settled compra(s) pasaron a $name", "Card saved · $settled purchase(s) moved to $name")
                                else tx("Tarjeta guardada", "Card saved"))
                            }, { if (it !is AuthException.SignedOut) error = it.message })
                            busy = false
                        }
                    }
                }
            }) { Text(tx("Guardar", "Save")) }
        },
        dismissButton = { TextButton(onDismiss, enabled = !busy) { Text(tx("Cancelar", "Cancel")) } },
    )
}
