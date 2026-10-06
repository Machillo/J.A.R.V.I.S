import Foundation

/// Hoy (UX-6): one presentation model for the four public blocks — Estado de hoy, Para atender,
/// Qué sigue, Accesos rápidos — answering how am I, how much can I spend, what needs attention and
/// what's next. Presentation only: every figure is the backend's (or a plain sum of the backend's
/// values), unknown stays unknown (nil, never 0), and no new financial rule is decided here.
/// - Free: the month's registered facts; Qué sigue is a deterministic fact or action.
/// - Basic: Free + the user's own budget left and this month's pending commitments; Qué sigue from
///   strategy-basic ("Tu plan del mes").
/// - VIP: Basic + safe to spend and the director's one recommendation (#326 contract), and
///   "Para atender" (#325).
/// The Owner's JARVIS space sits above these blocks in the app; it is not modelled here.
/// Android: `com.dincr.data.HomeToday`.
public struct HomeToday: Sendable, Equatable {
    public enum Tier: Sendable, Hashable { case free, basic, vip }

    public let tier: Tier
    public let status: HomeStatus
    /// Nil when the plan has no source for it (Free, Basic): the block is left out, never filled.
    public let attention: AttentionList.Today?
    public let next: HomeNext
    public let shortcuts: [HomeShortcut]

    // MARK: Builders

    public static func free(_ dashboard: FreeDashboard, debts: [Debt]?, today: Date = .now) -> HomeToday {
        let income = registered(dashboard.income)
        let result = income == nil ? nil : dashboard.balance ?? dashboard.availableAfterCommitments
        let status = HomeStatus(headline: .monthResult, amount: result, missing: income == nil ? [.income] : [],
                                income: income, expenses: registered(dashboard.expenses), debtPaid: registered(dashboard.debtPaid), result: result,
                                debtBalance: debtBalance(debts, fallback: dashboard.debtBalance), margin: nil, lowestBalance: nil, budget: nil, pending: nil)
        return HomeToday(tier: .free, status: status, attention: nil,
                         next: fallbackNext(incomeKnown: income != nil, debts: debts, today: today), shortcuts: HomeShortcut.allCases)
    }

    public static func basic(_ dashboard: BasicDashboard, budget: Budget?, calendar: FinancialCalendar?, plan: MonthPlan?,
                             debts: [Debt]?, today: Date = .now) -> HomeToday {
        let income = registered(dashboard.income)
        let result = income == nil ? nil : dashboard.balance
        let status = HomeStatus(headline: .monthResult, amount: result, missing: income == nil ? [.income] : [],
                                income: income, expenses: registered(dashboard.expenses), debtPaid: registered(dashboard.debtPaid), result: result,
                                debtBalance: debtBalance(debts, fallback: dashboard.debt?.remaining), margin: nil, lowestBalance: nil,
                                budget: budgetLeft(budget), pending: pending(calendar, today: today))
        let next: HomeNext
        if let plan, plan.needsIncome {
            next = HomeNext(kind: .needsInformation, missing: [.income], destination: .registerIncome)
        } else if let headline = text(plan?.summaryHeadline) {
            next = HomeNext(kind: .recommendation, title: headline, destination: .monthPlan)
        } else {
            next = fallbackNext(incomeKnown: income != nil, debts: debts, today: today)
        }
        return HomeToday(tier: .basic, status: status, attention: nil, next: next, shortcuts: HomeShortcut.allCases)
    }

    public static func vip(_ center: CommandCenter, budget: Budget?, calendar: FinancialCalendar?, debts: [Debt]?,
                           mailReviewAvailable: Bool = true, today: Date = .now, language: AppLanguage = .current) -> HomeToday {
        let month = center.reports?.current
        let income = registered(month?.income)
        let spend = center.safeToSpend
        let status = HomeStatus(headline: .safeToSpend, amount: spend?.amount,
                                missing: spend?.amount == nil ? HomeInput.codes(spend?.missing) : [],
                                income: income, expenses: registered(month?.expenses), debtPaid: registered(month?.debtPaid),
                                result: income == nil ? nil : month?.balance, debtBalance: debtBalance(debts, fallback: nil),
                                margin: spend?.monthlyMargin, lowestBalance: spend?.next45DaysMinimum,
                                budget: budgetLeft(budget), pending: pending(calendar, today: today))
        let next: HomeNext
        let director = center.director
        // The director needs inputs before recommending: priority `incomplete` (#326), or a known
        // priority whose target can't be chosen yet (a debt's rate is missing: `debt_interest_rates`).
        if director?.priority == "incomplete" || !HomeInput.codes(director?.missing).isEmpty {
            let missing = HomeInput.codes(director?.missing)
            next = HomeNext(kind: .needsInformation, title: text(director?.headline), missing: missing,
                            destination: missing.first?.destination ?? .incomeBase)
        } else if let headline = text(director?.headline) {
            next = HomeNext(kind: .recommendation, title: headline, detail: text(director?.nextAction), destination: .monthPlan)
        } else {
            next = fallbackNext(incomeKnown: income != nil, debts: debts, today: today)
        }
        return HomeToday(tier: .vip, status: status,
                         attention: AttentionList.today(center: center, mailReviewAvailable: mailReviewAvailable, language: language),
                         next: next, shortcuts: HomeShortcut.allCases)
    }

    // MARK: Rules (presentation)

    /// A month's registered movements: nothing registered is unknown (missing movements don't prove
    /// there were none), never shown as ₡0. No income registered also makes the result unknown.
    static func registered(_ value: Decimal?) -> Decimal? {
        guard let value, value > 0 else { return nil }
        return value
    }

    /// What is still owed: the debts' own balances (a plain sum), else the dashboard's figure.
    static func debtBalance(_ debts: [Debt]?, fallback: Decimal?) -> Decimal? {
        let total = debts.map { $0.compactMap(\.remainingAmount).filter { $0 > 0 }.reduce(0, +) } ?? fallback
        guard let total, total > 0 else { return nil }
        return total
    }

    /// The user's own budget (never DINCR's proposal): what is left and how much is used.
    static func budgetLeft(_ budget: Budget?) -> HomeStatus.BudgetLeft? {
        guard let budget, budget.isProposal == false, let items = budget.items, !items.isEmpty,
              let total = budget.totalBudgeted, total > 0 else { return nil }
        var spent: Decimal = 0
        for item in items {
            guard let value = item.spent else { return nil }
            spent += value
        }
        return HomeStatus.BudgetLeft(remaining: total - spent, used: ProgressValue(current: spent, target: total))
    }

    /// Payments still to come this month (recurring expenses and debts from today on). A payment with
    /// no known amount (0, #326) keeps the total unknown.
    static func pending(_ calendar: FinancialCalendar?, today: Date) -> HomeStatus.Pending? {
        guard let calendar, let events = calendar.events else { return nil }
        let key = dayKey(today)
        let due = events.filter { ["expense", "debt"].contains($0.kind ?? "") && ($0.date ?? "") >= key }
        let known = due.allSatisfy { ($0.amount ?? 0) > 0 }
        return HomeStatus.Pending(count: due.count, total: known ? due.reduce(Decimal(0)) { $0 + ($1.amount ?? 0) } : nil)
    }

    /// Qué sigue without a strategy engine (Free, or when the engine has nothing): the next known
    /// debt payment, else registering the month's income, else registering movements.
    static func fallbackNext(incomeKnown: Bool, debts: [Debt]?, today: Date) -> HomeNext {
        if let (debt, date) = nextDebtPayment(debts ?? [], today: today) {
            let amount = (debt.monthlyPayment ?? 0) > 0 ? debt.monthlyPayment : nil
            return HomeNext(kind: .commitment, title: text(debt.name), amount: amount, date: date, destination: .debts)
        }
        if !incomeKnown { return HomeNext(kind: .registerIncome, missing: [.income], destination: .registerIncome) }
        return HomeNext(kind: .registerMovement, destination: .registerMovement)
    }

    /// The earliest upcoming payment of a debt with a balance: its next payment date, or its payment
    /// day this month (next month once it has passed). Debts without either have no known date.
    static func nextDebtPayment(_ debts: [Debt], today: Date) -> (Debt, String)? {
        let key = dayKey(today)
        let calendar = Calendar(identifier: .gregorian)
        let parts = calendar.dateComponents([.year, .month, .day], from: today)
        let dated: [(Debt, String)] = debts.filter { ($0.remainingAmount ?? 0) > 0 }.compactMap { debt in
            if let next = debt.nextPaymentDate.map({ String($0.prefix(10)) }), next >= key { return (debt, next) }
            // A payment day that isn't a day of the month (stored by older flows) gives no date.
            guard let day = debt.paymentDay, (1...31).contains(day), let year = parts.year, let month = parts.month else { return nil }
            var (y, m) = (year, month)
            if day < (parts.day ?? 1) { (y, m) = m == 12 ? (y + 1, 1) : (y, m + 1) }
            let last = calendar.range(of: .day, in: .month, for: calendar.date(from: DateComponents(year: y, month: m, day: 1))!)?.count ?? 28
            return (debt, String(format: "%04d-%02d-%02d", y, m, min(day, last)))
        }
        return dated.min { ($0.1, $0.0.id) < ($1.1, $1.0.id) }
    }

    /// `yyyy-MM-dd` of a date in the Gregorian calendar (the backend's date keys).
    public static func dayKey(_ date: Date) -> String {
        let parts = Calendar(identifier: .gregorian).dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }

    private static func text(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else { return nil }
        return value
    }
}

/// Estado de hoy: the headline figure (nil = unknown, with what is missing) and compact facts.
public struct HomeStatus: Sendable, Equatable {
    public enum Headline: Sendable, Equatable {
        /// Free and Basic: the month's result from registered movements.
        case monthResult
        /// VIP: safe to spend, from the command center (#326).
        case safeToSpend
    }
    public struct BudgetLeft: Sendable, Equatable {
        public let remaining: Decimal
        public let used: ProgressValue
    }
    public struct Pending: Sendable, Equatable {
        public let count: Int
        /// Nil when a pending payment has no known amount.
        public let total: Decimal?
    }

    public let headline: Headline
    public let amount: Decimal?
    public let missing: [HomeInput]
    /// Income registered this month; nil when none is registered (never shown as ₡0).
    public let income: Decimal?
    /// Expenses registered this month; nil when none are registered.
    public let expenses: Decimal?
    /// Paid to debts this month (part of the result); nil when nothing is registered.
    public let debtPaid: Decimal?
    /// The month's result (income − expenses − paid to debts); nil while no income is registered.
    public let result: Decimal?
    /// What is still owed on debts; nil when nothing is owed or it is unknown.
    public let debtBalance: Decimal?
    /// VIP: the month's margin from the command center; nil when unknown (#326).
    public let margin: Decimal?
    /// VIP: the lowest expected balance in the next 45 days.
    public let lowestBalance: Decimal?
    public let budget: BudgetLeft?
    public let pending: Pending?
}

/// Qué sigue: exactly one thing. The detailed plan lives in Plan → Tu plan del mes.
public struct HomeNext: Sendable, Equatable {
    public enum Kind: Sendable, Equatable {
        /// The strategy engine's one recommendation (Basic: strategy-basic; VIP: the director).
        case recommendation
        /// The engine can't recommend yet: these inputs are missing.
        case needsInformation
        /// The next known debt payment.
        case commitment
        /// No income registered this month.
        case registerIncome
        /// Keep the month up to date.
        case registerMovement
    }

    public let kind: Kind
    /// Backend text (recommendation, director sentence) or the commitment's name.
    public let title: String?
    public let detail: String?
    /// Commitment amount; nil when unknown.
    public let amount: Decimal?
    /// Commitment date, `yyyy-MM-dd`.
    public let date: String?
    public let missing: [HomeInput]
    public let destination: HomeDestination

    public init(kind: Kind, title: String? = nil, detail: String? = nil, amount: Decimal? = nil, date: String? = nil,
                missing: [HomeInput] = [], destination: HomeDestination) {
        self.kind = kind; self.title = title; self.detail = detail; self.amount = amount; self.date = date
        self.missing = missing; self.destination = destination
    }
}

/// An input DINCR may not have (the backend's `missing` codes, #326).
public enum HomeInput: String, Sendable, Equatable, CaseIterable {
    case income
    case essentialExpenses = "essential_expenses"
    case debtPayments = "debt_payments"
    case savings
    case emergencyFundTarget = "emergency_fund_target"
    /// A debt's interest rate, needed to choose which debt to pay down first.
    case debtInterestRates = "debt_interest_rates"

    /// Where the user gives DINCR this input, in the flows that exist (never an estimate): income is
    /// registered as a movement (salary / pay stub), debts in Deudas, the rest in Plan → Ingresos y
    /// base (UX-7: the declared figures' home; there is no separate Situación screen).
    public var destination: HomeDestination {
        switch self {
        case .income: .registerIncome
        case .debtPayments, .debtInterestRates: .debts
        case .essentialExpenses, .savings, .emergencyFundTarget: .incomeBase
        }
    }

    /// Known codes in the backend's order; codes this app doesn't know are skipped.
    public static func codes(_ codes: [String]?) -> [HomeInput] { (codes ?? []).compactMap(HomeInput.init(rawValue:)) }
}

/// Screens Hoy opens. All exist on both platforms.
public enum HomeDestination: String, Sendable, Equatable, CaseIterable {
    case registerIncome, registerMovement, movements, debts, goals, incomeBase, monthPlan
}

/// Accesos rápidos: the same essentials for every plan.
public enum HomeShortcut: String, Sendable, Equatable, CaseIterable {
    case registerMovement, movements, debts, goals

    public var destination: HomeDestination {
        switch self {
        case .registerMovement: .registerMovement
        case .movements: .movements
        case .debts: .debts
        case .goals: .goals
        }
    }
}
