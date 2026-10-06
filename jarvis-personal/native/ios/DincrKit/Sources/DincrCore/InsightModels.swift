import Foundation

// Read models of the dashboards, reports and strategy screens. The backend computes every figure;
// the app only presents them. The Plan tab's strategy dashboards (`/vip/strategy-dashboard` for
// Users, `/jarvis/premium/strategy-dashboard` for the Owner) live in `StrategyModels.swift`; the
// backend picks the Users or Owner model by the server role (CLAUDE.md §4.A), never the app.
// `/vip/debt-advisory` is not used. Same shapes as Android `InsightModels.kt`.
// Every field is optional: a missing value is unknown and is shown as "—", never as zero.

public struct CategoryTotal: Decodable, Sendable, Equatable {
    public let category: String?
    public let amount: Decimal?
}

public struct GoalProgress: Decodable, Sendable, Equatable {
    public let current: Decimal?
    public let target: Decimal?
    public let progress: Double?
    public let active: Int?
}

/// `GET /user-product/free/monthly-summary?period=YYYY-MM`.
public struct MonthlySummary: Decodable, Sendable, Equatable {
    public let period: String?
    public let income: Decimal?
    public let expenses: Decimal?
    public let debtPaid: Decimal?
    public let balance: Decimal?
    public let topCategory: CategoryTotal?
    public let categories: [CategoryTotal]?
    public let savings: Decimal?
    public let goals: GoalProgress?
}

/// `GET /user-product/basic/dashboard` (Basic).
public struct BasicDashboard: Decodable, Sendable, Equatable {
    public struct DebtProgress: Decodable, Sendable, Equatable {
        public let original: Decimal?
        public let remaining: Decimal?
        public let monthly: Decimal?
        public let progress: Double?
    }
    public let month: String?
    public let income: Decimal?
    public let expenses: Decimal?
    public let debtPaid: Decimal?
    public let balance: Decimal?
    public let debt: DebtProgress?
    public let savings: Decimal?
    public let goals: GoalProgress?
    public let categories: [CategoryTotal]?
    public let monthlyHistory: [MonthTotals]?
}

/// `GET /user-product/basic/calendar?period=YYYY-MM` (Basic).
public struct FinancialCalendar: Decodable, Sendable, Equatable {
    public struct Event: Decodable, Sendable, Equatable {
        public let date: String?
        public let kind: String?
        public let name: String?
        public let amount: Decimal?
        public let source: String?
    }
    public struct Summary: Decodable, Sendable, Equatable {
        public let incomeEvents: Int?
        public let payments: Decimal?
        public let commitments: Int?
    }
    public let period: String?
    public let events: [Event]?
    public let summary: Summary?
}

/// `GET /user-product/basic/reports?period=YYYY-MM` (Basic; `advanced_reports`).
public struct MonthReport: Decodable, Sendable, Equatable {
    public struct Comparison: Decodable, Sendable, Equatable {
        public let income: Decimal?
        public let expenses: Decimal?
        public let debtPaid: Decimal?
    }
    public let period: String?
    public let income: Decimal?
    public let expenses: Decimal?
    public let debtPaid: Decimal?
    public let goalContributions: Decimal?
    public let saved: Decimal?
    public let balance: Decimal?
    public let categories: [CategoryTotal]?
    public let comparison: Comparison?
}

/// `GET /finance/strategy-basic` (Basic) and the neutral `/finance/strategy-vip` (VIP).
public struct Strategy: Decodable, Sendable, Equatable {
    public struct Allocation: Decodable, Sendable, Equatable {
        public let bucket: String?
        public let label: String?
        public let amount: Decimal?
        /// The debt an extra payment goes to (Basic `debt_extra`).
        public let debtId: Int?
    }
    /// How the Basic strategy got its monthly income: what the user declared, else the income
    /// recorded in DINCR (an estimate, never written back as declared), else none.
    public struct IncomeBasis: Decodable, Sendable, Equatable {
        public let source: String?
        public let policy: String?
        public let observedSource: String?
    }
    public struct TargetDebt: Decodable, Sendable, Equatable {
        public let name: String?
        public let remainingAmount: Decimal?
        public let monthlyPayment: Decimal?
    }
    public struct Projection: Decodable, Sendable, Equatable {
        public let name: String?
        public let months: Int?
        public let baselineMonths: Int?
        public let monthlyToTarget: Decimal?
    }
    public struct Paycheck: Decodable, Sendable, Equatable {
        public let payFrequency: String?
        public let estimatedPaycheck: Decimal?
        public let envelopes: [Allocation]?
        public let unassigned: Decimal?
    }
    public struct GoalGuidance: Decodable, Sendable, Equatable {
        public let name: String?
        public let remaining: Decimal?
        public let targetDate: String?
        public let monthlyNeeded: Decimal?
    }
    public struct InsightAlert: Decodable, Sendable, Equatable {
        public let level: String?
        public let code: String?
        public let message: String?
    }
    public struct Insights: Decodable, Sendable, Equatable {
        public let emergencyMonths: Double?
        public let emergencyProgress: Double?
        public let goalGuidance: [GoalGuidance]?
        public let alerts: [InsightAlert]?
        public let totalDebt: Decimal?
    }
    public let status: String?
    public let priority: String?
    public let monthlyIncome: Decimal?
    public let essentialExpenses: Decimal?
    public let minimumDebtPayments: Decimal?
    public let strategicMargin: Decimal?
    public let allocations: [Allocation]?
    public let vipAllocations: [Allocation]?
    public let targetDebt: TargetDebt?
    public let recommendation: String?
    public let warnings: [String]?
    public let projection: Projection?
    public let nextPaycheck: Paycheck?
    public let directorNote: String?
    public let insights: Insights?
    /// `declared` | `observed` | `none` (strategy-basic).
    public let incomeSource: String?
    public let incomeBasis: IncomeBasis?

    /// The income is an estimate from recorded movements, not a declared figure: the screen says so.
    public var usesObservedIncome: Bool { (incomeSource ?? incomeBasis?.source) == "observed" }
    /// No income to plan with: the screen asks for the financial situation instead of a strategy.
    public var needsIncome: Bool { status == "needs_income" }
}

/// `POST /finance/strategy-vip/simulate`: a what-if that is not saved.
public struct ScenarioRequest: Encodable, Sendable, Equatable {
    public let monthlyIncomeChange: Decimal
    public let monthlyExpenseChange: Decimal
    public let oneTimeExtra: Decimal
    public init(monthlyIncomeChange: Decimal, monthlyExpenseChange: Decimal, oneTimeExtra: Decimal) {
        self.monthlyIncomeChange = monthlyIncomeChange; self.monthlyExpenseChange = monthlyExpenseChange; self.oneTimeExtra = oneTimeExtra
    }
}

public struct ScenarioResult: Decodable, Sendable, Equatable {
    public struct Delta: Decodable, Sendable, Equatable {
        public let strategicMargin: Decimal?
        public let monthlyIncome: Decimal?
        public let essentialExpenses: Decimal?
    }
    public let current: Strategy?
    public let scenario: Strategy?
    public let delta: Delta?
}

/// `GET /user-product/vip/command-center` (VIP).
public struct CommandCenter: Decodable, Sendable, Equatable {
    public struct Director: Decodable, Sendable, Equatable {
        public let priority: String?
        public let headline: String?
        public let nextAction: String?
        public let dataComplete: Bool?
        /// With priority `incomplete`: the inputs DINCR needs before recommending (stable codes, #326).
        public let missing: [String]?
    }
    public struct Factor: Decodable, Sendable, Equatable {
        public let label: String?
        public let impact: String?
    }
    public struct Score: Decodable, Sendable, Equatable {
        public let value: Int?
        public let label: String?
        public let factors: [Factor]?
    }
    public struct Plan: Decodable, Sendable, Equatable {
        public let method: String?
        public let target: String?
        public let monthlyToTarget: Decimal?
        public let months: Int?
        public let interest: Decimal?
    }
    public struct DebtPlanner: Decodable, Sendable, Equatable {
        public let recommended: Plan?
        public let strategies: [Plan]?
    }
    public struct SafeToSpend: Decodable, Sendable, Equatable {
        public let amount: Decimal?
        public let monthlyMargin: Decimal?
        public let next45DaysMinimum: Decimal?
        /// Why a figure is null: the inputs DINCR doesn't know (stable codes, #326). Unknown ≠ 0.
        public let missing: [String]?

        enum CodingKeys: String, CodingKey {
            case amount, monthlyMargin, missing
            // convertFromSnakeCase turns `next_45_days_minimum` into `next45DaysMinimum`.
            case next45DaysMinimum
        }
    }
    public struct Alert: Decodable, Sendable, Equatable {
        public let severity: String?
        public let title: String?
        public let context: String?
        public let action: String?
    }
    public struct ProjectionPoint: Decodable, Sendable, Equatable {
        public let months: Int?
        public let cash: Decimal?
        public let debt: Decimal?
        public let netWorth: Decimal?
        public let confidence: String?
    }
    public struct RoadmapStep: Decodable, Sendable, Equatable {
        public let order: Int?
        public let title: String?
        public let amount: Decimal?
        public let why: String?
    }
    public struct Automation: Decodable, Sendable, Equatable {
        public let confirmed: Int?
        public let review: Int?
        public let duplicates: Int?
    }
    public let asOf: String?
    public let director: Director?
    public let score: Score?
    public let debtPlanner: DebtPlanner?
    public let safeToSpend: SafeToSpend?
    public let alerts: [Alert]?
    public let projections: [ProjectionPoint]?
    public let roadmap: [RoadmapStep]?
    public let automation: Automation?
    /// The ledger of recorded movements; `current` is this month's (Hoy's month facts for VIP).
    public let reports: Reports?

    public struct Reports: Decodable, Sendable, Equatable {
        public let current: MonthTotals?
    }
}

/// `GET /user-product/vip/aguinaldo` (VIP; 409 when not applicable). CRC by law.
public struct Aguinaldo: Decodable, Sendable, Equatable {
    public struct Period: Decodable, Sendable, Equatable {
        public let start: String?
        public let end: String?
        public let calculatedThrough: String?
    }
    public struct Month: Decodable, Sendable, Equatable {
        public let month: String?
        public let totalEarned: Decimal?
        public let entries: Int?
    }
    public let status: String?
    public let period: Period?
    public let earnedSalaryTotal: Decimal?
    public let accruedAguinaldo: Decimal?
    public let months: [Month]?
    public let missingMonths: [String]?
}

/// `GET /user-product/vip/lifecycle/monthly-review?period` (VIP).
public struct MonthlyReview: Decodable, Sendable, Equatable {
    public struct ScoreLine: Decodable, Sendable, Equatable {
        public let key: String?
        public let label: String?
        public let unit: String?
        public let current: Double?
        public let baseline: Double?
        public let delta: Double?
        /// `unknown` when a side can't be stated (the health score while a debt's rate is missing).
        public let trend: String?
        /// Why the line has no number (then `current` is nil): shown instead of a value.
        public let explanation: String?
    }
    public struct NextMonth: Decodable, Sendable, Equatable {
        public let priority: String?
        public let title: String?
        public let amount: Decimal?
        public let rationale: String?
    }
    public let status: String?
    public let period: String?
    public let headline: String?
    public let summary: String?
    public let scorecard: [ScoreLine]?
    public let nextMonth: NextMonth?
}

/// `GET /user-product/vip/lifecycle/proactive-advisor` (VIP).
public struct ProactiveAdvisor: Decodable, Sendable, Equatable {
    public struct Alert: Decodable, Sendable, Equatable, Identifiable {
        /// Where the advisor suggests looking (`route` is a backend code, mapped by `AttentionList`).
        public struct Action: Decodable, Sendable, Equatable {
            public let label: String?
            public let route: String?

            public init(label: String?, route: String?) { self.label = label; self.route = route }
        }

        public let id: String?
        public let code: String?
        public let severity: String?
        public let title: String?
        public let explanation: String?
        public let action: Action?

        public init(id: String?, code: String?, severity: String?, title: String?, explanation: String?, action: Action? = nil) {
            self.id = id; self.code = code; self.severity = severity; self.title = title; self.explanation = explanation; self.action = action
        }
    }
    public let status: String?
    public let asOf: String?
    public let alerts: [Alert]?
    public let message: String?
}
