package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject

/**
 * The invented account behind the App Store / Google Play screenshots (store-assets/), served by
 * [FakeBackend] as `Scenario.STORE` in Debug builds only. Same app and code paths as any fixture;
 * only the data differs:
 * - a fixed "today", so the images are identical on any capture day;
 * - six months of history, so the charts are full;
 * - a first name, a plan bought in the store (not a courtesy grant) and a completed situation;
 * - numbers that agree with each other (the emergency goal equals the declared savings, the
 *   dashboard sums the movements); strategy, command center and budget are the real backend
 *   engines' responses for this account ([engine]);
 * - text in the app's language, as the real backend localizes its text with Accept-Language
 *   (core/i18n.py). User-entered text (descriptions, names) is what an English- or
 *   Spanish-speaking user would type.
 */
internal class StoreSample(private val language: AppLanguage) {
    private fun t(spanish: String, english: String) = language.pick(spanish, english)
    private fun day(dayOfMonth: Int) = TODAY.withDayOfMonth(dayOfMonth).toString()
    private fun money(value: Long) = BigDecimal(value)

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

    /**
     * A backend response for this account exactly as the real engines computed it (strategy, VIP
     * command center, guided budget): `engine` in store-sample.json, pinned by
     * backend/tests/test_store_sample_engine.py. Never hand-written.
     */
    fun engine(name: String): String =
        golden[language.tag]?.jsonObject?.get("engine")?.jsonObject?.get(name)?.toString() ?: error("store-sample.json has no engine.$name")

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

        private val golden by lazy {
            val text = StoreSample::class.java.getResourceAsStream("/store-sample.json")?.bufferedReader()?.use { it.readText() }
                ?: error("store-sample.json is missing from the core/data resources")
            Json.parseToJsonElement(text).jsonObject
        }
    }
}
