import Foundation

/// Expenses waiting for the close, with the backend's rules (`pending_conversion`): an expense typed in
/// the other currency without a rate, asked for with `convert_at_close`, keeps its dollars and has no
/// colones amount. The movement list leaves it out; the pending listing shows it with its totals.
extension FixtureBackend {
    static let pendingFlag = "pending_conversion"

    func pendingRequested(_ body: [String: Any]) -> Bool { body["convert_at_close"] as? Bool == true }

    /// The backend's refusal for a pending request that can't wait, or nil.
    func pendingRefusal(_ body: [String: Any], origin: String, base: String) -> Answer? {
        guard origin == "expense" else { return error(422, "Solo un gasto puede esperar al cierre para convertirse.") }
        guard let currency = body["currency"] as? String, currency != base else {
            return error(422, "Solo un gasto en la otra moneda puede esperar al cierre para convertirse.")
        }
        if decimal(body["exchange_rate"]) != nil { return error(422, "Con tipo de cambio el gasto se convierte ahora; sin él, espera al cierre.") }
        return nil
    }

    /// A pending row: what the user typed, no colones amount and no rate.
    func markPending(_ row: inout [String: Any], typed: Decimal, currency: String) {
        row["amount"] = NSNull(); row["original_amount"] = number(typed); row["original_currency"] = currency
        row["exchange_rate"] = NSNull(); row[Self.pendingFlag] = true
    }

    func isPending(_ row: [String: Any]) -> Bool { row[Self.pendingFlag] as? Bool == true }

    func pendingConversion() -> [String: Any] {
        let pending = movements.filter(isPending).sorted { ($0["transaction_date"] as? String ?? "") > ($1["transaction_date"] as? String ?? "") }
        let items: [[String: Any]] = pending.map { row in
            ["movement_id": row["movement_id"] ?? "", "id": row["source_id"] ?? 0, "entry_date": row["transaction_date"] ?? "",
             "description": row["description"] ?? "", "category": row["category"] ?? "", "original_amount": row["original_amount"] ?? 0,
             "original_currency": row["original_currency"] ?? "", "financial_account_id": row["financial_account_id"] ?? NSNull()]
        }
        var totals: [String: (Decimal, Int)] = [:]
        for row in pending {
            let currency = row["original_currency"] as? String ?? ""
            let current = totals[currency] ?? (0, 0)
            totals[currency] = (current.0 + (decimal(row["original_amount"]) ?? 0), current.1 + 1)
        }
        return ["status": "ok", "available": true, "items": items,
                "totals": totals.keys.sorted().map { ["currency": $0, "amount": number(totals[$0]!.0), "count": totals[$0]!.1] }]
    }
}
