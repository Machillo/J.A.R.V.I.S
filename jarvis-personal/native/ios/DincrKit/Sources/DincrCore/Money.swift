import Foundation

// JARVIS → Mi dinero (Owner): the current cycle (`GET /finance/cycle-report`: expected and received
// income, the statement period's spending, debt payments, goal reserves and the real balance) and the
// Owner's accounts (`GET /finance/account-balances`). Both reads never write; saving or removing an
// account is an explicit Owner command. Every amount is the backend's: one it did not send is
// unknown (nil), never 0. Android twin: `Money.kt`.

/// `GET /finance/cycle-report`. Only the figures the screen shows.
public struct CycleReport: Decodable, Sendable, Equatable {
    public struct Period: Decodable, Sendable, Equatable {
        public let start: String?
        public let end: String?
        public let label: String?
        /// The statement period only: whether it already closed.
        public let closed: Bool?

        enum CodingKeys: String, CodingKey { case start, end, label, closed }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            start = c.lenient(String.self, .start); end = c.lenient(String.self, .end)
            label = c.lenient(String.self, .label); closed = c.lenient(Bool.self, .closed)
        }
    }

    public struct Income: Decodable, Sendable, Equatable {
        public let fixedExpected: Decimal?
        public let extraExpected: Decimal?
        public let expectedTotal: Decimal?
        public let receivedFromTransactions: Decimal?
        /// The projected salary still to come (received salary replaces the projection).
        public let pendingProjection: Decimal?
        public let otherCashInflows: Decimal?

        enum CodingKeys: String, CodingKey { case fixedExpected, extraExpected, expectedTotal, receivedFromTransactions, pendingProjection, otherCashInflows }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            fixedExpected = c.lenient(Decimal.self, .fixedExpected); extraExpected = c.lenient(Decimal.self, .extraExpected)
            expectedTotal = c.lenient(Decimal.self, .expectedTotal); receivedFromTransactions = c.lenient(Decimal.self, .receivedFromTransactions)
            pendingProjection = c.lenient(Decimal.self, .pendingProjection); otherCashInflows = c.lenient(Decimal.self, .otherCashInflows)
        }
    }

    public struct Expenses: Decodable, Sendable, Equatable {
        /// Spending plus debt payments.
        public let currentPeriod: Decimal?
        public let spendingOnly: Decimal?
        public let debtPayments: Decimal?
        public let transactionCount: Int?

        enum CodingKeys: String, CodingKey { case currentPeriod, spendingOnly, debtPayments, transactionCount }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            currentPeriod = c.lenient(Decimal.self, .currentPeriod); spendingOnly = c.lenient(Decimal.self, .spendingOnly)
            debtPayments = c.lenient(Decimal.self, .debtPayments); transactionCount = c.lenient(Int.self, .transactionCount)
        }
    }

    public struct Goals: Decodable, Sendable, Equatable {
        public let reservedCurrentPeriod: Decimal?

        enum CodingKeys: String, CodingKey { case reservedCurrentPeriod }
        public init(from decoder: Decoder) throws {
            reservedCurrentPeriod = try decoder.container(keyedBy: CodingKeys.self).lenient(Decimal.self, .reservedCurrentPeriod)
        }
    }

    public struct Cashflow: Decodable, Sendable, Equatable {
        public let realBalance: Decimal?
        public let loanReceived: Decimal?

        enum CodingKeys: String, CodingKey { case realBalance, loanReceived }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            realBalance = c.lenient(Decimal.self, .realBalance); loanReceived = c.lenient(Decimal.self, .loanReceived)
        }
    }

    public let status: String?
    public let asOf: String?
    /// The income cycle (5 → 5).
    public let cycle: Period?
    /// The card statement period (21 → 21).
    public let expenseCycle: Period?
    public let income: Income?
    public let expenses: Expenses?
    public let goals: Goals?
    public let cashflow: Cashflow?

    enum CodingKeys: String, CodingKey { case status, asOf, cycle, expenseCycle, income, expenses, goals, cashflow }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        status = c.lenient(String.self, .status); asOf = c.lenient(String.self, .asOf)
        cycle = c.lenient(Period.self, .cycle); expenseCycle = c.lenient(Period.self, .expenseCycle)
        income = c.lenient(Income.self, .income); expenses = c.lenient(Expenses.self, .expenses)
        goals = c.lenient(Goals.self, .goals); cashflow = c.lenient(Cashflow.self, .cashflow)
    }
}

/// `GET /finance/account-balances`: the Owner's active accounts and their real total in colones.
public struct AccountBalances: Decodable, Sendable, Equatable {
    public struct Account: Decodable, Sendable, Equatable, Identifiable {
        /// The backend's id: a number for a recorded account, a text (`ibkr-…`) for the brokerage snapshot.
        public let id: String
        public let accountName: String?
        public let bankName: String?
        public let accountLast4: String?
        public let currency: String?
        public let accountType: String?
        /// The last declared balance.
        public let currentBalance: Decimal?
        /// The declared balance plus the movements recorded since (absent for the brokerage snapshot).
        public let calculatedBalance: Decimal?
        public let balanceCrc: Decimal?
        public let balanceAsOf: String?
        public let includeInNetWorth: Bool
        public let readOnly: Bool
        public let source: String?
        public let movementsSinceBalance: Int?

        /// The numeric id a write needs; nil for the brokerage snapshot.
        public var accountId: Int? { Int(id) }
        /// Only recorded accounts can be updated or removed here (the brokerage snapshot is read-only).
        public var isEditable: Bool { !readOnly && accountId != nil }
        /// The balance shown: the calculated one when the backend sent it, else the declared one.
        public var balance: Decimal? { calculatedBalance ?? currentBalance }

        enum CodingKeys: String, CodingKey {
            case id, accountName, bankName, accountLast4, currency, accountType, currentBalance, calculatedBalance, balanceCrc, balanceAsOf
            case includeInNetWorth, readOnly, source, movementsSinceBalance
        }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            id = c.lenient(Int.self, .id).map(String.init) ?? c.lenient(String.self, .id) ?? ""
            accountName = c.lenient(String.self, .accountName); bankName = c.lenient(String.self, .bankName)
            accountLast4 = c.lenient(String.self, .accountLast4).flatMap { $0.isEmpty ? nil : $0 }
            currency = c.lenient(String.self, .currency); accountType = c.lenient(String.self, .accountType)
            currentBalance = c.lenient(Decimal.self, .currentBalance); calculatedBalance = c.lenient(Decimal.self, .calculatedBalance)
            balanceCrc = c.lenient(Decimal.self, .balanceCrc); balanceAsOf = c.lenient(String.self, .balanceAsOf)
            // The backend's default: an account counts toward net worth unless it says otherwise.
            includeInNetWorth = c.lenient(Bool.self, .includeInNetWorth) ?? true
            readOnly = c.lenient(Bool.self, .readOnly) ?? false
            source = c.lenient(String.self, .source); movementsSinceBalance = c.lenient(Int.self, .movementsSinceBalance)
        }
    }

    public let items: [Account]
    /// The included accounts' total, in colones.
    public let totalRealBalance: Decimal?
    public let currency: String?

    enum CodingKeys: String, CodingKey { case items, totalRealBalance, currency }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        items = c.lenient([Account].self, .items) ?? []
        totalRealBalance = c.lenient(Decimal.self, .totalRealBalance)
        currency = c.lenient(String.self, .currency)
    }
}

/// `POST /finance/account-balances`: creates or updates an account (identity: name + last 4 digits)
/// with the balance the Owner checked.
public struct AccountBalanceRequest: Encodable, Sendable, Equatable {
    public static let currencies = ["CRC", "USD"]
    public static let accountTypes = ["checking", "savings", "credit_card", "cash", "other"]

    public let accountName: String
    public let currentBalance: Decimal
    public let bankName: String
    public let accountLast4: String
    public let currency: String
    public let accountType: String
    public let includeInNetWorth: Bool
    public let annualInterestRate: Decimal
    public let source: String
    public let note: String

    public init(accountName: String, currentBalance: Decimal, bankName: String = "", accountLast4: String = "", currency: String = "CRC",
                accountType: String = "checking", includeInNetWorth: Bool = true) {
        self.accountName = accountName; self.currentBalance = currentBalance; self.bankName = bankName; self.accountLast4 = accountLast4
        self.currency = currency; self.accountType = accountType; self.includeInNetWorth = includeInNetWorth
        annualInterestRate = 0; source = "manual"; note = ""
    }

    enum CodingKeys: String, CodingKey {
        case currency, source, note
        case accountName = "account_name", currentBalance = "current_balance", bankName = "bank_name", accountLast4 = "account_last4"
        case accountType = "account_type", includeInNetWorth = "include_in_net_worth", annualInterestRate = "annual_interest_rate"
    }

    /// Empty, or exactly four digits.
    public static func isValidLast4(_ text: String) -> Bool { text.isEmpty || (text.count == 4 && text.allSatisfy { $0.isASCII && $0.isNumber }) }
}
