package com.dincr.app.ui

import android.app.Activity
import android.content.Context
import android.provider.Settings
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.tween
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.CreditCard
import androidx.compose.material.icons.rounded.Flag
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.ShoppingCart
import androidx.compose.material.icons.rounded.SouthWest
import androidx.compose.material3.Icon
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
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.design.generated.DincrSpacing
import kotlinx.coroutines.launch

private val StoryColor = Color(0xFF2A2E6E)
private val StoryControl = Color(0xFF3D4290)
private val StoryText2 = Color(0xFFD9DBF5)

private enum class WelcomeArt { TOGETHER, MONTH, STEPS, SAFE }
private class WelcomePage(val title: String, val message: String, val art: WelcomeArt)

/**
 * The first profile setup, after the story the first time. Per account and device: only its own mark
 * is stored. On fixture data it shows only when a test asks, so other flows go straight to the setup.
 */
@Composable
fun WelcomeThenProfileSetup(model: AppModel) {
    val context = LocalContext.current
    val profile by model.profile.collectAsStateWithLifecycle()
    val prefs = remember { context.getSharedPreferences("dincr_welcome", Context.MODE_PRIVATE) }
    val key = "seen:${profile?.id ?: 0}"
    val asked = (context as? Activity)?.intent?.getBooleanExtra("dincrWelcomeStory", false) == true
    var finished by remember { mutableStateOf(false) }
    if (!finished && (!model.isFixtures || asked) && !prefs.getBoolean(key, false)) {
        WelcomeStoryScreen {
            prefs.edit().putBoolean(key, true).apply()
            finished = true
        }
    } else {
        ProfileSetupScreen(model)
    }
}

/**
 * What DINCR is and what it's for, right before the first profile setup. Only words and drawings: it
 * asks nothing. iOS twin: `WelcomeStoryView`.
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun WelcomeStoryScreen(finish: () -> Unit) {
    val pages = listOf(
        WelcomePage(tx("Tu dinero, con propósito", "Your money, with purpose"), tx("DINCR reúne tus ingresos, gastos, deudas y metas en un solo lugar.", "DINCR brings your income, expenses, debts and goals into one place."), WelcomeArt.TOGETHER),
        WelcomePage(tx("Sabé dónde estás", "Know where you stand"), tx("Mirá de un vistazo cuánto entra, cuánto sale y cómo va tu mes.", "See at a glance what comes in, what goes out and how your month is going."), WelcomeArt.MONTH),
        WelcomePage(tx("Sabé qué sigue", "Know what comes next"), tx("Con tus datos, DINCR te muestra qué atender primero, paso a paso.", "With your data, DINCR shows you what to take care of first, step by step."), WelcomeArt.STEPS),
        WelcomePage(tx("Tus datos, tus decisiones", "Your data, your decisions"), tx("Vos decidís qué registrar. DINCR nunca te pide la contraseña de tu banco.", "You decide what to record. DINCR never asks for your bank password."), WelcomeArt.SAFE),
    )
    val pager = rememberPagerState { pages.size }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val moves = remember { Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) > 0f }
    Box(Modifier.fillMaxSize().background(StoryColor).testTag("welcome.story"), contentAlignment = Alignment.TopCenter) {
        Column(Modifier.widthIn(max = ContentMaxWidth).fillMaxSize().safeDrawingPadding().padding(DincrSpacing.s4), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextButton(finish, Modifier.heightIn(min = 48.dp).testTag("welcome.skip")) { Text(tx("Omitir", "Skip"), color = StoryText2, fontWeight = FontWeight.SemiBold) }
            }
            HorizontalPager(pager, Modifier.weight(1f).fillMaxWidth()) { index ->
                val page = pages[index]
                Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DincrSpacing.s6, Alignment.CenterVertically)) {
                    Box(Modifier.height(220.dp).fillMaxWidth().clearAndSetSemantics {}, contentAlignment = Alignment.Center) { Art(page.art, pager.currentPage == index, moves) }
                    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                        Text(page.title, style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.Bold), color = Color.White, textAlign = TextAlign.Center, modifier = Modifier.semantics { heading() })
                        Text(page.message, style = MaterialTheme.typography.bodyLarge, color = StoryText2, textAlign = TextAlign.Center)
                    }
                }
            }
            val stepLabel = tx("Paso ${pager.currentPage + 1} de ${pages.size}", "Step ${pager.currentPage + 1} of ${pages.size}")
            Row(Modifier.fillMaxWidth().semantics(mergeDescendants = true) { contentDescription = stepLabel }, horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s2, Alignment.CenterHorizontally)) {
                pages.indices.forEach { index ->
                    val selected = index == pager.currentPage
                    Box(Modifier.size(width = if (selected) 22.dp else 8.dp, height = 8.dp).background(if (selected) Color.White else StoryControl, CircleShape))
                }
            }
            val last = pager.currentPage == pages.lastIndex
            Box(
                Modifier.fillMaxWidth().heightIn(min = 48.dp).clip(CircleShape).background(Color.White).testTag("welcome.next")
                    .clickable(role = Role.Button) { if (last) finish() else scope.launch { pager.animateScrollToPage(pager.currentPage + 1) } },
                contentAlignment = Alignment.Center,
            ) { Text(if (last) tx("Empezar", "Get started") else tx("Continuar", "Continue"), style = MaterialTheme.typography.labelLarge, color = StoryColor) }
        }
    }
}

/** A page's drawing: its parts arrive one after another when the page is on screen. Decorative. */
@Composable
private fun Art(art: WelcomeArt, active: Boolean, moves: Boolean) {
    val shown = active || !moves
    when (art) {
        WelcomeArt.TOGETHER -> Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
            Row(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) { Tile(Icons.Rounded.SouthWest, 0, shown, moves); Tile(Icons.Rounded.ShoppingCart, 1, shown, moves) }
            Row(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) { Tile(Icons.Rounded.CreditCard, 2, shown, moves); Tile(Icons.Rounded.Flag, 3, shown, moves) }
        }
        WelcomeArt.MONTH -> Row(Modifier.height(190.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
            listOf(0.45f, 0.7f, 0.55f, 0.95f).forEachIndexed { index, part ->
                val height by animateDpAsState(if (shown) 190.dp * part else 8.dp, if (moves) tween(500, delayMillis = index * 90) else snap(), label = "bar")
                Box(Modifier.size(width = 44.dp, height = height).background(if (index == 3) Color.White else StoryControl, RoundedCornerShape(10.dp)))
            }
        }
        WelcomeArt.STEPS -> Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
            repeat(3) { index ->
                val progress = arrive(index, shown, moves)
                Row(Modifier.width(220.dp).alpha(progress), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                    Box(Modifier.size(36.dp).background(if (index == 0) Color.White else StoryControl, CircleShape), contentAlignment = Alignment.Center) {
                        Icon(Icons.Rounded.Check, null, tint = if (index == 0) StoryColor else Color.White)
                    }
                    Box(Modifier.size(width = (150 - index * 30).dp, height = 12.dp).background(StoryControl, CircleShape))
                }
            }
        }
        WelcomeArt.SAFE -> Box(contentAlignment = Alignment.Center) {
            Box(Modifier.size(190.dp).scale(arrive(1, shown, moves)).background(StoryControl.copy(alpha = 0.5f), CircleShape))
            Box(Modifier.size(130.dp).scale(arrive(0, shown, moves)).background(StoryControl, CircleShape))
            Icon(Icons.Rounded.Lock, null, tint = Color.White, modifier = Modifier.size(54.dp).scale(arrive(2, shown, moves)))
        }
    }
}

@Composable
private fun Tile(icon: ImageVector, order: Int, shown: Boolean, moves: Boolean) {
    val progress = arrive(order, shown, moves)
    Box(Modifier.size(76.dp).scale(progress).alpha(progress).background(StoryControl, RoundedCornerShape(20.dp)), contentAlignment = Alignment.Center) {
        Icon(icon, null, tint = Color.White, modifier = Modifier.size(30.dp))
    }
}

@Composable
private fun arrive(order: Int, shown: Boolean, moves: Boolean): Float {
    val value by animateFloatAsState(if (shown) 1f else 0f, if (moves) tween(450, delayMillis = order * 90) else snap(), label = "arrive")
    return value
}
