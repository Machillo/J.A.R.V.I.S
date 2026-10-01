package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Mail automation (VIP): connection status, candidates detected in bank notices, review and
// account ownership. The backend parses mail deterministically; nothing is saved without the
// user's review, and a candidate in another currency needs the user's own exchange rate.

/** `GET /user-product/vip/gmail/status`. */
@Serializable
data class MailStatus(
    val connected: Boolean = false,
    @SerialName("needs_reauthorization") val needsReauthorization: Boolean = false,
    val pending: Int? = null,
    @SerialName("microsoft_available") val microsoftAvailable: Boolean = false,
    val consent: Consent? = null,
    val connections: List<Connection> = emptyList(),
) {
    /** The server also lists disconnected (`disabled`) mailboxes; the user sees only the others. */
    val visibleConnections: List<Connection> get() = connections.filter { it.status != "disabled" }

    @Serializable
    data class Consent(val required: Boolean = true, val version: String? = null)

    @Serializable
    data class Connection(
        val id: Long,
        val provider: String? = null,
        @SerialName("google_email") val email: String? = null,
        val status: String? = null,
        @SerialName("automatic_updates") val automaticUpdates: Boolean? = null,
        @SerialName("import_since") val importSince: String? = null,
    )
}

@Serializable
data class MailConsentRequest(val accepted: Boolean, val version: String)

@Serializable
data class MailConnectRequest(
    @SerialName("import_scope") val importScope: String,
    /** The app language (`en`/`es`), for the provider's consent screens. */
    val locale: String,
)

@Serializable
data class MailConnectResponse(@SerialName("authorization_url") val authorizationUrl: String)

@Serializable
data class MailCompleteRequest(val flow: String, val completion: String)

@Serializable
data class MailCompleteResponse(val status: String? = null, val provider: String? = null, @SerialName("already_completed") val alreadyCompleted: Boolean? = null)

/** `POST /user-product/vip/gmail/sync`. */
@Serializable
data class MailSyncResult(
    val status: String? = null,
    val found: Int? = null,
    val pending: Int? = null,
    val duplicates: Int? = null,
    @SerialName("auto_saved") val autoSaved: Int? = null,
    @SerialName("scan_scope") val scanScope: String? = null,
    @SerialName("initial_scan_complete") val initialScanComplete: Boolean? = null,
    /** Ids of the mailboxes that could not be checked (`status` is then `partial`). */
    @SerialName("failed_connections") val failedConnections: List<Long> = emptyList(),
)

/** `GET /user-product/vip/gmail/emails`: an envelope, not a bare list. */
@Serializable
data class MailCandidateList(val status: String? = null, val items: List<MailCandidate> = emptyList())

/** A row of `GET /user-product/vip/gmail/emails`. */
@Serializable
data class MailCandidate(
    @SerialName("candidate_id") val candidateId: Long? = null,
    @SerialName("email_id") val emailId: Long? = null,
    @SerialName("related_candidate_id") val relatedCandidateId: Long? = null,
    val bank: String? = null,
    val sender: String? = null,
    val subject: String? = null,
    @SerialName("received_at") val receivedAt: String? = null,
    val description: String? = null,
    val amount: Money? = null,
    val currency: String? = null,
    @SerialName("original_amount") val originalAmount: Money? = null,
    @SerialName("original_currency") val originalCurrency: String? = null,
    @SerialName("account_base_currency") val accountBaseCurrency: String? = null,
    @SerialName("transaction_date") val transactionDate: String? = null,
    @SerialName("transaction_type") val transactionType: String? = null,
    val category: String? = null,
    @SerialName("review_status") val reviewStatus: String? = null,
    @SerialName("resolution_reason") val resolutionReason: String? = null,
    @SerialName("is_internal_transfer") val isInternalTransfer: Boolean? = null,
    @SerialName("source_type") val sourceType: String? = null,
    @SerialName("parse_reason") val parseReason: String? = null,
    /** The detected account (`/vip/financial-identity`) this notice belongs to, when known. */
    @SerialName("financial_account_id") val financialAccountId: Long? = null,
    /** Parser codes kept as text (may be null); shown nowhere as money. */
    @SerialName("bank_movement") val bankMovement: String? = null,
    @SerialName("financial_effect") val financialEffect: String? = null,
) {
    /**
     * The money as the bank notice stated it. The parser's converted `amount` is not trusted when
     * the notice was in another currency (backend `candidate_currency`): the native pair is
     * `(original_currency, original_amount)` then.
     */
    val nativeCurrency: String? get() =
        if (!originalCurrency.isNullOrBlank() && originalAmount != null && !originalCurrency.equals(currency, ignoreCase = true)) originalCurrency.uppercase() else currency?.uppercase()
    val nativeAmount: java.math.BigDecimal? get() =
        if (!originalCurrency.isNullOrBlank() && originalAmount != null && !originalCurrency.equals(currency, ignoreCase = true)) originalAmount else amount

    val isPending: Boolean get() = reviewStatus == "pending"

    /** The account's currency; missing means CRC, as `candidate_currency.transaction_amounts` reads it. */
    private val baseCurrency: String get() = accountBaseCurrency?.takeIf { it.isNotBlank() }?.uppercase() ?: "CRC"

    /** The base currency differs and both are convertible: accepting needs the user's rate. */
    val needsRate: Boolean get() {
        val native = nativeCurrency ?: return false
        return native != baseCurrency && native in CONVERTIBLE && baseCurrency in CONVERTIBLE
    }

    /** Another currency DINCR cannot convert: the notice can only be rejected. */
    val cannotConvert: Boolean get() {
        val native = nativeCurrency ?: return false
        return native != baseCurrency && !(native in CONVERTIBLE && baseCurrency in CONVERTIBLE)
    }

    /**
     * What `resolution_reason` means for the user. The field is an internal code: only the reasons
     * a pending notice can carry get a note, and any other code shows nothing.
     */
    val resolutionNote: ResolutionNote? get() = when {
        resolutionReason == "possible_cross_source_match" -> ResolutionNote.POSSIBLE_MATCH
        isInternalTransfer != true -> null
        resolutionReason == "paired_owned_transfer" -> ResolutionNote.PAIRED_OWN_TRANSFER
        resolutionReason == "confirmed_owned_endpoints" -> ResolutionNote.OWN_ACCOUNTS
        else -> null
    }

    enum class ResolutionNote { POSSIBLE_MATCH, PAIRED_OWN_TRANSFER, OWN_ACCOUNTS }

    companion object {
        val CONVERTIBLE = setOf("CRC", "USD")
    }
}

/** Body of `PUT /vip/gmail/candidates/{id}/accept` (accept with corrections). */
@Serializable
data class CandidateCorrection(
    @SerialName("transaction_date") val transactionDate: String,
    val description: String,
    /** In the notice's own currency. */
    val amount: Money,
    @SerialName("transaction_type") val transactionType: String,
    /** Always sent: omitting it would reset the category to "general". */
    val category: String,
    /** Colones per 1 dollar, typed by the user; only when the notice is in another currency. */
    @SerialName("exchange_rate") val exchangeRate: Money? = null,
)

/** Answer of accept / reject. `already_reviewed` means nothing changed now. */
@Serializable
data class CandidateReviewResult(
    val status: String? = null,
    @SerialName("candidate_id") val candidateId: Long? = null,
    @SerialName("transaction_id") val transactionId: Long? = null,
    @SerialName("already_reviewed") val alreadyReviewed: Boolean? = null,
    @SerialName("is_internal_transfer") val isInternalTransfer: Boolean? = null,
)

/** `GET /user-product/vip/financial-identity`. */
@Serializable
data class FinancialIdentity(val items: List<Account> = emptyList(), val summary: Summary? = null) {
    @Serializable
    data class Account(
        val id: Long,
        @SerialName("account_name") val accountName: String? = null,
        @SerialName("bank_name") val bankName: String? = null,
        @SerialName("institution_code") val institutionCode: String? = null,
        @SerialName("institution_country") val institutionCountry: String? = null,
        @SerialName("account_type") val accountType: String? = null,
        val currency: String? = null,
        @SerialName("account_last4") val accountLast4: String? = null,
        @SerialName("ownership_status") val ownershipStatus: String? = null,
    )

    @Serializable
    data class Summary(val total: Int? = null, val pending: Int? = null)
}

@Serializable
data class OwnershipRequest(@SerialName("ownership_status") val ownershipStatus: String, @SerialName("display_name") val displayName: String? = null)

/** `GET /vip/gmail/own-transfer-suggestions`. */
@Serializable
data class OwnTransferSuggestions(val items: List<Pair_> = emptyList()) {
    @Serializable
    data class Pair_(val first: Side? = null, val second: Side? = null)

    @Serializable
    data class Side(
        @SerialName("candidate_id") val candidateId: Long? = null,
        val bank: String? = null,
        val date: String? = null,
        val direction: String? = null,
        @SerialName("reference_end") val referenceEnd: String? = null,
        val amount: Money? = null,
        val currency: String? = null,
    )
}

@Serializable
data class OwnTransferRequest(
    @SerialName("counterpart_id") val counterpartId: Long,
    @SerialName("confirm_owned_accounts") val confirmOwnedAccounts: Boolean = true,
    @SerialName("unknown_direction") val unknownDirection: String? = null,
) {
    companion object {
        /**
         * The direction to declare for the notice whose direction is unknown: a transfer between
         * the user's own accounts leaves one and enters the other, so it is the opposite of the
         * known side (shown to the user before confirming). Null when both are known (nothing to
         * declare); [CANNOT_INFER] when neither side is known — the pair must be reviewed apart.
         */
        fun unknownDirection(first: String?, second: String?): String? {
            val a = first.takeIf { it == "in" || it == "out" }
            val b = second.takeIf { it == "in" || it == "out" }
            return when {
                a != null && b != null -> null
                a != null -> if (a == "in") "out" else "in"
                b != null -> if (b == "in") "out" else "in"
                else -> CANNOT_INFER
            }
        }

        const val CANNOT_INFER = "?"
    }
}
