import Foundation

// The fixture's Salvavidas automatic contributions (Debug demos and tests only), mirroring
// `backend/finance/salvavidas_plan.py` and `emergency_fund.py`: every scheduled date after the
// declared balance's day, up to today (and not after the end date), adds the amount; the Owner's
// rate adds simple daily interest. Derived when read; a read never writes. Android twin:
// `FakeSalvavidasPlan.kt`.
extension FixtureBackend {
    static let salvavidasFrequencies = ["weekly", "biweekly", "monthly"]

    /// What the stored plan added to `base` (the `auto_contribution` answer), or nil without a plan.
    func salvavidasPlanAnswer(base: Decimal, interestRate: Decimal?) -> [String: Any]? {
        guard let plan = salvavidasPlan, let start = Self.parseDay(plan["start_date"] as? String ?? "") else { return nil }
        let today = Self.parseDay(day(0)) ?? start
        let baseDate = salvavidasBaseDate.flatMap(Self.parseDay) ?? Self.utc.date(byAdding: .day, value: -1, to: start)!
        let enabled = plan["enabled"] as? Bool ?? false
        let amount = decimal(plan["amount"]) ?? 0
        let dates = enabled ? Self.scheduledDays(plan, after: baseDate, until: today) : []
        let contributions = amount * Decimal(dates.count)
        var interest = Decimal(0)
        if enabled, let rate = interestRate, rate > 0 {
            let r = rate / 100
            interest = base * r * Decimal(Self.days(from: baseDate, to: today)) / 365
            for date in dates { interest += amount * r * Decimal(Self.days(from: date, to: today)) / 365 }
            interest = Self.round2(interest)
        }
        let horizon = Self.utc.date(byAdding: .year, value: 2, to: today)!
        let next = enabled ? Self.scheduledDays(plan, after: today, until: horizon).first : nil
        var answer = plan
        answer["base_amount"] = number(base)
        answer["base_date"] = Self.dayString(baseDate)
        answer["contributions_count"] = dates.count
        answer["contributions_amount"] = number(contributions)
        answer["estimated_interest"] = number(interest)
        answer["next_date"] = next.map { Self.dayString($0) as Any } ?? NSNull()
        answer["total"] = number(base + contributions + interest)
        return answer
    }

    /// Scheduled days d with `after < d <= until`, within the plan's start and end.
    static func scheduledDays(_ plan: [String: Any], after: Date, until: Date) -> [Date] {
        guard let start = parseDay(plan["start_date"] as? String ?? "") else { return [] }
        let end = (plan["end_date"] as? String).flatMap(parseDay) ?? until
        let last = min(until, end)
        var days: [Date] = []
        for index in 0..<5000 {
            let date: Date
            switch plan["frequency"] as? String {
            case "monthly": date = utc.date(byAdding: .month, value: index, to: start)!
            case "biweekly": date = utc.date(byAdding: .day, value: index * 14, to: start)!
            default: date = utc.date(byAdding: .day, value: index * 7, to: start)!
            }
            if date > last { break }
            if date > after { days.append(date) }
        }
        return days
    }

    static func days(from: Date, to: Date) -> Int { max(utc.dateComponents([.day], from: from, to: to).day ?? 0, 0) }

    static func round2(_ value: Decimal) -> Decimal {
        var copy = value, rounded = Decimal()
        NSDecimalRound(&rounded, &copy, 2, .plain)
        return rounded
    }

    /// Validates `auto_contribution` like `salvavidas_plan.validated_plan`: the plan, or a 422.
    func validatedSalvavidasPlan(_ raw: Any?) -> (plan: [String: Any]?, refusal: Answer?) {
        guard let raw = raw as? [String: Any] else { return (nil, error(422, "Los aportes automáticos no son válidos.")) }
        guard let amount = decimal(raw["amount"]), amount > 0, amount <= SalvavidasPlanRequest.maxAmount else {
            return (nil, error(422, "Indicá un monto de aporte mayor que cero."))
        }
        guard let frequency = raw["frequency"] as? String, Self.salvavidasFrequencies.contains(frequency) else {
            return (nil, error(422, "La frecuencia debe ser semanal, quincenal o mensual."))
        }
        guard let startText = raw["start_date"] as? String, let start = Self.parseDay(startText) else {
            return (nil, error(422, "Indicá la fecha del primer aporte."))
        }
        var end: Date?
        if let endText = raw["end_date"] as? String, !endText.isEmpty {
            guard let parsed = Self.parseDay(endText), parsed >= start else {
                return (nil, error(422, "La fecha final debe ser después del primer aporte."))
            }
            end = parsed
        }
        return ([
            "enabled": raw["enabled"] as? Bool ?? false, "amount": number(amount), "frequency": frequency,
            "start_date": Self.dayString(start), "end_date": end.map { Self.dayString($0) as Any } ?? NSNull(),
        ], nil)
    }

    /// The plan and rate parts of `PUT /vip/salvavidas`, validated (nothing is changed here).
    struct SalvavidasPlanChange { var plan: [String: Any]?; var rate: Decimal? }

    func salvavidasPlanChange(_ body: [String: Any], balanceKnown: Bool) -> (change: SalvavidasPlanChange, refusal: Answer?) {
        var change = SalvavidasPlanChange()
        if let raw = body["annual_interest_rate"], !(raw is NSNull) {
            guard profile["role"] as? String == "owner" else {
                return (change, error(422, "La tasa de interés del Salvavidas no está disponible en tu plan."))
            }
            guard let value = decimal(raw), value >= 0, value <= 50 else {
                return (change, error(422, "Indicá una tasa de interés anual entre 0 % y 50 %."))
            }
            change.rate = value
        }
        if let raw = body["auto_contribution"], !(raw is NSNull) {
            let checked = validatedSalvavidasPlan(raw)
            if let refusal = checked.refusal { return (change, refusal) }
            change.plan = checked.plan
            if change.plan?["enabled"] as? Bool == true, !balanceKnown {
                return (change, error(422, "Indicá cuánto tenés ahorrado hoy (puede ser 0) para activar los aportes automáticos."))
            }
        }
        return (change, nil)
    }

    /// Declaring the balance restarts the count from today; turning the plan on counts from today.
    func apply(_ change: SalvavidasPlanChange, declaredNow: Bool) {
        let today = day(0)
        if let rate = change.rate { ownerSalvavidasRate = rate }
        if declaredNow { salvavidasBaseDate = today }
        if let plan = change.plan {
            let wasEnabled = salvavidasPlan?["enabled"] as? Bool ?? false
            if plan["enabled"] as? Bool == true, !wasEnabled, !declaredNow { salvavidasBaseDate = today }
            salvavidasPlan = plan
        }
    }
}
