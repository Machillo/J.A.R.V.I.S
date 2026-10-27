package com.dincr.app.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
import com.dincr.data.AmountInput
import com.dincr.data.AuthException
import com.dincr.data.Debt
import com.dincr.data.DebtScenarioRequest
import com.dincr.data.DebtScenarioResult
import com.dincr.design.Dincr
import com.dincr.design.DincrPrimaryButton
import kotlinx.coroutines.launch

/**
 * What the user wants to try in Escenarios (VIP). The debt ones answer how much would be left each
 * month after essentials and debt payments (`POST /finance/strategy-vip/debt-scenario`); nothing is
 * saved. Same choices as iOS's `ScenarioChoice`.
 */
enum class ScenarioChoice {
    GENERAL, PAY_OFF, EXTRA_PAYMENT, NEW_DEBT;

    val title: String
        get() = when (this) {
            GENERAL -> tx("Cambiar ingresos o gastos", "Change income or expenses")
            PAY_OFF -> tx("Pagar una deuda completa", "Pay a debt off")
            EXTRA_PAYMENT -> tx("Abonar a una deuda", "Make an extra payment to a debt")
            NEW_DEBT -> tx("Agregar una deuda nueva", "Add a new debt")
        }
}

@Composable
fun ScenarioChoicePicker(choice: ScenarioChoice, onChoice: (ScenarioChoice) -> Unit) {
    ChoiceChips(ScenarioChoice.entries.map { it to it.title }, choice, onChoice, label = tx("¿Qué querés probar?", "What do you want to try?"))
}

/** Pay off, extra payment or new debt: the inputs for the chosen what-if, then its answer. */
@Composable
fun DebtScenarioForm(model: AppModel, choice: ScenarioChoice) {
    val format = Dincr.money
    val scope = rememberCoroutineScope()
    var debts by remember(choice) { mutableStateOf<List<Debt>?>(null) }
    var debtId by remember(choice) { mutableStateOf<Long?>(null) }
    var amount by remember(choice) { mutableStateOf("") }
    var name by remember(choice) { mutableStateOf("") }
    var payment by remember(choice) { mutableStateOf("") }
    var rate by remember(choice) { mutableStateOf("") }
    var term by remember(choice) { mutableStateOf("") }
    var result by remember(choice) { mutableStateOf<DebtScenarioResult?>(null) }
    var error by remember(choice) { mutableStateOf<String?>(null) }
    var busy by remember(choice) { mutableStateOf(false) }

    LaunchedEffect(choice) {
        if (choice != ScenarioChoice.NEW_DEBT) {
            model.load(tx("No pudimos cargar tus deudas.", "We couldn’t load your debts.")) { model.api.debts() }
                .onSuccess { list -> debts = list.filter { (it.remainingAmount?.signum() ?: 0) > 0 } }
                .onFailure { debts = emptyList(); if (it !is AuthException.SignedOut) error = it.message }
        }
    }

    fun money(text: String) = AmountInput.parse(text, format.separators)

    /** The request for the chosen what-if, or null when an input is missing or invalid (`error` says which). */
    fun request(): DebtScenarioRequest? = when (choice) {
        ScenarioChoice.PAY_OFF -> debtId?.let { DebtScenarioRequest.payOff(it) }
        ScenarioChoice.EXTRA_PAYMENT -> {
            val value = money(amount)?.takeIf { it.signum() > 0 }
            if (debtId == null || value == null) { error = tx("Revisá el monto.", "Check the amount."); null }
            else DebtScenarioRequest.extraPayment(debtId!!, value)
        }
        else -> {
            val principal = money(amount)?.takeIf { it.signum() > 0 }
            val cuota = payment.takeIf { it.isNotBlank() }?.let(::money)
            val annual = rate.takeIf { it.isNotBlank() }?.let(::money)
            val months = term.takeIf { it.isNotBlank() }?.trim()?.toIntOrNull()
            when {
                principal == null -> { error = tx("Revisá el monto.", "Check the amount."); null }
                (payment.isNotBlank() && cuota == null) || (rate.isNotBlank() && annual == null) || (term.isNotBlank() && months == null) -> {
                    error = tx("Revisá la cuota, la tasa o el plazo.", "Check the payment, rate or term."); null
                }
                cuota == null && (annual == null || months == null) -> { error = tx("Indicá la cuota, o la tasa y el plazo.", "Enter the payment, or the rate and term."); null }
                else -> DebtScenarioRequest.newDebt(name.trim().takeIf { it.isNotEmpty() }, principal, cuota, annual, months)
            }
        }
    }

    Section(choice.title) {
        Caption(when (choice) {
            ScenarioChoice.PAY_OFF -> tx("Elegí una deuda: DINCR calcula cuánto te quedaría libre cada mes si la pagás completa.", "Choose a debt: DINCR shows how much you’d have left each month if you pay it off.")
            ScenarioChoice.EXTRA_PAYMENT -> tx("Elegí una deuda y el abono: DINCR muestra qué pasa si tu banco baja la cuota o acorta el plazo.", "Choose a debt and the amount: DINCR shows what happens if your lender lowers the payment or shortens the term.")
            else -> tx("Probá una deuda nueva: DINCR calcula cuánto te quedaría libre cada mes con su cuota.", "Try a new debt: DINCR shows how much you’d have left each month with its payment.")
        })
        if (choice == ScenarioChoice.NEW_DEBT) {
            OutlinedTextField(name, { name = it }, label = { Text(tx("Nombre (opcional)", "Name (optional)")) }, singleLine = true,
                modifier = Modifier.fillMaxWidth().testTag("scenario.new.name"))
            MoneyField(tx("Monto de la deuda", "Debt amount"), amount, { amount = it }, modifier = Modifier.testTag("scenario.amount"))
            MoneyField(tx("Cuota mensual (si la sabés)", "Monthly payment (if you know it)"), payment, { payment = it },
                supporting = tx("Sin cuota, DINCR la calcula con la tasa y el plazo.", "Without a payment, DINCR computes it from the rate and term."),
                modifier = Modifier.testTag("scenario.new.payment"))
            OutlinedTextField(rate, { rate = it }, label = { Text(tx("Tasa anual (%)", "Annual rate (%)")) }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.fillMaxWidth().testTag("scenario.new.rate"))
            OutlinedTextField(term, { term = it }, label = { Text(tx("Plazo (meses)", "Term (months)")) }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth().testTag("scenario.new.term"))
        } else {
            when (val list = debts) {
                null -> Caption(tx("Cargando tus deudas…", "Loading your debts…"))
                emptyList<Debt>() -> Text(tx("No tenés deudas activas registradas.", "You have no active debts recorded."), color = Dincr.colors.text)
                else -> ChoiceChips(list.map { it.id to (it.name ?: tx("Deuda", "Debt")) }, debtId ?: -1L, { debtId = it }, label = tx("Deuda", "Debt"))
            }
            if (choice == ScenarioChoice.EXTRA_PAYMENT) {
                MoneyField(tx("¿Cuánto querés abonar?", "How much do you want to pay?"), amount, { amount = it }, modifier = Modifier.testTag("scenario.amount"))
            }
        }
        error?.let { com.dincr.design.ErrorState(it) }
        DincrPrimaryButton(tx("Calcular", "Calculate"), loading = busy, enabled = choice == ScenarioChoice.NEW_DEBT || debtId != null,
            modifier = Modifier.testTag("scenario.run"), onClick = {
                error = null
                val built = request() ?: return@DincrPrimaryButton
                busy = true
                scope.launch {
                    model.load(tx("No pudimos calcular el escenario.", "We couldn’t calculate the scenario.")) { model.api.debtScenario(built) }
                        .onSuccess { result = it }
                        .onFailure { result = null; if (it !is AuthException.SignedOut) error = it.message }
                    busy = false
                }
            })
    }
    result?.let { DebtScenarioResultSection(it) }
}

/** The answer: the money left each month now and with the change; for an extra payment, both lender
 * policies side by side. Unknown figures show "—", never ₡0. */
@Composable
private fun DebtScenarioResultSection(result: DebtScenarioResult) {
    Section(tx("Resultado", "Result")) {
        AmountLine(tx("Te queda libre al mes hoy", "Left each month today"), result.monthlyLeftover.current)
        val options = result.options
        if (options != null) {
            options.lowerInstallment?.let { lower ->
                Text(tx("Si tu banco baja la cuota", "If your lender lowers the payment"), style = MaterialTheme.typography.titleSmall, color = Dincr.colors.text)
                AmountLine(tx("Cuota nueva", "New payment"), lower.monthlyPayment)
                AmountLine(tx("Te quedaría libre al mes", "Left each month"), lower.monthlyLeftover, emphasize = true)
            }
            options.shorterTerm?.let { shorter ->
                Text(tx("Si tu banco acorta el plazo", "If your lender shortens the term"), style = MaterialTheme.typography.titleSmall, color = Dincr.colors.text)
                AmountLine(tx("Misma cuota", "Same payment"), shorter.monthlyPayment)
                InfoLine(tx("Terminás antes", "You finish earlier"), months(shorter.monthsSaved))
                AmountLine(tx("Intereses que te ahorrás", "Interest you save"), shorter.interestSaved)
            }
        } else {
            AmountLine(tx("Te quedaría libre al mes", "Left each month"), result.monthlyLeftover.scenario, emphasize = true)
            AmountLine(tx("Diferencia al mes", "Monthly difference"), result.monthlyLeftover.change)
        }
        result.oneTimeAmount?.let {
            AmountLine(tx("Pago único", "One-off payment"), it)
            AmountLine(tx("Tus ahorros después", "Your savings afterwards"), result.liquidSavingsAfter)
        }
        if (result.kind == DebtScenarioRequest.PAY_OFF) result.payoff?.interest?.let { AmountLine(tx("Intereses que dejás de pagar", "Interest you stop paying"), it) }
        if (result.kind == DebtScenarioRequest.NEW_DEBT) {
            AmountLine(tx("Cuota de la deuda nueva", "New debt’s payment"), result.debt?.monthlyPayment)
            result.payoff?.interest?.let { AmountLine(tx("Intereses en total", "Total interest"), it) }
        }
        result.explanation?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) }
        result.warnings.forEach { Caption(it) }
    }
}

private fun months(value: Int?): String = when (value) {
    null -> "—"
    1 -> tx("1 mes", "1 month")
    else -> tx("$value meses", "$value months")
}
