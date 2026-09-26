package com.dincr.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AccountCircle
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.BarChart
import androidx.compose.material.icons.rounded.ReceiptLong
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
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.Appearance
import com.dincr.app.tx
import com.dincr.design.Dincr

enum class Destination(val icon: ImageVector) {
    HOME(Icons.Rounded.BarChart), MOVEMENTS(Icons.Rounded.ReceiptLong), PLAN(Icons.Rounded.TrackChanges),
    ADVISOR(Icons.Rounded.AutoAwesome), PROFILE(Icons.Rounded.AccountCircle);

    val label: String get() = when (this) {
        HOME -> tx("Hoy", "Today"); MOVEMENTS -> tx("Movimientos", "Transactions"); PLAN -> tx("Plan", "Plan")
        ADVISOR -> "DINCR"; PROFILE -> tx("Perfil", "Profile")
    }
}

/** PARITY B1 — five destinations; bar on compact width, rail from 600 dp (Material guidance). */
@Composable
fun MainScaffold(model: AppModel, appearance: Appearance, onAppearance: (Appearance) -> Unit) {
    var current by rememberSaveable { mutableStateOf(Destination.HOME) }
    val snackbar = remember { SnackbarHostState() }
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val expanded = maxWidth >= 600.dp
        Scaffold(
            containerColor = Dincr.colors.bg,
            snackbarHost = { SnackbarHost(snackbar) },
            bottomBar = {
                if (!expanded) NavigationBar(containerColor = Dincr.colors.surface) {
                    Destination.entries.forEach { d ->
                        NavigationBarItem(selected = current == d, onClick = { current = d }, icon = { Icon(d.icon, contentDescription = null) }, label = { Text(d.label, maxLines = 1) })
                    }
                }
            },
        ) { padding ->
            Row(Modifier.fillMaxSize()) {
                if (expanded) NavigationRail(containerColor = Dincr.colors.surface) {
                    Destination.entries.forEach { d ->
                        NavigationRailItem(selected = current == d, onClick = { current = d }, icon = { Icon(d.icon, contentDescription = null) }, label = { Text(d.label) })
                    }
                }
                Box(Modifier.weight(1f)) {
                    when (current) {
                        Destination.HOME -> HomeScreen(model, padding) { current = Destination.MOVEMENTS }
                        Destination.MOVEMENTS -> MovementsScreen(model, padding, snackbar)
                        Destination.PLAN -> PlaceholderScreen(Destination.PLAN.label, "E1–E12", padding)
                        Destination.ADVISOR -> PlaceholderScreen("DINCR", "F1–F10", padding)
                        Destination.PROFILE -> ProfileScreen(model, padding, appearance, onAppearance)
                    }
                }
            }
        }
    }
}
