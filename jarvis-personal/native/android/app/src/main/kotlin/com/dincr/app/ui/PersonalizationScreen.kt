package com.dincr.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.ShoppingCart
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AppLanguage
import com.dincr.data.AppearancePolicy
import com.dincr.data.AppearancePrefs
import com.dincr.data.AuthException
import com.dincr.data.MoneyFormat
import com.dincr.data.MovementKind
import com.dincr.data.generated.AppearanceCatalog
import com.dincr.data.generated.AppearanceOption
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.ErrorState
import com.dincr.design.MoneyRow
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrAppearanceTokens
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import kotlinx.coroutines.launch

/**
 * APP-1 — Personalización (Owner only in phase 1). Each choice is drawn at once across the whole
 * app as a draft ([com.dincr.app.AppearanceController.preview]); "Guardar" stores it on the
 * account, so it follows the Owner to its other devices; leaving without saving goes back to the
 * saved look. The preview card uses invented figures, never the account's. iOS: MAC REQUIRED.
 */
@Composable
fun PersonalizationScreen(model: AppModel, nav: Navigator) {
    val profile by model.profile.collectAsStateWithLifecycle()
    if (!AppearancePolicy.isPersonalizable(profile)) {
        LaunchedEffect(Unit) { nav.back() }
        return
    }
    val loaded = rememberLoad(model, fallback = tx("No pudimos cargar tu apariencia.", "We couldn’t load your appearance.")) { model.appearance.load() }
    val leave = { model.appearance.preview(null); nav.back() }
    // Any way out of the screen (back, a tab, sign-out) ends the preview.
    DisposableEffect(Unit) { onDispose { model.appearance.preview(null) } }
    // The controller's state, not the first read: after a save or a reset the editor starts from it.
    val server by model.appearance.state.collectAsStateWithLifecycle()
    DetailScaffold(tx("Personalización", "Personalization"), onBack = leave) {
        LoadContent(loaded, rows = 3) { first -> (server ?: first).let { AppearanceEditor(model, it.preferences, it.stored) } }
    }
}

@Composable
private fun AppearanceEditor(model: AppModel, saved: AppearancePrefs, stored: Boolean) {
    var draft by remember(saved) { mutableStateOf(saved) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var confirmReset by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val dirty = draft != saved
    LaunchedEffect(draft) { model.appearance.preview(if (dirty) draft else null) }
    fun choose(key: String, id: String) { draft = draft.with(key, id); error = null }
    fun run(fallback: String, block: suspend () -> Unit) {
        if (busy) return
        busy = true; error = null
        scope.launch {
            model.load(fallback) { block() }.onFailure { if (it !is AuthException.SignedOut) error = it.message }
            busy = false
        }
    }

    Text(tx("Elegí cómo se ve DINCR en tu cuenta. Cada cambio se ve al instante; se guarda en tu cuenta y se aplica en tus dispositivos al iniciar sesión.",
        "Choose how DINCR looks on your account. Each change shows at once; it is saved to your account and applies on your devices when you sign in."),
        style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
    AppearancePreview()

    OptionChips(AppearanceCatalog.option("theme"), draft, ::choose)
    Section(tx("Paleta", "Palette")) { PaletteChoices(draft, ::choose) }
    Section(tx("Color de acento", "Accent color")) { AccentChoices(draft, ::choose) }
    OptionChips(AppearanceCatalog.option("text_size"), draft, ::choose)
    OptionChips(AppearanceCatalog.option("typeface"), draft, ::choose)
    OptionChips(AppearanceCatalog.option("density"), draft, ::choose)
    OptionChips(AppearanceCatalog.option("surfaces"), draft, ::choose)

    error?.let { ErrorState(it) }
    Box(Modifier.testTag("appearance.save")) {
        DincrPrimaryButton(if (dirty) tx("Guardar cambios", "Save changes") else tx("Guardado", "Saved"),
            onClick = { run(tx("No pudimos guardar tu apariencia.", "We couldn’t save your appearance.")) { model.appearance.save(draft) } },
            enabled = dirty, loading = busy && dirty)
    }
    if (dirty) TextButton({ draft = saved; error = null }, Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("appearance.discard"), enabled = !busy) {
        Text(tx("Descartar cambios", "Discard changes"), color = Dincr.colors.tint, style = MaterialTheme.typography.titleMedium)
    }
    if (stored || draft != AppearancePrefs.OWNER_DEFAULT) {
        TextButton({ confirmReset = true }, Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("appearance.reset"), enabled = !busy) {
            Text(tx("Restaurar valores predeterminados", "Restore defaults"), color = Dincr.colors.tint, style = MaterialTheme.typography.titleMedium)
        }
    }
    Caption(tx("Experimento visual, solo para la cuenta Owner. No cambia tus datos ni tus cálculos.",
        "Visual experiment, for the Owner account only. It never changes your data or calculations."))
    Spacer(Modifier.heightIn(min = DincrSpacing.s4))
    if (confirmReset) ConfirmDialog(
        tx("¿Restaurar la apariencia predeterminada?", "Restore the default appearance?"),
        tx("Vuelve a Océano, acento Cian, texto estándar, densidad cómoda y superficies con contorno, en todos tus dispositivos.",
            "Goes back to Ocean, Cyan accent, standard text, comfortable density and outlined surfaces, on all your devices."),
        tx("Restaurar", "Restore"), destructive = false, busy = busy,
        onDismiss = { confirmReset = false },
        onConfirm = {
            confirmReset = false
            run(tx("No pudimos restaurar la apariencia.", "We couldn’t restore the appearance.")) { model.appearance.reset() }
        },
    )
}

private fun label(value: com.dincr.data.generated.AppearanceOptionValue) = AppLanguage.current().pick(value.es, value.en)

private val AppearanceOption.title: String get() = when (key) {
    "theme" -> tx("Tema", "Theme")
    "text_size" -> tx("Tamaño del texto", "Text size")
    "typeface" -> tx("Tipografía", "Typeface")
    "density" -> tx("Densidad", "Density")
    "surfaces" -> tx("Tarjetas y superficies", "Cards and surfaces")
    else -> key
}

@Composable
private fun OptionChips(option: AppearanceOption, draft: AppearancePrefs, choose: (String, String) -> Unit) {
    Section(option.title) {
        Box(Modifier.testTag("appearance.${option.key}")) {
            ChoiceChips(option.values.map { it.id to label(it) }, draft.id(option.key), onSelect = { choose(option.key, it) })
        }
    }
}

/** Is the scene drawn now dark? (The draft's theme, or the system's when it follows it.) */
@Composable
private fun drawingDark() = Dincr.colors.bg.luminance() < 0.5f

@Composable
private fun PaletteChoices(draft: AppearancePrefs, choose: (String, String) -> Unit) {
    val dark = drawingDark()
    FlowRow(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s3), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
        AppearanceCatalog.option("palette").values.forEach { value ->
            val n = DincrAppearanceTokens.palettes.getValue(value.id).pick(dark)
            val selected = draft.palette == value.id
            Column(
                Modifier.width(132.dp).testTag("appearance.palette.${value.id}")
                    .selectable(selected, role = Role.RadioButton) { choose("palette", value.id) },
                verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1),
            ) {
                Box(
                    Modifier.fillMaxWidth().heightIn(min = 72.dp).background(n.bg, RoundedCornerShape(Dincr.look.controlRadius))
                        .border(if (selected) 2.dp else 1.dp, if (selected) Dincr.colors.tint else Dincr.colors.fieldBorder, RoundedCornerShape(Dincr.look.controlRadius))
                        .padding(DincrSpacing.s2),
                ) {
                    Column(Modifier.fillMaxWidth().background(n.surface, RoundedCornerShape(8.dp)).padding(DincrSpacing.s2), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Box(Modifier.width(56.dp).heightIn(min = 6.dp).background(n.text, CircleShape))
                        Box(Modifier.width(36.dp).heightIn(min = 6.dp).background(n.textMuted, CircleShape))
                        Box(Modifier.width(72.dp).heightIn(min = 6.dp).background(n.surface2, CircleShape))
                    }
                    if (selected) SelectedMark(Modifier.align(Alignment.TopEnd))
                }
                Text(label(value), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text)
            }
        }
    }
}

@Composable
private fun AccentChoices(draft: AppearancePrefs, choose: (String, String) -> Unit) {
    val dark = drawingDark()
    FlowRow(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s4), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
        AppearanceCatalog.option("accent").values.forEach { value ->
            val a = DincrAppearanceTokens.accents.getValue(value.id).pick(dark)
            val selected = draft.accent == value.id
            Column(
                Modifier.widthIn(min = 64.dp).testTag("appearance.accent.${value.id}")
                    .selectable(selected, role = Role.RadioButton) { choose("accent", value.id) }.padding(vertical = DincrSpacing.s1),
                horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1),
            ) {
                Box(
                    Modifier.size(44.dp).background(a.tint, CircleShape)
                        .border(if (selected) 3.dp else 0.dp, if (selected) Dincr.colors.text else Color.Transparent, CircleShape),
                    contentAlignment = Alignment.Center,
                ) { if (selected) Icon(Icons.Rounded.Check, contentDescription = null, tint = a.onTint) }
                Text(label(value), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text, textAlign = TextAlign.Center)
            }
        }
    }
}

@Composable
private fun SelectedMark(modifier: Modifier) {
    Box(modifier.size(22.dp).background(Dincr.colors.tint, CircleShape), contentAlignment = Alignment.Center) {
        Icon(Icons.Rounded.Check, contentDescription = null, tint = Dincr.colors.onTint, modifier = Modifier.size(16.dp))
    }
}

/**
 * What the choice looks like, drawn with the live theme: a key figure, two facts, a money row and
 * the primary action. Invented figures (never the account's); not interactive.
 */
@Composable
private fun AppearancePreview() {
    val description = tx("Vista previa con datos de ejemplo", "Preview with sample data")
    Column(Modifier.testTag("appearance.preview").clearAndSetSemantics { contentDescription = description }, verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
        SectionTitle(tx("Vista previa", "Preview"))
        DincrCard {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                    Text(tx("Podés gastar con tranquilidad", "Safe to spend"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
                    MoneyText(BigDecimal("482500"), style = MaterialTheme.typography.displaySmall)
                    Caption(tx("Datos de ejemplo", "Sample data"))
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
                    Column {
                        Caption(tx("Ingresos", "Income"))
                        MoneyText(BigDecimal("1250000"), sign = MoneyFormat.Sign.INCOME, style = MaterialTheme.typography.labelLarge)
                    }
                    Column {
                        Caption(tx("Gastos", "Expenses"))
                        MoneyText(BigDecimal("767500"), sign = MoneyFormat.Sign.EXPENSE, style = MaterialTheme.typography.labelLarge)
                    }
                }
                MoneyRow(tx("Supermercado", "Groceries"), tx("Hoy · Alimentación", "Today · Food"), BigDecimal("18450"), MovementKind.EXPENSE, Icons.Rounded.ShoppingCart, readOnly = false)
                Box(Modifier.fillMaxWidth().heightIn(min = 52.dp).background(Dincr.colors.tint, RoundedCornerShape(Dincr.look.controlRadius)), contentAlignment = Alignment.Center) {
                    Text(tx("Registrar movimiento", "Record a movement"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.onTint)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                    Text(tx("Seleccionado", "Selected"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.onTintContainer,
                        modifier = Modifier.background(Dincr.colors.tintContainer, CircleShape).padding(horizontal = DincrSpacing.s3, vertical = DincrSpacing.s1))
                    Text(tx("Filtro", "Filter"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2,
                        modifier = Modifier.background(Dincr.colors.surface2, CircleShape).padding(horizontal = DincrSpacing.s3, vertical = DincrSpacing.s1))
                }
            }
        }
    }
}
