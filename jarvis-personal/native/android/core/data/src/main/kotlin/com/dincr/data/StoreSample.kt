package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate
import java.util.Locale

/**
 * The invented account behind the App Store / Google Play screenshots (store-assets/), served by
 * [FakeBackend] as `Scenario.STORE` in Debug builds only. Same app and code paths as any fixture;
 * only the data differs:
 * - a fixed "today", so the images are identical on any capture day;
 * - six months of history, so the charts are full;
 * - a first name, a plan bought in the store (not a courtesy grant) and a completed situation;
 * - numbers that agree with each other (the strategy margin is income − essentials − minimums, the
 *   projections follow that split, the emergency goal equals the declared savings);
 * - text in the app's language, as the real backend localizes its text with Accept-Language
 *   (core/i18n.py). User-entered text (descriptions, names) is what an English- or
 *   Spanish-speaking user would type.
 */
internal class StoreSample(private val language: AppLanguage) {
    private fun t(spanish: String, english: String) = language.pick(spanish, english)
    private fun day(dayOfMonth: Int) = TODAY.withDayOfMonth(dayOfMonth).toString()
    private fun money(value: Long) = BigDecimal(value)
    /** Amounts inside backend sentences, formatted like the profile's number format. */
    private fun colones(value: Long) = "₡" + String.format(Locale.US, "%,d", value).replace(",", t(".", ","))

    val cardName = t("Tarjeta principal", "Main card")
    val loanName = t("Préstamo del carro", "Car loan")
    val numberFormat = t("dot_comma", "comma_dot")

    private val food = t("Comida", "Food")
    private val transport = t("Transporte", "Transportation")
    private val utilities = t("Servicios", "Utilities")
    private val housing = t("Vivienda", "Housing")
    private val health = t("Salud", "Health")
    private val restaurants = t("Restaurantes", "Restaurants")
    private val entertainment = t("Entretenimiento", "Entertainment")
    private val shopping = t("Compras", "Shopping")
    private val salary = t("Salario", "Salary")
    private val paycheck = t("Salario quincenal", "Paycheck")
    private val groceries = t("Supermercado", "Groceries")
    private val gas = t("Gasolina", "Gas")

    fun situation() = FinancialProfile(
        incomeType = "fixed", fixedMonthlySalary = money(MONTHLY_INCOME), payFrequency = "biweekly",
        essentialMonthlyExpenses = money(ESSENTIALS), liquidSavings = money(SAVED), emergencyFundTarget = money(EMERGENCY_TARGET),
    )

    fun budget() = listOf(
        BudgetItem(food, money(150000)), BudgetItem(transport, money(70000)), BudgetItem(utilities, money(60000)),
        BudgetItem(restaurants, money(25000)), BudgetItem(entertainment, money(30000)),
    )

    /** The current month (paydays on the 15th and 28th, like the history) plus five earlier months. */
    fun movements(): List<Movement> {
        var id = 0L
        fun income(date: String) = (++id).let { Movement("salary:$it", it, "salary", date, paycheck, money(PAYCHECK), "income", salary, "", true) }
        fun expense(date: String, description: String, amount: Long, category: String) =
            (++id).let { Movement("expense:$it", it, "expense", date, description, money(amount), "expense", category, "", true) }
        val rows = mutableListOf(
            income(day(15)), income(day(28)),
            expense(day(2), t("Alquiler", "Rent"), 210000, housing),
            expense(day(4), groceries, 46300, food),
            expense(day(6), t("Luz y agua", "Power and water"), 31800, utilities),
            expense(day(8), t("Internet del hogar", "Home internet"), 24900, utilities),
            expense(day(11), gas, 30000, transport),
            expense(day(13), t("Farmacia", "Pharmacy"), 9800, health),
            expense(day(17), groceries, 52450, food),
            expense(day(21), gas, 25000, transport),
            expense(day(24), t("Almuerzo", "Lunch"), 8500, restaurants),
            expense(day(26), groceries, 38900, food),
            expense(day(27), t("Café", "Coffee"), 2300, restaurants),
        )
        // A subscription paid in dollars and converted at the entry's rate (#269).
        rows += (++id).let { Movement("expense:$it", it, "expense", day(19), t("Suscripción de streaming", "Streaming subscription"), BigDecimal("5075.00"), "expense", entertainment, "", true, BigDecimal(10), "USD", BigDecimal("507.5")) }
        val history = listOf(
            listOf(groceries to 142300, t("Luz, agua e internet", "Power, water and internet") to 58000, gas to 61500, t("Farmacia", "Pharmacy") to 18000, t("Cine", "Movies") to 27400),
            listOf(groceries to 151800, t("Luz, agua e internet", "Power, water and internet") to 56500, gas to 64200, t("Restaurante", "Restaurant") to 33900, t("Cine", "Movies") to 22000),
            listOf(groceries to 138900, t("Luz, agua e internet", "Power, water and internet") to 59800, gas to 58700, t("Consulta médica", "Doctor visit") to 42500, t("Ropa", "Clothes") to 36000),
            listOf(groceries to 147600, t("Luz, agua e internet", "Power, water and internet") to 57200, gas to 66100, t("Restaurante", "Restaurant") to 28400, t("Cine", "Movies") to 19500),
            listOf(groceries to 144100, t("Luz, agua e internet", "Power, water and internet") to 58400, gas to 60900, t("Ropa", "Clothes") to 41200, t("Farmacia", "Pharmacy") to 12800),
        )
        val categories = listOf(food, utilities, transport)
        history.forEachIndexed { index, month ->
            val first = TODAY.minusMonths(index + 1L)
            rows += income(first.withDayOfMonth(15).toString())
            rows += income(first.withDayOfMonth(28).toString())
            rows += expense(first.withDayOfMonth(2).toString(), t("Alquiler", "Rent"), 210000, housing)
            month.forEachIndexed { position, (description, amount) ->
                val category = categories.getOrNull(position) ?: when (description) {
                    t("Farmacia", "Pharmacy"), t("Consulta médica", "Doctor visit") -> health
                    t("Restaurante", "Restaurant") -> restaurants
                    t("Ropa", "Clothes") -> shopping
                    else -> entertainment
                }
                rows += expense(first.withDayOfMonth(5 + position * 4).toString(), description, amount.toLong(), category)
            }
        }
        return rows
    }

    fun debts() = listOf(
        Debt(1, cardName, "credit_card", money(750000), money(CARD_BALANCE), money(CARD_MINIMUM), BigDecimal("36.0"), null, 3, TODAY.plusDays(5).toString()),
        Debt(2, loanName, "loan", money(2400000), money(LOAN_BALANCE), money(LOAN_MINIMUM), BigDecimal("14.5"), 48, 1, null),
    )

    fun goals() = listOf(Goal(3, t("Fondo de emergencia", "Emergency fund"), money(EMERGENCY_TARGET), money(SAVED), TODAY.plusMonths(8).toString(), "high", "active"))

    fun savings() = listOf(SavingsPlan(4, t("Vacaciones", "Vacation"), money(25000), money(75000),
        TODAY.minusMonths(3).withDayOfMonth(1).toString(), TODAY.plusMonths(9).withDayOfMonth(1).toString(), "active"))

    fun recurring() = listOf(RecurringItem(5, t("Internet del hogar", "Home internet"), money(24900), utilities, "expense", "monthly", 8, true))

    fun candidates(): List<MailCandidate> {
        val bank = t("Mi banco", "My bank")
        return listOf(
            MailCandidate(21, 21, null, bank, "avisos@banco.example", t("Notificación de compra", "Purchase notice"), "${day(27)}T10:00:00Z", groceries, money(15300), "CRC",
                accountBaseCurrency = "CRC", transactionDate = day(27), transactionType = "expense", category = food, reviewStatus = "pending"),
            MailCandidate(22, 22, null, bank, "avisos@banco.example", t("Compra internacional", "International purchase"), "${day(26)}T10:00:00Z", t("Tienda en línea", "Online store"), money(25), "USD",
                accountBaseCurrency = "CRC", transactionDate = day(26), transactionType = "expense", category = shopping, reviewStatus = "pending"),
        )
    }

    private val margin = MONTHLY_INCOME - ESSENTIALS - CARD_MINIMUM - LOAN_MINIMUM

    fun strategy(vip: Boolean) = Strategy(
        "tight", "debt", money(MONTHLY_INCOME), money(ESSENTIALS), money(CARD_MINIMUM + LOAN_MINIMUM), money(margin),
        listOf(
            Strategy.Allocation("emergency", t("Fondo de emergencia", "Emergency fund"), money(TO_EMERGENCY)),
            Strategy.Allocation("debt_extra", t("Extra a la tarjeta", "Extra to the credit card"), money(TO_CARD)),
            Strategy.Allocation("flex", t("Libre", "Free to spend"), money(margin - TO_EMERGENCY - TO_CARD)),
        ),
        recommendation = t("Destiná ${colones(TO_CARD)} extra a la tarjeta y ${colones(TO_EMERGENCY)} a tu fondo de emergencia.",
            "Put ${colones(TO_CARD)} extra toward the credit card and ${colones(TO_EMERGENCY)} into your emergency fund."),
        projection = Strategy.Projection(cardName, CARD_MONTHS, CARD_MONTHS_AT_MINIMUM, money(CARD_MINIMUM + TO_CARD)),
        directorNote = if (vip) t("Priorizamos la deuda con la tasa más alta.", "We prioritize the debt with the highest rate.") else null,
    )

    fun commandCenter(): CommandCenter {
        // Each month: the minimums plus the extra lower the debt (net of about ₡36.000 of interest);
        // the emergency share raises the cash. Net worth = cash − debt.
        val points = listOf(1, 3, 6).map { months ->
            val cash = SAVED + TO_EMERGENCY * months
            val debt = CARD_BALANCE + LOAN_BALANCE - DEBT_DOWN_PER_MONTH * months
            CommandCenter.ProjectionPoint(months, money(cash), money(debt), money(cash - debt), "medium")
        }
        return CommandCenter(
            TODAY.toString(),
            CommandCenter.Director("debt", t("Tu prioridad es bajar la tarjeta", "Your priority is paying down the credit card"),
                t("Pagá ${colones(TO_CARD)} extra a la tarjeta este mes", "Pay ${colones(TO_CARD)} extra on the credit card this month"), true),
            CommandCenter.Score(72, t("Estable", "Stable"), listOf(CommandCenter.Factor(t("Ahorro de emergencia", "Emergency savings"), "warning"))),
            CommandCenter.DebtPlanner(CommandCenter.Plan("avalanche", cardName, money(CARD_MINIMUM + TO_CARD), CARD_MONTHS, money(CARD_INTEREST))),
            CommandCenter.SafeToSpend(money(margin - TO_EMERGENCY - TO_CARD), money(margin), money((CARD_MINIMUM + LOAN_MINIMUM) * 3 / 2)),
            listOf(CommandCenter.Alert("medium", t("Pago de tarjeta en 5 días", "Credit card payment in 5 days"),
                t("El pago mínimo vence pronto.", "The minimum payment is due soon."), t("Revisá la deuda", "Review the debt"))),
            points,
            listOf(
                // Titles and details as the backend words them (ai/strategy_dashboard.py).
                CommandCenter.RoadmapStep(1, t("Construir Salvavidas", "Build your emergency fund"), money(TO_EMERGENCY),
                    t("La prioridad es aumentar tus meses de cobertura antes de asumir más riesgo.", "The priority is to increase your months of coverage before taking on more risk.")),
                CommandCenter.RoadmapStep(2, t("Atacar deuda: $cardName", "Pay down debt: $cardName"), money(TO_CARD),
                    t("El sobrante destinado a deuda se concentra primero en esta obligación.", "The surplus for debt goes to this obligation first.")),
            ),
        )
    }

    companion object {
        /** The fixed "today" of the sample: the second payday of September 2026. */
        val TODAY: LocalDate = LocalDate.of(2026, 9, 28)
        const val PAYCHECK = 432500L
        const val MONTHLY_INCOME = PAYCHECK * 2
        const val ESSENTIALS = 420000L
        const val SAVED = 240000L
        const val EMERGENCY_TARGET = 600000L
        const val CARD_BALANCE = 585000L
        const val CARD_MINIMUM = 45000L
        const val LOAN_BALANCE = 1560000L
        const val LOAN_MINIMUM = 50000L
        const val TO_EMERGENCY = 120000L
        const val TO_CARD = 150000L
        /** ₡585.000 at 3 % a month paying ₡195.000: 4 payments, about ₡37.600 of interest. */
        const val CARD_MONTHS = 4
        const val CARD_INTEREST = 37600L
        /** The same balance paying only the ₡45.000 minimum: 17 months. */
        const val CARD_MONTHS_AT_MINIMUM = 17
        /** Minimums + extra (₡245.000) minus about ₡36.000 of monthly interest. */
        const val DEBT_DOWN_PER_MONTH = 209000L
    }
}
