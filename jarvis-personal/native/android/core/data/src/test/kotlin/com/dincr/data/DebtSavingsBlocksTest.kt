package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * DB-1 — Plan → Ahorro para deudas (Owner): the backend's proposal decoded and said in short sentences,
 * and the reminder on the day a block matures. The Swift twin is `DebtSavingsBlocksTests`. Synthetic data.
 */
class DebtSavingsBlocksTest {
    private val colones = MoneyFormat("CRC", MoneyFormat.Separators.DOT_COMMA)
    private val es = AppLanguage.SPANISH
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    private val proposalJson = """
        {"status": "proposal", "weekly_safe_amount": 13500.0, "committed_weekly": 0.0, "savings_interest_counted": false,
         "warnings": ["average_income_estimated", "something_new"], "short_debts": [],
         "proposal": {"mode": "block", "debt": {"id": 801, "name": "Préstamo de ejemplo", "remaining_amount": 1200000.0, "interest_rate": 24.0},
                      "weekly_amount": 13500.0, "contributions": 26, "term_months": 6, "start_date": "2026-11-05", "maturity_date": "2027-05-05",
                      "total_saved": 351000.0, "abono_amount": 351000.0, "balance_at_maturity": 1020000.0, "balance_after_abono": 669000.0,
                      "lock_cost": 21400.0, "recommendation": {"choice": "reduce_term", "reason": "saves_interest"}},
         "blocks": [{"id": "b1", "debt_id": 802, "debt_name": "Tarjeta de ejemplo", "mode": "block", "weekly_amount": 5000.0,
                     "start_date": "2026-10-01", "maturity_date": "2027-01-01", "term_months": 3, "contributions_total": 14,
                     "contributions_done": 5, "saved_so_far": 25000.0, "total_at_maturity": 70000.0, "next_date": "2026-11-05", "matured": false}]}
    """.trimIndent()

    private fun state(text: String = proposalJson) = json.decodeFromString(DebtSavingsBlocks.serializer(), text)

    @Test fun theProposalIsSaidInShortSentences() {
        val state = state()
        val proposal = state.proposal!!
        assertEquals("Ahorrá ₡13.500 cada jueves por 6 meses", DebtSavingsReading.headline(proposal, colones, es))
        assertEquals(listOf(
            "Es para Préstamo de ejemplo, la deuda que sigue en tu estrategia.",
            "Empieza el 5 nov 2026 y vence el 5 may 2027.",
            "Ese día le abonás ₡351.000 a Préstamo de ejemplo y te queda debiendo unos ₡669.000.",
            "Bloquearlo te cuesta unos ₡21.400 en intereses frente a abonar cada semana. Es el precio de no ver esa plata.",
            "Los intereses del ahorro no se cuentan: si llegan, son ganancia.",
        ), DebtSavingsReading.lines(state, colones, es))
        assertTrue(DebtSavingsReading.recommendation(proposal, es).startsWith("Al abonar, pedile al banco bajar el plazo: así ahorrás más intereses."))
        assertNull(DebtSavingsReading.statusMessage(state, es))
    }

    @Test fun onlyKnownWarningsAreShown() {
        assertEquals(listOf("Algunos salarios de los últimos 3 meses son estimados."), DebtSavingsReading.warnings(state(), es))
    }

    @Test fun preSavingNamesTheShortDebtsPaidFirst() {
        val text = proposalJson.replace("\"mode\": \"block\", \"debt\"", "\"mode\": \"presave\", \"debt\"")
            .replace("\"short_debts\": []", "\"short_debts\": [{\"id\": 9, \"name\": \"Tienda de ejemplo\", \"payoff_month\": 2}]")
        assertEquals("Mientras terminás de pagar Tienda de ejemplo, vas guardando para Préstamo de ejemplo.",
            DebtSavingsReading.lines(state(text), colones, es).first())
    }

    @Test fun withoutAProposalItSaysWhy() {
        fun none(status: String, committed: Int) = state("{\"status\": \"$status\", \"weekly_safe_amount\": 0, \"committed_weekly\": $committed, \"proposal\": null}")
        assertEquals("Tus deudas se terminan en 3 meses o menos: seguí pagándolas directo.", DebtSavingsReading.statusMessage(none("short_debts_only", 0), es))
        assertEquals("Tus ahorros bloqueados ya usan todo tu sobrante seguro de cada jueves.", DebtSavingsReading.statusMessage(none("no_surplus", 13500), es))
        assertEquals("Con tu salario sin extras no queda plata segura para bloquear.", DebtSavingsReading.statusMessage(none("no_surplus", 0), es))
        assertTrue(DebtSavingsReading.lines(none("no_debts", 0), colones, es).isEmpty())
    }

    @Test fun aBlockShowsItsProgressOrWhatToDoWhenItMatured() {
        val block = state().blocks!!.first()
        assertEquals(listOf("₡5.000 cada jueves", "Llevás ₡25.000 de ₡70.000 (5 de 14 jueves).", "Vence el 1 ene 2027."),
            DebtSavingsReading.blockLines(block, colones, es))
        val matured = block.copy(matured = true)
        assertEquals(listOf("Venció el 1 ene 2027: abonale ₡70.000 a Tarjeta de ejemplo."), DebtSavingsReading.blockLines(matured, colones, es))
    }

    @Test fun theDayABlockMaturesThePhoneSaysWhatToPay() {
        val blocks = state().blocks!!
        val plan = Reminders.plan(LocalDate.of(2026, 12, 20), emptyList(), null, colones, days = 20, language = es, blocks = blocks)
        val reminder = plan.first { it.id.startsWith("dincr.reminder.block.b1") }
        assertEquals(LocalDate.of(2027, 1, 1), reminder.at.toLocalDate())
        assertEquals("Hoy vence tu ahorro bloqueado", reminder.title)
        assertEquals("Abonale ₡70.000 a Tarjeta de ejemplo.", reminder.body)
        assertFalse(Reminders.plan(LocalDate.of(2026, 11, 1), emptyList(), null, colones, language = es, blocks = blocks).any { ".block." in it.id })
    }

    @Test fun theRequestCarriesWhatTheBankSet() {
        val body = Json.encodeToString(DebtSavingsBlockCreate.serializer(), DebtSavingsBlockCreate(801, BigDecimal(13500), "2026-11-05", 6, "block"))
        assertTrue(body, body.contains("\"debt_id\":801") && body.contains("\"weekly_amount\":13500") && body.contains("\"term_months\":6"))
    }

    @Test fun afterTheAbonoItSaysWhereTheDebtStandsAndWhatWasLeft() {
        fun applied(text: String) = json.decodeFromString(DebtSavingsBlockApplied.serializer(), text).block.applied
        assertEquals("Listo: tu deuda quedó en ₡649.000.", DebtSavingsReading.appliedMessage(
            applied("""{"block": {"id": "b1", "applied": {"amount": 351000, "outcome": "reduce_term", "new_remaining_amount": 649000, "left_over": 0}}}"""), colones, es))
        assertEquals("Listo: terminaste de pagar esa deuda. Te sobraron ₡50.000: mandalos a tu siguiente deuda o al Salvavidas.", DebtSavingsReading.appliedMessage(
            applied("""{"block": {"id": "b1", "applied": {"amount": 1050000, "outcome": "reduce_term", "new_remaining_amount": 0, "left_over": 50000}}}"""), colones, es))
    }

    @Test fun theAbonoCarriesTheNewInstallmentOnlyWhenTheBankLoweredIt() {
        val encoder = Json { explicitNulls = false }
        val term = encoder.encodeToString(DebtSavingsBlockApply.serializer(), DebtSavingsBlockApply.of(BigDecimal(351000), DebtSavingsBlockApply.REDUCE_TERM, BigDecimal(39000)))
        assertTrue(term, term.contains("\"outcome\":\"reduce_term\"") && !term.contains("39000"))
        val lower = encoder.encodeToString(DebtSavingsBlockApply.serializer(), DebtSavingsBlockApply.of(BigDecimal(351000), DebtSavingsBlockApply.REDUCE_INSTALLMENT, BigDecimal(39000)))
        assertTrue(lower, lower.contains("\"new_monthly_payment\":39000"))
    }

    @Test fun aDebtPaymentCarriesWhatTheBankDidOnlyWhenTheUserSaidIt() {
        val encoder = Json { explicitNulls = false }
        fun body(after: DebtAfterExtra?) = encoder.encodeToString(DebtPaymentRequest.serializer(), DebtPaymentRequest.of(BigDecimal(141500), after))
        assertEquals("{\"amount\":141500}", body(null))
        assertTrue(body(DebtAfterExtra.RemainingInstallments(10)).contains("\"remaining_installments\":10"))
        val lower = body(DebtAfterExtra.NewMonthlyPayment(BigDecimal(4104)))
        assertTrue(lower, lower.contains("\"new_monthly_payment\":4104") && !lower.contains("remaining"))
        val block = encoder.encodeToString(DebtSavingsBlockApply.serializer(),
            DebtSavingsBlockApply.of(BigDecimal(351000), DebtSavingsBlockApply.REDUCE_TERM, null, 12))
        assertTrue(block, block.contains("\"remaining_installments\":12"))
    }
}
