package com.dincr.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AuthException
import com.dincr.data.MoneyFormat
import com.dincr.data.ProfileSetup
import com.dincr.design.Dincr
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.ErrorState
import com.dincr.design.generated.DincrRadius
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import kotlinx.coroutines.launch

/** PARITY A9 — four steps, saved once. System Back goes to the previous step. */
@Composable
fun ProfileSetupScreen(model: AppModel) {
    val profile by model.profile.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    var step by rememberSaveable { mutableStateOf(0) }
    var name by rememberSaveable { mutableStateOf(profile?.firstName.orEmpty()) }
    var goal by rememberSaveable { mutableStateOf("") }
    var currency by rememberSaveable { mutableStateOf("CRC") }
    var alsoOther by rememberSaveable { mutableStateOf(false) }
    var separators by rememberSaveable { mutableStateOf(MoneyFormat.Separators.DOT_COMMA) }
    var placement by rememberSaveable { mutableStateOf(MoneyFormat.Placement.BEFORE) }
    var banks by rememberSaveable { mutableStateOf(setOf<String>()) }
    var saving by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val total = 4
    val canContinue = when (step) { 0 -> name.isNotBlank(); 1 -> goal.isNotEmpty(); else -> true }

    BackHandler(enabled = step > 0 && !saving) { step -= 1 }

    Column(Modifier.fillMaxSize().safeDrawingPadding().imePadding()) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(DincrSpacing.s4), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s6)) {
            LinearProgressIndicator(progress = { (step + 1f) / total }, modifier = Modifier.fillMaxWidth(), color = Dincr.colors.tint, trackColor = Dincr.colors.surface2)
            when (step) {
                0 -> Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
                    Header(tx("¿Cómo querés que te llamemos?", "What should we call you?"), tx("Podés cambiarlo después.", "You can change it later."))
                    OutlinedTextField(name, { name = it }, label = { Text(tx("Tu nombre", "Your name")) }, singleLine = true,
                        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words, imeAction = ImeAction.Next),
                        modifier = Modifier.fillMaxWidth())
                }
                1 -> Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
                    Header(tx("¿Qué querés lograr primero?", "What do you want to achieve first?"), tx("Nos ayuda a mostrarte primero lo que más te sirve.", "It helps us show you what matters most first."))
                    val goals = listOf(
                        "debt" to tx("Salir de deudas", "Pay off debt"), "save" to tx("Ahorrar para algo importante", "Save for something important"),
                        "partner" to tx("Organizar dinero en pareja o familia", "Manage money with a partner or family"),
                        "life_change" to tx("Prepararme para un cambio importante", "Prepare for a big change"),
                        "control" to tx("Tomar control de mis finanzas", "Take control of my finances"), "explore" to tx("Todavía no estoy seguro", "I’m not sure yet"),
                    )
                    Column(Modifier.background(Dincr.colors.surface, RoundedCornerShape(DincrRadius.lg)).padding(horizontal = DincrSpacing.s2)) {
                        goals.forEachIndexed { index, (id, label) ->
                            Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).selectable(goal == id, role = Role.RadioButton) { goal = id }.padding(horizontal = DincrSpacing.s2), verticalAlignment = Alignment.CenterVertically) {
                                RadioButton(goal == id, onClick = null)
                                Text(label, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text, modifier = Modifier.padding(start = DincrSpacing.s3))
                            }
                            if (index < goals.lastIndex) HorizontalDivider(color = Dincr.colors.line)
                        }
                    }
                }
                2 -> Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
                    Header(tx("¿Cómo querés ver tu dinero?", "How do you want to see your money?"), tx("No convertimos montos sin avisarte.", "We never convert amounts without telling you."))
                    Column(Modifier.background(Dincr.colors.surface, RoundedCornerShape(DincrRadius.lg)).padding(DincrSpacing.s4), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
                        Label(tx("Moneda principal", "Main currency"))
                        Segmented(listOf("CRC" to "CRC · Colón", "USD" to tx("USD · Dólar", "USD · Dollar")), currency) { currency = it }
                        Row(Modifier.fillMaxWidth().toggleable(alsoOther, role = Role.Switch) { alsoOther = it }.heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically) {
                            val other = if (currency == "CRC") "USD" else "CRC"
                            Text(tx("También uso $other", "I also use $other"), Modifier.weight(1f), color = Dincr.colors.text)
                            Switch(alsoOther, onCheckedChange = null)
                        }
                        Label(tx("Formato de números", "Number format"))
                        Segmented(listOf(MoneyFormat.Separators.DOT_COMMA to "123.456,78", MoneyFormat.Separators.COMMA_DOT to "123,456.78"), separators) { separators = it }
                        Label(tx("Posición del símbolo", "Symbol position"))
                        Segmented(listOf(MoneyFormat.Placement.BEFORE to tx("Antes", "Before"), MoneyFormat.Placement.AFTER to tx("Después", "After")), placement) { placement = it }
                        Row(Modifier.fillMaxWidth().semantics(mergeDescendants = true) {}, horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(tx("Así se verá", "Preview"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.textMuted)
                            Text(MoneyFormat(currency, separators, placement).format(BigDecimal("123456.78")), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                        }
                    }
                }
                else -> Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
                    Header(tx("¿Qué bancos usás?", "Which banks do you use?"), tx("Esto no conecta ninguna cuenta ni comparte contraseñas. DINCR nunca te pedirá la contraseña de tu banco.", "This doesn’t connect any account or share passwords. DINCR will never ask for your bank password."))
                    val list = listOf("bac" to "BAC Credomatic", "bn" to "Banco Nacional", "bcr" to "Banco de Costa Rica", "popular" to "Banco Popular",
                        "davivienda" to "Davivienda", "scotiabank" to tx("DAVIbank (antes Scotiabank)", "DAVIbank (formerly Scotiabank)"), "promerica" to "Promerica", "multimoney" to "MultiMoney")
                    Column(Modifier.background(Dincr.colors.surface, RoundedCornerShape(DincrRadius.lg)).padding(horizontal = DincrSpacing.s2)) {
                        list.forEachIndexed { index, (id, label) ->
                            val checked = id in banks
                            Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).toggleable(checked, role = Role.Checkbox) { banks = if (it) banks + id else banks - id }, verticalAlignment = Alignment.CenterVertically) {
                                Checkbox(checked, onCheckedChange = null)
                                Text(label, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text, modifier = Modifier.padding(start = DincrSpacing.s2))
                            }
                            if (index < list.lastIndex) HorizontalDivider(color = Dincr.colors.line)
                        }
                    }
                }
            }
            error?.let { ErrorState(it) }
        }
        Column(Modifier.fillMaxWidth().padding(DincrSpacing.s4), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            DincrPrimaryButton(
                text = if (step == total - 1) tx("Entrar a DINCR", "Enter DINCR") else tx("Continuar", "Continue"),
                enabled = canContinue, loading = saving, modifier = Modifier.widthIn(max = 600.dp).testTag("setup.continue"),
                onClick = {
                    if (step < total - 1) step += 1
                    else if (!saving) {
                        saving = true; error = null // set before launching: one submit, however fast the taps
                        scope.launch {
                            val currencies = listOf(currency) + if (alsoOther) listOf(if (currency == "CRC") "USD" else "CRC") else emptyList()
                            model.load(tx("No pudimos guardar tus preferencias. Intentá nuevamente.", "We couldn’t save your preferences. Please try again.")) {
                                model.service.completeProfileSetup(ProfileSetup(name.trim(), goal, currency, currencies, separators.wire, placement.wire, banks.sorted()))
                            }.onSuccess { model.apply(it) }.onFailure { if (it !is AuthException.SignedOut) error = it.message }
                            saving = false
                        }
                    }
                },
            )
            Text(if (step == total - 1) tx("Estas preferencias quedarán guardadas en tu cuenta.", "These preferences will be saved to your account.") else tx("Guardamos todo al terminar los cuatro pasos.", "We save everything when you finish the four steps."),
                style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)
        }
    }
}

@Composable
private fun Header(title: String, detail: String) {
    Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
        Text(title, style = MaterialTheme.typography.headlineSmall, color = Dincr.colors.text, modifier = Modifier.semantics { heading() })
        Text(detail, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text2)
    }
}

@Composable
private fun Label(text: String) = Text(text, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)

@Composable
private fun <T> Segmented(options: List<Pair<T, String>>, selected: T, onSelect: (T) -> Unit) {
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
        options.forEachIndexed { index, (value, label) ->
            SegmentedButton(selected == value, { onSelect(value) }, SegmentedButtonDefaults.itemShape(index, options.size)) { Text(label) }
        }
    }
}
