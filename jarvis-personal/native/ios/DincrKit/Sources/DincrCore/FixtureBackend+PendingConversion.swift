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

    /// The close of a pending row, with the backend's rule (`conversion_periods`): a card with a cut day
    /// closes at the first cut on or after the expense; anything else at the end of its calendar month.
    func pendingPeriod(_ row: [String: Any]) -> [String: Any] {
        let day = Self.parseDay(row["transaction_date"] as? String ?? "") ?? today
        let account = (row["financial_account_id"] as? Int).flatMap { id in identityAccounts.first { $0["id"] as? Int == id } }
        let isCard = account?["account_type"] as? String == "credit_card"
        if isCard, let account, let cut = account["statement_cut_day"] as? Int {
            let calendar = Self.utc
            func cutDate(_ month: Date) -> Date {
                let parts = calendar.dateComponents([.year, .month], from: month)
                let first = calendar.date(from: parts)!
                let last = calendar.range(of: .day, in: .month, for: first)!.count
                return calendar.date(byAdding: .day, value: min(cut, last) - 1, to: first)!
            }
            let thisCut = cutDate(day)
            let end = day <= thisCut ? thisCut : cutDate(calendar.date(byAdding: .month, value: 1, to: day)!)
            let previous = cutDate(calendar.date(byAdding: .month, value: -1, to: end)!)
            return ["key": "card:\(account["id"] as? Int ?? 0):\(Self.dayString(end))", "kind": "card",
                    "start": Self.dayString(calendar.date(byAdding: .day, value: 1, to: previous)!), "end": Self.dayString(end),
                    "cut_day_missing": false, "account_id": account["id"] ?? NSNull(),
                    "account_name": account["account_name"] ?? NSNull(), "account_last4": account["account_last4"] ?? NSNull()]
        }
        let calendar = Self.utc
        let first = calendar.date(from: calendar.dateComponents([.year, .month], from: day))!
        let last = calendar.date(byAdding: DateComponents(month: 1, day: -1), to: first)!
        return ["key": "month:\(Self.dayString(first).prefix(7))", "kind": "month", "start": Self.dayString(first), "end": Self.dayString(last),
                "cut_day_missing": isCard, "account_id": NSNull(), "account_name": NSNull(), "account_last4": NSNull()]
    }

    func pendingConversion() -> [String: Any] {
        let pending = movements.filter(isPending).sorted { ($0["transaction_date"] as? String ?? "") > ($1["transaction_date"] as? String ?? "") }
        let items: [[String: Any]] = pending.map { row in
            ["movement_id": row["movement_id"] ?? "", "id": row["source_id"] ?? 0, "entry_date": row["transaction_date"] ?? "",
             "description": row["description"] ?? "", "category": row["category"] ?? "", "original_amount": row["original_amount"] ?? 0,
             "original_currency": row["original_currency"] ?? "", "financial_account_id": row["financial_account_id"] ?? NSNull(),
             "period_key": pendingPeriod(row)["key"] ?? ""]
        }
        var groups: [String: (period: [String: Any], rows: [[String: Any]])] = [:]
        for row in pending {
            let period = pendingPeriod(row)
            let key = period["key"] as? String ?? ""
            groups[key, default: (period, [])].rows.append(row)
        }
        let periods: [[String: Any]] = groups.values.sorted { ($0.period["end"] as? String ?? "") < ($1.period["end"] as? String ?? "") }.map { group in
            var period = group.period
            period["closable"] = (period["end"] as? String ?? "") <= day(0)
            period["totals"] = totals(group.rows)
            period["count"] = group.rows.count
            return period
        }
        return ["status": "ok", "available": true, "items": items, "totals": totals(pending), "periods": periods]
    }

    private func totals(_ rows: [[String: Any]]) -> [[String: Any]] {
        var totals: [String: (Decimal, Int)] = [:]
        for row in rows {
            let currency = row["original_currency"] as? String ?? ""
            let current = totals[currency] ?? (0, 0)
            totals[currency] = (current.0 + (decimal(row["original_amount"]) ?? 0), current.1 + 1)
        }
        return totals.keys.sorted().map { ["currency": $0, "amount": number(totals[$0]!.0), "count": totals[$0]!.1] }
    }

    /// The close: one rate converts every row still waiting in the period, once it has ended.
    func closePending(_ body: [String: Any]) -> Answer {
        let key = body["period_key"] as? String ?? ""
        guard let rate = decimal(body["exchange_rate"]), rate > 0 else { return error(422, "Indicá el tipo de cambio.") }
        let indices = movements.indices.filter { isPending(movements[$0]) && pendingPeriod(movements[$0])["key"] as? String == key }
        guard let first = indices.first else { return error(404, "No hay gastos por convertir en ese cierre.") }
        let end = pendingPeriod(movements[first])["end"] as? String ?? ""
        guard end <= day(0) else { return error(409, "Este cierre termina el \(end): se convierte desde ese día.") }
        let base = profile["base_currency"] as? String ?? "CRC"
        var total: Decimal = 0
        for index in indices {
            var row = movements[index]
            let typed = decimal(row["original_amount"]) ?? 0
            let converted = ConversionPreview.baseAmount(typed: typed, currency: row["original_currency"] as? String ?? "USD", base: base, rate: rate) ?? typed
            row["amount"] = number(converted); row["exchange_rate"] = number(rate); row[Self.pendingFlag] = nil
            movements[index] = row
            total += converted
        }
        return ok(["status": "ok", "period_key": key, "converted": indices.count, "amount": number(total), "currency": base, "exchange_rate": number(rate)])
    }

    static let pendingSampleDescription = "Hotel en dólares"

    static func pendingSample(today: Date) -> [String: Any] {
        let lastMonth = utc.date(byAdding: .month, value: -1, to: today)!
        return ["movement_id": "expense:9100", "source_id": 9100, "origin": "expense", "transaction_date": dayString(lastMonth),
                "description": pendingSampleDescription, "amount": NSNull(), "transaction_type": "expense", "category": "Compras",
                "notes": "", "editable": true, "original_amount": NSDecimalNumber(value: 120), "original_currency": "USD",
                "exchange_rate": NSNull(), pendingFlag: true]
    }

    static let utc: Calendar = { var calendar = Calendar(identifier: .gregorian); calendar.timeZone = TimeZone(identifier: "UTC")!; return calendar }()

    static func parseDay(_ text: String) -> Date? {
        let parts = text.prefix(10).split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3 else { return nil }
        return utc.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2]))
    }

    static func dayString(_ date: Date) -> String {
        let parts = utc.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year!, parts.month!, parts.day!)
    }
}
