package com.dincr.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowRight
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.error
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AuthException
import com.dincr.data.MoneyFormat
import com.dincr.data.PullRefresh
import com.dincr.design.Dincr
import com.dincr.design.ErrorState
import com.dincr.design.MoneyText
import com.dincr.design.SkeletonBlock
import com.dincr.design.TabularNums
import com.dincr.design.generated.DincrRadius
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import java.math.RoundingMode
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import kotlinx.coroutines.launch

/** Content width on large screens (readable line length). */
val ContentMaxWidth = 640.dp

/**
 * A screen's backend data: loading, failed with a message, or ready. [refresh] (B17) reads again
 * and returns whether it could; when it can't, what was ready stays on screen ([PullRefresh.kept]).
 */
class LoadHandle<T>(state: androidx.compose.runtime.State<Load<T>>, val reload: () -> Unit, val replace: (T) -> Unit,
                    val refresh: suspend () -> Boolean = { true }) {
    val state: Load<T> by state
}

/**
 * Loads [block] when [keys] change and on [LoadHandle.reload]. Failures become a message the
 * screen can show; a rejected session signs out through [AppModel.load] (no crash, no stale data).
 */
@Composable
fun <T> rememberLoad(model: AppModel, vararg keys: Any?, fallback: String = tx("No pudimos cargar esta información.", "We couldn’t load this information."), block: suspend () -> T): LoadHandle<T> {
    val state = remember(*keys) { mutableStateOf<Load<T>>(Load.Loading) }
    var generation by remember(*keys) { mutableIntStateOf(0) }
    LaunchedEffect(generation, *keys) {
        if (state.value !is Load.Ready) state.value = Load.Loading
        model.load(fallback) { block() }
            .onSuccess { state.value = Load.Ready(it) }
            .onFailure { if (it !is AuthException.SignedOut) state.value = Load.Failed(it.message ?: fallback) }
    }
    val read by rememberUpdatedState(block)
    return remember(state) {
        LoadHandle(state, reload = { generation += 1 }, replace = { state.value = Load.Ready(it) }, refresh = {
            val result = model.load(fallback) { read() }
            val current = (state.value as? Load.Ready<T>)?.value
            when (val kept = PullRefresh.kept(current, result)) {
                null -> result.exceptionOrNull()?.takeIf { it !is AuthException.SignedOut }?.let { state.value = Load.Failed(it.message ?: fallback) }
                else -> state.value = Load.Ready(kept)
            }
            result.isSuccess
        })
    }
}

/**
 * B17 — a tab that reads again when pulled down (Plan, Patrimonio, Perfil): the platform's
 * indicator while [AppModel.refreshTab] runs, one refresh at a time, and the same refresh as a
 * TalkBack action on the tab's title. Hoy and Movimientos keep their own. iOS: `.refreshable`.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RefreshableTab(model: AppModel, title: String, extra: (suspend () -> Boolean)? = null, content: @Composable ColumnScope.() -> Unit) {
    var refreshing by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val refresh = {
        if (!refreshing) {
            refreshing = true
            scope.launch { try { model.refreshTab(extra) } finally { refreshing = false } }
        }
    }
    val action = tx("Actualizar", "Refresh")
    PullToRefreshBox(refreshing, onRefresh = refresh, modifier = Modifier.fillMaxSize().testTag("tab.refresh")) {
        ScreenColumn {
            Text(title, style = MaterialTheme.typography.headlineMedium, color = Dincr.colors.text, modifier = Modifier.semantics {
                heading()
                customActions = listOf(CustomAccessibilityAction(action) { refresh(); true })
            })
            content()
        }
    }
}

/** Skeleton while loading, inline error with retry on failure, [content] when ready. */
@Composable
fun <T> LoadContent(handle: LoadHandle<T>, rows: Int = 4, content: @Composable (T) -> Unit) {
    when (val s = handle.state) {
        Load.Loading -> SkeletonBlock(rows = rows)
        is Load.Failed -> ErrorState(s.message, onRetry = handle.reload)
        is Load.Ready -> content(s.value)
    }
}

/** Scrolling column with DINCR gutters, centred at [ContentMaxWidth]. */
@Composable
fun ScreenColumn(padding: PaddingValues = PaddingValues(), content: @Composable ColumnScope.() -> Unit) {
    Box(Modifier.fillMaxSize().padding(padding).imePadding(), contentAlignment = Alignment.TopCenter) {
        Column(
            Modifier.widthIn(max = ContentMaxWidth).fillMaxWidth().verticalScroll(rememberScrollState())
                .padding(horizontal = DincrSpacing.s4, vertical = DincrSpacing.s4),
            verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4),
            content = content,
        )
    }
}

/** A pushed screen: title, back arrow (and Android back), optional actions. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DetailScaffold(title: String, onBack: () -> Unit, actions: @Composable () -> Unit = {}, content: @Composable ColumnScope.() -> Unit) {
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().background(Dincr.colors.bg)) {
        TopAppBar(
            title = { Text(title, style = MaterialTheme.typography.titleLarge, maxLines = 1, modifier = Modifier.semantics { heading() }) },
            navigationIcon = {
                IconButton(onClick = onBack, modifier = Modifier.size(48.dp)) {
                    Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = tx("Volver", "Back"))
                }
            },
            actions = { actions() },
            colors = TopAppBarDefaults.topAppBarColors(containerColor = Dincr.colors.bg, titleContentColor = Dincr.colors.text, navigationIconContentColor = Dincr.colors.text),
        )
        ScreenColumn(content = content)
    }
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text, modifier = modifier.semantics { heading() })
}

/** Label on the left, amount on the right (tabular). */
@Composable
fun AmountLine(label: String, amount: BigDecimal?, emphasize: Boolean = false, sign: MoneyFormat.Sign = MoneyFormat.Sign.NONE, currency: String? = null) {
    Row(Modifier.fillMaxWidth().heightIn(min = 40.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text2, modifier = Modifier.weight(1f))
        MoneyText(amount, sign = sign, currency = currency,
            style = (if (emphasize) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyLarge).copy(fontWeight = FontWeight.SemiBold))
    }
}

/** Label and value text (non-money). */
@Composable
fun InfoLine(label: String, value: String) {
    Row(Modifier.fillMaxWidth().heightIn(min = 40.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text2, modifier = Modifier.weight(1f))
        Text(value, style = MaterialTheme.typography.bodyLarge.merge(TabularNums), color = Dincr.colors.text)
    }
}

/** A tappable row leading to another screen (≥ 56 dp). */
@Composable
fun NavRow(icon: ImageVector, title: String, subtitle: String? = null, badge: String? = null, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(onClick = onClick).padding(vertical = DincrSpacing.s2),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(40.dp).background(Dincr.colors.surface2, RoundedCornerShape(DincrRadius.md)), contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = null, tint = Dincr.colors.tint, modifier = Modifier.size(22.dp))
        }
        Column(Modifier.weight(1f).padding(horizontal = DincrSpacing.s3)) {
            Text(title, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text)
            subtitle?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted) }
        }
        badge?.let { PlanBadge(it) }
        Icon(Icons.AutoMirrored.Rounded.KeyboardArrowRight, contentDescription = null, tint = Dincr.colors.textMuted)
    }
}

/** "Basic" / "VIP" pill. */
@Composable
fun PlanBadge(text: String) {
    val vip = text.equals("VIP", ignoreCase = true)
    Text(
        text, style = MaterialTheme.typography.labelMedium,
        color = if (vip) Dincr.colors.vip else Dincr.colors.onTintContainer,
        modifier = Modifier.background(if (vip) Dincr.colors.vipContainer else Dincr.colors.tintContainer, RoundedCornerShape(DincrRadius.xs))
            .padding(horizontal = DincrSpacing.s2, vertical = 2.dp),
    )
}

/** Progress as a bar with its value in text (DESIGN.md: no rings). Ratio in 0..1. */
@Composable
fun ProgressLine(ratio: Double, label: String) {
    val clamped = ratio.coerceIn(0.0, 1.0).toFloat()
    Column(Modifier.fillMaxWidth().semantics(mergeDescendants = true) { contentDescription = label }) {
        LinearProgressIndicator(progress = { clamped }, modifier = Modifier.fillMaxWidth().height(8.dp), color = Dincr.colors.tint, trackColor = Dincr.colors.surface2, drawStopIndicator = {})
        Text(label, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.text2, modifier = Modifier.padding(top = DincrSpacing.s1))
    }
}

/** Percent of [part] over [whole], or null when [whole] is not positive (unknown, never 0 %). */
fun percentOf(part: BigDecimal?, whole: BigDecimal?): Double? {
    if (part == null || whole == null || whole.signum() <= 0) return null
    return part.divide(whole, 6, RoundingMode.HALF_UP).toDouble()
}

/** A text field with a visible label, inline error and the right keyboard. */
@Composable
fun FormField(label: String, value: String, onChange: (String) -> Unit, error: String? = null, keyboard: KeyboardType = KeyboardType.Text, prefix: String? = null, supporting: String? = null, singleLine: Boolean = true, modifier: Modifier = Modifier) {
    OutlinedTextField(
        value = value, onValueChange = onChange, label = { Text(label) }, singleLine = singleLine,
        prefix = prefix?.let { { Text(it) } },
        isError = error != null,
        supportingText = (error ?: supporting)?.let { { Text(it) } },
        keyboardOptions = KeyboardOptions(keyboardType = keyboard),
        shape = RoundedCornerShape(DincrRadius.md),
        colors = OutlinedTextFieldDefaults.colors(unfocusedBorderColor = Dincr.colors.fieldBorder, focusedBorderColor = Dincr.colors.tint),
        modifier = modifier.fillMaxWidth().semantics { if (error != null) error(error) },
    )
}

/** A money field: the user's separators, the currency symbol as prefix. */
@Composable
fun MoneyField(label: String, value: String, onChange: (String) -> Unit, error: String? = null, symbol: String = Dincr.money.symbol, supporting: String? = null, modifier: Modifier = Modifier) =
    FormField(label, value, onChange, error, KeyboardType.Decimal, prefix = symbol, supporting = supporting, modifier = modifier)

/** Example amount in the user's format, for error copy ("por ejemplo 18.450"). */
@Composable
fun amountExample(): String = Dincr.money.format(BigDecimal(18450)).removePrefix(Dincr.money.symbol).trim()

/** A date (`YYYY-MM-DD`) picked with the Material date picker; [allowClear] adds "Sin fecha". */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DateField(label: String, value: LocalDate?, onChange: (LocalDate?) -> Unit, allowClear: Boolean = false) {
    var open by remember { mutableStateOf(false) }
    Row(
        Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable { open = true }
            .background(Dincr.colors.surface, RoundedCornerShape(DincrRadius.md)).padding(horizontal = DincrSpacing.s4),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)
            Text(value?.let { dateLabel(it) } ?: tx("Sin fecha", "No date"), style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text)
        }
        Icon(Icons.Rounded.CalendarMonth, contentDescription = null, tint = Dincr.colors.tint)
    }
    if (open) {
        val picker = rememberDatePickerState(initialSelectedDateMillis = (value ?: LocalDate.now()).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli())
        DatePickerDialog(
            onDismissRequest = { open = false },
            confirmButton = {
                TextButton({ picker.selectedDateMillis?.let { onChange(Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate()) }; open = false }) { Text(tx("Listo", "Done")) }
            },
            dismissButton = {
                Row {
                    if (allowClear) TextButton({ onChange(null); open = false }) { Text(tx("Sin fecha", "No date")) }
                    TextButton({ open = false }) { Text(tx("Cancelar", "Cancel")) }
                }
            },
        ) { DatePicker(picker) }
    }
}

fun dateLabel(date: LocalDate): String =
    java.time.format.DateTimeFormatter.ofPattern("d MMM yyyy", java.util.Locale.getDefault()).format(date)

fun dateLabel(iso: String?): String = iso?.take(10)?.let { runCatching { dateLabel(LocalDate.parse(it)) }.getOrNull() } ?: "—"

/** One-of-many choice as chips (wraps on small screens). */
@Composable
fun <T> ChoiceChips(options: List<Pair<T, String>>, selected: T, onSelect: (T) -> Unit, label: String? = null) {
    Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
        label?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted) }
        androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s2), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            options.forEach { (value, text) ->
                FilterChip(
                    selected = value == selected, onClick = { onSelect(value) }, label = { Text(text) },
                    modifier = Modifier.heightIn(min = 48.dp),
                    colors = FilterChipDefaults.filterChipColors(selectedContainerColor = Dincr.colors.tintContainer, selectedLabelColor = Dincr.colors.onTintContainer),
                )
            }
        }
    }
}

/** Destructive or important confirmation. */
@Composable
fun ConfirmDialog(title: String, message: String, confirm: String, destructive: Boolean = true, busy: Boolean = false, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(title) },
        text = { Text(message) },
        confirmButton = {
            TextButton(onConfirm, enabled = !busy) { Text(confirm, color = if (destructive) Dincr.colors.negative else Dincr.colors.tint) }
        },
        dismissButton = { TextButton(onDismiss, enabled = !busy) { Text(tx("Cancelar", "Cancel")) } },
    )
}

/**
 * Asks for one amount (payment, contribution). [submit] gets the parsed value and its idempotency
 * key and returns an error message or null; the dialog stays single-flight while it runs. Retrying
 * the same amount after an error reuses the key (no double payment on a lost response).
 */
@Composable
fun AmountDialog(title: String, message: String?, confirm: String, onDismiss: () -> Unit, submit: suspend (BigDecimal, String) -> String?) {
    val separators = Dincr.money.separators
    val example = amountExample()
    val submission = remember { com.dincr.data.AmountSubmission() }
    var text by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                message?.let { Text(it, color = Dincr.colors.text2) }
                MoneyField(tx("Monto", "Amount"), text, { text = it; error = null }, error)
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, onClick = {
                val amount = com.dincr.data.AmountInput.parse(text, separators)
                if (amount == null) { error = tx("Escribí un monto mayor que cero, por ejemplo $example.", "Enter an amount above zero, for example $example."); return@TextButton }
                busy = true
                val key = submission.keyFor(amount)
                scope.launch { error = submit(amount, key); busy = false }
            }) { Text(confirm) }
        },
        dismissButton = { TextButton(onDismiss, enabled = !busy) { Text(tx("Cancelar", "Cancel")) } },
    )
}

/** Small uppercase-free caption under a figure. */
@Composable
fun Caption(text: String) = Text(text, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)

/** A form in a bottom sheet: title, fields, inline error, single-flight primary action. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FormSheet(title: String, saving: Boolean, error: String?, primary: String, onPrimary: () -> Unit, onDismiss: () -> Unit, extra: @Composable () -> Unit = {}, content: @Composable ColumnScope.() -> Unit) {
    val sheet = androidx.compose.material3.rememberModalBottomSheetState(skipPartiallyExpanded = true)
    androidx.compose.material3.ModalBottomSheet(onDismissRequest = { if (!saving) onDismiss() }, sheetState = sheet, containerColor = Dincr.colors.surface) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = DincrSpacing.s4, vertical = DincrSpacing.s2),
            verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4),
        ) {
            Text(title, style = MaterialTheme.typography.headlineSmall, color = Dincr.colors.text, modifier = Modifier.semantics { heading() })
            content()
            error?.let { ErrorState(it) }
            com.dincr.design.DincrPrimaryButton(primary, onPrimary, loading = saving)
            extra()
            androidx.compose.foundation.layout.Spacer(Modifier.height(DincrSpacing.s6))
        }
    }
}
