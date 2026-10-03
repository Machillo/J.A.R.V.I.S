package com.dincr.app.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Chat
import androidx.compose.material.icons.rounded.AccountBalanceWallet
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.Insights
import androidx.compose.material.icons.rounded.PieChart
import androidx.compose.material.icons.rounded.Psychology
import androidx.compose.material.icons.rounded.QueryStats
import androidx.compose.material.icons.rounded.RequestQuote
import androidx.compose.material.icons.rounded.Timeline
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.Jarvis
import com.dincr.design.DincrCard
import com.dincr.design.EmptyState

/**
 * JARVIS: the Owner's personal space inside DINCR, opened from the Profile hub. Only the server's
 * role opens it ([Jarvis.isAvailable]), and the backend still decides every JARVIS request. The chat
 * is ported (J1, [JarvisChatScreen]); a section not ported yet says so instead of showing sample
 * content (iOS: `JarvisViews.swift`).
 */
@Composable
fun JarvisHubScreen(model: AppModel, nav: Navigator) = OwnerOnly(model, nav) {
    DetailScaffold("JARVIS", onBack = nav::back) {
        Caption(tx("Tus funciones personales vuelven a DINCR por etapas.", "Your personal features are coming back to DINCR step by step."))
        DincrCard {
            Column {
                Jarvis.Section.entries.forEach { section ->
                    NavRow(section.icon, section.title, if (section.isAvailable) section.summary else tx("En restauración", "Being restored")) {
                        nav.open("jarvis/${section.wire}")
                    }
                }
            }
        }
    }
}

/** A JARVIS section: a ported one (chat, agenda, analysis, money control), or a "being restored" screen that never shows sample data. */
@Composable
fun JarvisSectionScreen(model: AppModel, nav: Navigator, wire: String?) = OwnerOnly(model, nav) {
    val section = Jarvis.Section.from(wire)
    if (section == null) {
        LaunchedEffect(Unit) { nav.back() }
        return@OwnerOnly
    }
    if (section == Jarvis.Section.CHAT) {
        JarvisChatScreen(model, nav)
        return@OwnerOnly
    }
    if (section == Jarvis.Section.CALENDAR) {
        JarvisAgendaScreen(model, nav)
        return@OwnerOnly
    }
    if (section == Jarvis.Section.ANALYSIS) {
        JarvisAnalysisScreen(model, nav)
        return@OwnerOnly
    }
    if (section == Jarvis.Section.MONEY_CONTROL) {
        JarvisReceivablesScreen(model, nav)
        return@OwnerOnly
    }
    DetailScaffold(section.title, onBack = nav::back) {
        EmptyState(section.icon, tx("En restauración", "Being restored"),
            tx("${section.summary}. Esta función todavía no está disponible en la app.", "${section.summary}. This feature isn’t available in the app yet."))
    }
}

/**
 * Renders JARVIS only for the Owner. The routes are reachable only from the Owner's Profile hub;
 * this also leaves a screen kept on the back stack if the identity stops being the Owner.
 */
@Composable
private fun OwnerOnly(model: AppModel, nav: Navigator, content: @Composable () -> Unit) {
    val profile by model.profile.collectAsStateWithLifecycle()
    if (Jarvis.isAvailable(profile)) content() else LaunchedEffect(Unit) { nav.back() }
}

private val Jarvis.Section.title: String get() = when (this) {
    Jarvis.Section.CHAT -> tx("Chat", "Chat")
    Jarvis.Section.MEMORY -> tx("Memoria", "Memory")
    Jarvis.Section.CALENDAR -> tx("Agenda", "Calendar")
    Jarvis.Section.STRATEGY -> tx("Estrategia personal", "Personal strategy")
    Jarvis.Section.MONEY -> tx("Mi dinero", "My money")
    Jarvis.Section.MONEY_CONTROL -> tx("Control de dinero", "Money control")
    Jarvis.Section.WEALTH -> tx("Patrimonio", "Wealth")
    Jarvis.Section.RECORDS -> tx("Registros", "Records")
    Jarvis.Section.ANALYSIS -> tx("Análisis financiero", "Financial analysis")
}

private val Jarvis.Section.summary: String get() = when (this) {
    Jarvis.Section.CHAT -> tx("Conversar con JARVIS y registrar con tu confirmación", "Talk to JARVIS and record with your confirmation")
    Jarvis.Section.MEMORY -> tx("Lo que JARVIS recuerda de vos", "What JARVIS remembers about you")
    Jarvis.Section.CALENDAR -> tx("Tus eventos y recordatorios", "Your events and reminders")
    Jarvis.Section.STRATEGY -> tx("Tu estrategia con tus ingresos reales", "Your strategy with your real income")
    Jarvis.Section.MONEY -> tx("Tu ciclo, tus cuentas y los pagos de tus deudas", "Your cycle, your accounts and your debt payments")
    Jarvis.Section.MONEY_CONTROL -> tx("Tus cuentas por cobrar: quién te debe y cuánto", "Money owed to you: who owes you and how much")
    Jarvis.Section.WEALTH -> tx("Patrimonio, inversiones y negocios", "Net worth, investments and businesses")
    Jarvis.Section.RECORDS -> tx("Importar, conciliar y tu línea de tiempo", "Import, reconcile and your timeline")
    Jarvis.Section.ANALYSIS -> tx("Gastos, flujo, patrimonio y salud financiera", "Spending, cash flow, net worth and financial health")
}

private val Jarvis.Section.icon: ImageVector get() = when (this) {
    Jarvis.Section.CHAT -> Icons.AutoMirrored.Rounded.Chat
    Jarvis.Section.MEMORY -> Icons.Rounded.Psychology
    Jarvis.Section.CALENDAR -> Icons.Rounded.CalendarMonth
    Jarvis.Section.STRATEGY -> Icons.Rounded.Insights
    Jarvis.Section.MONEY -> Icons.Rounded.AccountBalanceWallet
    Jarvis.Section.MONEY_CONTROL -> Icons.Rounded.RequestQuote
    Jarvis.Section.WEALTH -> Icons.Rounded.PieChart
    Jarvis.Section.RECORDS -> Icons.Rounded.Timeline
    Jarvis.Section.ANALYSIS -> Icons.Rounded.QueryStats
}
