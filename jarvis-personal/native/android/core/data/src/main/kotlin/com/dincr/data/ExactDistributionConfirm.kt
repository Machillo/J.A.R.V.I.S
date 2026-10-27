package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * CONFIRMAR of the Owner's exact-amount distribution (backend/ai/owner_distribution.py).
 *
 * The calculated distribution is a plan: it writes nothing. Its answer carries a [ConfirmationPlan]
 * that says what CONFIRMAR would record for each destination. Confirming is the Owner declaring he
 * carried it out: the backend recomputes it, applies it only when it is the split the Owner saw
 * ([ExactDistributionConfirmRequest.expectedItems]) and records it once per confirmation key.
 * iOS: `ExactDistributionConfirm.swift`.
 */
@Serializable
data class ConfirmationPlan(
    val steps: List<Step> = emptyList(),
    val confirmable: Boolean = false,
    @SerialName("blocking_reasons") val blockingReasons: List<String> = emptyList(),
    /** The plan as one value (which debt and goal get what); sent back with CONFIRMAR. */
    val fingerprint: String? = null,
) {
    @Serializable
    data class Step(
        val key: String? = null,
        val amount: Money? = null,
        /** debt_extra_payment, salvavidas_deposit, goal_contribution, investment_reserve, not_recorded. */
        val action: String? = null,
        val targets: List<DebtTarget> = emptyList(),
        @SerialName("goal_name") val goalName: String? = null,
    )

    @Serializable
    data class DebtTarget(
        @SerialName("debt_id") val debtId: Long? = null,
        val name: String? = null,
        val amount: Money? = null,
    )
}

@Serializable
data class ExpectedDistributionItem(val key: String, val amount: Money)

@Serializable
data class ExactDistributionConfirmRequest(
    val amount: Money,
    @SerialName("confirmation_key") val confirmationKey: String,
    @SerialName("expected_items") val expectedItems: List<ExpectedDistributionItem>,
    @SerialName("plan_fingerprint") val planFingerprint: String,
    val currency: String = "CRC",
)

@Serializable
data class ExactDistributionConfirmation(
    /** `applied`, or `already_applied` when this confirmation key had already been recorded. */
    val status: String? = null,
    val confirmation: Record? = null,
) {
    @Serializable
    data class Record(
        val id: Long? = null,
        val amount: Money? = null,
        @SerialName("created_at") val createdAt: String? = null,
    )
}
