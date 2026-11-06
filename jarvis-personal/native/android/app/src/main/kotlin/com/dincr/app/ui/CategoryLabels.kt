package com.dincr.app.ui

import com.dincr.app.tx

/** The app's own category names in English (iOS: `CategoryStyle.english`). Anything else stays as written. */
private val englishCategories = mapOf(
    "Comida" to "Food",
    "Vivienda" to "Housing",
    "Servicios" to "Utilities",
    "Internet" to "Internet",
    "Teléfono" to "Phone",
    "Transporte" to "Transport",
    "Gasolina" to "Fuel",
    "Restaurante" to "Restaurants",
    "Salud" to "Health",
    "Entretenimiento" to "Entertainment",
    "Compras" to "Shopping",
    "Seguros" to "Insurance",
    "Deporte" to "Sports",
    "Mascotas" to "Pets",
    "Otros" to "Other",
    "Salario" to "Salary",
    "Boleta de pago" to "Pay stub",
    "Bono" to "Bonus",
    "Reembolso" to "Refund",
    "Otros ingresos" to "Other income",
    "Supermercado" to "Groceries",
    "Horas extra" to "Overtime",
    "Deudas" to "Debts",
    "Ahorro" to "Savings",
    "Educación" to "Education",
    "Ropa" to "Clothing",
    "Viajes" to "Travel",
    "Suscripciones" to "Subscriptions",
)

/** A stored (Spanish) category as the app's language reads it; null or empty: null. */
fun categoryLabel(category: String?): String? = category?.takeIf { it.isNotEmpty() }?.let { tx(it, englishCategories[it] ?: it) }
