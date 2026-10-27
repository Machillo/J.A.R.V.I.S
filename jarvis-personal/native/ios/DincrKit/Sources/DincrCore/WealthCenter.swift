import Foundation

// JARVIS → Patrimonio (Owner): the investment center (`GET /finance/investment-center`: the latest
// IBKR or manual portfolio snapshot, its positions and the money reserved to invest) and the
// business center (`GET /finance/business-center`: the Owner's businesses and their movements).
// Both reads never write. Refreshing from IBKR, creating a business and recording a movement are
// explicit Owner commands. Every amount is the backend's: one it did not send is unknown (nil),
// never 0. Android twin: `WealthCenter.kt`.

/// `GET /finance/investment-center`.
public struct InvestmentCenter: Decodable, Sendable, Equatable {
    /// The latest portfolio snapshot. The backend sends `{}` when there is none.
    public struct Portfolio: Decodable, Sendable, Equatable {
        public let marketValue: Decimal?
        public let contributedCapital: Decimal?
        public let realizedPnl: Decimal?
        public let unrealizedPnl: Decimal?
        public let dividends: Decimal?
        public let currency: String?
        public let snapshotAt: String?
        public let source: String?

        enum CodingKeys: String, CodingKey { case marketValue, contributedCapital, realizedPnl, unrealizedPnl, dividends, currency, snapshotAt, source }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            marketValue = c.lenient(Decimal.self, .marketValue); contributedCapital = c.lenient(Decimal.self, .contributedCapital)
            realizedPnl = c.lenient(Decimal.self, .realizedPnl); unrealizedPnl = c.lenient(Decimal.self, .unrealizedPnl)
            dividends = c.lenient(Decimal.self, .dividends); currency = c.lenient(String.self, .currency)
            snapshotAt = c.lenient(String.self, .snapshotAt); source = c.lenient(String.self, .source)
        }
    }

    /// One position of the snapshot (`investment_position_snapshots`).
    public struct Position: Decodable, Sendable, Equatable, Identifiable {
        public let symbol: String?
        public let secType: String?
        public let currency: String?
        /// The quantity held (`position`).
        public let quantity: Decimal?
        public let marketPrice: Decimal?
        public let marketValue: Decimal?
        public let unrealizedPnl: Decimal?
        public var id: String { "\(symbol ?? "")|\(secType ?? "")|\(currency ?? "")" }

        enum CodingKeys: String, CodingKey { case symbol, secType, currency, position, marketPrice, marketValue, unrealizedPnl }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            symbol = c.lenient(String.self, .symbol); secType = c.lenient(String.self, .secType); currency = c.lenient(String.self, .currency)
            quantity = c.lenient(Decimal.self, .position); marketPrice = c.lenient(Decimal.self, .marketPrice)
            marketValue = c.lenient(Decimal.self, .marketValue); unrealizedPnl = c.lenient(Decimal.self, .unrealizedPnl)
        }
    }

    /// The figures shown for the portfolio; only built when there is a snapshot.
    public struct Figures: Sendable, Equatable {
        public let marketValue: Decimal
        public let contributedCapital: Decimal?
        public let netPnl: Decimal?
        public let returnPct: Decimal?
        public let currency: String?
    }

    public enum SyncState: Sendable, Equatable { case current, stale, manual, unknown }

    public let portfolio: Portfolio?
    public let reservedToInvestCrc: Decimal?
    public let grossPnl: Decimal?
    public let netPnl: Decimal?
    public let returnPct: Decimal?
    public let positions: [Position]
    public let syncStatus: String?
    public let snapshotAgeSeconds: Int?
    public let syncMethod: String?
    /// Whether the server can refresh the snapshot from IBKR (Flex credentials configured).
    public let flexConfigured: Bool
    public let includedInNetWorth: Bool?

    enum CodingKeys: String, CodingKey {
        case portfolio, reservedToInvestCrc, grossPnl, netPnl, returnPct, positions, syncStatus, snapshotAgeSeconds, syncMethod, flexConfigured, includedInNetWorth
    }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        portfolio = c.lenient(Portfolio.self, .portfolio)
        reservedToInvestCrc = c.lenient(Decimal.self, .reservedToInvestCrc)
        grossPnl = c.lenient(Decimal.self, .grossPnl); netPnl = c.lenient(Decimal.self, .netPnl); returnPct = c.lenient(Decimal.self, .returnPct)
        positions = c.lenient([Position].self, .positions) ?? []
        syncStatus = c.lenient(String.self, .syncStatus)
        snapshotAgeSeconds = c.lenient(Int.self, .snapshotAgeSeconds)
        syncMethod = c.lenient(String.self, .syncMethod)
        flexConfigured = c.lenient(Bool.self, .flexConfigured) ?? false
        includedInNetWorth = c.lenient(Bool.self, .includedInNetWorth)
    }

    /// Whether there is a portfolio snapshot at all. Without one the backend still answers
    /// `gross_pnl`, `net_pnl` and `return_pct` as 0: that is unknown, not a zero return.
    public var hasPortfolio: Bool { portfolio?.marketValue != nil }

    /// The portfolio figures, or nil when there is no snapshot (never ₡0 / 0 %).
    public var figures: Figures? {
        guard hasPortfolio, let portfolio, let market = portfolio.marketValue else { return nil }
        return Figures(marketValue: market, contributedCapital: portfolio.contributedCapital, netPnl: netPnl,
                       // No contributed capital: the backend's 0 % return is unknown, not a result.
                       returnPct: (portfolio.contributedCapital ?? 0) > 0 ? returnPct : nil, currency: portfolio.currency)
    }

    public var syncState: SyncState {
        switch syncStatus {
        case "current": .current
        case "stale": .stale
        case "manual_ready_for_ibkr": .manual
        default: .unknown
        }
    }

    /// Whole hours since the snapshot, or nil when unknown.
    public var ageHours: Int? { snapshotAgeSeconds.map { max(0, $0) / 3600 } }
}

/// `POST /finance/investment-center/sync-ibkr`: the server's answer after refreshing the snapshot.
public struct IbkrSyncResult: Decodable, Sendable, Equatable {
    public let status: String?
    public let positions: Int?
}

/// `GET /finance/business-center`.
public struct BusinessCenter: Decodable, Sendable, Equatable {
    public struct Business: Decodable, Sendable, Equatable, Identifiable {
        public let id: Int
        public let name: String?
        public let description: String?
        public let ownershipPct: Decimal?
        public let status: String?

        enum CodingKeys: String, CodingKey { case id, name, description, ownershipPct, status }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            id = c.lenient(Int.self, .id) ?? 0
            name = c.lenient(String.self, .name); description = c.lenient(String.self, .description)
            ownershipPct = c.lenient(Decimal.self, .ownershipPct); status = c.lenient(String.self, .status)
        }
    }

    public struct Movement: Decodable, Sendable, Equatable, Identifiable {
        public let id: Int
        public let businessId: Int?
        public let movementDate: String?
        /// `income`, `expense` or `capital`.
        public let movementType: String?
        public let amount: Decimal?
        public let description: String?
        public let category: String?

        enum CodingKeys: String, CodingKey { case id, businessId, movementDate, movementType, amount, description, category }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            id = c.lenient(Int.self, .id) ?? 0
            businessId = c.lenient(Int.self, .businessId); movementDate = c.lenient(String.self, .movementDate)
            movementType = c.lenient(String.self, .movementType); amount = c.lenient(Decimal.self, .amount)
            description = c.lenient(String.self, .description); category = c.lenient(String.self, .category)
        }
    }

    public let businesses: [Business]
    public let movements: [Movement]
    public let income: Decimal?
    public let expenses: Decimal?
    public let profit: Decimal?
    public let capital: Decimal?

    enum CodingKeys: String, CodingKey { case businesses, movements, income, expenses, profit, capital }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        businesses = c.lenient([Business].self, .businesses) ?? []
        movements = c.lenient([Movement].self, .movements) ?? []
        income = c.lenient(Decimal.self, .income); expenses = c.lenient(Decimal.self, .expenses)
        profit = c.lenient(Decimal.self, .profit); capital = c.lenient(Decimal.self, .capital)
    }

    /// The business's movements, newest first as the backend sent them, at most `limit`.
    public func movements(of business: Business, limit: Int = 5) -> [Movement] {
        Array(movements.filter { $0.businessId == business.id }.prefix(limit))
    }
}

/// `POST /finance/business-center/businesses`.
public struct BusinessCreateRequest: Encodable, Sendable, Equatable {
    public let name: String
    public let description: String?
    public let ownershipPct: Decimal
    public init(name: String, description: String? = nil, ownershipPct: Decimal = 100) {
        self.name = name; self.description = description; self.ownershipPct = ownershipPct
    }
    enum CodingKeys: String, CodingKey { case name, description, ownershipPct = "ownership_pct" }
}

/// `POST /finance/business-center/movements`. An income or expense also creates a transaction in the
/// Owner's ledger (backend `business_center.py`); capital does not.
public struct BusinessMovementRequest: Encodable, Sendable, Equatable {
    public static let types = ["income", "expense", "capital"]

    public let businessId: Int
    public let movementType: String
    public let amount: Decimal
    public let movementDate: String?
    public let description: String
    public let category: String?
    public init(businessId: Int, movementType: String, amount: Decimal, movementDate: String? = nil, description: String, category: String? = nil) {
        self.businessId = businessId; self.movementType = movementType; self.amount = amount
        self.movementDate = movementDate; self.description = description; self.category = category
    }
    enum CodingKeys: String, CodingKey {
        case amount, description, category
        case businessId = "business_id", movementType = "movement_type", movementDate = "movement_date"
    }

    /// Whether the movement also lands in the Owner's transactions.
    public var createsTransaction: Bool { movementType == "income" || movementType == "expense" }
}

/// The answer of both business writes (the stored row).
public struct BusinessWriteResult: Decodable, Sendable, Equatable {
    public let id: Int?
}
