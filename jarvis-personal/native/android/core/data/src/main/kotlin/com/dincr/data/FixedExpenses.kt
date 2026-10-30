package com.dincr.data

import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Plan → Gastos fijos (FX-1, Owner): the Owner's fixed expenses (`fixed_expenses`, the table his
 * Salvavidas and strategy read) through `/finance/fixed-expenses` (INTERNAL_ONLY: the backend refuses
 * everyone else). VIP manages its recurring expenses instead (`/user-product/basic/recurring`).
 * Removing deactivates the row, as the backend does. iOS twin: `FixedExpenseModels.swift`.
 */
@Serializable
data class OwnerFixedExpense(
    val id: Long,
    val name: String? = null,
    val category: String? = null,
    @SerialName("expected_amount") val expectedAmount: Money? = null,
    val currency: String? = null,
    val frequency: String? = null,
    @SerialName("interval_months") val intervalMonths: Int? = null,
    @SerialName("due_day") val dueDay: Int? = null,
    @SerialName("is_active") val isActive: Boolean? = null,
) {
    /** What it costs per month (the amount divided by its interval), like the Salvavidas counts it. */
    val monthlyAmount: BigDecimal? get() = expectedAmount?.divide(BigDecimal(maxOf(intervalMonths ?: 1, 1)), 2, RoundingMode.HALF_UP)
}

/** The body of a create (POST) or edit (PUT): only the fields the form edits; always monthly, every N months. */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class OwnerFixedExpenseRequest(
    val name: String,
    val category: String,
    @SerialName("expected_amount") val expectedAmount: Money,
    @SerialName("interval_months") val intervalMonths: Int,
    @SerialName("due_day") val dueDay: Int? = null,
    @EncodeDefault val frequency: String = "monthly",
) {
    companion object {
        val INTERVALS = listOf(1, 2, 3, 6, 12)

        /** The form's checks before sending; null when valid, else the message to show. */
        fun problem(name: String, amount: BigDecimal?, intervalMonths: Int, dueDay: Int?, spanish: Boolean = true): String? = when {
            name.isBlank() -> if (spanish) "Escribí un nombre." else "Enter a name."
            amount == null || amount.signum() <= 0 -> if (spanish) "Escribí un monto mayor que cero." else "Enter an amount above zero."
            intervalMonths !in INTERVALS -> if (spanish) "Elegí cada cuántos meses se paga." else "Choose how often it is paid."
            dueDay != null && dueDay !in 1..31 -> if (spanish) "El día va de 1 a 31." else "The day goes from 1 to 31."
            else -> null
        }
    }
}
