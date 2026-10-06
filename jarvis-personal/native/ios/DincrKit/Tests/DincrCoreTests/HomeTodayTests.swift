import Foundation
import Testing
@testable import DincrCore

/// Hoy's four blocks (UX-6): presentation rules per plan, synthetic data. Android twin:
/// `HomeTodayTest.kt` — the same cases with the same expectations.
@Suite struct HomeTodayTests {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try APIClient.decoder.decode(T.self, from: Data(json.utf8))
    }

    /// 2026-10-10, noon, so the day is the same in any time zone the tests run in.
    private let today = Calendar(identifier: .gregorian).date(from: DateComponents(year: 2026, month: 10, day: 10, hour: 12))!

    private func free(income: Int = 500000, expenses: Int = 120000) throws -> FreeDashboard {
        try decode(FreeDashboard.self, #"{"month":"2026-10","income":\#(income),"expenses":\#(expenses),"debt_paid":0,"balance":\#(income - expenses),"available_after_commitments":\#(income - expenses),"categories":[{"category":"Comida","amount":80000}],"monthly_history":[]}"#)
    }

    private func basic(income: Int = 500000) throws -> BasicDashboard {
        try decode(BasicDashboard.self, #"{"month":"2026-10","income":\#(income),"expenses":120000,"debt_paid":0,"balance":\#(income - 120000)}"#)
    }

    private func debts(_ json: String = #"[{"id":1,"name":"Tarjeta sintética","remaining_amount":300000,"monthly_payment":45000,"payment_day":15}]"#) throws -> [Debt] {
        try decode([Debt].self, json)
    }

    private let budget = #"{"items":[{"category":"Comida","monthly_limit":150000,"spent":90000},{"category":"Transporte","monthly_limit":50000,"spent":10000}],"total_budgeted":200000,"is_proposal":false}"#
    private let calendar = #"{"period":"2026-10","events":[{"date":"2026-10-05","kind":"debt","name":"Pasado","amount":30000},{"date":"2026-10-12","kind":"expense","name":"Internet","amount":25000},{"date":"2026-10-20","kind":"debt","name":"Tarjeta","amount":45000},{"date":"2026-10-25","kind":"goal","name":"Meta","amount":10000},{"date":"2026-10-28","kind":"income","name":"Ingreso esperado","amount":0}]}"#

    private func center(_ json: String) throws -> CommandCenter { try decode(CommandCenter.self, json) }

    // MARK: Free

    @Test func freeHasTheFourBlocksWithRealFactsAndNoIntelligence() throws {
        let home = HomeToday.free(try free(), debts: [], today: today)
        #expect(home.tier == .free)
        #expect(home.status.headline == .monthResult)        // never safe to spend
        #expect(home.status.amount == 380000 && home.status.missing.isEmpty)
        #expect(home.status.income == 500000 && home.status.expenses == 120000)
        #expect(home.status.budget == nil && home.status.pending == nil && home.status.lowestBalance == nil)
        #expect(home.attention == nil)                         // no source: left out, nothing invented
        #expect(home.next.kind == .registerMovement)
        #expect(home.shortcuts == HomeShortcut.allCases)
    }

    @Test func freeWithoutRegisteredIncomeIsUnknownNeverZero() throws {
        let home = HomeToday.free(try free(income: 0), debts: [], today: today)
        #expect(home.status.amount == nil && home.status.result == nil && home.status.income == nil)
        #expect(home.status.missing == [.income])
        #expect(home.status.missing.first?.destination == .registerIncome)  // the real flow, never an estimate
        #expect(home.next.kind == .registerIncome)
    }

    @Test func freeNextIsTheNextKnownDebtPayment() throws {
        let home = HomeToday.free(try free(), debts: try debts(), today: today)
        #expect(home.next.kind == .commitment)
        #expect(home.next.title == "Tarjeta sintética" && home.next.date == "2026-10-15" && home.next.amount == 45000)
        #expect(home.next.destination == .debts)
    }

    @Test func aPaymentDayAlreadyPassedMovesToNextMonthAndUnknownAmountsStayUnknown() throws {
        let home = HomeToday.free(try free(), debts: try debts(#"[{"id":2,"name":"Préstamo","remaining_amount":900000,"monthly_payment":0,"payment_day":3},{"id":3,"name":"Pagada","remaining_amount":0,"monthly_payment":10000,"payment_day":11}]"#), today: today)
        #expect(home.next.date == "2026-11-03")
        #expect(home.next.amount == nil)  // a stored 0 is an unknown payment (#326), not ₡0
        #expect(home.next.title == "Préstamo")
    }

    // MARK: Basic

    @Test func basicAddsItsOwnBudgetAndPendingCommitmentsWithoutVipIntelligence() throws {
        let home = HomeToday.basic(try basic(), budget: try decode(Budget.self, budget), calendar: try decode(FinancialCalendar.self, calendar),
                                   plan: nil, debts: [], today: today)
        #expect(home.tier == .basic && home.status.headline == .monthResult && home.attention == nil)
        #expect(home.status.budget?.remaining == 100000)
        #expect(home.status.budget?.used.fraction == 0.5)
        #expect(home.status.pending == HomeStatus.Pending(count: 2, total: 70000))  // from today on, payments only
        #expect(home.status.lowestBalance == nil)
    }

    @Test func dincrsBudgetProposalIsNotTheUsersBudget() throws {
        let proposal = try decode(Budget.self, #"{"items":[{"category":"Comida","monthly_limit":100000,"spent":0}],"total_budgeted":100000,"is_proposal":true}"#)
        #expect(HomeToday.basic(try basic(), budget: proposal, calendar: nil, plan: nil, debts: [], today: today).status.budget == nil)
    }

    @Test func aPendingPaymentWithoutAKnownAmountKeepsTheTotalUnknown() throws {
        let cal = try decode(FinancialCalendar.self, #"{"events":[{"date":"2026-10-20","kind":"debt","name":"Tarjeta","amount":0},{"date":"2026-10-21","kind":"expense","name":"Luz","amount":15000}]}"#)
        #expect(HomeToday.basic(try basic(), budget: nil, calendar: cal, plan: nil, debts: [], today: today).status.pending == HomeStatus.Pending(count: 2, total: nil))
    }

    @Test func basicNextComesFromStrategyBasic() throws {
        let plan = MonthPlan(.basic(try decode(Strategy.self, #"{"status":"tight","strategic_margin":214000,"recommendation":"Destiná ₡100.000 a la tarjeta."}"#)))
        let home = HomeToday.basic(try basic(), budget: nil, calendar: nil, plan: plan, debts: try debts(), today: today)
        #expect(home.next.kind == .recommendation && home.next.destination == .monthPlan)
        #expect(home.next.title?.isEmpty == false)
        let needsIncome = MonthPlan(.basic(try decode(Strategy.self, #"{"status":"needs_income"}"#)))
        let missing = HomeToday.basic(try basic(), budget: nil, calendar: nil, plan: needsIncome, debts: [], today: today).next
        #expect(missing.kind == .needsInformation && missing.missing == [.income] && missing.destination == .registerIncome)
    }

    // MARK: VIP

    private let knownCenter = #"""
    {"safe_to_spend":{"amount":118000,"monthly_margin":214000,"next_45_days_minimum":96000,"missing":[]},
     "director":{"priority":"debt","headline":"Atacar Tarjeta","next_action":"Asigná ₡40,000 a esta prioridad.","missing":[]},
     "reports":{"current":{"month":"2026-10","income":600000,"expenses":200000,"debt_paid":40000,"balance":360000}},
     "roadmap":[{"order":1,"title":"Abonar a Tarjeta","amount":40000},{"order":2,"title":"Invertir","amount":0}],
     "score":{"value":72,"label":"Estable"},"projections":[{"months":6,"net_worth":1000000}],
     "alerts":[{"severity":"medium","title":"A1"},{"severity":"high","title":"A2"},{"severity":"critical","title":"A3"},{"severity":"medium","title":"A4"}],
     "automation":{"review":0}}
    """#

    @Test func vipShowsSafeToSpendAndOneRecommendationWithAttention() throws {
        let home = HomeToday.vip(try center(knownCenter), budget: nil, calendar: nil, debts: [], today: today)
        #expect(home.tier == .vip && home.status.headline == .safeToSpend)
        #expect(home.status.amount == 118000 && home.status.missing.isEmpty && home.status.lowestBalance == 96000)
        #expect(home.status.income == 600000 && home.status.result == 360000)
        #expect(home.next.kind == .recommendation && home.next.title == "Atacar Tarjeta" && home.next.destination == .monthPlan)
        // Para atender (#325): at most three, the rest behind "Ver todas".
        #expect(home.attention?.visible.count == 3 && home.attention?.showsSeeAll == true)
        #expect(home.attention?.visible.first?.severity == "critical")
    }

    @Test func vipUnknownSafeToSpendIsUnknownWithWhatIsMissing() throws {
        let home = HomeToday.vip(try center(#"""
        {"safe_to_spend":{"amount":null,"monthly_margin":null,"next_45_days_minimum":250000,"missing":["income","debt_payments","future_code"]},
         "director":{"priority":"incomplete","headline":"Aún no tengo suficiente información para recomendarte una prioridad","missing":["income","debt_payments"]},
         "roadmap":[],"alerts":[]}
        """#), budget: nil, calendar: nil, debts: [], today: today)
        #expect(home.status.amount == nil)                         // never ₡0
        #expect(home.status.missing == [.income, .debtPayments])   // unknown codes are skipped
        #expect(home.next.kind == .needsInformation)               // no invented priority
        #expect(home.next.missing == [.income, .debtPayments] && home.next.destination == .registerIncome)
        #expect(home.attention?.isEmpty == true)
    }

    @Test func vipAddsBasicsCompactFacts() throws {
        let home = HomeToday.vip(try center(knownCenter), budget: try decode(Budget.self, budget), calendar: try decode(FinancialCalendar.self, calendar),
                                 debts: [], today: today)
        #expect(home.status.budget?.remaining == 100000 && home.status.pending?.count == 2)
    }

    // MARK: Review cases (unknown ≠ 0, adding up, invalid data)

    @Test func basicWithoutRegisteredIncomeIsUnknownToo() throws {
        let home = HomeToday.basic(try basic(income: 0), budget: nil, calendar: nil, plan: nil, debts: [], today: today)
        #expect(home.status.amount == nil && home.status.missing == [.income] && home.next.kind == .registerIncome)
    }

    @Test func nothingRegisteredIsNotAZero() throws {
        let home = HomeToday.free(try free(income: 0, expenses: 0), debts: [], today: today)
        #expect(home.status.income == nil && home.status.expenses == nil)  // "Sin registrar", never ₡0
    }

    @Test func theResultAddsUpWithWhatWasPaidToDebts() throws {
        let dashboard = try decode(FreeDashboard.self, #"{"month":"2026-10","income":500000,"expenses":120000,"debt_paid":40000,"balance":340000,"categories":[],"monthly_history":[]}"#)
        let home = HomeToday.free(dashboard, debts: try debts(), today: today)
        #expect(home.status.result == 340000 && home.status.debtPaid == 40000)
        #expect(home.status.debtBalance == 300000)  // the debts' own balances
    }

    @Test func vipWithoutTheMonthsLedgerHasNoInventedFacts() throws {
        let home = HomeToday.vip(try center(#"{"safe_to_spend":{"amount":118000,"monthly_margin":null,"missing":[]},"alerts":[]}"#),
                                 budget: nil, calendar: nil, debts: nil, today: today)
        #expect(home.status.income == nil && home.status.expenses == nil && home.status.result == nil)
        #expect(home.status.margin == nil && home.status.debtBalance == nil)
        #expect(HomeToday.vip(try center(knownCenter), budget: nil, calendar: nil, debts: [], today: today).status.margin == 214000)
    }

    @Test func aBudgetWithoutTheProposalFlagOrASpentValueIsNotShown() throws {
        let noFlag = try decode(Budget.self, #"{"items":[{"category":"Comida","monthly_limit":100000,"spent":0}],"total_budgeted":100000}"#)
        let noSpent = try decode(Budget.self, #"{"items":[{"category":"Comida","monthly_limit":100000}],"total_budgeted":100000,"is_proposal":false}"#)
        #expect(HomeToday.budgetLeft(noFlag) == nil && HomeToday.budgetLeft(noSpent) == nil)
    }

    @Test func noKnownPaymentsIsZeroKnownNotNone() throws {
        let cal = try decode(FinancialCalendar.self, #"{"events":[]}"#)
        #expect(HomeToday.pending(cal, today: today) == HomeStatus.Pending(count: 0, total: 0))
        #expect(HomeToday.pending(nil, today: today) == nil)
    }

    @Test func anInvalidPaymentDayGivesNoDate() throws {
        let home = HomeToday.free(try free(), debts: try debts(#"[{"id":4,"name":"Rara","remaining_amount":100000,"monthly_payment":10000,"payment_day":0},{"id":5,"name":"Otra","remaining_amount":100000,"monthly_payment":10000,"payment_day":40}]"#), today: today)
        #expect(home.next.kind == .registerMovement)  // skipped, never a crash or a wrong date
    }

    // MARK: General

    @Test func missingInputsLeadToTheRealFlows() {
        #expect(HomeInput.income.destination == .registerIncome)
        #expect(HomeInput.debtPayments.destination == .debts)
        #expect([HomeInput.essentialExpenses, .savings, .emergencyFundTarget].allSatisfy { $0.destination == .incomeBase })  // UX-7: Plan → Ingresos y base
        #expect(HomeInput.codes(["essential_expenses", "savings", "emergency_fund_target"]) == [.essentialExpenses, .savings, .emergencyFundTarget])
    }

    @Test func quickAccessIsTheSameForEveryPlan() throws {
        let tiers = [HomeToday.free(try free(), debts: [], today: today).shortcuts,
                     HomeToday.basic(try basic(), budget: nil, calendar: nil, plan: nil, debts: [], today: today).shortcuts,
                     HomeToday.vip(try center(knownCenter), budget: nil, calendar: nil, debts: [], today: today).shortcuts]
        #expect(tiers.allSatisfy { $0 == [.registerMovement, .movements, .debts, .goals] })
    }
}
