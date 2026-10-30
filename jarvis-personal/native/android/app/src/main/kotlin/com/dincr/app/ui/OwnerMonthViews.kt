package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import com.dincr.app.tx
import com.dincr.data.MessageKind
import com.dincr.data.MoneyFormat
import com.dincr.data.MonthlySummary
import com.dincr.data.OwnerReading
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrMessage
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import java.time.YearMonth

// The Owner's month in Movimientos → Resumen del mes (backend owner_ledger, the same reading as
// Hoy and JARVIS → Análisis financiero). It says which period it covers, whether the month is
// complete, what each figure means, and shows the figures the ledger reports apart (other money
// in, refunds, gross payroll) instead of leaving them out. Every amount is the backend's.
// iOS: `OwnerMonthSummary` (AdvisorViews.swift).

/** The Owner's monthly figures, each with what it means. Shown only when the answer is the Owner's ledger. */
@Composable
fun OwnerMonthSummary(s: MonthlySummary) {
    Caption(tx("Mes calendario, del primer al último día. Solo cuenta dinero que ya se movió.",
        "The calendar month, first to last day. Only money that already moved counts."))
    if (s.complete == false) {
        DincrMessage(MessageKind.ATTENTION, tx("Este mes todavía no está completo", "This month isn’t complete yet"),
            s.incompleteReasons.joinToString("\n") { OwnerReading.incompleteReason(it, s.pendingMailCount, s.unclassifiedCount) })
    } else when (OwnerReading.monthState(s, YearMonth.now().toString())) {
        // Nothing recorded is unknown, not a verified zero; a month in progress can still change.
        OwnerReading.MonthState.NO_MOVEMENTS -> Caption(tx("No hay movimientos registrados en este mes: las cifras en cero significan que no hay registros, no que se confirmó que no hubo dinero.",
            "No movements recorded this month: the zero figures mean there are no records, not that no money moved."))
        OwnerReading.MonthState.IN_PROGRESS -> Caption(tx("Mes en curso: hasta hoy no quedan avisos sin revisar ni movimientos sin clasificar. Las cifras cambian hasta que termine el mes.",
            "Month in progress: so far no notices are left to review and no movements to classify. The figures change until the month ends."))
        OwnerReading.MonthState.CLOSED -> Caption(tx("Mes completo: no quedan avisos sin revisar ni movimientos sin clasificar.",
            "Complete month: no notices left to review and no movements to classify."))
    }
    DincrCard {
        Column(Modifier.testTag("summary.owner.month"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            AmountLine(tx("Ingresos recibidos", "Income received"), s.income, sign = MoneyFormat.Sign.INCOME)
            Caption(tx("Depósitos y salario neto que entraron este mes.", "Deposits and net salary that came in this month."))
            AmountLine(tx("Gastos", "Spending"), s.expenses)
            Caption(refundNote(s.grossExpenses, s.refunds))
            AmountLine(tx("Pagos de deuda", "Debt payments"), s.debtPaid)
            Caption(tx("Cuotas y abonos pagados a tus deudas.", "Instalments and extra payments made to your debts."))
            AmountLine(tx("Resultado del mes", "Result of the month"), s.balance, emphasize = true)
            Caption(tx("Ingresos recibidos menos gastos y pagos de deuda.", "Income received minus spending and debt payments."))
        }
    }
    if (positive(s.otherInflows)) Section(tx("Otro dinero que entró (no es ingreso)", "Other money in (not income)")) {
        Column(Modifier.testTag("summary.owner.otherInflows")) {
            if (positive(s.loanReceived)) AmountLine(tx("Préstamos recibidos", "Loans received"), s.loanReceived)
            if (positive(s.receivablePayments)) AmountLine(tx("Cobros de dinero que te debían", "Money owed to you, collected"), s.receivablePayments)
            if (positive(s.assetSaleProceeds)) AmountLine(tx("Ventas de bienes", "Sales of things you owned"), s.assetSaleProceeds)
            AmountLine(tx("Resultado contando ese dinero", "Result including that money"), s.cashFlow, emphasize = true)
            Caption(tx("Entró a tus cuentas pero no lo ganaste: por eso no suma a tus ingresos.",
                "It came into your accounts but you didn’t earn it, so it doesn’t add to your income."))
        }
    }
    s.payrollAccrued?.takeIf { OwnerReading.hasPayroll(it) }?.let { p ->
        Section(tx("Nómina bruta registrada (aparte)", "Gross payroll recorded (apart)")) {
            Column(Modifier.testTag("summary.owner.payroll")) {
                p.overtimeGross?.takeIf { it.signum() != 0 }?.let { AmountLine(tx("Horas extra (bruto)", "Overtime (gross)"), it) }
                p.vghGross?.takeIf { it.signum() != 0 }?.let { AmountLine(tx("Rebajos por vacaciones u otros (VGH, bruto)", "Leave deductions (VGH, gross)"), it) }
                p.bonusesGross?.takeIf { it.signum() != 0 }?.let { AmountLine(tx("Bonos (bruto)", "Bonuses (gross)"), it) }
                Caption(tx("Montos antes de cargas sociales e impuestos. Ese dinero llega dentro del depósito del salario, por eso no se suma otra vez a tus ingresos.",
                    "Amounts before social charges and taxes. That money arrives inside the salary deposit, so it isn’t added to your income again."))
            }
        }
    }
}

/** What the spending line means: net of refunds, with the gross amount when there were refunds. */
@Composable
private fun refundNote(gross: BigDecimal?, refunds: BigDecimal?): String =
    if (gross != null && positive(refunds) && refunds!! <= gross) tx("Gastos de ${Dincr.money.format(gross)} menos reembolsos de ${Dincr.money.format(refunds!!)}.",
        "Spending of ${Dincr.money.format(gross)} minus refunds of ${Dincr.money.format(refunds!!)}.")
    else tx("Compras y pagos del mes, ya restados los reembolsos.", "Purchases and payments of the month, refunds already taken out.")

private fun positive(amount: BigDecimal?) = (amount?.signum() ?: 0) > 0
