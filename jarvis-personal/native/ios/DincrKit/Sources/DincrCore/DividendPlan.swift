import Foundation

// Plan de dividendos (Owner; JARVIS → Patrimonio; `GET/PUT /finance/investment-center/dividend-plan`):
// how much capital a monthly dividend goal needs, with one or two stocks the Owner picks. Every
// figure is the backend's (`finance/dividend_plan.py`); one it did not send is unknown (nil), never 0.
// Android twin: `DividendPlan.kt`.

public struct DividendPlan: Decodable, Sendable, Equatable {
    public struct Stock: Codable, Sendable, Equatable {
        public let symbol: String
        public let sharePct: Decimal
        public let yieldPct: Decimal?

        public init(symbol: String, sharePct: Decimal, yieldPct: Decimal?) {
            self.symbol = symbol; self.sharePct = sharePct; self.yieldPct = yieldPct
        }

        enum CodingKeys: String, CodingKey { case symbol, sharePct, yieldPct }
        public func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(symbol, forKey: .symbol); try c.encode(sharePct, forKey: .sharePct); try c.encode(yieldPct, forKey: .yieldPct)
        }
    }

    public struct Config: Decodable, Sendable, Equatable {
        public let stocks: [Stock]
        public let goalMonthlyUsd: Decimal?
        public let monthlyAmountUsd: Decimal?
        public let withholdingPct: Decimal?
    }

    public struct Gate: Decodable, Sendable, Equatable {
        public struct Blocker: Decodable, Sendable, Equatable { public let code: String }
        public let open: Bool
        public let blockers: [Blocker]
    }

    public struct Result: Decodable, Sendable, Equatable {
        public struct Horizon: Decodable, Sendable, Equatable { public let years: Int; public let amountUsd: Decimal }
        public struct Purchase: Decodable, Sendable, Equatable { public let symbol: String; public let amountUsd: Decimal }

        public let ready: Bool
        public let netYieldPct: Decimal?
        public let capitalNeededUsd: Decimal?
        public let currentValueUsd: Decimal?
        public let missingUsd: Decimal?
        public let netMonthlyDividendNowUsd: Decimal?
        public let monthsToGoal: Int?
        public let monthlyNeeded: [Horizon]
        public let buyThisMonth: [Purchase]
    }

    public let config: Config
    public let heldSymbols: [String]
    public let gate: Gate
    public let result: Result

    /// No stock chosen yet: the card invites to set it up instead of showing empty figures.
    public var isConfigured: Bool { !config.stocks.isEmpty }
}

/// `PUT /finance/investment-center/dividend-plan`: every field is sent (a null clears it).
public struct DividendPlanUpdate: Encodable, Sendable, Equatable {
    public let stocks: [DividendPlan.Stock]
    public let goalMonthlyUsd: Decimal?
    public let monthlyAmountUsd: Decimal?
    public let withholdingPct: Decimal?

    public init(stocks: [DividendPlan.Stock], goalMonthlyUsd: Decimal?, monthlyAmountUsd: Decimal?, withholdingPct: Decimal?) {
        self.stocks = stocks; self.goalMonthlyUsd = goalMonthlyUsd; self.monthlyAmountUsd = monthlyAmountUsd; self.withholdingPct = withholdingPct
    }

    enum CodingKeys: String, CodingKey { case stocks, goalMonthlyUsd, monthlyAmountUsd, withholdingPct }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(stocks, forKey: .stocks); try c.encode(goalMonthlyUsd, forKey: .goalMonthlyUsd)
        try c.encode(monthlyAmountUsd, forKey: .monthlyAmountUsd); try c.encode(withholdingPct, forKey: .withholdingPct)
    }
}

extension DincrService {
    /// A read: it only calculates, and never buys or moves anything.
    public func dividendPlan() async throws -> DividendPlan { try await client.get("/finance/investment-center/dividend-plan") }

    public func updateDividendPlan(_ update: DividendPlanUpdate) async throws -> DividendPlan {
        try await client.send("PUT", "/finance/investment-center/dividend-plan", body: update)
    }
}
