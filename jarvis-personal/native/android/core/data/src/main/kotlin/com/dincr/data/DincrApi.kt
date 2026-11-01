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

    // --- Personal appearance (APP-1: the Owner only; the backend refuses everyone else) ---------
    suspend fun appearance(): AppearanceState = client.get("/user-product/appearance")
    suspend fun saveAppearance(prefs: AppearancePrefs): AppearanceState = client.send("PUT", "/user-product/appearance", prefs.sanitized())
    suspend fun resetAppearance(): AppearanceState = client.send("DELETE", "/user-product/appearance")

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
    /**
     * [paidWith] only for an expense: [PaidWithChange.Unchanged] leaves the stored link as it is (the
     * key is not sent); a cleared link travels as an explicit null, so that body is built by hand.
     */
    suspend fun update(movementId: String, update: MovementUpdate, paidWith: PaidWithChange = PaidWithChange.Unchanged) {
        val path = "/user-product/free/movements/${encode(movementId)}"
        if (paidWith !is PaidWithChange.Set) {
            client.send<MovementUpdate, Acknowledgement>("PUT", path, update)
            return
        }
        val fields = client.json.encodeToJsonElement(MovementUpdate.serializer(), update) as kotlinx.serialization.json.JsonObject
        client.send<kotlinx.serialization.json.JsonObject, Acknowledgement>("PUT", path, kotlinx.serialization.json.JsonObject(
            fields + ("financial_account_id" to kotlinx.serialization.json.JsonPrimitive(paidWith.accountId))))
    }
    /** The own accounts and cards an expense can say it was paid with. */
    suspend fun paidWithOptions(): PaidWithOptions = client.get("/user-product/finance/expenses/paid-with-options")
    /** The dollar expenses waiting for the close, with their totals per currency. */
    suspend fun pendingConversion(): PendingConversion = client.get("/user-product/finance/expenses/pending-conversion")
    /** The close (3d): converts every expense waiting in one period with the user's one rate. */
    suspend fun closePending(close: PendingClose, idempotencyKey: String): PendingCloseResult =
        client.send("POST", "/user-product/finance/expenses/pending-conversion/close", close, idempotencyKey)
    suspend fun delete(movementId: String) {
        client.send<Acknowledgement>("DELETE", "/user-product/free/movements/${encode(movementId)}")
    }

    // --- Debts --------------------------------------------------------------------------------------
    suspend fun debts(): List<Debt> = client.get("/user-product/finance/debts")
    suspend fun createDebt(request: DebtRequest, key: String): Debt = client.send("POST", "/user-product/finance/debts", request.checked(), key)
    suspend fun updateDebt(id: Long, request: DebtRequest, key: String): Debt = client.send("PUT", "/user-product/finance/debts/$id", request.checked(), key)
    suspend fun deleteDebt(id: Long): Acknowledgement = client.send("DELETE", "/user-product/finance/debts/$id")
    /** DEB-07a — the payments recorded in DINCR for this debt, newest first (read-only). */
    suspend fun debtPayments(id: Long): List<DebtPayment> = client.get("/user-product/finance/debts/$id/payments")
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

    // --- Plan: strategy, distribution, Salvavidas ----------------------------------------------------
    /** VIP Users' director strategy (`strategy.scope == "users"`). */
    suspend fun strategyDashboard(): StrategyDashboard = client.get("/user-product/vip/strategy-dashboard")
    /** The Owner's strategy (`strategy.scope == "owner"`): only called when `/auth/me` says owner ([StrategyContract]). */
    suspend fun ownerStrategyDashboard(): StrategyDashboard = client.get("/jarvis/premium/strategy-dashboard")
    suspend fun debtSavingsBlocks(): DebtSavingsBlocks = client.get("/jarvis/premium/debt-savings-blocks")
    suspend fun createDebtSavingsBlock(request: DebtSavingsBlockCreate): Acknowledgement =
        client.send("POST", "/jarvis/premium/debt-savings-blocks", request)
    suspend fun cancelDebtSavingsBlock(id: String): Acknowledgement = client.send("DELETE", "/jarvis/premium/debt-savings-blocks/${encode(id)}")
    /** Owner only (phase 1): the same strategy applied to an amount the Owner confirms. Writes nothing. */
    suspend fun ownerExactDistribution(request: ExactDistributionRequest): StrategyDashboard =
        client.send("POST", "/jarvis/premium/strategy-dashboard/exact-distribution", request)
    /** Owner only: CONFIRMAR — records the distribution the Owner carried out, once per confirmation key. */
    suspend fun ownerConfirmExactDistribution(request: ExactDistributionConfirmRequest): ExactDistributionConfirmation =
        client.send("POST", "/jarvis/premium/strategy-dashboard/exact-distribution/confirm", request)
    /** FA-1: VIP and the Owner. A read: it never writes. */
    suspend fun financialAnalysis(): FinancialAnalysis = client.get("/user-product/vip/financial-analysis")
    /** WE-2: VIP and the Owner. A read: it never writes. */
    suspend fun wealth(): Wealth = client.get("/user-product/vip/wealth")
    /** RT-1: VIP and the Owner. */
    suspend fun retirement(): Retirement = client.get("/user-product/vip/retirement")
    suspend fun updateRetirement(update: RetirementUpdate): Retirement = client.send("PUT", "/user-product/vip/retirement", update)
    suspend fun salvavidas(): Salvavidas = client.get("/user-product/vip/salvavidas")
    suspend fun updateSalvavidas(update: SalvavidasUpdate): Salvavidas = client.send("PUT", "/user-product/vip/salvavidas", update)

    // --- VIP ----------------------------------------------------------------------------------------
    suspend fun commandCenter(): CommandCenter = client.get("/user-product/vip/command-center")
    suspend fun strategyVip(): Strategy = client.get("/user-product/finance/strategy-vip")
    suspend fun simulate(request: ScenarioRequest): ScenarioResult = client.send("POST", "/user-product/finance/strategy-vip/simulate", request)
    suspend fun debtScenario(request: DebtScenarioRequest): DebtScenarioResult = client.send("POST", "/user-product/finance/strategy-vip/debt-scenario", request)
    suspend fun aguinaldo(): Aguinaldo = client.get("/user-product/vip/aguinaldo")
    suspend fun monthlyReview(period: String): MonthlyReview = client.get("/user-product/vip/lifecycle/monthly-review", mapOf("period" to period))
    suspend fun proactiveAdvisor(): ProactiveAdvisor = client.get("/user-product/vip/lifecycle/proactive-advisor")

    /**
     * DINCR → Hoy. The proactive advisor compares today with an earlier saved observation; until one
     * exists it answers BASELINE with no alerts. Meanwhile the command center already computes the
     * current alerts (the main Today shows them), so this surface shows those, read-only and labelled
     * as the current situation, instead of "nothing urgent". Not BASELINE: the advisor alone.
     */
    suspend fun dincrToday(): DincrToday {
        val advisor = proactiveAdvisor()
        if (advisor.status != "BASELINE") return DincrToday(advisor, null)
        val current = try { commandCenter().alerts } catch (e: kotlin.coroutines.cancellation.CancellationException) { throw e } catch (_: Exception) { null }
        return DincrToday(advisor, current)
    }

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
    /** The same review inbox, for one bank (as the candidates name it) or one detected account (Cuentas). */
    suspend fun mailCandidates(bank: String? = null, financialAccountId: Long? = null): List<MailCandidate> =
        client.get<MailCandidateList>("/user-product/vip/gmail/emails", buildMap {
            put("status", "")
            bank?.trim()?.takeIf { it.isNotEmpty() }?.let { put("bank", it.take(80)) }
            financialAccountId?.takeIf { it > 0 }?.let { put("financial_account_id", it.toString()) }
        }).items
    suspend fun acceptCandidate(id: Long): CandidateReviewResult = client.send("POST", "/user-product/vip/gmail/candidates/$id/accept")
    suspend fun correctCandidate(id: Long, correction: CandidateCorrection): CandidateReviewResult =
        client.send("PUT", "/user-product/vip/gmail/candidates/$id/accept", correction.checked())
    suspend fun rejectCandidate(id: Long): CandidateReviewResult = client.send("POST", "/user-product/vip/gmail/candidates/$id/reject")
    suspend fun ownTransferSuggestions(): OwnTransferSuggestions = client.get("/user-product/vip/gmail/own-transfer-suggestions")
    suspend fun confirmOwnTransfer(candidateId: Long, request: OwnTransferRequest): Acknowledgement =
        client.send("POST", "/user-product/vip/gmail/candidates/$candidateId/own-transfer", request)
    suspend fun financialIdentity(): FinancialIdentity = client.get("/user-product/vip/financial-identity")
    suspend fun setAccountOwnership(id: Long, own: Boolean): Acknowledgement =
        setAccountOwnership(id, if (own) AccountOwnership.OWN else AccountOwnership.NOT_MINE)
    suspend fun setAccountOwnership(id: Long, ownership: AccountOwnership): Acknowledgement =
        client.send("PUT", "/user-product/vip/financial-identity/accounts/$id", OwnershipRequest(ownership.wire))
    /**
     * Sets or clears (`null`) an own credit card's statement cut day. The key always travels, even as
     * an explicit null: the client drops null fields, so the body is built by hand.
     */
    suspend fun setStatementCutDay(id: Long, day: Int?): Acknowledgement =
        client.send("PUT", "/user-product/vip/financial-identity/accounts/$id/statement-cut-day",
            kotlinx.serialization.json.buildJsonObject { put("statement_cut_day", kotlinx.serialization.json.JsonPrimitive(day)) })
    /** Marks as own an account no notice came from; the backend re-evaluates the pending notices. */
    suspend fun declareOwnAccount(declaration: OwnAccountDeclaration): FinancialAccountResult =
        client.send("POST", "/user-product/vip/financial-identity/accounts", declaration)

    // --- JARVIS "Análisis financiero" (Owner; the routers are Owner-only on the server) --------------
    suspend fun transactionAnalysis(): TransactionAnalysis = client.get("/transactions/analysis/summary")
    suspend fun netWorth(): NetWorthReport = client.get("/finance/net-worth")
    suspend fun financialEngine(): FinancialEngineReport = client.get("/finance/engine")

    // --- JARVIS "Mi dinero" (Owner; `/finance/*` is Owner-only on the server) -------------------------
    // Saving or removing an account is an explicit Owner command, never retried on its own.
    suspend fun cycleReport(): CycleReport = client.get("/finance/cycle-report")
    suspend fun accountBalances(): AccountBalances = client.get("/finance/account-balances")
    /** Creates the account, or updates the one with the same name and last 4 digits, with this balance. */
    suspend fun saveAccountBalance(request: AccountBalanceRequest) {
        client.send<AccountBalanceRequest, Acknowledgement>("POST", "/finance/account-balances", request)
    }
    /** Removes the account from the Owner's accounts (the backend deactivates it). */
    suspend fun removeAccountBalance(id: Long) {
        client.send<Acknowledgement>("DELETE", "/finance/account-balances/$id")
    }

    // --- JARVIS "Patrimonio" (Owner; `/finance/*` is Owner-only on the server) -----------------------
    // The reads never write. The writes are explicit Owner commands, never retried on their own.
    suspend fun investmentCenter(): InvestmentCenter = client.get("/finance/investment-center")
    /** Asks the server to refresh the snapshot from IBKR (an external call that can fail). */
    suspend fun syncIbkr(): IbkrSyncResult = client.send("POST", "/finance/investment-center/sync-ibkr")
    suspend fun businessCenter(): BusinessCenter = client.get("/finance/business-center")
    suspend fun createBusiness(request: BusinessCreateRequest): BusinessWriteResult =
        client.send("POST", "/finance/business-center/businesses", request)
    /** An income or expense also creates a transaction in the Owner's ledger. */
    suspend fun addBusinessMovement(request: BusinessMovementRequest): BusinessWriteResult =
        client.send("POST", "/finance/business-center/movements", request)

    // --- JARVIS "Registros" (Owner; `/finance/*` is Owner-only on the server) -------------------------
    suspend fun moneyTimeline(days: Int = 45): MoneyTimeline = client.get("/finance/timeline", mapOf("days" to days.toString()))
    suspend fun reconciliation(): Reconciliation = client.get("/finance/reconciliation")
    /** An explicit Owner command, never retried on its own. */
    suspend fun confirmReconciliation(accountId: Long, request: ReconciliationConfirmRequest): ReconciliationConfirmResult =
        client.send("POST", "/finance/reconciliation/$accountId/confirm", request)

    // --- JARVIS "Control de dinero" (Owner; `/finance/*` is Owner-only on the server) ----------------
    // The writes are explicit Owner commands, never retried on their own: the backend does not deduplicate them.
    suspend fun receivables(): ReceivablesReport = client.get("/finance/receivables")
    suspend fun recordReceivablePayment(id: Long, request: ReceivablePaymentRequest) =
        checkWrite(client.send<ReceivablePaymentRequest, ReceivableWriteResult>("POST", "/finance/receivables/$id/payments", request))
    suspend fun addReceivableEntry(request: ReceivableEntryRequest) =
        checkWrite(client.send<ReceivableEntryRequest, ReceivableWriteResult>("POST", "/finance/receivables/entries", request))

    suspend fun additionalCards(): AdditionalCards = client.get("/finance/additional-cards")
    /** Marks a card as carried by [personName]; its pending purchase notices become that person's debt. */
    suspend fun saveAdditionalCard(last4: String, personName: String): AdditionalCardResult =
        client.send("PUT", "/finance/additional-cards/$last4", AdditionalCardRequest(personName))
    /** The card is not additional any more: its settled purchases go back to review. Nothing is deleted. */
    suspend fun stopAdditionalCard(last4: String): AdditionalCardResult = client.send("DELETE", "/finance/additional-cards/$last4")

    // --- Plan → Gastos fijos (Owner; `/finance/*` is Owner-only on the server) -----------------------
    suspend fun ownerFixedExpenses(): List<OwnerFixedExpense> = client.get("/finance/fixed-expenses")
    suspend fun createOwnerFixedExpense(request: OwnerFixedExpenseRequest) {
        client.send<OwnerFixedExpenseRequest, kotlinx.serialization.json.JsonElement>("POST", "/finance/fixed-expenses", request)
    }
    suspend fun updateOwnerFixedExpense(id: Long, request: OwnerFixedExpenseRequest) {
        client.send<OwnerFixedExpenseRequest, kotlinx.serialization.json.JsonElement>("PUT", "/finance/fixed-expenses/$id", request)
    }
    /** Removes it from the list: the backend deactivates the row; nothing else is deleted. */
    suspend fun removeOwnerFixedExpense(id: Long) {
        client.send<kotlinx.serialization.json.JsonElement>("DELETE", "/finance/fixed-expenses/$id")
    }

    /** The backend refuses these writes in the body with HTTP 200: an error, never "saved". */
    private fun checkWrite(result: ReceivableWriteResult) {
        if (!result.succeeded) throw ApiError(ApiError.Kind.VALIDATION, code = result.status.orEmpty(), message = result.message ?: "No pudimos guardarlo.")
    }

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
