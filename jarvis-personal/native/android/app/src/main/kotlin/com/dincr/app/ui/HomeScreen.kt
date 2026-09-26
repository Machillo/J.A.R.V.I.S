package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Inbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AuthException
import com.dincr.data.FreeDashboard
import com.dincr.data.MoneyFormat
import com.dincr.design.BannerTone
import com.dincr.design.CategoryBars
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.EmptyState
import com.dincr.design.ErrorState
import com.dincr.design.IncomeExpenseBars
import com.dincr.design.MoneyText
import com.dincr.design.SkeletonBlock
import com.dincr.design.StatusBanner
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import kotlinx.coroutines.launch

sealed interface Load<out T> { data object Loading : Load<Nothing>; data class Failed(val message: String) : Load<Nothing>; data class Ready<T>(val value: T) : Load<T> }

/** PARITY C1 — Free overview. All figures are backend values; nothing is derived here. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(model: AppModel, padding: PaddingValues, openMovements: () -> Unit) {
    val profile by model.profile.collectAsStateWithLifecycle()
    var state by remember { mutableStateOf<Load<FreeDashboard>>(Load.Loading) }
    var refreshing by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    suspend fun load() {
        model.load(tx("No pudimos cargar tu resumen.", "We couldn’t load your overview.")) { model.service.freeDashboard() }
            .onSuccess { state = Load.Ready(it) }
            .onFailure { if (it !is AuthException.SignedOut) state = Load.Failed(it.message.orEmpty()) }
    }
    LaunchedEffect(Unit) { load() }

    PullToRefreshBox(refreshing, onRefresh = { scope.launch { refreshing = true; load(); refreshing = false } }, modifier = Modifier.fillMaxSize().padding(padding)) {
        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(DincrSpacing.s4),
            verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            item {
                Text(tx("Hola, ${profile?.firstName.orEmpty()}", "Hi, ${profile?.firstName.orEmpty()}"), style = MaterialTheme.typography.headlineMedium,
                    color = Dincr.colors.text, modifier = Modifier.fillMaxWidth().widthIn(max = 600.dp).padding(top = DincrSpacing.s6).semantics { heading() })
            }
            when (val s = state) {
                Load.Loading -> item { Column(Modifier.widthIn(max = 600.dp)) { SkeletonBlock(rows = 3) } }
                is Load.Failed -> item { Column(Modifier.widthIn(max = 600.dp)) { ErrorState(s.message) { scope.launch { state = Load.Loading; load() } } } }
                is Load.Ready -> {
                    val d = s.value
                    if (profile?.plan != "free") item {
                        // Basic and VIP dashboards (PARITY C2, C3) are not built yet; say so.
                        val plan = planName(profile?.plan)
                        Column(Modifier.widthIn(max = 600.dp)) {
                            StatusBanner(BannerTone.INFO, tx("Resumen básico", "Basic overview"),
                                tx("Tu panel completo de $plan todavía está en la app actual de DINCR.", "Your full $plan dashboard is still in the current DINCR app."))
                        }
                    }
                    item { Column(Modifier.widthIn(max = 600.dp)) { KeyFigure(d) } }
                    // Presentation only: the backend always sends six months, zero-filled for new accounts.
                    val empty = d.categories.isEmpty() && d.income.signum() == 0 && d.expenses.signum() == 0 &&
                        d.monthlyHistory.all { it.income.signum() == 0 && it.expenses.signum() == 0 }
                    if (empty) item {
                        Column(Modifier.widthIn(max = 600.dp)) {
                            EmptyState(Icons.Rounded.Inbox, tx("Todavía no hay movimientos", "No transactions yet"),
                                tx("Cuando registrés ingresos y gastos, acá verás tu mes y en qué se va el dinero.", "When you record income and expenses, you’ll see your month and where the money goes here.")) {
                                DincrPrimaryButton(tx("Agregar movimiento", "Add transaction"), openMovements)
                            }
                        }
                    } else {
                        item { Section(tx("Ingresos y gastos", "Income and expenses")) { IncomeExpenseBars(d.monthlyHistory.map { Triple(shortMonth(it.month), it.income, it.expenses) }) } }
                        item { Section(tx("En qué se va el dinero", "Where the money goes")) { CategoryBars(d.categories.map { it.category to it.amount }) } }
                        item {
                            Column(Modifier.widthIn(max = 600.dp)) {
                                TextButton(onClick = openMovements, modifier = Modifier.fillMaxWidth()) { Text(tx("Ver movimientos", "See transactions"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.tint) }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun KeyFigure(d: FreeDashboard) {
    DincrCard {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Text(tx("Disponible este mes", "Available this month"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
            MoneyText(d.available, style = MaterialTheme.typography.displaySmall)
            Row(Modifier.padding(top = DincrSpacing.s2), horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s6)) {
                Figure(tx("Ingresos", "Income"), d.income, MoneyFormat.Sign.INCOME)
                Figure(tx("Gastos", "Expenses"), d.expenses, MoneyFormat.Sign.EXPENSE)
            }
            d.debtBalance?.takeIf { it.signum() > 0 }?.let { debt ->
                HorizontalDivider(color = Dincr.colors.line, modifier = Modifier.padding(vertical = DincrSpacing.s1))
                Row(Modifier.fillMaxWidth().semantics(mergeDescendants = true) {}, horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(tx("Deuda pendiente", "Outstanding debt"), style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
                    MoneyText(debt, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}

@Composable
private fun Figure(label: String, amount: BigDecimal, sign: MoneyFormat.Sign) {
    Column(Modifier.semantics(mergeDescendants = true) {}) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)
        MoneyText(amount, sign = sign)
    }
}

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    Column(Modifier.widthIn(max = 600.dp)) {
        DincrCard {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                Text(title, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text, modifier = Modifier.semantics { heading() })
                content()
            }
        }
    }
}

fun shortMonth(period: String): String {
    val month = period.substringAfter('-').toIntOrNull() ?: return period
    val names = if (tx("es", "en") == "es") listOf("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic")
    else listOf("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return names.getOrElse(month - 1) { period }
}
