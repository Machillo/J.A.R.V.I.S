import Foundation

// The fixture backend's Plan tab, Cuentas and JARVIS analysis routes (Debug demos and tests only).
// Same shapes and access rules as FastAPI: `/vip/*` needs VIP; `/jarvis/*`, `/transactions/*` and
// `/finance/*` admit only the verified Owner (INTERNAL_ONLY); Strategy and Salvavidas answer the Owner
// model only to the server's Owner role. Every name and amount is invented (CLAUDE.md §4.F); the
// figures are fixed samples or simple sums of the fixture's own rows.
extension FixtureBackend {
    private var role: String { profile["role"] as? String ?? "user" }
    private var isOwnerRole: Bool { role == "owner" }
    private var isInternalRole: Bool { role == "owner" }

    /// The routes of this file, or nil to keep routing.
    func planRoute(_ method: String, _ path: String, _ query: [String: String], _ body: [String: Any]) -> Answer? {
        switch (method, path) {
        case ("GET", "/user-product/vip/strategy-dashboard"):
            if let denied = needs(.vip) { return denied }
            return ok(strategyDashboard(owner: isOwnerRole))
        case ("GET", "/jarvis/premium/strategy-dashboard"):
            guard isInternalRole else { return error(403, "No tienes permisos para realizar esta acción.") }
            return ok(strategyDashboard(owner: isOwnerRole))
        case ("GET", "/user-product/vip/salvavidas"):
            if let denied = needs(.vip) { return denied }
            return ok(isOwnerRole ? ownerSalvavidas() : usersSalvavidas())
        case ("PUT", "/user-product/vip/salvavidas"):
            if let denied = needs(.vip) { return denied }
            return updateSalvavidas(body)
        case ("GET", "/transactions/analysis/summary"), ("GET", "/finance/net-worth"), ("GET", "/finance/engine"):
            guard isInternalRole else { return error(403, "No tienes permisos para realizar esta acción.") }
            return ok(analysis(path))
        default:
            return nil
        }
    }

    // MARK: Strategy

    /// strategy-basic: the declared income first; without one, the income recorded in the fixture
    /// (`observed`, never written back as declared); without any, `needs_income`.
    func strategyBasic() -> [String: Any] {
        let declared = decimal((situation ?? [:])["fixed_monthly_salary"]).map { $0 > 0 } ?? false
        let recorded = movements.contains { $0["transaction_type"] as? String == "income" }
        if !declared && !recorded {
            return ["status": "needs_income", "priority": "income", "monthly_income": 0, "essential_expenses": 0, "minimum_debt_payments": number(sum(debts, "monthly_payment")),
                    "strategic_margin": 0, "allocations": [Any](), "target_debt": NSNull(),
                    "recommendation": "Completá tus ingresos para que DINCR pueda construir una estrategia mensual.",
                    "warnings": ["No hay un ingreso mensual estimable."], "projection": NSNull(),
                    "income_source": "none", "income_basis": ["source": "none", "policy": "income-policy-v1"]]
        }
        let basis: [String: Any] = declared ? ["source": "declared", "policy": NSNull()]
            : ["source": "observed", "policy": "income-policy-v1", "observed_source": "recorded_income"]
        var answer = Self.strategy
        answer["income_source"] = declared ? "declared" : "observed"
        answer["income_basis"] = basis
        return answer
    }

    /// `/vip/strategy-dashboard` and `/jarvis/premium/strategy-dashboard`: the Users model, or the
    /// Owner's (historical JARVIS fields) for the server's Owner role only.
    func strategyDashboard(owner: Bool) -> [String: Any] {
        let hasIncome = movements.contains { $0["transaction_type"] as? String == "income" }
        var strategy: [String: Any] = [
            "month": String(day(0).prefix(7)), "scope": owner ? "owner" : "users",
            "status": hasIncome ? "controlled" : "needs_income",
            "title": "Director Financiero · ATAQUE DE DEUDA", "mode": "debt_attack",
            "objective": hasIncome ? "Modo ATAQUE DE DEUDA: hay deuda con tasa alta." : "Registrá o declará tus ingresos para que DINCR pueda repartir tu sobrante.",
            "priority": ["kind": "debt", "title": "Atacar deuda: Tarjeta de crédito", "detail": "El sobrante destinado a deuda se concentra primero en esta obligación."],
            "monthly_income": hasIncome ? 865_000 : 0, "income_policy": ["policy": "income-policy-v1", "source": hasIncome ? "recorded" : "none"],
            // Recurring obligations not yet covered by recorded spending: max(24.900 − 312.000, 0).
            "monthly_expenses": 312_000, "debt_commitment_current_cycle": 95_000, "pending_recurring_total": 0,
            "recurring_obligation_items": [["id": 45, "name": "Internet", "due_day": 4, "monthly_amount": 24_900]],
            "safe_to_spend": 64_000, "distributable_account_cash": NSNull(),
            "emergency_fund": ["current": 120_000, "monthly_base": 330_000, "next_target": 330_000, "gap_to_next_target": 210_000, "level": "one_month_building"],
            "timeline": [["priority": 1, "name": "Tarjeta de crédito", "remaining_amount": 420_000, "recommended_payment": 205_000, "estimated_payoff_date": "2027-02-01"],
                         ["priority": 2, "name": "Préstamo del carro", "remaining_amount": 820_000, "recommended_payment": 50_000, "estimated_payoff_date": "2028-06-01"]],
            "estimated_debt_free_date": "2028-06-01", "total_debt": 1_240_000, "debt_progress_percent": 58.67, "investment_recommended": 0,
            "rules": ["Solo se distribuye el sobrante que queda después de obligaciones y gastos ya registrados.",
                      "Las deudas activas reservan al menos su cuota mensual completa antes de repartir dinero."],
            "allocation_base_amount": 458_000,
            "allocation_items": [["key": "ataque_de_deuda", "percentage": 50.0, "amount": 229_000, "target_name": "Tarjeta de crédito"],
                                 ["key": "fondo_de_emergencia", "percentage": 35.0, "amount": 160_300],
                                 ["key": "vida_controlada", "percentage": 15.0, "amount": 68_700]],
            "distribution_formula": ["income": 865_000, "recorded_spending": 312_000, "debt_commitment": 95_000, "pending_recurring": 0, "surplus": 458_000, "deficit": 0],
        ]
        if owner {
            // The Owner's cycle, cash and statement figures (invented, like everything here).
            let ownerFields: [String: Any] = [
                "recurring_monthly_income": 900_000, "current_month_extra_net": 45_000, "income_received_current_cycle": 450_000,
                "remaining_income_current_cycle": 495_000, "distributable_account_cash": 310_000, "statement_expenses": 180_000,
                "new_expenses_after_cut": 42_000, "mandatory_fixed_pending": 120_000,
                "mandatory_fixed_pending_items": [["name": "Alquiler", "amount": 120_000, "due_day": 28]],
                "investment_portfolio": ["market_value": 1_500, "contributed_capital": 1_350, "net_pnl": 150, "currency": "USD"],
                "base_timeline": [Any](), "months_saved_by_current_extras": 3,
                "distribution_formula": ["cash_available_now": 310_000, "income": 495_000, "statement_spending": 180_000, "new_spending_after_cut": 42_000,
                                         "debt_commitment": 95_000, "mandatory_fixed_pending": 120_000, "surplus": 368_000, "deficit": 0],
            ]
            strategy.merge(ownerFields) { $1 }
        }
        return ["status": "OK", "user_role": role, "title": strategy["title"] ?? "", "content": strategy["objective"] ?? "",
                "strategy": strategy, "updated_at": "\(day(0))T12:00:00", "has_premium_strategy": true, "source": "live_database"]
    }

    // MARK: Salvavidas

    /// Users: months of the fixture's own obligations; the fund is the declared savings (unknown
    /// without a situation, never zero).
    func usersSalvavidas() -> [String: Any] {
        let debtItems: [[String: Any]] = debts.map { ["id": $0["id"] ?? 0, "name": $0["name"] ?? "Deuda", "debt_type": $0["debt_type"] ?? "other",
                                                      "monthly_payment": $0["monthly_payment"] ?? 0, "remaining_amount": $0["remaining_amount"] ?? 0,
                                                      "payment_day": $0["payment_day"] ?? NSNull()] }
        let active = recurring.filter { row in
            // Precomputed: the right side of && is an autoclosure, which must not capture JSON dictionaries.
            let isActive = row["is_active"] as? Bool ?? true
            let isExpense = (row["item_type"] as? String ?? "expense") == "expense"
            return isActive && isExpense
        }
        let obligations: [[String: Any]] = active.map { ["id": $0["id"] ?? 0, "name": $0["name"] ?? "Pago recurrente", "expected_amount": $0["amount"] ?? 0,
                                                         "monthly_amount": $0["amount"] ?? 0, "frequency": $0["frequency"] ?? "monthly", "due_day": $0["due_day"] ?? NSNull()] }
        let debtMonthly = sum(debts, "monthly_payment")
        let recurringMonthly = sum(active, "amount")
        let base = debtMonthly + recurringMonthly
        let months = salvavidasTargetMonths
        let target = base * Decimal(months)
        let current = decimal((situation ?? [:])["liquid_savings"])
        var answer: [String: Any] = [
            "status": base > 0 ? "OK" : "needs_obligations", "scope": "users",
            "current_amount": current.map { number($0) as Any } ?? NSNull(), "current_amount_known": current != nil,
            "current_amount_source": current == nil ? NSNull() as Any : "declared" as Any,
            "monthly_base": number(base), "target_months": months, "allowed_target_months": [1, 3, 6], "target_amount": number(target),
            "missing_amount": current.map { number(max(target - $0, 0)) as Any } ?? NSNull(),
            "components": ["debt_monthly_payments": number(debtMonthly), "recurring_obligations": number(recurringMonthly)],
            "debts": debtItems, "obligations": obligations,
            "milestones": [1, 3, 6].map { m -> [String: Any] in
                let goal = base * Decimal(m)
                return ["months": m, "target": number(goal), "reached": current.map { base > 0 && $0 >= goal } ?? false]
            },
            "verification": ["mode": "declared", "message": current == nil
                ? "Declará tus ahorros disponibles para medir la cobertura."
                : "El fondo es el ahorro disponible que declaraste."],
        ]
        if let current, base > 0 {
            answer["coverage_months"] = number(current / base)
            answer["progress_percent"] = number(target > 0 ? min(current / target * 100, 100) : 0)
        } else {
            answer["coverage_months"] = NSNull()
            answer["progress_percent"] = NSNull()
        }
        return answer
    }

    /// The Owner's historical JARVIS model: debts, mandatory and protected fixed expenses, a manual balance.
    func ownerSalvavidas() -> [String: Any] {
        let optional: [(Int, String, Decimal)] = [(62, "Internet", 24_900), (63, "Gimnasio", 18_000)]
        let mandatory: Decimal = 210_000
        let protectedMonthly = optional.filter { ownerProtectedExpenses.contains($0.0) }.reduce(Decimal(0)) { $0 + $1.2 }
        let debtMonthly = sum(debts, "monthly_payment")
        let base = debtMonthly + mandatory + protectedMonthly
        let months = salvavidasTargetMonths
        let target = base * Decimal(months)
        let current = ownerSalvavidasCurrent
        return [
            "status": "OK", "scope": "owner", "current_amount": number(current), "monthly_base": number(base), "target_months": months,
            "target_amount": number(target), "missing_amount": number(max(target - current, 0)),
            "coverage_months": number(base > 0 ? current / base : 0), "progress_percent": number(target > 0 ? min(current / target * 100, 100) : 0),
            "protected_expense_ids": ownerProtectedExpenses.sorted(),
            "components": ["debt_monthly_payments": number(debtMonthly), "mandatory_fixed_expenses": number(mandatory), "protected_expenses": number(protectedMonthly)],
            "debts": debts.map { row -> [String: Any] in ["id": row["id"] ?? 0, "name": row["name"] ?? "Deuda", "monthly_payment": row["monthly_payment"] ?? 0, "remaining_amount": row["remaining_amount"] ?? 0] },
            "mandatory_expenses": [["id": 61, "name": "Alquiler", "monthly_amount": number(mandatory), "frequency": "monthly", "selected": true, "mandatory": true]],
            "available_expenses": optional.map { item -> [String: Any] in
                ["id": item.0, "name": item.1, "monthly_amount": number(item.2), "frequency": "monthly", "selected": ownerProtectedExpenses.contains(item.0)]
            },
            "excluded_debt_duplicates": [["id": 64, "name": "Cuota de la tarjeta", "monthly_amount": 45_000, "frequency": "monthly", "selected": false]],
            "milestones": [1, 3, 6].map { m -> [String: Any] in ["months": m, "target": number(base * Decimal(m)), "reached": base > 0 && current >= base * Decimal(m)] },
            "verification": ["mode": "manual", "account_linked": false, "message": "Guardá el saldo para crear y vincular la cuenta financiera Salvavidas."],
        ]
    }

    /// Users may set the 1/3/6 goal and their declared savings (422 without a situation); never
    /// protected expenses. The Owner may set any of the three.
    func updateSalvavidas(_ body: [String: Any]) -> Answer {
        // Validate everything first, like the backend: a refused request changes nothing.
        var months: Int?
        if let raw = body["target_months"] {
            guard let value = raw as? Int, [1, 3, 6].contains(value) else { return error(422, "El objetivo del Salvavidas debe ser de 1, 3 o 6 meses.") }
            months = value
        }
        let amount = decimal(body["current_amount"])
        if body["current_amount"] != nil, amount == nil || amount! < 0 { return error(422, "Monto inválido.") }
        let protectedIDs = body["protected_expense_ids"] as? [Int]
        if !isOwnerRole {
            if let ids = protectedIDs, !ids.isEmpty { return error(422, "Los gastos protegidos no aplican a tu Salvavidas.") }
            if amount != nil, situation == nil { return error(422, "Declará primero tus ingresos para guardar tus ahorros.") }
        }
        if let months { salvavidasTargetMonths = months }
        if isOwnerRole {
            if let amount { ownerSalvavidasCurrent = amount }
            if let ids = protectedIDs { ownerProtectedExpenses = Set(ids.filter { [62, 63].contains($0) }) }
            return ok(ownerSalvavidas())
        }
        if let amount { situation?["liquid_savings"] = number(amount) }
        return ok(usersSalvavidas())
    }

    // MARK: Cuentas

    /// `/vip/gmail/emails?status=&bank=&financial_account_id=` over the single candidate store.
    func filteredCandidates(_ query: [String: String]) -> [[String: Any]] {
        var rows = candidates
        if let status = query["status"], !status.isEmpty { rows = rows.filter { $0["review_status"] as? String == status } }
        if let bank = query["bank"]?.trimmingCharacters(in: .whitespaces), !bank.isEmpty {
            rows = rows.filter { ($0["bank"] as? String ?? "").lowercased() == bank.lowercased() }
        }
        if let raw = query["financial_account_id"], let accountID = Int(raw) {
            rows = rows.filter { $0["financial_account_id"] as? Int == accountID }
        }
        return rows
    }

    /// Detected accounts: the display label in `bank_name` ("BAC", "Banco Popular", like
    /// `financial_identity._institution_label`) and the code in `institution_code`; invented account
    /// names and last four digits, and no `current_balance` (a detected account's balance is unknown).
    static func sampleAccounts() -> [[String: Any]] {
        [
            ["id": 1, "account_name": "Cuenta de ahorro", "bank_name": "BAC", "institution_code": "bac", "institution_country": "CR",
             "account_type": "savings", "account_last4": "1234", "currency": "CRC", "ownership_status": "pending"],
            ["id": 2, "account_name": "Tarjeta de crédito", "bank_name": "BAC", "institution_code": "bac", "institution_country": "CR",
             "account_type": "credit_card", "account_last4": "5678", "currency": "USD", "ownership_status": "own"],
            ["id": 3, "account_name": "Cuenta corriente", "bank_name": "Banco Popular", "institution_code": "popular", "institution_country": "CR",
             "account_type": "checking", "account_last4": "9012", "currency": "CRC", "ownership_status": "pending"],
            ["id": 4, "account_name": "Cuenta de ejemplo", "bank_name": "Entidad de ejemplo", "institution_code": NSNull(), "institution_country": "CR",
             "account_type": "checking", "account_last4": "3456", "currency": "CRC", "ownership_status": "pending"],
        ]
    }

    // MARK: JARVIS · Análisis financiero

    func analysis(_ path: String) -> [String: Any] {
        switch path {
        case "/transactions/analysis/summary":
            let months = history()
            return [
                "summary": ["income": 5_190_000, "expenses": 2_480_000, "debt_payments": 570_000, "net_from_transactions": 2_140_000, "total_transactions": 64],
                "top_expense_categories": [["category": "Vivienda", "total": 1_260_000], ["category": "Comida", "total": 540_000]],
                "expenses_by_month": months.map { row -> [String: Any] in ["month": row["month"] ?? "", "total": row["expenses"] ?? 0] },
                "monthly_flow": months.map { row -> [String: Any] in
                    ["month": row["month"] ?? "", "income": row["income"] ?? 0, "expenses": row["expenses"] ?? 0, "monthly_balance": row["balance"] ?? 0]
                },
                "spending_breakdown": ["period": ["start": "\(day(0).prefix(4))-01-01", "end": day(0), "label": "\(day(0).prefix(4)) YTD"], "total": 2_480_000,
                                       "categories": [["category": "Vivienda", "total": 1_260_000, "count": 6], ["category": "Comida", "total": 540_000, "count": 22],
                                                      ["category": "Transporte", "total": 380_000, "count": 18], ["category": "Salud", "total": 300_000, "count": 4]],
                                       "transactions": [Any]()],
            ]
        case "/finance/net-worth":
            return ["assets": ["savings": [Any](), "investments": [Any](), "savings_total": 640_000, "investments_total": 760_000, "assets_total": 1_400_000],
                    "liabilities": ["debts": [Any](), "debt_total": number(sum(debts, "remaining_amount")), "monthly_debt_payments": number(sum(debts, "monthly_payment"))],
                    "net_worth": number(1_400_000 - sum(debts, "remaining_amount")),
                    "history": [Any](), "change": ["amount": 35_000, "percentage": 2.5, "compared_with": day(30)],
                    "status": "positive", "interpretation": "Tus activos registrados superan tus deudas.", "recommendations": ["Mantener control de deuda y seguir aumentando patrimonio."]]
        default:
            return ["status": "OK",
                    "health": ["status": "OK", "score": 62.5, "confidence": 0.75, "level": "stable"],
                    "forecast": ["status": "OK", "month": String(day(0).prefix(7)), "projected_end_balance": 185_000, "alert": NSNull()],
                    "emergency_fund": ["status": "OK", "current": 450_000, "monthly_base": 330_000, "recommended_6_months": 1_980_000, "coverage_months": 1.36],
                    "debts": ["status": "OK", "recommended": ["name": "avalanche", "priority_debt": ["name": "Tarjeta de crédito", "remaining_amount": 420_000]],
                              "note": "Avalancha es la estrategia recomendada por costo."],
                    "recommendations": ["Prioridad avalancha: Tarjeta de crédito.", "Salvavidas objetivo: ₡1.980.000 para 6 meses de cobertura."],
                    "data_policy": "El motor calcula solo con datos existentes."]
        }
    }
}
