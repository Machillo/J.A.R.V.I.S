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
// the rest (Json { ignoreUnknownKeys = true }). Same contract as the iOS DincrCore models;
// pinned by fixture tests because OpenAPI has no response schemas yet.

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
    val id: String,
    val email: String? = null,
    @SerialName("display_name") val displayName: String? = null,
    val role: String? = "user",
    @SerialName("plan_selected") val planSelected: Boolean? = true,
    @SerialName("profile_setup_completed") val profileSetupCompleted: Boolean? = true,
    @SerialName("base_currency") val baseCurrency: String? = "CRC",
    @SerialName("number_format") val numberFormat: String? = "dot_comma",
    @SerialName("currency_placement") val currencyPlacement: String? = "before",
    val subscription: Subscription? = null,
    val legal: Legal? = null,
) {
    @Serializable
    data class Subscription(val plan: String? = null, val status: String? = null)

    @Serializable
    data class Legal(
        val required: Boolean? = null,
        @SerialName("terms_version") val termsVersion: String? = null,
        @SerialName("privacy_version") val privacyVersion: String? = null,
    )

    /** Owner/admin sessions are never served by the public app (Owner boundary). */
    val isOwner: Boolean get() = role == "owner" || role == "admin"
    val plan: String get() = subscription?.plan ?: "free"
    val firstName: String?
        get() = (displayName ?: email?.substringBefore("@"))?.trim()?.split(" ")?.firstOrNull()?.takeIf { it.isNotEmpty() }
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
    @SerialName("source_id") val sourceId: Int? = null,
    val origin: String? = null,
    @SerialName("transaction_date") val transactionDate: String? = null,
    val description: String? = null,
    val amount: Money,
    @SerialName("transaction_type") val transactionType: String? = null,
    val category: String? = null,
    val notes: String? = null,
    val editable: Boolean = false,
    /** Present once movements carry their own currency (multi-currency work in progress). */
    val currency: String? = null,
) {
    /** Anything that is not income is money leaving (expense, debt payment). */
    val kind: MovementKind get() = if (transactionType == "income") MovementKind.INCOME else MovementKind.EXPENSE
    val day: String? get() = transactionDate?.take(10)
}

/** Body of `POST /user-product/finance/income` | `/expenses`. */
@Serializable
data class EntryCreate(
    val amount: Money,
    val description: String,
    val category: String,
    @SerialName("entry_date") val entryDate: String?,
)

/** Body of `PUT /user-product/free/movements/{id}`. */
@Serializable
data class MovementUpdate(
    @SerialName("transaction_date") val transactionDate: String,
    val description: String,
    val amount: Money,
    @SerialName("transaction_type") val transactionType: String,
    val category: String,
    val notes: String = "",
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
