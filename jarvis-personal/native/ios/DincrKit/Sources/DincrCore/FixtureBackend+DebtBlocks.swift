import Foundation

// The fixture backend's Plan → Ahorro para deudas routes (Debug demos and tests only). Same shapes and
// access rule as FastAPI (`ai/owner_debt_blocks.py`, `ai/owner_debt_block_store.py`): `/jarvis/*`
// admits only the verified Owner; one block per debt at a time (409). Every name and amount is invented
// (CLAUDE.md §4.F); the proposal is a fixed sample, not the engine.

extension FixtureBackend {
    func debtBlocksRoute(_ method: String, _ path: String, _ body: [String: Any]) -> Answer? {
        guard path == "/jarvis/premium/debt-savings-blocks" || path.hasPrefix("/jarvis/premium/debt-savings-blocks/") else { return nil }
        guard profile["role"] as? String == "owner" else { return error(403, "No tienes permisos para realizar esta acción.") }
        switch method {
        case "GET":
            return ok(debtBlocksState())
        case "POST":
            guard let debtId = body["debt_id"] as? Int, let weekly = decimal(body["weekly_amount"]), weekly > 0,
                  let start = body["start_date"] as? String, let term = body["term_months"] as? Int, (3...60).contains(term) else {
                return error(422, "Revisá el ahorro.")
            }
            guard !ownerDebtBlocks.contains(where: { $0["debt_id"] as? Int == debtId }) else {
                return error(409, "Esa deuda ya tiene un ahorro bloqueado.")
            }
            let weeks = term * 52 / 12
            ownerDebtBlocks.append(["id": "fixture-block-\(ownerDebtBlocks.count + 1)", "debt_id": debtId, "debt_name": "Préstamo de ejemplo",
                                    "mode": body["mode"] ?? "block", "weekly_amount": Self.number(weekly), "start_date": start,
                                    "maturity_date": monthDayISO(monthsAhead: term), "term_months": term, "contributions_total": weeks,
                                    "contributions_done": 0, "saved_so_far": 0, "total_at_maturity": Self.number(weekly * Decimal(weeks)),
                                    "next_date": start, "matured": false])
            return ok(["status": "OK"])
        case "DELETE":
            let id = String(path.split(separator: "/").last ?? "")
            guard ownerDebtBlocks.contains(where: { $0["id"] as? String == id }) else { return error(404, "No encontramos ese ahorro.") }
            ownerDebtBlocks.removeAll { $0["id"] as? String == id }
            return ok(["status": "OK", "deleted": id])
        default:
            return nil
        }
    }

    private func monthDayISO(monthsAhead: Int) -> String {
        let calendar = Calendar(identifier: .gregorian)
        let day = calendar.date(byAdding: .month, value: monthsAhead, to: today) ?? today
        let parts = calendar.dateComponents([.year, .month, .day], from: day)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }

    /// One proposal while no block exists; with a block the debt is taken and nothing is left to lock.
    private func debtBlocksState() -> [String: Any] {
        let base: [String: Any] = ["weekly_safe_amount": ownerDebtBlocks.isEmpty ? 13_500 : 0, "committed_weekly": ownerDebtBlocks.isEmpty ? 0 : 13_500,
                                   "short_debts": [Any](), "warnings": ["average_income_estimated"], "blocks": ownerDebtBlocks]
        guard ownerDebtBlocks.isEmpty else { return base.merging(["status": "no_surplus", "proposal": NSNull()]) { $1 } }
        let proposal: [String: Any] = [
            "mode": "block", "debt": ["id": 801, "name": "Préstamo de ejemplo", "remaining_amount": 1_200_000, "interest_rate": 24],
            "weekly_amount": 13_500, "contributions": 26, "term_months": 6,
            "start_date": monthDayISO(monthsAhead: 0), "maturity_date": monthDayISO(monthsAhead: 6),
            "total_saved": 351_000, "abono_amount": 351_000, "balance_at_maturity": 1_020_000, "balance_after_abono": 669_000,
            "lock_cost": 21_400, "recommendation": ["choice": "reduce_term", "reason": "saves_interest"],
        ]
        return base.merging(["status": "proposal", "proposal": proposal]) { $1 }
    }
}
