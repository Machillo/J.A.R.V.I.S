package com.dincr.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Bolt
import androidx.compose.material.icons.rounded.DirectionsBus
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Inbox
import androidx.compose.material.icons.rounded.LocalGasStation
import androidx.compose.material.icons.rounded.LocalHospital
import androidx.compose.material.icons.rounded.NorthEast
import androidx.compose.material.icons.rounded.Restaurant
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.ShoppingCart
import androidx.compose.material.icons.rounded.SouthWest
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.data.ApiError
import com.dincr.data.AuthException
import com.dincr.data.SearchText
import com.dincr.data.Movement
import com.dincr.data.MovementKind
import com.dincr.design.Dincr
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.EmptyState
import com.dincr.design.ErrorState
import com.dincr.design.MoneyRow
import com.dincr.design.SkeletonBlock
import com.dincr.design.generated.DincrSpacing
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlinx.coroutines.launch

enum class MovementFilter { ALL, INCOME, EXPENSE }

/**
 * PARITY D1, D3–D6 (partial: no debt or category filter yet) — movements by day, search, filter,
 * add, edit, delete. The backend returns the whole history; search and the type filter only
 * narrow what is already on screen.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MovementsScreen(model: AppModel, padding: PaddingValues, snackbar: SnackbarHostState) {
    var state by remember { mutableStateOf<Load<List<Movement>>>(Load.Loading) }
    var query by rememberSaveable { mutableStateOf("") }
    var filter by rememberSaveable { mutableStateOf(MovementFilter.ALL) }
    var editing by remember { mutableStateOf<EditorMode?>(null) }
    var pendingDelete by remember { mutableStateOf<Movement?>(null) }
    var refreshing by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val profile by model.profile.collectAsStateWithLifecycle()
    val baseCurrency = profile?.baseCurrency ?: "CRC"
    var deleting by remember { mutableStateOf(false) }
    suspend fun load() {
        model.load(tx("No pudimos cargar tus movimientos.", "We couldn’t load your transactions.")) { model.service.movements() }
            .onSuccess { state = Load.Ready(it) }
            .onFailure { if (it !is AuthException.SignedOut) state = Load.Failed(it.message.orEmpty()) }
    }
    LaunchedEffect(Unit) { load() }

    Box(Modifier.fillMaxSize().padding(padding)) {
        PullToRefreshBox(refreshing, onRefresh = { scope.launch { refreshing = true; load(); refreshing = false } }) {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = DincrSpacing.s4, end = DincrSpacing.s4, bottom = 96.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                item {
                    Column(Modifier.widthIn(max = 600.dp).fillMaxWidth().padding(top = DincrSpacing.s6), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                        Text(tx("Movimientos", "Transactions"), style = MaterialTheme.typography.headlineMedium, color = Dincr.colors.text, modifier = Modifier.semantics { heading() })
                        OutlinedTextField(query, { query = it }, placeholder = { Text(tx("Buscar movimientos", "Search transactions")) }, leadingIcon = { Icon(Icons.Rounded.Search, null) }, singleLine = true, modifier = Modifier.fillMaxWidth())
                        Row(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                            MovementFilter.entries.forEach { f ->
                                FilterChip(filter == f, { filter = f }, label = { Text(when (f) { MovementFilter.ALL -> tx("Todos", "All"); MovementFilter.INCOME -> tx("Ingresos", "Income"); MovementFilter.EXPENSE -> tx("Gastos", "Expenses") }) })
                            }
                        }
                    }
                }
                when (val s = state) {
                    Load.Loading -> item { Column(Modifier.widthIn(max = 600.dp).padding(top = DincrSpacing.s4)) { SkeletonBlock(rows = 5, showsFigure = false) } }
                    is Load.Failed -> item { Column(Modifier.widthIn(max = 600.dp).padding(top = DincrSpacing.s4)) { ErrorState(s.message) { scope.launch { state = Load.Loading; load() } } } }
                    is Load.Ready -> {
                        val visible = s.value.filter {
                            (filter == MovementFilter.ALL || (filter == MovementFilter.INCOME) == (it.kind == MovementKind.INCOME)) &&
                                SearchText.matches(query, listOf(it.description, it.category))
                        }
                        if (visible.isEmpty()) item {
                            Column(Modifier.widthIn(max = 600.dp).padding(top = DincrSpacing.s4)) {
                                val none = s.value.isEmpty()
                                EmptyState(if (none) Icons.Rounded.Inbox else Icons.Rounded.Search,
                                    if (none) tx("Todavía no hay movimientos", "No transactions yet") else tx("Nada coincide con tu búsqueda", "Nothing matches your search"),
                                    if (none) tx("Registrá tu primer ingreso o gasto para empezar.", "Record your first income or expense to begin.") else tx("Probá otra palabra o cambiá el filtro.", "Try another word or change the filter."),
                                    if (none) ({ DincrPrimaryButton(tx("Agregar movimiento", "Add transaction"), { editing = EditorMode.Create }) }) else null)
                            }
                        }
                        visible.groupBy { it.day.orEmpty() }.toSortedMap(compareByDescending { it }).forEach { (day, rows) ->
                            item(key = "h-$day") {
                                Text(dayLabel(day), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2,
                                    modifier = Modifier.widthIn(max = 600.dp).fillMaxWidth().padding(top = DincrSpacing.s5, bottom = DincrSpacing.s1).semantics { heading() })
                            }
                            items(rows, key = { it.movementId }) { movement ->
                                val editable = movement.isEditable(baseCurrency)
                                val edit = CustomAccessibilityAction(tx("Editar", "Edit")) { editing = EditorMode.Edit(movement); true }
                                val delete = CustomAccessibilityAction(tx("Eliminar", "Delete")) { pendingDelete = movement; true }
                                MoneyRow(
                                    title = movement.description?.takeIf { it.isNotBlank() } ?: movement.category ?: tx("Movimiento", "Transaction"),
                                    subtitle = listOfNotNull(movement.category, if (editable) null else tx("Solo lectura", "Read only")).joinToString(" · "),
                                    amount = movement.amount, kind = movement.kind, icon = iconFor(movement), readOnly = !editable,
                                    modifier = Modifier.widthIn(max = 600.dp)
                                        .then(if (editable) Modifier.clickable { editing = EditorMode.Edit(movement) }.semantics { customActions = listOf(edit, delete) } else Modifier),
                                )
                            }
                        }
                    }
                }
            }
        }
        val addLabel = tx("Agregar movimiento", "Add transaction")
        ExtendedFloatingActionButton(
            text = { Text(tx("Agregar", "Add")) },
            icon = { Icon(Icons.Rounded.Add, contentDescription = null) },
            onClick = { editing = EditorMode.Create },
            expanded = true,
            containerColor = Dincr.colors.tint, contentColor = Dincr.colors.onTint,
            modifier = Modifier.align(Alignment.BottomEnd).padding(DincrSpacing.s4).testTag("movements.add")
                .semantics { contentDescription = addLabel },
        )
    }

    editing?.let { mode ->
        MovementEditorSheet(model, mode, onDismiss = { editing = null }, onSaved = { message ->
            editing = null
            scope.launch { load(); snackbar.showSnackbar(message) }
        }, onDelete = { pendingDelete = it; editing = null })
    }

    pendingDelete?.let { movement ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text(tx("¿Eliminar «${movement.description ?: "movimiento"}»?", "Delete “${movement.description ?: "transaction"}”?")) },
            text = { Text(tx("Esta acción no se puede deshacer.", "This can’t be undone.")) },
            confirmButton = {
                TextButton({
                    pendingDelete = null
                    if (deleting) return@TextButton
                    deleting = true
                    scope.launch {
                        val result = model.load(tx("No pudimos eliminarlo. Intentá de nuevo.", "We couldn’t delete it. Please try again.")) { model.service.delete(movement.movementId) }
                        deleting = false
                        val gone = (result.exceptionOrNull() as? ApiError)?.kind == ApiError.Kind.NOT_FOUND
                        when {
                            result.isSuccess -> { load(); snackbar.showSnackbar(tx("Movimiento eliminado", "Transaction deleted")) }
                            // Already gone (deleted elsewhere or twice): show the list as it really is.
                            gone -> { load(); snackbar.showSnackbar(tx("Ese movimiento ya no existía.", "That transaction was already gone.")) }
                            result.exceptionOrNull() !is AuthException.SignedOut -> snackbar.showSnackbar(result.exceptionOrNull()?.message.orEmpty())
                        }
                    }
                }) { Text(tx("Eliminar", "Delete"), color = Dincr.colors.negative) }
            },
            dismissButton = { TextButton({ pendingDelete = null }) { Text(tx("Cancelar", "Cancel")) } },
        )
    }
}

private fun iconFor(m: Movement): ImageVector = if (m.kind == MovementKind.INCOME) Icons.Rounded.SouthWest else when (m.category?.lowercase()) {
    "vivienda", "alquiler" -> Icons.Rounded.Home
    "comida", "supermercado", "compras" -> Icons.Rounded.ShoppingCart
    "restaurante" -> Icons.Rounded.Restaurant
    "transporte" -> Icons.Rounded.DirectionsBus
    "gasolina" -> Icons.Rounded.LocalGasStation
    "servicios", "internet", "teléfono" -> Icons.Rounded.Bolt
    "salud" -> Icons.Rounded.LocalHospital
    else -> Icons.Rounded.NorthEast
}

fun dayLabel(day: String, today: LocalDate = LocalDate.now()): String {
    if (day.isEmpty()) return tx("Sin fecha", "No date")
    val date = runCatching { LocalDate.parse(day) }.getOrNull() ?: return day
    return when (date) {
        today -> tx("Hoy", "Today")
        today.minusDays(1) -> tx("Ayer", "Yesterday")
        else -> {
            val locale = if (tx("es", "en") == "es") Locale.forLanguageTag("es-CR") else Locale.US
            date.format(DateTimeFormatter.ofPattern(if (date.year == today.year) tx("d 'de' MMMM", "MMMM d") else tx("d 'de' MMMM yyyy", "MMMM d, yyyy"), locale))
        }
    }
}
