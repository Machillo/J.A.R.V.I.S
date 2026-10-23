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
    /** What CONFIRMAR would record for [result]; null before a result. */
    val plan: ConfirmationPlan? = null,
    /** One key per calculated result: repeating a confirmation (retry, double tap) records it once. */
    val confirmationKey: String? = null,
    /** Set once the backend recorded this result: the Owner declared he carried it out. */
    val confirmation: ExactDistributionConfirmation? = null,
) {
    /** A new amount: the previous result (and error) no longer describe it. */
    fun edited(text: String): ExactDistributionForm = ExactDistributionForm(amountText = text)

    /** The answer for [forText]; kept only when it is still the amount on screen. A new result gets a new key. */
    fun calculated(forText: String, strategy: DirectorStrategy?, plan: ConfirmationPlan? = null,
                   key: String = java.util.UUID.randomUUID().toString()): ExactDistributionForm =
        if (forText == amountText) copy(result = strategy, error = null, plan = plan, confirmationKey = key, confirmation = null) else this

    fun failed(message: String?): ExactDistributionForm = copy(error = message)

    /** CONFIRMAR is offered only for a calculated result the backend says it can record, once. */
    val canConfirm: Boolean get() = result != null && plan?.confirmable == true && confirmationKey != null && confirmation == null

    /** The split the Owner reviewed, sent with CONFIRMAR: the backend records nothing when its own differs. */
    fun confirmRequest(amount: java.math.BigDecimal): ExactDistributionConfirmRequest? {
        val strategy = result ?: return null
        val key = confirmationKey ?: return null
        return ExactDistributionConfirmRequest(amount, key, strategy.allocationItems.mapNotNull { item ->
            item.key?.let { k -> item.amount?.let { ExpectedDistributionItem(k, it) } }
        })
    }

    /** The backend's answer for [key]; kept only when it is still this result's key. */
    fun confirmed(key: String, answer: ExactDistributionConfirmation): ExactDistributionForm =
        if (key == confirmationKey) copy(confirmation = answer, error = null) else this
}
