package com.dincr.data

/**
 * The Owner's exact-amount form (Plan → Distribución de dinero → Monto exacto). A result always
 * belongs to the amount it was calculated from: editing the amount drops it, and an answer that
 * arrives for an amount the Owner has since changed is ignored. iOS: `ExactDistributionForm`.
 */
data class ExactDistributionForm(
    val amountText: String = "",
    val result: DirectorStrategy? = null,
    val error: String? = null,
) {
    /** A new amount: the previous result (and error) no longer describe it. */
    fun edited(text: String): ExactDistributionForm = ExactDistributionForm(amountText = text)

    /** The answer for [forText]; kept only when it is still the amount on screen. */
    fun calculated(forText: String, strategy: DirectorStrategy?): ExactDistributionForm =
        if (forText == amountText) copy(result = strategy, error = null) else this

    fun failed(message: String?): ExactDistributionForm = copy(error = message)
}
