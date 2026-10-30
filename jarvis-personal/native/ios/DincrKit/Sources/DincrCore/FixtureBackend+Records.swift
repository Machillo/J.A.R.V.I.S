import Foundation

// The fixture backend's JARVIS → Registros routes (Debug demos and tests only). Same shapes and
// access rule as FastAPI: `/finance/*` admits only the verified Owner (INTERNAL_ONLY). Every name
// and amount is invented (CLAUDE.md §4.F).
extension FixtureBackend {
    func recordsRoute(_ method: String, _ path: String, _ body: [String: Any]) -> Answer? {
        guard path == "/finance/timeline" || path.hasPrefix("/finance/reconciliation") else { return fixedExpensesRoute(method, path, body) }
        guard profile["role"] as? String == "owner" else { return error(403, "No tienes permisos para realizar esta acción.") }
        switch method {
        case "GET" where path == "/finance/timeline":
            return ok(timeline())
        case "GET" where path == "/finance/reconciliation":
            return ok(reconciliation())
        case "POST" where path.hasSuffix("/confirm"):
            let id = Int(path.split(separator: "/").dropLast().last ?? "") ?? -1
            guard [801, 802].contains(id) else { return error(404, "Cuenta financiera no encontrada.") }
            guard let balance = decimal(body["real_balance"]) else { return error(422, "Saldo inválido.") }
            ownerConfirmedBalances[id] = balance
            return ok(["status": "OK", "account_id": id, "real_balance": number(balance), "confirmed": true])
        default:
            return nil
        }
    }

    private func timeline() -> [String: Any] {
        let events: [[String: Any]] = [
            ["date": day(3), "name": "Cuota · Préstamo de ejemplo", "kind": "debt_payment", "amount": 50_000, "impact": -50_000, "source": "debt"],
            ["date": day(8), "name": "Internet de ejemplo", "kind": "recurring_expense", "amount": 24_900, "impact": -24_900, "source": "fixed_expense"],
            ["date": day(12), "name": "Ingreso de salario", "kind": "income", "amount": 450_000, "impact": 450_000, "source": "pay_schedule"],
        ]
        var balance: Decimal = 310_000
        let projected = events.map { event -> [String: Any] in
            balance += (event["impact"] as? NSNumber)?.decimalValue ?? 0
            var row = event
            row["projected_balance"] = number(balance)
            return row
        }
        return ["status": "OK", "start_date": day(0), "end_date": day(45), "opening_available": 310_000, "events": projected,
                "ending_available": number(balance), "event_count": projected.count,
                "assumptions": ["Solo se proyectan ingresos con calendario configurado y obligaciones activas con fecha y monto."]]
    }

    private func reconciliation() -> [String: Any] {
        func account(_ id: Int, _ name: String, _ last4: String, expected: Decimal, real: Decimal) -> [String: Any] {
            let real = ownerConfirmedBalances[id] ?? real
            let expected = ownerConfirmedBalances[id] ?? expected
            let difference = real - expected
            return ["account_id": id, "account_name": name, "institution": "Banco de ejemplo", "last4": last4, "currency": "CRC",
                    "expected_balance": number(expected), "real_balance": number(real), "difference": number(difference),
                    "movements_since_balance": ownerConfirmedBalances[id] == nil ? 4 : 0, "balance_as_of": day(-6),
                    "status": difference == 0 ? "ok" : "needs_review"]
        }
        let accounts = [account(801, "Cuenta de ejemplo", "1111", expected: 290_000, real: 310_000),
                        account(802, "Ahorro de ejemplo", "2222", expected: 120_000, real: 120_000)]
        let review = accounts.filter { $0["status"] as? String == "needs_review" }.count
        return ["status": "OK", "accounts": accounts, "discrepancies": [Any](), "unlinked_transactions": [Any](), "possible_duplicates": [Any](),
                "summary": ["accounts": accounts.count, "needs_review": review, "unlinked": 2, "possible_duplicates": 0, "untracked_accounts": 1],
                "note": "DINCR solo detecta y propone revisión. Ningún movimiento se borra, duplica o corrige automáticamente."]
    }
}
