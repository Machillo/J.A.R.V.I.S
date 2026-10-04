import Foundation

// JARVIS "Análisis financiero" (Owner only): the historical web Finanzas tab, read from three
// Owner routes (the backend's INTERNAL_ONLY routers decide; the app shows the section only to
// the Owner role):
// - `GET /transactions/analysis/summary` (transactions/analyzer.py `get_transaction_analysis`),
// - `GET /finance/net-worth` (finance/service.py `get_net_worth_report`),
// - `GET /finance/engine` (finance/strategic_engine.py `get_financial_engine_report`).
// Every figure is the backend's; decoding is tolerant (unknown or odd values are nil, never zero).
// Android twin: `OwnerAnalysis.kt`.

/// `GET /transactions/analysis/summary`.
public struct TransactionAnalysis: Decodable, Sendable, Equatable {
    public struct Summary: Decodable, Sendable, Equatable {
        public let income: Decimal?
        public let expenses: Decimal?
        public let debtPayments: Decimal?
        public let netFromTransactions: Decimal?
        public let totalTransactions: Int?

        enum CodingKeys: String, CodingKey { case income, expenses, debtPayments, netFromTransactions, totalTransactions }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            income = c.lenient(Decimal.self, .income)
            expenses = c.lenient(Decimal.self, .expenses)
            debtPayments = c.lenient(Decimal.self, .debtPayments)
            netFromTransactions = c.lenient(Decimal.self, .netFromTransactions)
            totalTransactions = c.lenient(Int.self, .totalTransactions)
        }
    }
    /// A month of `monthly_flow` (income vs spending) or of `expenses_by_month` (`total`).
    public struct MonthPoint: Decodable, Sendable, Equatable, Identifiable {
        public let month: String
        public let income: Decimal?
        public let expenses: Decimal?
        public let total: Decimal?
        public let monthlyBalance: Decimal?
        public var id: String { month }

        enum CodingKeys: String, CodingKey { case month, income, expenses, total, monthlyBalance }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            month = c.lenient(String.self, .month) ?? ""
            income = c.lenient(Decimal.self, .income)
            expenses = c.lenient(Decimal.self, .expenses)
            total = c.lenient(Decimal.self, .total)
            monthlyBalance = c.lenient(Decimal.self, .monthlyBalance)
        }
    }
    public struct CategoryTotal: Decodable, Sendable, Equatable {
        public let category: String?
        public let total: Decimal?
        public let count: Int?

        enum CodingKeys: String, CodingKey { case category, total, count }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            category = c.lenient(String.self, .category)
            total = c.lenient(Decimal.self, .total)
            count = c.lenient(Int.self, .count)
        }
    }
    public struct SpendingBreakdown: Decodable, Sendable, Equatable {
        public struct Period: Decodable, Sendable, Equatable {
            public let start: String?
            public let end: String?
            public let label: String?
        }
        public let period: Period?
        public let total: Decimal?
        public let categories: [CategoryTotal]?

        enum CodingKeys: String, CodingKey { case period, total, categories }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            period = c.lenient(Period.self, .period)
            total = c.lenient(Decimal.self, .total)
            categories = c.lenient([CategoryTotal].self, .categories)
        }
    }

    public let summary: Summary?
    public let expensesByMonth: [MonthPoint]?
    public let monthlyFlow: [MonthPoint]?
    public let spendingBreakdown: SpendingBreakdown?

    enum CodingKeys: String, CodingKey { case summary, expensesByMonth, monthlyFlow, spendingBreakdown }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        summary = c.lenient(Summary.self, .summary)
        expensesByMonth = c.lenient([MonthPoint].self, .expensesByMonth)
        monthlyFlow = c.lenient([MonthPoint].self, .monthlyFlow)
        spendingBreakdown = c.lenient(SpendingBreakdown.self, .spendingBreakdown)
    }

    /// The last `count` months of the flow with both figures, for the income vs expenses chart.
    public func flowMonths(last count: Int = 6) -> [MonthTotals] {
        let rows = (monthlyFlow ?? []).compactMap { point -> MonthTotals? in
            guard !point.month.isEmpty, let income = point.income, let expenses = point.expenses else { return nil }
            return MonthTotals(month: point.month, income: income, expenses: expenses, balance: point.monthlyBalance)
        }
        return Array(rows.suffix(count))
    }

    /// Spending categories with a known total, largest first (the backend already sorts them).
    public var spendingCategories: [CategoryAmount] {
        (spendingBreakdown?.categories ?? []).compactMap { row in
            guard let category = row.category, let total = row.total else { return nil }
            return CategoryAmount(category: category, amount: total)
        }
    }
}

/// `GET /finance/net-worth` (patrimonio).
public struct NetWorthReport: Decodable, Sendable, Equatable {
    public struct Assets: Decodable, Sendable, Equatable {
        public let savingsTotal: Decimal?
        public let investmentsTotal: Decimal?
        public let assetsTotal: Decimal?

        enum CodingKeys: String, CodingKey { case savingsTotal, investmentsTotal, assetsTotal }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            savingsTotal = c.lenient(Decimal.self, .savingsTotal)
            investmentsTotal = c.lenient(Decimal.self, .investmentsTotal)
            assetsTotal = c.lenient(Decimal.self, .assetsTotal)
        }
    }
    public struct Liabilities: Decodable, Sendable, Equatable {
        public let debtTotal: Decimal?
        public let monthlyDebtPayments: Decimal?

        enum CodingKeys: String, CodingKey { case debtTotal, monthlyDebtPayments }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            debtTotal = c.lenient(Decimal.self, .debtTotal)
            monthlyDebtPayments = c.lenient(Decimal.self, .monthlyDebtPayments)
        }
    }
    public struct Change: Decodable, Sendable, Equatable {
        public let amount: Decimal?
        public let percentage: Double?
        public let comparedWith: String?

        enum CodingKeys: String, CodingKey { case amount, percentage, comparedWith }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            amount = c.lenient(Decimal.self, .amount)
            percentage = c.lenient(Double.self, .percentage)
            comparedWith = c.lenient(String.self, .comparedWith)
        }
    }

    public let assets: Assets?
    public let liabilities: Liabilities?
    public let netWorth: Decimal?
    public let change: Change?
    public let status: String?
    public let interpretation: String?
    public let recommendations: [String]?

    enum CodingKeys: String, CodingKey { case assets, liabilities, netWorth, change, status, interpretation, recommendations }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        assets = c.lenient(Assets.self, .assets)
        liabilities = c.lenient(Liabilities.self, .liabilities)
        netWorth = c.lenient(Decimal.self, .netWorth)
        change = c.lenient(Change.self, .change)
        status = c.lenient(String.self, .status)
        interpretation = c.lenient(String.self, .interpretation)
        recommendations = c.lenient([String].self, .recommendations)
    }
}

/// `GET /finance/engine`: health score, month-end forecast, emergency fund, debt strategy.
public struct FinancialEngineReport: Decodable, Sendable, Equatable {
    public struct Health: Decodable, Sendable, Equatable {
        public let score: Double?
        public let level: String?
        public let confidence: Double?

        enum CodingKeys: String, CodingKey { case score, level, confidence }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            score = c.lenient(Double.self, .score)
            level = c.lenient(String.self, .level)
            confidence = c.lenient(Double.self, .confidence)
        }
    }
    public struct Forecast: Decodable, Sendable, Equatable {
        public struct Alert: Decodable, Sendable, Equatable {
            public let level: String?
            public let message: String?
        }
        public let month: String?
        public let projectedEndBalance: Decimal?
        public let alert: Alert?

        enum CodingKeys: String, CodingKey { case month, projectedEndBalance, alert }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            month = c.lenient(String.self, .month)
            projectedEndBalance = c.lenient(Decimal.self, .projectedEndBalance)
            alert = c.lenient(Alert.self, .alert)
        }
    }
    public struct EmergencyFund: Decodable, Sendable, Equatable {
        public let current: Decimal?
        public let monthlyBase: Decimal?
        public let recommended6Months: Decimal?
        public let coverageMonths: Double?

        enum CodingKeys: String, CodingKey {
            case current, monthlyBase, coverageMonths
            // convertFromSnakeCase turns `recommended_6_months` into `recommended6Months`.
            case recommended6Months
        }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            current = c.lenient(Decimal.self, .current)
            monthlyBase = c.lenient(Decimal.self, .monthlyBase)
            recommended6Months = c.lenient(Decimal.self, .recommended6Months)
            coverageMonths = c.lenient(Double.self, .coverageMonths)
        }
    }
    public struct DebtStrategies: Decodable, Sendable, Equatable {
        public struct Plan: Decodable, Sendable, Equatable {
            public struct Target: Decodable, Sendable, Equatable {
                public let name: String?
                public let remainingAmount: Decimal?

                enum CodingKeys: String, CodingKey { case name, remainingAmount }
                public init(from decoder: Decoder) throws {
                    let c = try decoder.container(keyedBy: CodingKeys.self)
                    name = c.lenient(String.self, .name)
                    remainingAmount = c.lenient(Decimal.self, .remainingAmount)
                }
            }
            public let name: String?
            public let priorityDebt: Target?

            enum CodingKeys: String, CodingKey { case name, priorityDebt }
            public init(from decoder: Decoder) throws {
                let c = try decoder.container(keyedBy: CodingKeys.self)
                name = c.lenient(String.self, .name)
                priorityDebt = c.lenient(Target.self, .priorityDebt)
            }
        }
        public let status: String?
        public let recommended: Plan?
        public let note: String?

        enum CodingKeys: String, CodingKey { case status, recommended, note }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            status = c.lenient(String.self, .status)
            recommended = c.lenient(Plan.self, .recommended)
            note = c.lenient(String.self, .note)
        }
    }

    public let status: String?
    public let health: Health?
    public let forecast: Forecast?
    public let emergencyFund: EmergencyFund?
    public let debts: DebtStrategies?
    public let recommendations: [String]?

    enum CodingKeys: String, CodingKey { case status, health, forecast, emergencyFund, debts, recommendations }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        status = c.lenient(String.self, .status)
        health = c.lenient(Health.self, .health)
        forecast = c.lenient(Forecast.self, .forecast)
        emergencyFund = c.lenient(EmergencyFund.self, .emergencyFund)
        debts = c.lenient(DebtStrategies.self, .debts)
        recommendations = c.lenient([String].self, .recommendations)
    }
}

/// The three answers of the Owner's analysis, loaded together.
public struct OwnerAnalysis: Sendable, Equatable {
    public let transactions: TransactionAnalysis
    public let netWorth: NetWorthReport
    public let engine: FinancialEngineReport

    public init(transactions: TransactionAnalysis, netWorth: NetWorthReport, engine: FinancialEngineReport) {
        self.transactions = transactions; self.netWorth = netWorth; self.engine = engine
    }
}
