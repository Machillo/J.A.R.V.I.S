import Foundation

// The fixture backend's JARVIS → Patrimonio routes (Debug demos and tests only). Same shapes and
// access rule as FastAPI (`investment_center.py`, `business_center.py`): `/finance/*` admits only the
// verified Owner (INTERNAL_ONLY). Every name and amount is invented (CLAUDE.md §4.F).

/// The Owner's invented businesses and movements, and how old the portfolio snapshot is.
struct FixtureWealth {
    struct Business { let id: Int; let name: String; let description: String?; let ownershipPct: Decimal }
    struct Movement { let id: Int; let businessId: Int; let date: String; let type: String; let amount: Decimal; let description: String; let category: String? }

    var businesses: [Business] = [Business(id: 9101, name: "Negocio de ejemplo", description: "Venta de ejemplo", ownershipPct: 100)]
    var movements: [Movement] = [
        Movement(id: 9201, businessId: 9101, date: "2026-10-12", type: "income", amount: 80_000, description: "Venta de ejemplo", category: nil),
        Movement(id: 9202, businessId: 9101, date: "2026-10-05", type: "expense", amount: 30_000, description: "Insumos de ejemplo", category: nil),
    ]
    /// Seconds since the snapshot: a few hours old until the Owner refreshes it from IBKR.
    var snapshotAgeSeconds = 5 * 3600
    /// The saved dividend plan (`PUT .../dividend-plan`); none until the Owner sets it up.
    var dividendPlan: [String: Any]?
}

extension FixtureBackend {
    func wealthRoute(_ method: String, _ path: String, _ body: [String: Any]) -> Answer? {
        guard path.hasPrefix("/finance/investment-center") || path.hasPrefix("/finance/business-center") else { return recordsRoute(method, path, body) }
        guard profile["role"] as? String == "owner" else { return error(403, "No tienes permisos para realizar esta acción.") }
        switch (method, path) {
        case ("GET", "/finance/investment-center"):
            return ok(investmentCenter())
        case ("POST", "/finance/investment-center/sync-ibkr"):
            ownerWealth.snapshotAgeSeconds = 0
            return ok(["status": "OK", "snapshot_id": 9001, "positions": 2, "read_only": true, "sync_method": "flex"])
        case ("POST", "/finance/investment-center/dividend-yield"):
            guard (body["symbol"] as? String ?? "") == "ACME" else { return error(502, "No pudimos traer el dividendo de esa acción. Podés escribirlo vos.") }
            return ok(["symbol": "ACME", "yield_pct": 4, "annual_dividend_usd": 4, "price_usd": 100, "payments": 4, "source": "fixture"])
        case ("GET", "/finance/investment-center/dividend-plan"):
            return ok(dividendPlanAnswer())
        case ("PUT", "/finance/investment-center/dividend-plan"):
            let stocks = body["stocks"] as? [[String: Any]] ?? []
            guard !stocks.isEmpty, stocks.count <= 2 else { return error(422, "Elegí una o dos acciones.") }
            guard stocks.reduce(Decimal(0), { $0 + (decimal($1["share_pct"]) ?? 0) }) == 100 else { return error(422, "Los porcentajes tienen que sumar 100.") }
            ownerWealth.dividendPlan = body
            return ok(dividendPlanAnswer())
        case ("GET", "/finance/business-center"):
            return ok(businessCenter())
        case ("POST", "/finance/business-center/businesses"):
            let name = (body["name"] as? String ?? "").trimmingCharacters(in: .whitespaces)
            guard !name.isEmpty else { return error(422, "Nombre requerido.") }
            let ownership = decimal(body["ownership_pct"]) ?? 100
            guard ownership >= 0, ownership <= 100 else { return error(422, "El porcentaje debe estar entre 0 y 100.") }
            let business = FixtureWealth.Business(id: nextId(), name: name, description: body["description"] as? String, ownershipPct: ownership)
            ownerWealth.businesses.append(business)
            return ok(["id": business.id, "name": name, "ownership_pct": number(ownership), "status": "active"])
        case ("POST", "/finance/business-center/movements"):
            let kind = (body["movement_type"] as? String ?? "").lowercased()
            guard ["income", "expense", "capital"].contains(kind) else { return error(400, "movement_type debe ser income, expense o capital") }
            guard let amount = decimal(body["amount"]), amount > 0 else { return error(422, "Monto inválido.") }
            let description = (body["description"] as? String ?? "").trimmingCharacters(in: .whitespaces)
            guard !description.isEmpty else { return error(422, "Descripción requerida.") }
            let businessId = (body["business_id"] as? NSNumber)?.intValue ?? -1
            guard ownerWealth.businesses.contains(where: { $0.id == businessId }) else { return error(404, "Negocio no encontrado") }
            let movement = FixtureWealth.Movement(id: nextId(), businessId: businessId, date: body["movement_date"] as? String ?? day(0), type: kind,
                                                  amount: amount, description: description, category: body["category"] as? String)
            ownerWealth.movements.insert(movement, at: 0)
            return ok(["id": movement.id, "business_id": businessId, "movement_type": kind, "amount": number(amount)])
        default:
            return nil
        }
    }

    private func investmentCenter() -> [String: Any] {
        let positions: [[String: Any]] = [
            ["symbol": "ETF de ejemplo", "sec_type": "ETF", "currency": "USD", "position": 10, "market_price": 100, "market_value": 1_000, "unrealized_pnl": 100, "realized_pnl": 0],
            ["symbol": "Acción de ejemplo", "sec_type": "STK", "currency": "USD", "position": 5, "market_price": 100, "market_value": 500, "unrealized_pnl": 30, "realized_pnl": 0],
        ]
        return ["portfolio": ["market_value": 1_500, "contributed_capital": 1_350, "realized_pnl": 0, "unrealized_pnl": 130, "dividends": 20,
                              "currency": "USD", "source": "ibkr_readonly", "sync_method": "flex", "snapshot_at": "2026-10-20T12:00:00+00:00"],
                "flows": [Any](), "reserved_to_invest_crc": 100_000, "gross_pnl": 150, "net_pnl": 150, "return_pct": 11.11,
                "positions": positions, "sync_status": "current", "snapshot_age_seconds": ownerWealth.snapshotAgeSeconds,
                "read_only": true, "sync_method": "flex", "flex_configured": true, "included_in_net_worth": true,
                "net_worth_rate": ["rate": 500, "date": "2026-10-20"]]
    }

    /// Invented fixed figures: the calculation itself is the backend's (`finance/dividend_plan.py`),
    /// tested there. The stock gate is closed, as for an Owner with expensive debt.
    private func dividendPlanAnswer() -> [String: Any] {
        let gate: [String: Any] = ["open": false, "blockers": [["code": "expensive_debt"], ["code": "salvavidas_short"]]]
        let empty: [String: Any] = ["ready": false, "current_value_usd": 500, "monthly_needed": [Any](), "buy_this_month": [Any]()]
        guard let saved = ownerWealth.dividendPlan else {
            return ["config": ["stocks": [Any](), "goal_monthly_usd": 1_000, "withholding_pct": 30], "held_symbols": ["ACME"], "gate": gate, "result": empty]
        }
        let stocks = saved["stocks"] as? [[String: Any]] ?? []
        guard stocks.allSatisfy({ decimal($0["yield_pct"]) != nil }) else {
            return ["config": saved, "held_symbols": ["ACME"], "gate": gate, "result": empty]
        }
        // Without a monthly amount the backend gives no date.
        let months: Any = decimal(saved["monthly_amount_usd"]) == nil ? NSNull() : 310
        let result: [String: Any] = [
            "ready": true, "blended_yield_pct": 4, "net_yield_pct": 2.8, "capital_needed_usd": 428_571.43, "current_value_usd": 500, "missing_usd": 428_071.43,
            "net_monthly_dividend_now_usd": 1.17, "months_to_goal": months,
            "monthly_needed": [["years": 10, "amount_usd": 3_050], ["years": 15, "amount_usd": 1_850], ["years": 20, "amount_usd": 1_250]],
            "buy_this_month": [Any](),
        ]
        return ["config": saved, "held_symbols": ["ACME"], "gate": gate, "result": result]
    }

    private func businessCenter() -> [String: Any] {
        func total(_ type: String) -> Decimal { ownerWealth.movements.filter { $0.type == type }.reduce(0) { $0 + $1.amount } }
        let income = total("income"), expenses = total("expense")
        return ["businesses": ownerWealth.businesses.map { business -> [String: Any] in
                    var row: [String: Any] = ["id": business.id, "name": business.name, "ownership_pct": number(business.ownershipPct), "status": "active"]
                    if let description = business.description { row["description"] = description }
                    return row
                },
                "movements": ownerWealth.movements.map { movement -> [String: Any] in
                    var row: [String: Any] = ["id": movement.id, "business_id": movement.businessId, "movement_date": movement.date,
                                              "movement_type": movement.type, "amount": number(movement.amount), "description": movement.description]
                    if let category = movement.category { row["category"] = category }
                    return row
                },
                "income": number(income), "expenses": number(expenses), "profit": number(income - expenses), "capital": number(total("capital"))]
    }
}
