package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AccountCircle
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.BarChart
import androidx.compose.material.icons.automirrored.rounded.ReceiptLong
import androidx.compose.material.icons.rounded.TrackChanges
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.dincr.app.AppModel
import com.dincr.app.Appearance
import com.dincr.app.tx
import com.dincr.data.AppLanguage
import com.dincr.data.OpsFlag
import com.dincr.design.BannerTone
import com.dincr.design.Dincr
import com.dincr.design.StatusBanner
import com.dincr.design.generated.DincrSpacing

enum class Destination(val route: String, val icon: ImageVector) {
    HOME("home", Icons.Rounded.BarChart), MOVEMENTS("movements", Icons.AutoMirrored.Rounded.ReceiptLong), PLAN("plan", Icons.Rounded.TrackChanges),
    ADVISOR("advisor", Icons.Rounded.AutoAwesome), PROFILE("profile", Icons.Rounded.AccountCircle);

    val label: String get() = when (this) {
        HOME -> tx("Hoy", "Today"); MOVEMENTS -> tx("Movimientos", "Transactions"); PLAN -> tx("Plan", "Plan")
        ADVISOR -> "DINCR"; PROFILE -> tx("Perfil", "Profile")
    }

    companion object {
        /** Which tab a pushed screen belongs to (the tab stays highlighted, as in the Capacitor app). */
        fun of(route: String?): Destination = when (route?.substringBefore('/')) {
            null, "home" -> HOME
            "movements", "monthly" -> MOVEMENTS
            "plan", "debts", "goals", "budget", "calendar", "recurring", "emergency", "aguinaldo" -> PLAN
            "advisor", "strategy", "scenarios", "review", "today", "projections", "reports" -> ADVISOR
            else -> PROFILE
        }
    }
}

/** Opens a route; tab roots keep one copy each and restore their state. */
class Navigator(private val controller: NavHostController) {
    fun open(route: String) = controller.navigate(route) { launchSingleTop = true }
    /** Stacks [route] even over the same destination pattern (the agenda opening the chat: both `jarvis/{section}`). */
    fun push(route: String) = controller.navigate(route)
    fun back() { controller.popBackStack() }
    fun tab(destination: Destination) = controller.navigate(destination.route) {
        popUpTo(controller.graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}

/** PARITY B1 — five destinations; bar on compact width, rail from 600 dp (Material guidance). */
@Composable
fun MainScaffold(model: AppModel, appearance: Appearance, onAppearance: (Appearance) -> Unit) {
    val controller = rememberNavController()
    val nav = remember(controller) { Navigator(controller) }
    val entry by controller.currentBackStackEntryAsState()
    val current = Destination.of(entry?.destination?.route)
    val snackbar = remember { SnackbarHostState() }
    val notice by model.notice.collectAsStateWithLifecycle()
    val route by model.pendingRoute.collectAsStateWithLifecycle()
    var offerLock by remember { mutableStateOf(!model.appLock.onboardingSeen && !model.isFixtures) }
    LaunchedEffect(notice) { notice?.let { snackbar.showSnackbar(it); model.consumeNotice() } }
    LaunchedEffect(route) { route?.let { nav.open(it); model.consumeRoute() } }
    if (offerLock) AppLockOffer(model) { offerLock = false }
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val expanded = maxWidth >= 600.dp
        Scaffold(
            containerColor = Dincr.colors.bg,
            snackbarHost = { SnackbarHost(snackbar) },
            bottomBar = {
                if (!expanded) NavigationBar(containerColor = Dincr.colors.surface) {
                    Destination.entries.forEach { d ->
                        NavigationBarItem(selected = current == d, onClick = { nav.tab(d) }, icon = { Icon(d.icon, contentDescription = null) }, label = { Text(d.label, maxLines = 1) })
                    }
                }
            },
        ) { padding ->
            Row(Modifier.fillMaxSize().padding(bottom = padding.calculateBottomPadding())) {
                if (expanded) NavigationRail(containerColor = Dincr.colors.surface) {
                    Destination.entries.forEach { d ->
                        NavigationRailItem(selected = current == d, onClick = { nav.tab(d) }, icon = { Icon(d.icon, contentDescription = null) }, label = { Text(d.label) })
                    }
                }
                Column(Modifier.weight(1f).statusBarsPadding()) {
                    GlobalBanners(model)
                    Box(Modifier.weight(1f)) {
                        NavHost(controller, startDestination = Destination.HOME.route) {
                            val top = PaddingValues()
                            composable("home") { HomeScreen(model, top, nav) }
                            composable("movements") { MovementsScreen(model, top, snackbar, nav) }
                            composable("monthly") { MonthlySummaryScreen(model, nav) }
                            composable("plan") { PlanHubScreen(model, nav) }
                            composable("debts") { DebtsScreen(model, nav) }
                            composable("goals") { GoalsScreen(model, nav) }
                            composable("budget") { BudgetScreen(model, nav) }
                            composable("calendar") { CalendarScreen(model, nav) }
                            composable("recurring") { RecurringScreen(model, nav) }
                            composable("emergency") { EmergencyScreen(model, nav) }
                            composable("aguinaldo") { AguinaldoScreen(model, nav) }
                            composable("advisor") { AdvisorHubScreen(model, nav) }
                            composable("strategy") { StrategyScreen(model, nav) }
                            composable("scenarios") { ScenariosScreen(model, nav) }
                            composable("review") { MonthlyReviewScreen(model, nav) }
                            composable("today") { TodayScreen(model, nav) }
                            composable("projections") { ProjectionsScreen(model, nav) }
                            composable("reports") { ReportsScreen(model, nav) }
                            composable("profile") { ProfileHubScreen(model, nav) }
                            composable("situation") { SituationScreen(model, nav) }
                            composable("settings") { SettingsScreen(model, nav, appearance, onAppearance) }
                            composable("plans") { PlanSettingsScreen(model, nav) }
                            composable("security") { SecurityScreen(model, nav) }
                            composable("mail") { MailScreen(model, nav) }
                            composable("accounts") { AccountsScreen(model, nav) }
                            composable("support") { SupportScreen(model, nav) }
                            // JARVIS: the Owner's personal space (Jarvis.isAvailable); each screen checks it again.
                            composable("jarvis") { JarvisHubScreen(model, nav) }
                            composable("jarvis/{section}") { entry -> JarvisSectionScreen(model, nav, entry.arguments?.getString("section")) }
                        }
                    }
                }
            }
        }
    }
}

/** B5/B7/A1 — changes paused, service health and optional update, above every screen. */
@Composable
private fun GlobalBanners(model: AppModel) {
    val flags by model.flags.collectAsStateWithLifecycle()
    val health by model.health.collectAsStateWithLifecycle()
    val release by model.release.collectAsStateWithLifecycle()
    val language = AppLanguage.current()
    Column(Modifier.fillMaxWidth().padding(horizontal = DincrSpacing.s4), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2), horizontalAlignment = Alignment.CenterHorizontally) {
        if (!flags.isEnabled(OpsFlag.FINANCIAL_WRITES) && flags.flags.isNotEmpty()) Box(Modifier.widthIn(max = ContentMaxWidth).padding(top = DincrSpacing.s2)) {
            StatusBanner(BannerTone.WARNING, tx("Cambios temporalmente pausados", "Changes temporarily paused"),
                flags.message(OpsFlag.FINANCIAL_WRITES, language) ?: tx("Podés ver tu información; guardar cambios está en pausa por mantenimiento.", "You can see your information; saving changes is paused for maintenance."))
        }
        when (health?.status) {
            "degraded" -> Box(Modifier.widthIn(max = ContentMaxWidth)) { StatusBanner(BannerTone.WARNING, tx("Servicio con demoras", "Service is slow"), tx("Algunas funciones pueden tardar más de lo normal.", "Some features may take longer than usual.")) }
            "major_outage" -> Box(Modifier.widthIn(max = ContentMaxWidth)) { StatusBanner(BannerTone.ERROR, tx("Servicio interrumpido", "Service interrupted"), tx("Estamos trabajando para restablecer DINCR. Tus datos están a salvo.", "We’re working to restore DINCR. Your data is safe.")) }
        }
        release?.takeIf { it.isOptional && !model.optionalUpdateDismissed }?.let { policy ->
            Box(Modifier.widthIn(max = ContentMaxWidth)) {
                Column {
                    StatusBanner(BannerTone.INFO, tx("Hay una versión nueva", "A new version is available"),
                        (if (language == AppLanguage.SPANISH) policy.messageEs else policy.messageEn) ?: tx("Actualizá cuando puedas.", "Update when you can."))
                    TextButton({ model.dismissOptionalUpdate() }) { Text(tx("Ahora no", "Not now"), color = Dincr.colors.tint) }
                }
            }
        }
    }
}
