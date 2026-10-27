package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AccountBalance
import androidx.compose.material.icons.rounded.Work
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.AuthException
import com.dincr.data.BusinessCenter
import com.dincr.data.BusinessCreateRequest
import com.dincr.data.BusinessMovementRequest
import com.dincr.data.InvestmentCenter
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.EmptyState
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.coroutines.launch

/**
 * JARVIS → Patrimonio (Owner only): the investments (the latest IBKR or manual portfolio snapshot and
 * its positions, "Actualizar desde IBKR") and the businesses (their totals and movements, "Nuevo
 * negocio", "Registrar movimiento"). Opening it only reads; every write is an explicit Owner command,
 * sent once and never retried on its own. Without a portfolio snapshot it says so instead of showing
 * ₡0 / 0 %. The net worth stays in Análisis financiero ("Ver patrimonio neto"). Not the public
 * Patrimonio tab ([WealthScreen]). iOS: `WealthView`.
 */
@Composable
fun OwnerWealthScreen(model: AppModel, nav: Navigator) {
    var tab by remember { mutableStateOf("investments") }
    val investments = rememberLoad(model, fallback = tx("No pudimos cargar tus inversiones.", "We couldn’t load your investments.")) { model.api.investmentCenter() }
    val businesses = rememberLoad(model, fallback = tx("No pudimos cargar tus negocios.", "We couldn’t load your businesses.")) { model.api.businessCenter() }
    var syncing by remember { mutableStateOf(false) }
    var syncError by remember { mutableStateOf<String?>(null) }
    var addingBusiness by remember { mutableStateOf(false) }
    var recording by remember { mutableStateOf<BusinessCenter.Business?>(null) }
    val scope = rememberCoroutineScope()
    // "Actualizar desde IBKR": one request (disabled while it runs), never retried on its own; the backend's error is shown as is.
    val sync: () -> Unit = {
        if (!syncing) {
            syncing = true
            syncError = null
            scope.launch {
                model.load(tx("No pudimos actualizar desde IBKR.", "We couldn’t update from IBKR.")) { model.api.syncIbkr() }
                    .fold({ investments.reload(); model.showNotice(tx("Portafolio actualizado", "Portfolio updated")) },
                        { if (it !is AuthException.SignedOut) syncError = it.message })
                syncing = false
            }
        }
    }
    DetailScaffold(tx("Patrimonio", "Wealth"), nav::back) {
        ChoiceChips(listOf("investments" to tx("Inversiones", "Investments"), "businesses" to tx("Negocios", "Businesses")), tab, { tab = it })
        if (tab == "investments") LoadContent(investments) { InvestmentsContent(it, syncing, syncError, sync) }
        else LoadContent(businesses) { BusinessesContent(it, add = { addingBusiness = true }, record = { business -> recording = business }) }
        DincrCard(Modifier.testTag("wealth.netWorth")) {
            NavRow(Icons.Rounded.AccountBalance, tx("Ver patrimonio neto", "See net worth"), tx("En Análisis financiero", "In Financial analysis")) {
                nav.push("jarvis/analysis")
            }
        }
    }
    if (addingBusiness) BusinessEntryDialog(model, onDismiss = { addingBusiness = false }) {
        addingBusiness = false; businesses.reload(); model.showNotice(tx("Negocio creado", "Business created"))
    }
    recording?.let { business ->
        BusinessMovementDialog(model, business, onDismiss = { recording = null }) {
            recording = null; businesses.reload(); model.showNotice(tx("Movimiento registrado", "Movement recorded"))
        }
    }
}

/** A percentage with up to two decimals ("11,11 %"). */
private fun percentLabel(value: BigDecimal): String {
    val format = java.text.NumberFormat.getNumberInstance(java.util.Locale.getDefault()).apply { maximumFractionDigits = 2 }
    return "${format.format(value)} %"
}

private fun quantityLabel(value: BigDecimal): String =
    java.text.NumberFormat.getNumberInstance(java.util.Locale.getDefault()).apply { maximumFractionDigits = 4 }.format(value)

@Composable
private fun InvestmentsContent(center: InvestmentCenter, syncing: Boolean, syncError: String?, sync: () -> Unit) {
    DincrCard(Modifier.testTag("wealth.investments")) {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            val figures = center.figures
            if (figures != null) {
                AmountLine(tx("Valor de mercado", "Market value"), figures.marketValue, currency = figures.currency)
                AmountLine(tx("Capital aportado", "Contributed capital"), figures.contributedCapital, currency = figures.currency)
                AmountLine(tx("Ganancia neta", "Net gain"), figures.netPnl, currency = figures.currency)
                figures.returnPct?.let { pct ->
                    Row(Modifier.heightIn(min = 40.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(tx("Rendimiento", "Return"), style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text2, modifier = Modifier.weight(1f))
                        Text(percentLabel(pct), style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold), color = Dincr.colors.text)
                    }
                }
            } else {
                // Unknown ≠ 0: without a snapshot the backend's 0 figures are not shown.
                Text(tx("Todavía no hay datos de tu portafolio", "There’s no portfolio data yet"), style = MaterialTheme.typography.titleMedium,
                    color = Dincr.colors.text, modifier = Modifier.testTag("wealth.investments.empty"))
            }
            syncCaption(center)?.let { Caption(it) }
            AmountLine(tx("Reservado para invertir", "Reserved to invest"), center.reservedToInvestCrc, currency = "CRC")
            if (center.flexConfigured) {
                TextButton(sync, enabled = !syncing, modifier = Modifier.heightIn(min = 48.dp).testTag("wealth.sync")) {
                    Text(if (syncing) tx("Actualizando…", "Updating…") else tx("Actualizar desde IBKR", "Update from IBKR"), color = Dincr.colors.tint)
                }
            }
            syncError?.let { Text(it, color = Dincr.colors.negative, style = MaterialTheme.typography.bodySmall) }
        }
    }
    if (center.positions.isNotEmpty()) {
        DincrCard(Modifier.testTag("wealth.positions")) {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                Caption(tx("Posiciones", "Positions"))
                center.positions.forEach { position ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(position.symbol ?: tx("Posición", "Position"), style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text)
                            position.quantity?.let { Caption(tx("Cantidad: ${quantityLabel(it)}", "Quantity: ${quantityLabel(it)}")) }
                            position.unrealizedPnl?.let { pnl ->
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Caption(tx("Ganancia no realizada: ", "Unrealized gain: "))
                                    MoneyText(pnl, style = MaterialTheme.typography.bodySmall, currency = position.currency)
                                }
                            }
                        }
                        MoneyText(position.marketValue, currency = position.currency)
                    }
                }
            }
        }
    }
}

private fun syncCaption(center: InvestmentCenter): String? = when (center.syncState) {
    InvestmentCenter.SyncState.CURRENT -> center.ageHours?.let { hours ->
        if (hours == 0L) tx("Actualizado hace menos de 1 h", "Updated less than 1 h ago") else tx("Actualizado hace $hours h", "Updated $hours h ago")
    } ?: tx("Actualizado", "Up to date")
    InvestmentCenter.SyncState.STALE -> tx("Desactualizado", "Out of date")
    InvestmentCenter.SyncState.MANUAL -> tx("Manual", "Manual")
    InvestmentCenter.SyncState.UNKNOWN -> null
}

private fun typeLabel(type: String?): String = when (type) {
    "income" -> tx("Ingreso", "Income")
    "expense" -> tx("Gasto", "Expense")
    "capital" -> tx("Capital", "Capital")
    else -> tx("Movimiento", "Movement")
}

@Composable
private fun BusinessesContent(center: BusinessCenter, add: () -> Unit, record: (BusinessCenter.Business) -> Unit) {
    DincrCard(Modifier.testTag("wealth.businesses")) {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            AmountLine(tx("Ingresos", "Income"), center.income)
            AmountLine(tx("Gastos", "Expenses"), center.expenses)
            AmountLine(tx("Ganancia", "Profit"), center.profit)
            AmountLine(tx("Capital aportado", "Capital contributed"), center.capital)
            TextButton(add, modifier = Modifier.heightIn(min = 48.dp).testTag("wealth.addBusiness")) {
                Text(tx("Nuevo negocio", "New business"), color = Dincr.colors.tint)
            }
        }
    }
    if (center.businesses.isEmpty()) {
        EmptyState(Icons.Rounded.Work, tx("Todavía no tenés negocios", "You don’t have businesses yet"),
            tx("Con «Nuevo negocio» registrás uno.", "Use “New business” to add one."))
    }
    center.businesses.forEach { business ->
        DincrCard(Modifier.testTag("wealth.business.${business.id}")) {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                Text(business.name ?: tx("Negocio", "Business"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                business.description?.takeIf { it.isNotBlank() }?.let { Caption(it) }
                business.ownershipPct?.let { Caption(tx("Participación: ${percentLabel(it)}", "Ownership: ${percentLabel(it)}")) }
                val movements = center.movementsOf(business)
                if (movements.isEmpty()) Caption(tx("Sin movimientos todavía", "No movements yet"))
                movements.forEach { movement ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(movement.description ?: typeLabel(movement.movementType), style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text)
                            Caption(listOfNotNull(typeLabel(movement.movementType), movement.movementDate?.let { dateLabel(it) }).joinToString(" · "))
                        }
                        MoneyText(movement.amount?.let { if (movement.movementType == "expense") it.negate() else it })
                    }
                }
                TextButton({ record(business) }, modifier = Modifier.heightIn(min = 48.dp).testTag("wealth.addMovement.${business.id}")) {
                    Text(tx("Registrar movimiento", "Record movement"), color = Dincr.colors.tint)
                }
            }
        }
    }
}

/** "Nuevo negocio": sent once (disabled while it is sent), never retried on its own. */
@Composable
private fun BusinessEntryDialog(model: AppModel, onDismiss: () -> Unit, onSaved: () -> Unit) {
    var name by remember { mutableStateOf("") }
    var detail by remember { mutableStateOf("") }
    var ownership by remember { mutableStateOf("100") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(tx("Nuevo negocio", "New business")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                FormField(tx("Nombre", "Name"), name, { name = it; error = null }, modifier = Modifier.testTag("wealth.business.name"))
                FormField(tx("Descripción (opcional)", "Description (optional)"), detail, { detail = it }, modifier = Modifier.testTag("wealth.business.description"))
                FormField(tx("Participación (%)", "Ownership (%)"), ownership, { ownership = it; error = null }, keyboard = KeyboardType.Decimal,
                    modifier = Modifier.testTag("wealth.business.ownership"))
                error?.let { Text(it, color = Dincr.colors.negative, style = MaterialTheme.typography.bodySmall) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, modifier = Modifier.testTag("wealth.business.save"), onClick = {
                val trimmed = name.trim()
                val percent = ownership.trim().replace(',', '.').toBigDecimalOrNull()
                when {
                    trimmed.isEmpty() -> error = tx("Escribí el nombre del negocio.", "Enter the business name.")
                    percent == null -> error = tx("La participación va de 0 a 100.", "Ownership goes from 0 to 100.")
                    percent < BigDecimal.ZERO || percent > BigDecimal(100) -> error = tx("La participación va de 0 a 100.", "Ownership goes from 0 to 100.")
                    else -> {
                        busy = true
                        scope.launch {
                            model.load(tx("No pudimos crearlo. Revisá la lista antes de intentar de nuevo.", "We couldn’t create it. Check the list before trying again.")) {
                                model.api.createBusiness(BusinessCreateRequest(trimmed, detail.trim().ifEmpty { null }, percent))
                            }.fold({ onSaved() }, { if (it !is AuthException.SignedOut) error = it.message })
                            busy = false
                        }
                    }
                }
            }) { Text(tx("Guardar", "Save")) }
        },
        dismissButton = { TextButton(onDismiss, enabled = !busy) { Text(tx("Cancelar", "Cancel")) } },
    )
}

/**
 * "Registrar movimiento": an income, expense or capital contribution of one business. An income or
 * expense also lands in the Owner's transactions, and the form says so. Sent once, never retried.
 */
@Composable
private fun BusinessMovementDialog(model: AppModel, business: BusinessCenter.Business, onDismiss: () -> Unit, onSaved: () -> Unit) {
    var type by remember { mutableStateOf("income") }
    var amount by remember { mutableStateOf("") }
    var detail by remember { mutableStateOf("") }
    var date by remember { mutableStateOf<LocalDate?>(LocalDate.now()) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val separators = Dincr.money.separators
    val example = amountExample()
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(business.name ?: tx("Registrar movimiento", "Record movement")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                ChoiceChips(BusinessMovementRequest.types.map { it to typeLabel(it) }, type, { type = it }, tx("Tipo", "Type"))
                MoneyField(tx("Monto", "Amount"), amount, { amount = it; error = null }, modifier = Modifier.testTag("wealth.movement.amount"))
                FormField(tx("Descripción", "Description"), detail, { detail = it; error = null }, modifier = Modifier.testTag("wealth.movement.description"))
                DateField(tx("Fecha", "Date"), date, { date = it })
                if (type != "capital") Text(tx("También se registra en tus movimientos.", "It’s also recorded in your transactions."),
                    style = MaterialTheme.typography.bodySmall, color = Dincr.colors.text2, modifier = Modifier.testTag("wealth.movement.ledgerNote"))
                error?.let { Text(it, color = Dincr.colors.negative, style = MaterialTheme.typography.bodySmall) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, modifier = Modifier.testTag("wealth.movement.save"), onClick = {
                val value = AmountInput.parse(amount, separators)
                val description = detail.trim()
                when {
                    value == null -> error = tx("Escribí un monto mayor que cero, por ejemplo $example.", "Enter an amount above zero, for example $example.")
                    description.isEmpty() -> error = tx("Escribí una descripción.", "Enter a description.")
                    else -> {
                        busy = true
                        scope.launch {
                            model.load(tx("No pudimos registrarlo. Revisá la lista antes de intentar de nuevo.", "We couldn’t record it. Check the list before trying again.")) {
                                model.api.addBusinessMovement(BusinessMovementRequest(business.id, type, value, date?.toString(), description))
                            }.fold({ onSaved() }, { if (it !is AuthException.SignedOut) error = it.message })
                            busy = false
                        }
                    }
                }
            }) { Text(tx("Registrar", "Record")) }
        },
        dismissButton = { TextButton(onDismiss, enabled = !busy) { Text(tx("Cancelar", "Cancel")) } },
    )
}
