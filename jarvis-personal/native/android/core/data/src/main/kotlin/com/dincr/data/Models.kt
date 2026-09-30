package com.dincr.data

import java.math.BigDecimal
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonEncoder
import kotlinx.serialization.json.JsonUnquotedLiteral
import kotlinx.serialization.json.jsonPrimitive

// Client models for the DINCR API. They decode only the fields the screens use and ignore
// the rest (Json { ignoreUnknownKeys = true }). Same fields, types and optionality as the iOS
// DincrCore models, following the FastAPI code; pinned by fixtures that mirror what the
// backend builds (native/CONTRACT.md).

/** Money travels as JSON numbers; BigDecimal keeps them exact (no Double rounding). */
object MoneySerializer : KSerializer<BigDecimal> {
    override val descriptor = PrimitiveSerialDescriptor("Money", PrimitiveKind.STRING)
    override fun deserialize(decoder: Decoder): BigDecimal {
        val element = (decoder as JsonDecoder).decodeJsonElement().jsonPrimitive
        return BigDecimal(element.content)
    }
    @OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
    override fun serialize(encoder: Encoder, value: BigDecimal) {
        (encoder as JsonEncoder).encodeJsonElement(JsonUnquotedLiteral(value.stripTrailingZeros().toPlainString()))
    }
}

typealias Money = @Serializable(with = MoneySerializer::class) BigDecimal

/** `GET /auth/me` */
@Serializable
data class Profile(
    /** `allowed_users.id`: an integer, not the Supabase UUID. */
    val id: Long,
    val email: String? = null,
    @SerialName("display_name") val displayName: String? = null,
    // Missing fields decode to null, as on iOS, so a missing gate flag never opens the app.
    val role: String? = null,
    @SerialName("plan_selected") val planSelected: Boolean? = null,
    @SerialName("profile_setup_completed") val profileSetupCompleted: Boolean? = null,
    @SerialName("base_currency") val baseCurrency: String? = null,
    @SerialName("number_format") val numberFormat: String? = null,
    @SerialName("currency_placement") val currencyPlacement: String? = null,
    /** Currencies this backend converts for manual entries (#269); base only when absent. */
    @SerialName("entry_currencies") val entryCurrencies: List<String> = emptyList(),
    @SerialName("enabled_currencies") val enabledCurrencies: List<String> = emptyList(),
    @SerialName("usage_goal") val usageGoal: String? = null,
    @SerialName("onboarding_completed") val onboardingCompleted: Boolean? = null,
    val subscription: Subscription? = null,
    val legal: Legal? = null,
) {
    @Serializable
    data class Subscription(
        val plan: String? = null,
        @SerialName("plan_name") val planName: String? = null,
        /** active | pending | expired */
        val status: String? = null,
        /** self_service (store) | courtesy | owner */
        @SerialName("access_source") val accessSource: String? = null,
        @SerialName("expires_at") val expiresAt: String? = null,
        @SerialName("pending_plan") val pendingPlan: String? = null,
        @SerialName("pending_effective_at") val pendingEffectiveAt: String? = null,
        @SerialName("pending_requires_payment") val pendingRequiresPayment: Boolean? = null,
        @SerialName("access_notice") val accessNotice: AccessNotice? = null,
    )

    @Serializable
    data class AccessNotice(val code: String? = null, val title: String? = null, val message: String? = null)

    @Serializable
    data class Legal(
        val required: Boolean? = null,
        @SerialName("terms_version") val termsVersion: String? = null,
        @SerialName("privacy_version") val privacyVersion: String? = null,
        @SerialName("accepted_at") val acceptedAt: String? = null,
    )

    /**
     * The Owner uses the public app like any account: its own data, at least VIP (the backend grants
     * Owner every product feature), and no internal screen (the public app has none).
     */
    val isOwner: Boolean get() = role == "owner"
    /** Admin sessions are not served by the public app (Owner boundary). */
    val usesInternalAppOnly: Boolean get() = role == "admin"
    /** The Owner account is never deleted from the public app (DELETE /auth/me would remove it). */
    val canDeleteAccountInApp: Boolean get() = !isOwner
    val plan: String get() = subscription?.plan?.lowercase() ?: "free"
    /** What the app offers; the backend still decides every request. Only the server's role elevates Owner. */
    val planTier: PlanTier get() = if (isOwner) PlanTier.VIP else PlanTier.from(plan)
    val isCourtesy: Boolean get() = subscription?.accessSource == "courtesy"
    val firstName: String?
        get() = (displayName ?: email?.substringBefore("@"))?.trim()?.split(" ")?.firstOrNull()?.takeIf { it.isNotEmpty() }
}

/**
 * Where a signed-in identity lands in the public app, in order: the Owner boundary, legal, profile
 * setup, plan. The server decides role and plan; this only routes (iOS: `IdentityGate.of`).
 */
enum class IdentityGate {
    INTERNAL_ONLY, LEGAL_REQUIRED, PROFILE_SETUP, CHOOSE_PLAN, READY;

    companion object {
        fun of(profile: Profile): IdentityGate = when {
            profile.usesInternalAppOnly -> INTERNAL_ONLY
            profile.legal?.required == true -> LEGAL_REQUIRED
            profile.profileSetupCompleted != true -> PROFILE_SETUP
            // Owner's plan is granted by the backend, never chosen (POST /auth/plan ignores Owner).
            profile.planSelected != true && !profile.isOwner -> CHOOSE_PLAN
            else -> READY
        }
    }
}

@Serializable
data class MonthTotals(
    val month: String,
    val income: Money,
    val expenses: Money,
    @SerialName("debt_paid") val debtPaid: Money? = null,
    val balance: Money? = null,
)

@Serializable
data class CategoryAmount(val category: String, val amount: Money)

/** `GET /user-product/free/dashboard` */
@Serializable
data class FreeDashboard(
    val month: String,
    val income: Money,
    val expenses: Money,
    @SerialName("debt_paid") val debtPaid: Money? = null,
    @SerialName("debt_balance") val debtBalance: Money? = null,
    val balance: Money? = null,
    @SerialName("available_after_commitments") val availableAfterCommitments: Money? = null,
    val categories: List<CategoryAmount> = emptyList(),
    @SerialName("monthly_history") val monthlyHistory: List<MonthTotals> = emptyList(),
) {
    /** The key figure. The backend owns it; the client never derives it. */
    val available: BigDecimal? get() = availableAfterCommitments ?: balance
}

enum class MovementKind { INCOME, EXPENSE }

/** A row of `GET /user-product/free/movements`. */
@Serializable
data class Movement(
    @SerialName("movement_id") val movementId: String,
    @SerialName("source_id") val sourceId: Long? = null,
    val origin: String? = null,
    @SerialName("transaction_date") val transactionDate: String? = null,
    val description: String? = null,
    val amount: Money,
    @SerialName("transaction_type") val transactionType: String? = null,
    val category: String? = null,
    val notes: String? = null,
    val editable: Boolean = false,
    /**
     * Set when the amount was typed in, or received in, another currency (#269 manual entries,
     * #273 mail transactions): [amount] is already in the base currency and these keep the
     * typed figure and the user's rate.
     */
    @SerialName("original_amount") val originalAmount: Money? = null,
    @SerialName("original_currency") val originalCurrency: String? = null,
    @SerialName("exchange_rate") val exchangeRate: Money? = null,
) {
    /**
     * Whether this app may edit or delete the row. The prototype does not edit currencies (it
     * never sends `currency`/`exchange_rate`), and a `PUT` without them makes the backend store
     * the row as a plain base-currency amount: `original_amount`, `original_currency` and
     * `exchange_rate` would be erased by a change to the description alone. So any row carrying
     * any of them stays read-only, whatever its currency. A row without a date is read-only too:
     * the full-replacement `PUT` would have to invent one.
     */
    val isEditable: Boolean
        get() = editable && originalAmount == null && originalCurrency == null && exchangeRate == null &&
            transactionDate?.take(10)?.let { DATE.matches(it) } == true

    /** The row carries currency data (typed or received in another currency). */
    val hasCurrencyData: Boolean get() = originalAmount != null || originalCurrency != null || exchangeRate != null

    private val hasValidDate: Boolean get() = transactionDate?.take(10)?.let { DATE.matches(it) } == true

    /**
     * A manual income or expense typed in another currency can be edited safely by sending its
     * currency and the user's own rate back (`PUT /free/movements` accepts both for `salary` /
     * `expense`): the backend recomputes the base amount exactly as when it was created. Needs
     * the complete original data and a currency this backend converts ([entryCurrencies]). Mail
     * transactions and partial data stay read-only.
     */
    fun isCurrencyEditable(entryCurrencies: List<String>): Boolean {
        val currency = originalCurrency?.uppercase() ?: return false
        return editable && hasValidDate && origin in MANUAL_ORIGINS && originalAmount != null && exchangeRate != null &&
            exchangeRate.signum() > 0 && entryCurrencies.any { it.equals(currency, ignoreCase = true) }
    }

    /** Whether this app may edit or delete the row at all. */
    fun canEdit(entryCurrencies: List<String>): Boolean = isEditable || isCurrencyEditable(entryCurrencies)

    /** Manual income/expense rows may switch to another currency on edit (the backend converts). */
    val acceptsCurrency: Boolean get() = origin in MANUAL_ORIGINS

    /** The backend sends only "income" or "expense"; anything else is money leaving. */
    val kind: MovementKind get() = if (transactionType == "income") MovementKind.INCOME else MovementKind.EXPENSE
    val day: String? get() = transactionDate?.take(10)

    companion object {
        private val DATE = Regex("""\d{4}-\d{2}-\d{2}""")
        private val MANUAL_ORIGINS = setOf("salary", "expense")
    }
}

/**
 * Body of `POST /user-product/finance/income` | `/expenses`. [amount] is in [currency] when one is
 * sent (then [exchangeRate], colones per 1 dollar, typed by the user, is required); without a
 * currency it is in the base currency. DINCR never invents a rate.
 */
@Serializable
data class EntryCreate(
    val amount: Money,
    val description: String,
    val category: String,
    @SerialName("entry_date") val entryDate: String?,
    val currency: String? = null,
    @SerialName("exchange_rate") val exchangeRate: Money? = null,
)

/** Body of `PUT /user-product/free/movements/{id}`; currency and rate as in [EntryCreate]. */
@Serializable
data class MovementUpdate(
    @SerialName("transaction_date") val transactionDate: String,
    val description: String,
    val amount: Money,
    @SerialName("transaction_type") val transactionType: String,
    val category: String,
    val notes: String = "",
    val currency: String? = null,
    @SerialName("exchange_rate") val exchangeRate: Money? = null,
)

/** Body of `POST /auth/profile-setup`. */
@Serializable
data class ProfileSetup(
    @SerialName("display_name") val displayName: String,
    @SerialName("usage_goal") val usageGoal: String,
    @SerialName("base_currency") val baseCurrency: String,
    @SerialName("enabled_currencies") val enabledCurrencies: List<String>,
    @SerialName("number_format") val numberFormat: String,
    @SerialName("currency_placement") val currencyPlacement: String,
    @SerialName("selected_financial_institutions") val selectedFinancialInstitutions: List<String>,
)

@Serializable
internal data class ProfileEnvelope(val profile: Profile)
