import Foundation

// The fixture backend's JARVIS → Mi dinero routes (Debug demos and tests only). Same shapes and
// access rule as FastAPI: `/finance/*` admits only the verified Owner (INTERNAL_ONLY). Every name
// and amount is invented (CLAUDE.md §4.F).

/// One of the Owner's accounts with its declared balance.
struct FixtureAccount {
    let id: Int
    let name: String
    var bank: String
    let last4: String
    var currency: String
    var type: String
    var balance: Decimal
    var includeInNetWorth: Bool
    /// The day of the declared balance, in days from today.
    var asOfOffset: Int

    static let seed: [FixtureAccount] = [
        FixtureAccount(id: 901, name: "Cuenta de ejemplo", bank: "Banco de ejemplo", last4: "1111", currency: "CRC", type: "checking",
                       balance: 310_000, includeInNetWorth: true, asOfOffset: -3),
        FixtureAccount(id: 902, name: "Ahorro en dólares", bank: "Banco de ejemplo", last4: "2222", currency: "USD", type: "savings",
                       balance: 1_200, includeInNetWorth: true, asOfOffset: -10),
        FixtureAccount(id: 903, name: "Detectada por correo", bank: "Banco de ejemplo", last4: "3333", currency: "CRC", type: "checking",
                       balance: 0, includeInNetWorth: false, asOfOffset: -1),
    ]
}

extension FixtureBackend {
    /// An invented colones-per-dollar rate for the fixture's totals.
    private static let usdRate: Decimal = 500

    func moneyRoute(_ method: String, _ path: String, _ body: [String: Any]) -> Answer? {
        guard path == "/finance/cycle-report" || path.hasPrefix("/finance/account-balances") else { return nil }
        guard profile["role"] as? String == "owner" else { return error(403, "No tienes permisos para realizar esta acción.") }
        switch method {
        case "GET" where path == "/finance/cycle-report":
            return ok(cycleReport())
        case "GET" where path == "/finance/account-balances":
            return ok(accountBalances())
        case "POST" where path == "/finance/account-balances":
            let name = (body["account_name"] as? String ?? "").trimmingCharacters(in: .whitespaces)
            guard !name.isEmpty, let balance = decimal(body["current_balance"]) else { return error(422, "Datos inválidos.") }
            let last4 = body["account_last4"] as? String ?? ""
            let account = FixtureAccount(
                id: ownerAccounts.first(where: { $0.name.lowercased() == name.lowercased() && $0.last4 == last4 })?.id ?? nextId(),
                name: name, bank: body["bank_name"] as? String ?? "", last4: last4, currency: (body["currency"] as? String ?? "CRC").uppercased(),
                type: body["account_type"] as? String ?? "checking", balance: balance,
                includeInNetWorth: body["include_in_net_worth"] as? Bool ?? true, asOfOffset: 0)
            if let index = ownerAccounts.firstIndex(where: { $0.id == account.id }) {
                ownerAccounts[index] = account
            } else {
                ownerAccounts.append(account)
            }
            return ok(["status": "OK", "item": row(account)])
        case "DELETE":
            let id = Int(path.split(separator: "/").last ?? "") ?? -1
            guard let index = ownerAccounts.firstIndex(where: { $0.id == id }) else { return error(404, "Cuenta financiera no encontrada.") }
            ownerAccounts.remove(at: index)
            return ok(["status": "OK", "id": id])
        default:
            return nil
        }
    }

    private func crc(_ account: FixtureAccount) -> Decimal { account.currency == "USD" ? account.balance * Self.usdRate : account.balance }

    private func row(_ account: FixtureAccount) -> [String: Any] {
        ["id": account.id, "account_name": account.name, "bank_name": account.bank, "account_last4": account.last4,
         "currency": account.currency, "account_type": account.type, "current_balance": number(account.balance),
         "calculated_balance": number(account.balance), "balance_crc": number(crc(account)), "balance_as_of": day(account.asOfOffset),
         "include_in_net_worth": account.includeInNetWorth, "is_active": true, "source": "manual", "movements_since_balance": 0]
    }

    private func accountBalances() -> [String: Any] {
        let total = ownerAccounts.filter(\.includeInNetWorth).reduce(Decimal(0)) { $0 + crc($1) }
        return ["status": "OK", "items": ownerAccounts.map { row($0) }, "total_real_balance": number(total), "currency": "CRC"]
    }

    private func cycleReport() -> [String: Any] {
        ["status": "OK", "as_of": day(0),
         "cycle": ["start": day(-20), "end": day(10), "label": "\(day(-20)) → \(day(10))", "closing_day": 5, "rolls_on_day": 6],
         "expense_cycle": ["start": day(-34), "end": day(-4), "label": "\(day(-34)) → \(day(-4))", "cut_day": 21, "closed": true],
         "income": ["fixed_expected": 900_000, "extra_expected": 0, "expected_total": 900_000, "received_from_transactions": 450_000,
                    "salary_received": 450_000, "pending_projection": 450_000, "other_cash_inflows": 0, "items": [Any]()],
         "expenses": ["current_period": 380_000, "spending_only": 260_000, "debt_payments": 120_000, "items": [Any](), "transaction_count": 18],
         "goals": ["reserved_current_period": 50_000, "reserves": [Any]()],
         "cashflow": ["real_balance": 470_000, "loan_received": 0]]
    }
}
