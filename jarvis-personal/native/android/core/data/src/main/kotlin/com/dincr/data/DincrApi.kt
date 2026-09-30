package com.dincr.data

import java.net.URLEncoder
import java.util.UUID
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/**
 * Every backend operation the public DINCR app uses, 1:1 with the FastAPI routes the Capacitor app
 * calls (see native/CONTRACT.md). The backend is authoritative: plans (402/403), kill switches
 * (503 feature_temporarily_unavailable), workspace scoping and money bounds are enforced there;
 * this client adds the same bounds before sending so a bad value never reaches the database.
 *
 * Writes the backend can deduplicate carry an `X-Idempotency-Key`: one key per user submission,
 * reused when the same submission is retried ([IdempotencyKey]).
 */
class DincrApi(private val client: ApiClient) {
    // --- Identity, legal, onboarding, plans --------------------------------------------------
    suspend fun me(): Profile = client.get("/auth/me")
    suspend fun deleteAccount(): Acknowledgement = client.send("DELETE", "/auth/me")
    suspend fun exportData(): JsonElement = client.get("/auth/me/export")
    suspend fun acceptLegal(request: LegalAcceptRequest): LegalAcceptResult = client.send("POST", "/auth/legal/accept", request)
    suspend fun completeProfileSetup(setup: ProfileSetup): Profile =
        client.send<ProfileSetup, ProfileEnvelope>("POST", "/auth/profile-setup", setup).profile
    suspend fun plans(): List<PlanOption> = client.get("/auth/plans")
    suspend fun choosePlan(request: PlanChangeRequest): PlanChangeResult = client.send("POST", "/auth/plan", request)
    suspend fun billingCatalog(): BillingCatalog = client.get("/product-ops/billing/catalog")

    // --- Operations ------------------------------------------------------------------------------
    suspend fun featureFlags(): FeatureFlags = client.get("/product-ops/feature-flags")
    suspend fun health(): ServiceHealth = client.get("/product-ops/health")
    suspend fun releasePolicy(version: String): ReleasePolicy =
        client.getPublic("/product-ops/release-policy", mapOf("platform" to "android", "version" to version))
    suspend fun recordEvent(event: ProductEvent) {
        if (event.eventName !in ProductEvent.ALLOWED) return
        client.send<ProductEvent, Acknowledgement>("POST", "/product-ops/events", event)
    }
    suspend fun supportTickets(): List<SupportTicket> = client.get("/product-ops/feedback")
    suspend fun createSupportTicket(request: SupportRequest): SupportCreated = client.send("POST", "/product-ops/feedback", request)

    /**
     * JARVIS (Owner): one chat message and the engine's answer. A POST: never retried on its own (a
     * change is saved only after the Owner's "sí", itself a new message).
     */
    /** JARVIS agenda (Owner): the historical upcoming events, from today to [days] out, in order. */
    suspend fun jarvisUpcomingEvents(days: Int = JarvisAgenda.DAYS): List<JarvisEvent> =
        JarvisAgenda.from(client.get<kotlinx.serialization.json.JsonElement>("/jarvis/calendar/upcoming", mapOf("days" to days.toString())))
            ?: throw ApiError.decoding(client.currentLanguage)

    suspend fun jarvisChat(message: String): JarvisChatReply =
        JarvisChatReply.from(client.send<JarvisChatRequest, kotlinx.serialization.json.JsonElement>("POST", "/jarvis/chat", JarvisChatRequest(message)))
            ?: throw ApiError.decoding(client.currentLanguage)
    suspend fun resolveTicket(id: Long, resolved: Boolean): Acknowledgement =
        client.send("PATCH", "/product-ops/feedback/$id/resolution", ResolutionRequest(if (resolved) "resolved" else "still_happening"))

    // --- Movements ---------------------------------------------------------------------------------
    suspend fun freeDashboard(): FreeDashboard = client.get("/user-product/free/dashboard")
    suspend fun monthlySummary(period: String): MonthlySummary = client.get("/user-product/free/monthly-summary", mapOf("period" to period))
    suspend fun movements(): List<Movement> = client.get("/user-product/free/movements")
    suspend fun create(kind: MovementKind, entry: EntryCreate, idempotencyKey: String) {
        val path = if (kind == MovementKind.INCOME) "/user-product/finance/income" else "/user-product/finance/expenses"
        client.send<EntryCreate, JsonElement>("POST", path, entry, idempotencyKey)
    }
    suspend fun update(movementId: String, update: MovementUpdate) {
        client.send<MovementUpdate, Acknowledgement>("PUT", "/user-product/free/movements/${encode(movementId)}", update)
    }
    suspend fun delete(movementId: String) {
        client.send<Acknowledgement>("DELETE", "/user-product/free/movements/${encode(movementId)}")
    }

    // --- Debts --------------------------------------------------------------------------------------
    suspend fun debts(): List<Debt> = client.get("/user-product/finance/debts")
    suspend fun createDebt(request: DebtRequest, key: String): Debt = client.send("POST", "/user-product/finance/debts", request.checked(), key)
    suspend fun updateDebt(id: Long, request: DebtRequest, key: String): Debt = client.send("PUT", "/user-product/finance/debts/$id", request.checked(), key)
    suspend fun deleteDebt(id: Long): Acknowledgement = client.send("DELETE", "/user-product/finance/debts/$id")
    suspend fun payDebt(id: Long, amount: java.math.BigDecimal, key: String): DebtPaymentResult =
        client.send("POST", "/user-product/finance/debts/$id/payments", AmountRequest(amount), key)

    // --- Goals and savings plans ----------------------------------------------------------------------
    suspend fun goals(): List<Goal> = client.get("/user-product/goals")
    suspend fun createGoal(request: GoalRequest, key: String): Goal = client.send("POST", "/user-product/goals", request.checked(), key)
    suspend fun updateGoal(id: Long, request: GoalRequest, key: String): Goal = client.send("PUT", "/user-product/goals/$id", request.checked(), key)
    suspend fun deleteGoal(id: Long): Acknowledgement = client.send("DELETE", "/user-product/goals/$id")
    suspend fun contributeToGoal(id: Long, contribution: GoalContribution, key: String): Goal =
        client.send("POST", "/user-product/goals/$id/contributions", contribution.checked(), key)
    suspend fun savingsPlans(): List<SavingsPlan> = client.get("/user-product/savings-plans")
    suspend fun createSavingsPlan(request: SavingsPlanRequest, key: String): SavingsPlan = client.send("POST", "/user-product/savings-plans", request.checked(), key)
    suspend fun updateSavingsPlan(id: Long, request: SavingsPlanRequest, key: String): SavingsPlan = client.send("PUT", "/user-product/savings-plans/$id", request.checked(), key)
    suspend fun deleteSavingsPlan(id: Long): Acknowledgement = client.send("DELETE", "/user-product/savings-plans/$id")
    suspend fun contributeToSavingsPlan(id: Long, contribution: SavingsContribution, key: String): SavingsPlan =
        client.send("POST", "/user-product/savings-plans/$id/contributions", contribution.checked(), key)

    // --- Financial situation --------------------------------------------------------------------------
    suspend fun financialSituation(): FinancialSituation = client.get("/user-product/financial-situation")
    suspend fun updateFinancialSituation(profile: FinancialProfile, key: String): FinancialSituation =
        client.send("PUT", "/user-product/financial-situation", profile, key)

    // --- Basic ----------------------------------------------------------------------------------------
    suspend fun basicDashboard(): BasicDashboard = client.get("/user-product/basic/dashboard")
    suspend fun budget(): Budget = client.get("/user-product/basic/budget")
    suspend fun updateBudget(update: BudgetUpdate, key: String): Budget = client.send("PUT", "/user-product/basic/budget", update, key)
    suspend fun calendar(period: String): FinancialCalendar = client.get("/user-product/basic/calendar", mapOf("period" to period))
    suspend fun recurring(): RecurringList = client.get("/user-product/basic/recurring")
    suspend fun createRecurring(request: RecurringRequest, key: String): RecurringItem = client.send("POST", "/user-product/basic/recurring", request, key)
    suspend fun updateRecurring(id: Long, request: RecurringRequest, key: String): RecurringItem = client.send("PUT", "/user-product/basic/recurring/$id", request, key)
    suspend fun deleteRecurring(id: Long): Acknowledgement = client.send("DELETE", "/user-product/basic/recurring/$id")
    suspend fun report(period: String): MonthReport = client.get("/user-product/basic/reports", mapOf("period" to period))
    suspend fun strategyBasic(): Strategy = client.get("/user-product/finance/strategy-basic")

    // --- VIP ----------------------------------------------------------------------------------------
    suspend fun commandCenter(): CommandCenter = client.get("/user-product/vip/command-center")
    suspend fun strategyVip(): Strategy = client.get("/user-product/finance/strategy-vip")
    suspend fun simulate(request: ScenarioRequest): ScenarioResult = client.send("POST", "/user-product/finance/strategy-vip/simulate", request)
    suspend fun aguinaldo(): Aguinaldo = client.get("/user-product/vip/aguinaldo")
    suspend fun monthlyReview(period: String): MonthlyReview = client.get("/user-product/vip/lifecycle/monthly-review", mapOf("period" to period))
    suspend fun proactiveAdvisor(): ProactiveAdvisor = client.get("/user-product/vip/lifecycle/proactive-advisor")

    // --- Mail (VIP) -----------------------------------------------------------------------------------
    suspend fun mailStatus(): MailStatus = client.get("/user-product/vip/gmail/status")
    suspend fun acceptMailConsent(version: String): Acknowledgement =
        client.send("POST", "/user-product/vip/gmail/consent", MailConsentRequest(true, version))
    suspend fun connectMail(provider: MailReturn.Provider, importScope: String, language: AppLanguage): MailConnectResponse =
        client.send("POST", if (provider == MailReturn.Provider.GMAIL) "/user-product/vip/gmail/connect" else "/user-product/vip/mail/microsoft/connect", MailConnectRequest(importScope, language.tag))
    suspend fun completeMailConnection(flow: String, completion: String): MailCompleteResponse =
        client.send("POST", "/user-product/vip/mail/oauth/complete", MailCompleteRequest(flow, completion))
    suspend fun syncMail(): MailSyncResult = client.send("POST", "/user-product/vip/gmail/sync")
    suspend fun disconnectMail(connectionId: Long): Acknowledgement =
        client.send("DELETE", "/user-product/vip/gmail", mapOf("connection_id" to connectionId.toString()))
    suspend fun mailCandidates(pendingOnly: Boolean): List<MailCandidate> =
        client.get<MailCandidateList>("/user-product/vip/gmail/emails", mapOf("status" to if (pendingOnly) "pending" else "")).items
    suspend fun acceptCandidate(id: Long): CandidateReviewResult = client.send("POST", "/user-product/vip/gmail/candidates/$id/accept")
    suspend fun correctCandidate(id: Long, correction: CandidateCorrection): CandidateReviewResult =
        client.send("PUT", "/user-product/vip/gmail/candidates/$id/accept", correction.checked())
    suspend fun rejectCandidate(id: Long): CandidateReviewResult = client.send("POST", "/user-product/vip/gmail/candidates/$id/reject")
    suspend fun ownTransferSuggestions(): OwnTransferSuggestions = client.get("/user-product/vip/gmail/own-transfer-suggestions")
    suspend fun confirmOwnTransfer(candidateId: Long, request: OwnTransferRequest): Acknowledgement =
        client.send("POST", "/user-product/vip/gmail/candidates/$candidateId/own-transfer", request)
    suspend fun financialIdentity(): FinancialIdentity = client.get("/user-product/vip/financial-identity")
    suspend fun setAccountOwnership(id: Long, own: Boolean): Acknowledgement =
        client.send("PUT", "/user-product/vip/financial-identity/accounts/$id", OwnershipRequest(if (own) "own" else "not_mine"))

    // --- Store billing ----------------------------------------------------------------------------------
    suspend fun storeCatalog(): StoreCatalog = client.get("/product-ops/billing/store/catalog")
    suspend fun storeEntitlement(): StoreEntitlement = client.get("/product-ops/billing/store/entitlement")
    suspend fun storeCustomerToken(): CustomerToken = client.send("POST", "/product-ops/billing/store/customer-token")
    suspend fun verifyGooglePurchase(purchaseToken: String, productId: String): StoreVerification =
        client.send("POST", "/product-ops/billing/store/google/purchases", GooglePurchaseRequest(purchaseToken, productId))

    companion object {
        /** Movement ids look like `expense:42`; keep the colon, escape anything path-breaking. */
        fun encode(id: String): String = URLEncoder.encode(id, "UTF-8").replace("%3A", ":").replace("+", "%20")
    }
}

/** A generic `{status, ...}` answer. */
@Serializable
data class Acknowledgement(val status: String? = null)

/** One key per user submission: a retry of the same body reuses it, a new body gets a new key. */
object IdempotencyKey {
    fun new(): String = "op_" + UUID.randomUUID().toString().replace("-", "")
}

/**
 * The key of one amount submission (debt payment, contribution). Retrying the same amount after a
 * failure — including a timeout where the server did record it — reuses the key, so the backend
 * answers from the first request instead of recording the money twice. A different amount is a
 * new submission with a new key. `10000` and `10000.00` are the same amount.
 */
class AmountSubmission(private val newKey: () -> String = IdempotencyKey::new) {
    private var last: Pair<java.math.BigDecimal, String>? = null

    fun keyFor(amount: java.math.BigDecimal): String {
        last?.let { (previous, key) -> if (previous.compareTo(amount) == 0) return key }
        return newKey().also { last = amount to it }
    }
}
