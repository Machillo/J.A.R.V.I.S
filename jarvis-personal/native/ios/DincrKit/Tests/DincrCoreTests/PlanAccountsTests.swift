import Foundation
import Testing
@testable import DincrCore

/// Plan tab (Aguinaldo, Estrategia, Salvavidas, Distribución), the three strategy contracts, Cuentas
/// sharing the Email Monitor's review, bank logos, the situation's work days and the Owner's
/// analysis. Shapes are the backend's (ai/strategy_dashboard.py, finance/emergency_fund.py,
/// user_product/gmail_service.py, financial_identity.py). Android: `PlanAccountsTest.kt`.
@Suite struct PlanAccountsTests {
    func service(_ transport: ScriptedTransport) -> DincrService {
        DincrService(client: APIClient(baseURL: URL(string: "https://api.example.test")!, tokens: CountingTokens(), transport: transport, language: .spanish, backoff: { _ in }))
    }

    func profile(role: String = "user", plan: String?) -> Profile {
        Profile(id: 1, role: role, subscription: plan.map { Profile.Subscription(plan: $0, status: "active") })
    }

    static func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try APIClient.decoder.decode(type, from: Data(json.utf8))
    }

    static let allOn = FeatureFlags(flags: OpsFlag.allCases.map { FeatureFlags.Flag(flagKey: $0.rawValue, enabled: true) })
    static func off(_ flag: OpsFlag) -> FeatureFlags {
        FeatureFlags(flags: OpsFlag.allCases.map { FeatureFlags.Flag(flagKey: $0.rawValue, enabled: $0 != flag) })
    }

    // MARK: Plan tab

    @Test func planHasExactlyItsRowsInOrder() {
        // UX-4: Deudas joins Plan after "Tu plan del mes"; the other rows keep their order.
        #expect(PlanHubItem.allCases.map(\.rawValue) == ["aguinaldo", "strategy", "debts", "salvavidas", "distribution"])
    }

    @Test func eachRowKeepsItsHistoricalGate() {
        let on = Self.allOn
        // Debts are every plan's own reality: available to Free, never paused by an intelligence switch.
        #expect(PlanTier.allCases.allSatisfy { PlanHubItem.debts.availability(tier: $0, flags: on) == .available })
        #expect(PlanHubItem.debts.availability(tier: .free, flags: Self.off(.vipIntelligence)) == .available)
        #expect(PlanHubItem.strategy.availability(tier: .free, flags: on) == .locked(.basic))
        #expect(PlanHubItem.distribution.availability(tier: .free, flags: on) == .locked(.basic))
        #expect(PlanHubItem.salvavidas.availability(tier: .basic, flags: on) == .locked(.vip))
        #expect(PlanHubItem.aguinaldo.availability(tier: .basic, flags: on) == .locked(.vip))
        #expect(PlanHubItem.strategy.availability(tier: .basic, flags: on) == .available)
        #expect(PlanHubItem.distribution.availability(tier: .basic, flags: on) == .available)
        #expect(PlanHubItem.allCases.allSatisfy { $0.availability(tier: .vip, flags: on) == .available })
        // The aguinaldo and Salvavidas pause with vip_intelligence, not with gmail_automation.
        let paused = Self.off(.vipIntelligence)
        #expect(PlanHubItem.aguinaldo.availability(tier: .vip, flags: paused) == .paused(.vipIntelligence))
        #expect(PlanHubItem.salvavidas.availability(tier: .vip, flags: paused) == .paused(.vipIntelligence))
        #expect(PlanHubItem.strategy.availability(tier: .vip, flags: paused) == .available)
        #expect(PlanHubItem.aguinaldo.availability(tier: .vip, flags: Self.off(.gmailAutomation)) == .available)
        // The Owner passes every gate by the server role only.
        let owner = profile(role: "owner", plan: nil)
        #expect(PlanHubItem.allCases.allSatisfy { $0.availability(tier: owner.planTier, flags: on) == .available })
        #expect(PlanHubItem.strategy.availability(tier: profile(plan: "owner").planTier, flags: on) == .locked(.basic))
    }

    // MARK: Strategy: Basic ≠ VIP Users ≠ Owner

    @Test func strategySourceFollowsTheServerRoleAndPlan() {
        let on = Self.allOn
        #expect(StrategySource.of(profile(role: "owner", plan: "vip"), flags: on) == .ownerDashboard)
        #expect(StrategySource.of(profile(role: "owner", plan: nil), flags: on) == .ownerDashboard)
        #expect(StrategySource.of(profile(plan: "vip"), flags: on) == .usersDashboard)
        #expect(StrategySource.of(profile(plan: "vip"), flags: Self.off(.vipIntelligence)) == .basic)
        #expect(StrategySource.of(profile(plan: "basic"), flags: on) == .basic)
        #expect(StrategySource.of(profile(plan: "free"), flags: on) == .unavailable)
        #expect(StrategySource.of(nil, flags: on) == .unavailable)
        // A plan code or a look-alike role never opens the Owner's route.
        #expect(StrategySource.of(profile(plan: "owner"), flags: on) == .unavailable)
        #expect(StrategySource.of(profile(role: "Owner", plan: "vip"), flags: on) == .usersDashboard)
        #expect(StrategySource.of(profile(role: "admin", plan: "vip"), flags: on) != .ownerDashboard)
    }

    @Test func eachContractReadsItsOwnEndpoint() async throws {
        let basic = #"{"status":"healthy","monthly_income":865000,"income_source":"declared","allocations":[{"bucket":"emergency","label":"Reserva","amount":60000}]}"#
        let dashboard = #"{"status":"OK","user_role":"user","title":"T","content":"C","strategy":{"scope":"users","status":"controlled"},"source":"live_database"}"#
        let transport = ScriptedTransport([.status(200, basic), .status(200, dashboard), .status(200, dashboard)])
        let api = service(transport)
        _ = try await api.planStrategy(.basic)
        _ = try await api.planStrategy(.usersDashboard)
        _ = try await api.planStrategy(.ownerDashboard)
        #expect(transport.requests.map { $0.url!.path } == [
            "/user-product/finance/strategy-basic", "/user-product/vip/strategy-dashboard", "/jarvis/premium/strategy-dashboard",
        ])
        #expect(transport.requests.allSatisfy { $0.httpMethod == "GET" }, "reading a strategy never writes")
        await #expect(throws: APIError.self) { _ = try await api.planStrategy(.unavailable) }
        #expect(transport.requests.count == 3, "Free never calls a strategy route")
    }

    @Test func basicStrategySaysWhenTheIncomeIsObserved() throws {
        let observed = try Self.decode(Strategy.self, #"{"status":"healthy","income_source":"observed","income_basis":{"source":"observed","policy":"v1","observed_source":"recorded"}}"#)
        #expect(observed.usesObservedIncome && !observed.needsIncome)
        #expect(observed.incomeBasis?.observedSource == "recorded")
        let declared = try Self.decode(Strategy.self, #"{"status":"healthy","income_source":"declared","income_basis":{"source":"declared","policy":null}}"#)
        #expect(!declared.usesObservedIncome)
        let none = try Self.decode(Strategy.self, #"{"status":"needs_income","income_source":"none","allocations":[]}"#)
        #expect(none.needsIncome && PlanStrategy.basic(none).needsIncome)
        #expect(IncomeSourceLabel.observedNote(.spanish) == "Estimado con tus ingresos registrados (no declarado)")
        #expect(IncomeSourceLabel.observedNote(.english) == "Estimated from your recorded income (not declared)")
        #expect(IncomeSourceLabel.label("recorded", language: .spanish) == IncomeSourceLabel.observedNote(.spanish))
    }

    @Test func dashboardDecodingIsTolerantAndUsersNeverGetCash() throws {
        let users = try Self.decode(StrategyDashboard.self, #"""
        {"status":"OK","user_role":"user","extra":{"x":1},"strategy":{"scope":"users","status":"controlled","monthly_income":"oops",
         "safe_to_spend":64000,"distributable_account_cash":null,"timeline":"not-a-list","priority":{"kind":"debt","title":"Atacar deuda"},
         "emergency_fund":{"current":120000,"level":"one_month_building","unknown":true},
         "allocation_items":[{"key":"ataque_de_deuda","percentage":50.0,"amount":216550,"target_name":"Tarjeta"}],
         "distribution_formula":{"income":865000,"recorded_spending":312000,"debt_commitment":95000,"pending_recurring":24900,"surplus":433100,"deficit":0},
         "rules":["Regla"],"new_key":[1,2,3]}}
        """#)
        let plan = try #require(users.strategy)
        #expect(!plan.isOwnerScope && plan.monthlyIncome == nil, "an odd value is unknown, not zero")
        #expect(plan.timeline == nil && plan.safeToSpend == 64000 && plan.distributableAccountCash == nil)
        #expect(plan.emergencyFund?.current == 120000 && plan.priority?.kind == "debt")
        #expect(plan.distributionFormula?.lines.map { $0.key } == ["income", "recorded_spending", "debt_commitment", "pending_recurring", "surplus", "deficit"])
        let owner = try Self.decode(StrategyDashboard.self, #"""
        {"status":"OK","user_role":"owner","strategy":{"scope":"owner","distributable_account_cash":310000,"current_month_extra_net":45000,
         "mandatory_fixed_pending_items":[{"name":"Alquiler","amount":120000,"due_day":28}],"months_saved_by_current_extras":3,
         "distribution_formula":{"cash_available_now":310000,"income":495000,"statement_spending":180000,"new_spending_after_cut":42000,
           "debt_commitment":95000,"mandatory_fixed_pending":120000,"surplus":368000,"deficit":0}}}
        """#)
        let ownerPlan = try #require(owner.strategy)
        #expect(ownerPlan.isOwnerScope && ownerPlan.distributableAccountCash == 310000)
        #expect(ownerPlan.mandatoryFixedPendingItems?.first?.amount == 120000)
        #expect(ownerPlan.distributionFormula?.lines.first?.key == "cash_available_now")
        #expect(ownerPlan.distributionFormula?.lines.count == 8)
    }

    @Test func distributionLabelsAreTheHistoricalOnes() {
        #expect(DistributionLabels.bucket("meta_prioritaria", language: .spanish) == "Meta prioritaria")
        #expect(DistributionLabels.bucket("ataque_de_deuda", targetName: "Tarjeta", language: .spanish) == "Ataque de deuda · Tarjeta")
        #expect(DistributionLabels.bucket("ataque_de_deuda", language: .spanish) == "Ataque de deuda")
        #expect(DistributionLabels.bucket("fondo_de_emergencia", language: .spanish) == "Salvavidas")
        #expect(DistributionLabels.bucket("vida_controlada", language: .spanish) == "Vida controlada")
        #expect(DistributionLabels.bucket("inversion", language: .spanish) == "Inversión")
        #expect(DistributionLabels.bucket("metas_o_inversion", language: .spanish) == "Metas o inversión")
    }

    @Test func distributionReadsTheSameStrategyAnswer() async throws {
        // Estrategia and Distribución load the same contract: one answer carries both.
        let backend = FixtureBackend(scenario: .populated, plan: .vip, latency: .zero)
        let api = FixtureBackend.service(backend)
        guard case .dashboard(let dashboard) = try await api.planStrategy(.usersDashboard) else { Issue.record("expected the dashboard"); return }
        let plan = try #require(dashboard.strategy)
        #expect(plan.scope == "users" && plan.distributableAccountCash == nil)
        #expect(plan.allocationItems?.first?.key == "ataque_de_deuda" && plan.allocationItems?.first?.targetName == "Tarjeta de crédito")
        #expect(plan.distributionFormula?.cashAvailableNow == nil, "Users have no cash line")
        let requests = await backend.requests
        #expect(requests.allSatisfy { $0.url?.path != "/user-product/finance/strategy-vip" })
    }

    @Test func theFixtureServesEachContractByRole() async throws {
        let user = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        do {
            _ = try await user.ownerStrategyDashboard()
            Issue.record("a user must not reach the Owner's strategy")
        } catch let error as APIError {
            #expect(error.status == 403)
        }
        let owner = FixtureBackend.service(FixtureBackend(scenario: .populated, role: .owner, latency: .zero))
        #expect(try await owner.ownerStrategyDashboard().strategy?.isOwnerScope == true)
        #expect(try await user.strategyDashboard().strategy?.isOwnerScope == false)
        // Basic: recorded income only → observed; no income at all → needs_income.
        let basic = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .basic, latency: .zero))
        #expect(try await basic.strategyBasic().usesObservedIncome)
        let empty = FixtureBackend.service(FixtureBackend(scenario: .empty, plan: .basic, latency: .zero))
        #expect(try await empty.strategyBasic().needsIncome)
        var declared = FinancialProfile()
        declared.incomeType = "fixed"; declared.fixedMonthlySalary = 900_000; declared.workDaysPerWeek = 5
        _ = try await empty.updateFinancialSituation(declared, idempotencyKey: "op_declared01")
        let strategy = try await empty.strategyBasic()
        #expect(strategy.incomeSource == "declared" && !strategy.needsIncome)
    }

    // MARK: Salvavidas

    @Test func usersSalvavidasWithUnknownSavingsIsNeverZeroMonths() throws {
        let fund = try Self.decode(Salvavidas.self, #"""
        {"status":"OK","scope":"users","current_amount":null,"current_amount_known":false,"monthly_base":95000,"target_months":6,
         "allowed_target_months":[1,3,6],"target_amount":570000,"missing_amount":null,"coverage_months":null,"progress_percent":null,
         "components":{"debt_monthly_payments":70100,"recurring_obligations":24900},
         "debts":[{"id":31,"name":"Tarjeta","monthly_payment":45000}],"obligations":[{"id":45,"name":"Internet","monthly_amount":24900,"frequency":"monthly","due_day":4}],
         "milestones":[{"months":1,"target":95000,"reached":false}],"verification":{"mode":"declared","message":"Declará tus ahorros."}}
        """#)
        #expect(!fund.isOwnerScope && !fund.savingsKnown)
        #expect(fund.coverageLabel(language: .spanish) == "Sin dato")
        #expect(!fund.coverageLabel(language: .spanish).contains("0"))
        #expect(fund.debts?.first?.monthlyAmount == 45000 && fund.obligations?.first?.dueDay == 4)
        #expect(fund.targetChoices == [1, 3, 6])
        // A zero declared saving is known (and shown as such); a null one never is.
        let zero = try Self.decode(Salvavidas.self, #"{"scope":"users","current_amount":0,"current_amount_known":true,"coverage_months":0}"#)
        #expect(zero.savingsKnown && zero.coverageLabel(language: .spanish) == "0,0 meses")
        let needs = try Self.decode(Salvavidas.self, #"{"status":"needs_obligations","scope":"users","monthly_base":0}"#)
        #expect(needs.needsObligations)
    }

    @Test func ownerSalvavidasDecodesTheHistoricalModel() throws {
        let fund = try Self.decode(Salvavidas.self, #"""
        {"status":"OK","scope":"owner","current_amount":450000,"monthly_base":350000,"target_months":6,"coverage_months":1.29,
         "protected_expense_ids":[62],"components":{"debt_monthly_payments":95000,"mandatory_fixed_expenses":210000,"protected_expenses":24900},
         "mandatory_expenses":[{"id":61,"name":"Alquiler","monthly_amount":210000,"selected":true,"mandatory":true}],
         "available_expenses":[{"id":62,"name":"Internet","monthly_amount":24900,"selected":true},{"id":63,"name":"Gimnasio","monthly_amount":18000,"selected":false}],
         "excluded_debt_duplicates":[],"verification":{"mode":"manual","account_linked":false,"message":"Guardá el saldo."}}
        """#)
        #expect(fund.isOwnerScope && fund.savingsKnown)
        #expect(fund.availableExpenses?.map(\.lineId) == [62, 63] && fund.availableExpenses?.first?.selected == true)
        #expect(fund.components?.mandatoryFixedExpenses == 210000 && fund.verification?.accountLinked == false)
        #expect(fund.coverageLabel(language: .english) == "1.3 months")
    }

    @Test func salvavidasUpdatesSendOneFieldAndValidateFirst() async throws {
        func body(_ update: SalvavidasUpdate) throws -> String { String(decoding: try APIClient.encoder.encode(update), as: UTF8.self) }
        #expect(try body(.target(months: 3)) == #"{"target_months":3}"#)
        #expect(try body(.currentAmount(250_000)) == #"{"current_amount":250000}"#)
        #expect(try body(.protectedExpenses([63, 62])) == #"{"protected_expense_ids":[62,63]}"#)
        let transport = ScriptedTransport([.status(200, #"{"status":"OK","scope":"users","target_months":3}"#)])
        let api = service(transport)
        await #expect(throws: APIError.self) { _ = try await api.updateSalvavidas(.target(months: 2)) }
        await #expect(throws: APIError.self) { _ = try await api.updateSalvavidas(.currentAmount(-1)) }
        #expect(transport.requests.isEmpty, "an invalid change never leaves the device")
        #expect(try await api.updateSalvavidas(.target(months: 3)).targetMonths == 3)
        #expect(transport.requests.first?.httpMethod == "PUT" && transport.requests.first?.url?.path == "/user-product/vip/salvavidas")
    }

    @Test func theFixtureMirrorsTheSalvavidasContract() async throws {
        let user = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        let fund = try await user.salvavidas()
        #expect(fund.scope == "users" && !fund.savingsKnown && fund.coverageMonths == nil)
        // Users: no protected expenses, and savings only with a situation (the same declared field).
        await #expect(throws: APIError.self) { _ = try await user.updateSalvavidas(.protectedExpenses([62])) }
        await #expect(throws: APIError.self) { _ = try await user.updateSalvavidas(.currentAmount(100_000)) }
        var situation = FinancialProfile()
        situation.incomeType = "fixed"; situation.workDaysPerWeek = 5
        _ = try await user.updateFinancialSituation(situation, idempotencyKey: "op_situation1")
        let saved = try await user.updateSalvavidas(.currentAmount(285_300))
        #expect(saved.savingsKnown && saved.currentAmount == 285_300 && saved.coverageMonths != nil)
        #expect(try await user.financialSituation().financialProfile?.liquidSavings == 285_300)
        #expect(try await user.updateSalvavidas(.target(months: 3)).targetMonths == 3)
        let owner = FixtureBackend.service(FixtureBackend(scenario: .populated, role: .owner, latency: .zero))
        let ownerFund = try await owner.updateSalvavidas(.protectedExpenses([62, 63]))
        #expect(ownerFund.isOwnerScope && ownerFund.protectedExpenseIds == [62, 63])
        let basic = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .basic, latency: .zero))
        await #expect(throws: APIError.self) { _ = try await basic.salvavidas() }
    }

    // MARK: Situation: work days for every income type

    @Test func workDaysAreRequiredForEveryIncomeType() async throws {
        #expect(WorkDays.defaultValue == 5)
        #expect(WorkDays.parse("5") == 5 && WorkDays.parse(" 7 ") == 7)
        for bad in ["0", "8", "", "x", "2.5", "-1"] { #expect(WorkDays.parse(bad) == nil, "\(bad)") }
        let api = FixtureBackend.service(FixtureBackend(scenario: .populated, latency: .zero))
        var fixed = FinancialProfile()
        fixed.incomeType = "fixed"; fixed.fixedMonthlySalary = 800_000
        do {
            _ = try await api.updateFinancialSituation(fixed, idempotencyKey: "op_nodays001")
            Issue.record("a fixed income without work days must be refused, like the backend")
        } catch let error as APIError {
            #expect(error.status == 422)
        }
        fixed.workDaysPerWeek = WorkDays.defaultValue
        let body = try #require(try JSONSerialization.jsonObject(with: APIClient.encoder.encode(fixed)) as? [String: Any])
        #expect(body["work_days_per_week"] as? Int == 5)
        _ = try await api.updateFinancialSituation(fixed, idempotencyKey: "op_withdays01")
        #expect(try await api.financialSituation().financialProfile?.workDaysPerWeek == 5)
    }

    // MARK: Cuentas: the same review as the Email Monitor

    @Test func cuentasFiltersTheSameInbox() async throws {
        let json = #"{"status":"ok","items":[{"candidate_id":7,"bank":"bac","review_status":"confirmed","financial_account_id":3,"bank_movement":"purchase","financial_effect":null}]}"#
        let transport = ScriptedTransport([.status(200, json), .status(200, json)])
        let api = service(transport)
        let byBank = try await api.mailCandidates(bank: "bac")
        #expect(byBank.first?.financialAccountId == 3 && byBank.first?.bankMovement == "purchase" && byBank.first?.financialEffect == nil)
        _ = try await api.mailCandidates(financialAccountID: 3)
        let queries = transport.requests.map { URLComponents(url: $0.url!, resolvingAgainstBaseURL: false)?.queryItems ?? [] }
        #expect(queries[0] == [URLQueryItem(name: "bank", value: "bac")])
        #expect(queries[1] == [URLQueryItem(name: "financial_account_id", value: "3")])
        #expect(transport.requests.allSatisfy { $0.url?.path == "/user-product/vip/gmail/emails" })
    }

    @Test func aReviewInCuentasIsTheSameReviewInTheEmailMonitor() async throws {
        let backend = FixtureBackend(scenario: .populated, plan: .vip, latency: .zero)
        let api = FixtureBackend.service(backend)
        let before = try await api.movements().count
        // Accept in Cuentas (a bank's list, asked by its code) → the Email Monitor no longer shows it pending.
        let bank = try await api.mailCandidates(bank: "bac")
        #expect(Set(bank.compactMap(\.candidateId)) == [21, 22])
        let accepted = try await api.acceptCandidate(id: 21)
        #expect(accepted.status == "confirmed")
        #expect(!(try await api.mailCandidates(pendingOnly: true)).contains { $0.candidateId == 21 })
        #expect(try await api.mailCandidates(financialAccountID: 1).first?.reviewStatus == "confirmed")
        // Accepting again (from either surface) writes nothing.
        let again = try await api.acceptCandidate(id: 21)
        #expect(again.alreadyReviewed == true && again.transactionId == accepted.transactionId)
        #expect(try await api.movements().count == before + 1)
        // Reject in the Email Monitor → Cuentas shows it rejected.
        _ = try await api.rejectCandidate(id: 23)
        #expect(try await api.mailCandidates(financialAccountID: 3).first?.reviewStatus == "rejected")
        #expect(try await api.mailCandidates(bank: "popular").first?.reviewStatus == "rejected")
        #expect(try await api.movements().count == before + 1, "reject never creates a transaction")
    }

    @Test func accountsGroupByInstitutionCodeWithoutBalances() async throws {
        let api = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        let accounts = try await api.financialIdentity().items ?? []
        let groups = BankGroup.make(accounts: accounts, candidates: try await api.mailCandidates(pendingOnly: false))
        #expect(groups.map(\.id) == ["bac", "popular", BankGroup.otherID], "known banks first, then Otras instituciones")
        let bac = try #require(groups.first)
        #expect(bac.accounts.count == 2 && bac.brand?.logoAsset == "BankBAC" && bac.displayName == "BAC" && bac.bankCodes == ["bac"])
        #expect(bac.movements == 2 && bac.pending == 2)
        let other = try #require(groups.last)
        // Notice 24 says "unknown" but is linked to account 4 (no code): it is listed under Otras instituciones.
        #expect(other.isOther && other.accounts.map(\.id) == [4] && other.movements == 1 && other.bankCodes == ["unknown"])
        #expect(BankGroup.rows(of: BankGroup.otherID, accounts: accounts, candidates: try await api.mailCandidates(pendingOnly: false)).compactMap(\.candidateId) == [24])
        #expect(accounts.first?.maskedNumber == "•••• 1234")
        // Ownership answers are kept by the fixture, like account_balances.
        try await api.setAccountOwnership(id: 1, own: true)
        #expect(try await api.financialIdentity().items?.first { $0.id == 1 }?.ownershipStatus == "own")
    }

    /// The account's label ("Banco Popular") is not what notices store ("popular"): asking with the
    /// label finds nothing, so Cuentas always asks with the code and shows the label.
    @Test func aBankWhoseLabelDiffersFromItsCodeListsItsMovements() async throws {
        let api = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        let accounts = try await api.financialIdentity().items ?? []
        let groups = BankGroup.make(accounts: accounts, candidates: try await api.mailCandidates(pendingOnly: false))
        let popular = try #require(groups.first { $0.id == "popular" })
        #expect(popular.displayName == "Banco Popular" && popular.bankCodes == ["popular"] && popular.movements == 1)
        #expect(try await api.mailCandidates(bank: "Banco Popular").isEmpty, "the label never matches a notice")
        let rows = try await api.mailCandidates(bank: try #require(popular.bankCodes.first))
        #expect(rows.compactMap(\.candidateId) == [23] && rows.allSatisfy { BankGroup.groupID(of: $0, accounts: accounts) == "popular" })
    }

    static func notice(_ id: Int?, _ bank: String?, account: Int? = nil, status: String = "pending") -> MailCandidate {
        MailCandidate(candidateId: id, bank: bank, description: nil, amount: 1, currency: "CRC", accountBaseCurrency: "CRC",
                      transactionDate: nil, transactionType: "expense", category: nil, reviewStatus: status, financialAccountId: account)
    }

    static func account(_ id: Int, _ label: String?, _ code: String?) -> FinancialIdentity.Account {
        FinancialIdentity.Account(id: id, accountName: nil, bankName: label, currency: "CRC", accountLast4: nil, ownershipStatus: "pending", institutionCode: code)
    }

    @Test func noticesWithoutADetectedAccountStillHaveTheirBank() {
        let groups = BankGroup.make(accounts: [], candidates: [Self.notice(1, "multimoney"), Self.notice(2, "unknown"), Self.notice(3, ""), Self.notice(4, nil), Self.notice(5, "MultiMoney")])
        #expect(groups.map(\.id) == ["multimoney", BankGroup.otherID])
        #expect(groups.first?.bankCodes == ["multimoney"] && groups.first?.movements == 2 && groups.first?.displayName == "MultiMoney")
        // "unknown" names no institution DINCR knows: Otras. No bank and no account: only in the Email Monitor.
        #expect(groups.last?.movements == 1)
    }

    /// The same input as Android's `AccountsAnalysisTest.accountsAreGroupedByInstitutionCodeWithoutBalances`
    /// gives the same groups, in the web app's historical bank order (not alphabetical).
    @Test func groupsMatchAndroidForTheSameInput() {
        let accounts = [Self.account(1, "BAC", "bac"), Self.account(2, "Banco Popular", "popular")]
        let candidates = [Self.notice(21, "bac", account: 1), Self.notice(22, "bac", account: 1), Self.notice(23, "popular", account: 2),
                          Self.notice(25, "multimoney"), Self.notice(24, "cooperativa_ejemplo", status: "confirmed")]
        let groups = BankGroup.make(accounts: accounts, candidates: candidates)
        #expect(groups.map(\.id) == ["bac", "multimoney", "popular", BankGroup.otherID])
        let bac = groups[0]
        #expect(bac.accounts.count == 1 && bac.movements == 2 && bac.pending == 2 && bac.bankCodes == ["bac"])
        #expect(groups[1].accounts.isEmpty && groups[1].movements == 1)
        #expect(groups[2].bankCodes == ["popular"] && groups[2].displayName == "Banco Popular")
        #expect(groups[3].brand == nil && groups[3].bankCodes == ["cooperativa_ejemplo"] && groups[3].pending == 0)
        // A notice without a bank goes to its linked account's bank; an email row without a candidate is not a movement.
        #expect(BankGroup.groupID(of: Self.notice(30, nil, account: 2), accounts: accounts) == "popular")
        #expect(BankGroup.rows(of: BankGroup.otherID, accounts: accounts, candidates: candidates + [Self.notice(nil, "cooperativa_ejemplo")]).compactMap(\.candidateId) == [24])
    }

    @Test func detectedAccountsNeverCarryABalanceOrAFullNumber() throws {
        let account = try Self.decode(FinancialIdentity.Account.self, #"{"id":9,"bank_name":"Banco Nacional","institution_code":"bn","account_last4":"12345678","current_balance":0}"#)
        #expect(account.maskedNumber == "•••• 5678")
        #expect(account.brand.id == "bn")
        let mirror = Mirror(reflecting: account).children.compactMap(\.label)
        #expect(!mirror.contains { $0.lowercased().contains("balance") }, "a detected account's balance is unknown: it is not even decoded")
    }

    // MARK: Bank logos

    @Test func bankIdentityMatchesTheWebMapping() {
        #expect(BankBrand.identify("bac")?.logoAsset == "BankBAC")
        #expect(BankBrand.identify("BAC Credomatic")?.id == "bac")
        #expect(BankBrand.identify("Banco Nacional de Costa Rica")?.id == "bn", "must win over Banco de Costa Rica")
        #expect(BankBrand.identify("BANCO DE COSTA RICA")?.id == "bcr")
        #expect(BankBrand.identify("scotiabank")?.id == "davibank")
        #expect(BankBrand.identify("Promérica")?.id == "promerica", "accents are ignored")
        #expect(BankBrand.identify("Multi Money")?.id == "multimoney")
        #expect(BankBrand.identify("bp")?.id == "popular")
        #expect(BankBrand.identify(nil) == nil && BankBrand.identify("unknown") == nil && BankBrand.identify("") == nil)
        #expect(BankBrand.identify(inText: "Notificación de transacción BAC")?.id == "bac")
        #expect(BankBrand.identify(inText: "avisos@banco.test") == nil)
    }

    @Test func anUnknownBankFallsBackToItsInitials() {
        let unknown = BankBrand.describe(nil, fallbackName: "Banco de ejemplo")
        #expect(!unknown.isKnown && unknown.logoAsset == nil && unknown.name == "Banco de ejemplo" && unknown.short == "EJE")
        #expect(BankBrand.initials("Caja de Ahorro Local") == "CA")
        #expect(BankBrand.describe(nil).short == "?")
        #expect(BankBrand.describe("bcr", fallbackName: "Otro nombre").id == "bcr", "the institution code wins")
    }

    @Test func everyLogoIsAHistoricalAssetInTheCatalog() throws {
        #expect(Set(BankBrand.logoAssets.keys) == ["bac", "bcr", "bn", "davibank", "davivienda", "multimoney", "popular", "promerica"])
        for asset in BankBrand.logoAssets.values {
            let contents = IdentityGuardTests.iosRoot.appending(path: "DINCR/Resources/Assets.xcassets/\(asset).imageset/Contents.json")
            let text = try String(contentsOf: contents, encoding: .utf8)
            let file = try #require(text.components(separatedBy: "\"filename\" : \"").dropFirst().first?.prefix { $0 != "\"" })
            // A byte copy of frontend/src/assets/institutions/<file> (never downloaded or redrawn).
            let copy = try Data(contentsOf: contents.deletingLastPathComponent().appending(path: String(file)))
            let original = try Data(contentsOf: IdentityGuardTests.iosRoot.deletingLastPathComponent().deletingLastPathComponent()
                .appending(path: "frontend/src/assets/institutions/\(file)"))
            #expect(copy == original, "\(asset)")
        }
    }

    @Test func onboardingOffersTheLogosAsAPreferenceOnly() throws {
        #expect(BankBrand.onboardingChoices.map { $0.id } == ["bac", "bn", "bcr", "popular", "davivienda", "scotiabank", "promerica", "multimoney"])
        #expect(BankBrand.onboardingChoices.allSatisfy { BankBrand.describe($0.id).logoAsset != nil })
        let source = try IdentityGuardTests.read("DINCR/Features/Onboarding/ProfileSetupView.swift")
        #expect(source.contains("no conecta tus cuentas"))
        #expect(source.contains("selectedFinancialInstitutions: institutions.sorted()"), "same stored field and request as before")
    }

    // MARK: JARVIS · Análisis financiero (Owner)

    @Test func ownerAnalysisReadsTheThreeHistoricalRoutes() async throws {
        let summary = #"{"summary":{"income":100,"expenses":60,"total_transactions":3},"expenses_by_month":[{"month":"2026-08","total":60}],"monthly_flow":[{"month":"2026-08","income":100,"expenses":60,"monthly_balance":40}],"spending_breakdown":{"period":{"label":"2026 YTD"},"total":60,"categories":[{"category":"Comida","total":60,"count":3}]}}"#
        let worth = #"{"assets":{"assets_total":500},"liabilities":{"debt_total":200},"net_worth":300,"change":{"amount":10,"percentage":null}}"#
        let engine = #"{"status":"OK","health":{"score":62.5,"level":"stable"},"forecast":{"projected_end_balance":185000,"alert":null},"emergency_fund":{"current":1,"recommended_6_months":6},"debts":{"status":"EMPTY","recommended":null}}"#
        let transport = RoutedTransport(["/transactions/analysis/summary": summary, "/finance/net-worth": worth, "/finance/engine": engine])
        let api = DincrService(client: APIClient(baseURL: URL(string: "https://api.example.test")!, tokens: CountingTokens(), transport: transport, language: .spanish, backoff: { _ in }))
        let analysis = try await api.ownerAnalysis()
        #expect(transport.requests.map { $0.url!.path }.sorted() == ["/finance/engine", "/finance/net-worth", "/transactions/analysis/summary"])
        #expect(transport.requests.allSatisfy { $0.httpMethod == "GET" })
        #expect(analysis.transactions.flowMonths().first?.income == 100 && analysis.transactions.spendingCategories.first?.category == "Comida")
        #expect(analysis.netWorth.netWorth == 300 && analysis.netWorth.assets?.assetsTotal == 500)
        #expect(analysis.engine.health?.score == 62.5 && analysis.engine.forecast?.projectedEndBalance == 185000)
    }

    @Test func ownerAnalysisDecodesTheBackendShapes() throws {
        let engine = try Self.decode(FinancialEngineReport.self, #"{"status":"OK","health":{"score":62.5,"level":"stable","confidence":0.75},"forecast":{"projected_end_balance":185000,"alert":{"level":"high","message":"Proyección negativa"}},"emergency_fund":{"current":450000,"recommended_6_months":1980000,"coverage_months":1.36},"debts":{"status":"OK","recommended":{"name":"avalanche","priority_debt":{"name":"Tarjeta","remaining_amount":420000}}},"recommendations":["Uno"]}"#)
        #expect(engine.health?.score == 62.5 && engine.emergencyFund?.recommended6Months == 1_980_000)
        #expect(engine.forecast?.alert?.message == "Proyección negativa" && engine.debts?.recommended?.priorityDebt?.name == "Tarjeta")
        let summary = try Self.decode(TransactionAnalysis.self, #"{"monthly_flow":[{"month":"2026-07","income":1,"expenses":2},{"month":"","income":5,"expenses":5},{"month":"2026-08","income":null,"expenses":3}],"spending_breakdown":{"categories":[{"category":"Comida","total":60},{"category":null,"total":5}]}}"#)
        #expect(summary.flowMonths().map(\.month) == ["2026-07"], "months with unknown figures are not charted as zero")
        #expect(summary.spendingCategories.map(\.category) == ["Comida"])
    }

    @Test func onlyTheOwnerGetsTheAnalysisSection() async throws {
        #expect(Jarvis.Section.analysis.isAvailable)
        for plan in [PlanTier.free, .basic, .vip] {
            let user = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: plan, latency: .zero))
            do {
                _ = try await user.ownerAnalysis()
                Issue.record("a \(plan) user must not reach the Owner's analysis")
            } catch let error as APIError {
                #expect(error.status == 403)
            }
        }
        let owner = try await FixtureBackend.service(FixtureBackend(scenario: .populated, role: .owner, latency: .zero)).ownerAnalysis()
        #expect(owner.engine.health?.score != nil && owner.netWorth.netWorth != nil && !owner.transactions.flowMonths().isEmpty)
    }

    // MARK: Logo tiles

    @Test func theWhiteMultiMoneyLogoSitsOnTheHistoricalDarkTile() {
        // The historical asset is white on transparent: on a white tile it was an empty white box.
        #expect(BankBrand.identify("multimoney")?.logoNeedsDarkTile == true)
        for other in ["bac", "bcr", "bn", "popular", "promerica", "davivienda", "davibank"] {
            #expect(BankBrand.identify(other)?.logoNeedsDarkTile == false, "\(other)")
        }
        #expect(BankBrand.identify("cooperativa ejemplo")?.logoNeedsDarkTile != true)
    }

    // MARK: DINCR → Hoy

    @Test func dincrTodayShowsTheCurrentAlertsWhileTheAdvisorHasNoEarlierObservation() async throws {
        // The advisor answers BASELINE (native never saves observations); the command center already
        // knows today's alerts, the same ones the main Today shows.
        let vip = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        let today = try await vip.dincrToday()
        #expect(today.isBaseline)
        let center = try await vip.commandCenter()
        #expect(today.currentAlerts == center.alerts)
        #expect(today.currentAlerts?.first?.title == "Pago de tarjeta en 5 días")
    }
}

/// Answers by path (the analysis loads its three routes concurrently, in any order).
final class RoutedTransport: HTTPTransport, @unchecked Sendable {
    private let lock = NSLock()
    private let bodies: [String: String]
    private var recorded: [URLRequest] = []

    init(_ bodies: [String: String]) { self.bodies = bodies }

    var requests: [URLRequest] { lock.withLock { recorded } }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let body: String? = lock.withLock {
            recorded.append(request)
            return bodies[request.url!.path]
        }
        return (Data((body ?? "{}").utf8), HTTPURLResponse(url: request.url!, statusCode: body == nil ? 404 : 200, httpVersion: nil, headerFields: nil)!)
    }
}
