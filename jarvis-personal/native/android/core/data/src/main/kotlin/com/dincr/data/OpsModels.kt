package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Account, plan and operations contracts: legal acceptance, plans, feature flags, service health,
// release policy, support tickets and store billing.

@Serializable
data class LegalAcceptRequest(
    @SerialName("accept_terms") val acceptTerms: Boolean,
    @SerialName("accept_privacy") val acceptPrivacy: Boolean,
    @SerialName("terms_version") val termsVersion: String,
    @SerialName("privacy_version") val privacyVersion: String,
)

@Serializable
data class LegalAcceptResult(val status: String? = null, val required: Boolean? = null)

/** An item of `GET /auth/plans`. */
@Serializable
data class PlanOption(
    val code: String,
    val name: String? = null,
    val tagline: String? = null,
    val features: List<String> = emptyList(),
    @SerialName("regular_price_crc") val regularPriceCrc: Long? = null,
    val promotion: Promotion? = null,
)

@Serializable
data class Promotion(val code: String? = null, val active: Boolean = false, @SerialName("ends_at") val endsAt: String? = null, val message: String? = null)

/** `POST /auth/plan`. */
@Serializable
data class PlanChangeRequest(
    val plan: String,
    @SerialName("accept_beta_terms") val acceptBetaTerms: Boolean = false,
    @SerialName("consent_version") val consentVersion: String,
)

/** ok | plan_kept | downgrade_scheduled | promotion_active. */
@Serializable
data class PlanChangeResult(
    val status: String? = null,
    val plan: String? = null,
    @SerialName("pending_plan") val pendingPlan: String? = null,
    @SerialName("effective_at") val effectiveAt: String? = null,
    val message: String? = null,
    val profile: Profile? = null,
)

/** `GET /product-ops/billing/catalog`. */
@Serializable
data class BillingCatalog(val plans: List<CatalogPlan> = emptyList(), val promotion: Promotion? = null, val notice: String? = null) {
    @Serializable
    data class CatalogPlan(val code: String, @SerialName("regular_price_crc") val regularPriceCrc: Long? = null)
}

/** `GET /product-ops/feature-flags`. */
@Serializable
data class FeatureFlags(val flags: List<Flag> = emptyList(), @SerialName("cache_seconds") val cacheSeconds: Int? = null) {
    @Serializable
    data class Flag(
        @SerialName("flag_key") val key: String,
        val enabled: Boolean = false,
        @SerialName("disabled_message_es") val disabledMessageEs: String? = null,
        @SerialName("disabled_message_en") val disabledMessageEn: String? = null,
    )

    /** A flag's state; unknown (missing, or flags not loaded) is the backend's safe default. */
    fun isEnabled(flag: OpsFlag): Boolean = flags.firstOrNull { it.key == flag.key }?.enabled ?: flag.safeDefault

    fun message(flag: OpsFlag, language: AppLanguage): String? =
        flags.firstOrNull { it.key == flag.key }?.let { if (language == AppLanguage.SPANISH) it.disabledMessageEs else it.disabledMessageEn }
}

/** `GET /product-ops/health`. */
@Serializable
data class ServiceHealth(val status: String? = null, @SerialName("active_incidents") val activeIncidents: Int? = null, @SerialName("checked_at") val checkedAt: String? = null)

/** `GET /product-ops/release-policy?platform=android&version=` (public, fail-open). */
@Serializable
data class ReleasePolicy(
    val status: String? = null,
    val required: Boolean = false,
    val active: Boolean = false,
    @SerialName("latest_version") val latestVersion: String? = null,
    @SerialName("minimum_supported_version") val minimumSupportedVersion: String? = null,
    @SerialName("update_url") val updateUrl: String? = null,
    @SerialName("message_es") val messageEs: String? = null,
    @SerialName("message_en") val messageEn: String? = null,
) {
    val isRequired: Boolean get() = active && (required || status == "required")
    val isOptional: Boolean get() = active && !isRequired && status == "optional"
}

/** A support ticket (`GET /product-ops/feedback`). */
@Serializable
data class SupportTicket(
    val id: Long,
    val category: String? = null,
    val subject: String? = null,
    val status: String? = null,
    @SerialName("user_resolution") val userResolution: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("public_id") val publicId: String? = null,
)

/** `POST /product-ops/feedback`. */
@Serializable
data class SupportRequest(
    val category: String,
    val subject: String,
    val message: String,
    @SerialName("app_version") val appVersion: String? = null,
    val screen: String? = null,
    @SerialName("error_reference") val errorReference: String? = null,
)

@Serializable
data class SupportCreated(val id: Long? = null, @SerialName("public_id") val publicId: String? = null, @SerialName("email_sent") val emailSent: Boolean? = null)

@Serializable
data class ResolutionRequest(val resolution: String)

/** `POST /product-ops/events`: only the backend's allow-listed names are ever sent. */
@Serializable
data class ProductEvent(
    @SerialName("event_name") val eventName: String,
    val surface: String,
    val success: Boolean = true,
    @SerialName("app_version") val appVersion: String? = null,
) {
    companion object {
        val ALLOWED = setOf(
            "dashboard_opened", "finance_opened", "debts_opened", "goals_opened", "transactions_opened", "strategy_opened",
            "budget_opened", "calendar_opened", "recurring_opened", "reports_opened", "settings_opened", "feedback_submitted",
            "checkout_started", "onboarding_completed", "api_error", "subscription_lifecycle",
        )
    }
}

/** `GET /product-ops/billing/store/catalog`. */
@Serializable
data class StoreCatalog(val plans: List<Plan> = emptyList(), @SerialName("trial_days") val trialDays: Int? = null, val stores: Stores? = null) {
    @Serializable
    data class Plan(val code: String, val monthly: Product? = null, val annual: Product? = null)

    @Serializable
    data class Product(@SerialName("price_crc") val priceCrc: Long? = null, @SerialName("product_id") val productId: String? = null)

    @Serializable
    data class Stores(val google: Ready? = null, val apple: Ready? = null)

    @Serializable
    data class Ready(val ready: Boolean = false)
}

/** `GET /product-ops/billing/store/entitlement`: the server's view of the store subscription. */
@Serializable
data class StoreEntitlement(
    val plan: String? = null,
    val entitlement: String? = null,
    val status: String? = null,
    val provider: String? = null,
    @SerialName("billing_period") val billingPeriod: String? = null,
    @SerialName("current_period_end") val currentPeriodEnd: String? = null,
    @SerialName("cancel_at_period_end") val cancelAtPeriodEnd: Boolean? = null,
    @SerialName("auto_renew") val autoRenew: Boolean? = null,
    @SerialName("pending_plan") val pendingPlan: String? = null,
    @SerialName("product_id") val productId: String? = null,
) {
    /** A store subscription the server counts as live (`product_ops.store_billing.ACTIVE_STATES`). iOS: `StoreEntitlement.isLive`. */
    val isLive: Boolean get() = provider in setOf("google", "apple") && status in LIVE_STATUSES

    companion object {
        val LIVE_STATUSES = setOf("trialing", "active", "grace_period")
    }
}

@Serializable
data class CustomerToken(val token: String)

@Serializable
data class GooglePurchaseRequest(@SerialName("purchase_token") val purchaseToken: String, @SerialName("product_id") val productId: String)

@Serializable
data class StoreVerification(val status: String? = null, val plan: String? = null, val resolved: Boolean? = null, val acknowledgement: String? = null)
