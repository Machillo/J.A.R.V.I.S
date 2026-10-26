import Foundation

// `POST /finance/strategy-vip/debt-scenario` on the fixture's own debts (Debug demos and tests only):
// the backend's shape and errors (`debt_scenarios.py`), with simple fixed math instead of its
// amortization. Unknown stays unknown (JSON null), as on the server.
extension FixtureBackend {
    func debtScenario(_ body: [String: Any]) -> Answer {
        let current = decimal(Self.strategy["strategic_margin"]) ?? 0
        func value(_ amount: Decimal?) -> Any { amount.map { number($0) } ?? NSNull() }
        func leftover(_ change: Decimal?) -> [String: Any] {
            ["current": number(current), "scenario": value(change.map { current + $0 }), "change": value(change)]
        }
        func failure(_ status: Int, _ code: String, _ message: String) -> Answer { (status, ["detail": ["code": code, "message": message]]) }
        let kind = body["kind"] as? String ?? ""
        let amount = decimal(body["amount"])

        if kind == "new_debt" {
            guard let principal = amount, principal > 0 else { return failure(422, "amount_required", "Indicá el monto de la deuda nueva.") }
            let declared = decimal(body["monthly_payment"])
            let term = (body["term_months"] as? Int).flatMap { $0 > 0 ? Decimal($0) : nil }
            guard let payment = declared ?? term.map({ principal / $0 }) else {
                return failure(422, "payment_or_terms_required", "Indicá la cuota, o la tasa y el plazo, de la deuda nueva.")
            }
            let name = (body["name"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "Deuda nueva"
            return ok(["rule_version": "debt-scenarios-v1", "kind": kind,
                       "debt": ["id": NSNull(), "name": name, "remaining_amount": number(principal), "monthly_payment": number(payment),
                                "monthly_payment_source": declared == nil ? "computed" : "declared", "interest_rate": value(decimal(body["annual_rate"]))],
                       "monthly_leftover": leftover(-payment), "one_time_amount": NSNull(), "liquid_savings_after": NSNull(),
                       "options": NSNull(), "payoff": ["months": NSNull(), "interest": NSNull()], "warnings": [String](),
                       "explanation": "La cuota de \(name) saldría de tu mes."])
        }

        guard let id = body["debt_id"] as? Int else { return failure(422, "debt_required", "Elegí una de tus deudas.") }
        guard let debt = debts.first(where: { $0["id"] as? Int == id }), let remaining = decimal(debt["remaining_amount"]), remaining > 0 else {
            return failure(404, "debt_not_found", "No encontramos esa deuda.")
        }
        let payment = decimal(debt["monthly_payment"])
        let view: [String: Any] = ["id": id, "name": debt["name"] ?? NSNull(), "remaining_amount": number(remaining),
                                   "monthly_payment": value(payment), "interest_rate": value(decimal(debt["interest_rate"]))]
        let warnings = payment == nil ? ["Esta deuda no tiene cuota mensual; DINCR no la inventó."] : [String]()

        if kind == "pay_off" {
            return ok(["rule_version": "debt-scenarios-v1", "kind": kind, "debt": view, "monthly_leftover": leftover(payment),
                       "one_time_amount": number(remaining), "liquid_savings_after": NSNull(), "options": NSNull(),
                       "payoff": ["months": NSNull(), "interest": NSNull()], "warnings": warnings,
                       "explanation": "Si pagás \(debt["name"] as? String ?? "esta deuda") completa, esa cuota queda libre cada mes."])
        }
        guard kind == "extra_payment" else { return failure(422, "unknown_kind", "Ese escenario no existe.") }
        guard let extra = amount, extra > 0 else { return failure(422, "amount_required", "Indicá cuánto querés abonar.") }
        guard extra < remaining else { return failure(422, "covers_debt", "Ese abono cubre toda la deuda: probá el escenario de pagarla.") }
        let lower = payment.map { $0 * (remaining - extra) / remaining }
        let monthsSaved = payment.map { NSDecimalNumber(decimal: extra / $0).intValue }
        return ok(["rule_version": "debt-scenarios-v1", "kind": kind, "debt": view,
                   "monthly_leftover": ["current": number(current), "scenario": NSNull(), "change": NSNull()],
                   "one_time_amount": number(extra), "liquid_savings_after": NSNull(), "payoff": NSNull(),
                   "options": ["lower_installment": ["monthly_payment": value(lower), "monthly_leftover": value(both(payment, lower).map { current + $0.0 - $0.1 }),
                                                     "change": value(both(payment, lower).map { $0.0 - $0.1 })],
                               "shorter_term": ["monthly_payment": value(payment), "monthly_leftover": number(current),
                                                "months_saved": monthsSaved ?? NSNull(), "interest_saved": NSNull()]],
                   "warnings": warnings,
                   "explanation": "Tu banco decide si el abono baja la cuota o acorta el plazo: bajar la cuota libera dinero cada mes; acortar el plazo ahorra más intereses."])
    }
}

private func both(_ first: Decimal?, _ second: Decimal?) -> (Decimal, Decimal)? {
    guard let first, let second else { return nil }
    return (first, second)
}
