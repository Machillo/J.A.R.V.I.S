package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AuthException
import com.dincr.data.CorrectionInput
import com.dincr.data.FinancialReading
import com.dincr.data.Retirement
import com.dincr.data.RetirementReading
import com.dincr.data.RetirementUpdate
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.coroutines.launch

/**
 * RT-1 — Plan → Retiro (VIP and the Owner): what you have put aside for retirement (ROP and a voluntary
 * pension, declared here), read in simple words ([RetirementReading]). Saving is your explicit action.
 * iOS twin: `RetirementView.swift`.
 */
@Composable
fun RetirementScreen(model: AppModel, nav: Navigator) {
    val data = rememberLoad(model) {
        // Optional: without a normal month there is no age comparison.
        val income = runCatching { FinancialReading.normal(model.api.financialAnalysis())?.income }.getOrNull()
        model.api.retirement() to income
    }
    DetailScaffold(tx("Retiro", "Retirement"), nav::back) {
        LoadContent(data) { (retirement, income) -> RetirementContent(model, retirement, income) { data.reload() } }
    }
}

@Composable
private fun RetirementContent(model: AppModel, retirement: Retirement, income: BigDecimal?, saved: () -> Unit) {
    val format = Dincr.money
    val config = retirement.config
    val lines = RetirementReading.lines(config, income, LocalDate.now().year, format)
    var rop by remember(config) { mutableStateOf(config.ropBalance?.let(format::inputText).orEmpty()) }
    var voluntary by remember(config) { mutableStateOf(config.voluntaryBalance?.let(format::inputText).orEmpty()) }
    var birth by remember(config) { mutableStateOf(config.birthYear?.toString().orEmpty()) }
    var age by remember(config) { mutableStateOf(config.retireAge?.toString().orEmpty()) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    DincrCard {
        Column(Modifier.fillMaxWidth().testTag("retirement.reading"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            if (lines.isEmpty()) Text(tx("Todavía no registraste tu ahorro para el retiro.", "You haven’t recorded your retirement savings yet."), color = Dincr.colors.text)
            lines.forEachIndexed { index, line ->
                Text(line, style = if (index == 0) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyMedium,
                    color = if (index == 0) Dincr.colors.text else Dincr.colors.text2)
            }
        }
    }
    Section(tx("Tus datos", "Your details")) {
        MoneyField(tx("Saldo del ROP", "ROP balance"), rop, { rop = it }, modifier = Modifier.testTag("retirement.rop"))
        MoneyField(tx("Pensión voluntaria (si tenés)", "Voluntary pension (if any)"), voluntary, { voluntary = it }, modifier = Modifier.testTag("retirement.voluntary"))
        OutlinedTextField(birth, { birth = it }, label = { Text(tx("Año de nacimiento", "Year of birth")) }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth().testTag("retirement.birth"))
        OutlinedTextField(age, { age = it }, label = { Text(tx("Edad de retiro (65 si no sabés)", "Retirement age (65 if unsure)")) }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth().testTag("retirement.age"))
        Caption(tx("El saldo del ROP aparece en el estado de cuenta de tu operadora de pensiones.", "Your ROP balance is on your pension fund statement."))
        error?.let { com.dincr.design.ErrorState(it) }
        DincrPrimaryButton(tx("Guardar", "Save"), loading = saving, modifier = Modifier.testTag("retirement.save"), onClick = {
            val ropValue = rop.takeIf { it.isNotBlank() }?.let { CorrectionInput.amount(it, format.separators) }
            val voluntaryValue = voluntary.takeIf { it.isNotBlank() }?.let { CorrectionInput.amount(it, format.separators) }
            val birthValue = birth.takeIf { it.isNotBlank() }?.trim()?.toIntOrNull()
            val ageValue = age.takeIf { it.isNotBlank() }?.trim()?.toIntOrNull()
            if ((rop.isNotBlank() && ropValue == null) || (voluntary.isNotBlank() && voluntaryValue == null) ||
                (birth.isNotBlank() && birthValue == null) || (age.isNotBlank() && ageValue == null)) {
                error = tx("Revisá los montos, el año y la edad.", "Check the amounts, the year and the age."); return@DincrPrimaryButton
            }
            saving = true; error = null
            scope.launch {
                model.load(tx("No pudimos guardar.", "We couldn’t save.")) { model.api.updateRetirement(RetirementUpdate(ropValue, voluntaryValue, birthValue, ageValue)) }
                    .onSuccess { saved() }
                    .onFailure { if (it !is AuthException.SignedOut) error = it.message }
                saving = false
            }
        })
    }
}
