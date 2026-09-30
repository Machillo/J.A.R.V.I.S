import Foundation

/// An in-memory DINCR backend behind the HTTP transport, for Debug demos, previews and tests only
/// (`LaunchPolicy` never selects it in a Release build). The real `APIClient` and `DincrService`
/// run against it, so headers, errors and JSON are exercised exactly as against FastAPI, with the
/// same response shapes (e.g. `/vip/gmail/emails` answers `{status, items}`, `failed_connections`
/// is a list). Every name and amount is invented (CLAUDE.md §4.F).
///
/// It mirrors the backend rules the app depends on: plan minimums (403), idempotent creates
/// (`X-Idempotency-Key` replays; another body is a 409), a single-use mail `flow`/`completion`,
/// reviewed candidates answering `already_reviewed` without writing, and reject never creating a
/// transaction. It does not compute financial results beyond simple sums for display.
public actor FixtureBackend: HTTPTransport {
    public enum Scenario: String, Sendable, CaseIterable {
        case populated, empty, failing, newUser, legalRequired, choosePlan
        /// VIP account whose mailbox is not connected yet: consent → connect → return → sync.
        case mailOnboarding
        /// The store screenshots' account (`StoreSample`): the backend engines' own answers, a fixed date.
        case store
    }

    public static let baseURL = URL(string: "https://fixture.dincr.invalid")!
    public static let authorizeHost = "accounts.fixture.invalid"

    let scenario: Scenario
    let latency: Duration
    let today: Date
    let language: AppLanguage
    /// `.store`: the budget limits the engine answer was computed for (edits fall back to the local view).
    private let storeBudget: [[String: Any]]?
    private var profile: [String: Any]
    private var movements: [[String: Any]] = []
    private var debts: [[String: Any]] = []
    private var goals: [[String: Any]] = []
    private var savings: [[String: Any]] = []
    private var recurring: [[String: Any]] = []
    private var budget: [[String: Any]] = [["category": "Comida", "monthly_limit": 150_000], ["category": "Transporte", "monthly_limit": 60_000]]
    private var situation: [String: Any]?
    private var candidates: [[String: Any]] = []
    private var tickets: [[String: Any]] = []
    private var mailConnected: Bool
    private var mailConsentAccepted: Bool
    /// flow → completion issued by the fixture "provider"; redeemed once.
    private var pendingFlows: [String: String] = [:]
    private var nextID = 500
    private var replays: [String: (body: Data?, status: Int, response: Data)] = [:]
    /// The change the scripted JARVIS chat waits a "sí" / "no" for.
    private var jarvisPending = false
    /// The scripted pending question (a goal's name), and whether it is asking about "Fondo de emergencia".
    private var jarvisAsksGoalName = false
    private var jarvisClarifying = false
    public private(set) var requests: [URLRequest] = []

    /// The role this fake server gives its account in `/auth/me` (UI tests of the role matrix). The
    /// app still learns the role only from `/auth/me`, exactly as with the real backend.
    public enum Role: String, Sendable, CaseIterable {
        case user, owner, admin
    }

    public init(scenario: Scenario = .populated, plan: PlanTier = .free, role: Role = .user, latency: Duration = .milliseconds(300),
                today: Date = .now, language: AppLanguage = .current) {
        self.scenario = scenario
        self.latency = latency
        self.language = language
        // STORE images must not depend on the capture day.
        self.today = scenario == .store ? Self.date(StoreSample.today) : today
        self.storeBudget = scenario == .store ? StoreSample.budget(language) : nil
        let vip = plan == .vip || scenario == .mailOnboarding
        self.mailConnected = scenario == .populated && vip
        self.mailConsentAccepted = scenario == .populated && vip
        self.profile = Self.sampleProfile(scenario: scenario, plan: scenario == .mailOnboarding ? .vip : plan)
        // A synchronous actor initializer cannot call isolated methods: the seed is built statically.
        if scenario == .populated || scenario == .mailOnboarding {
            let seed = Self.seed(today: today)
            movements = seed.movements; debts = seed.debts; goals = seed.goals; savings = seed.savings; recurring = seed.recurring
            if scenario == .populated && vip { candidates = Self.sampleCandidates(today: today) }
        }
        if scenario == .store {
            profile = StoreSample.profile(plan: plan, language: language)
            movements = StoreSample.rows("movements", language: language)
            debts = StoreSample.rows("debts", language: language)
            goals = StoreSample.rows("goals", language: language)
            recurring = StoreSample.rows("recurring", language: language)
            savings = StoreSample.savings(language)
            budget = StoreSample.budget(language)
            situation = StoreSample.situation(language)
            mailConnected = plan == .vip
            mailConsentAccepted = plan == .vip
            if plan == .vip { candidates = StoreSample.candidates(language) }
        }
        profile["role"] = role.rawValue
        if role == .owner {
            // Like the backend seed: the Owner's plan is VIP, granted with access_source owner.
            profile["subscription"] = ["plan": "vip", "plan_name": "VIP", "status": "active", "access_source": "owner"]
        }
    }

    static func date(_ day: String) -> Date {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = .current
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: day) ?? .now
    }

    /// `.store`: the engine's answer for a read route, as the real backend computed it.
    private func storeEngine(_ method: String, _ path: String) -> Answer? {
        guard scenario == .store, method == "GET" else { return nil }
        let name: String
        let tier: PlanTier
        switch path {
        case "/user-product/free/dashboard": name = "free_dashboard"; tier = .free
        case "/user-product/finance/strategy-basic": name = "strategy_basic"; tier = .basic
        case "/user-product/finance/strategy-vip": name = "strategy_vip"; tier = .vip
        case "/user-product/vip/command-center": name = "command_center"; tier = .vip
        case "/user-product/basic/budget":
            // Until the limits are edited, the backend's guided budget for these limits.
            let current = try? JSONSerialization.data(withJSONObject: budget, options: [.sortedKeys])
            let original = try? JSONSerialization.data(withJSONObject: storeBudget ?? [], options: [.sortedKeys])
            guard current == original else { return nil }
            name = "budget"; tier = .basic
        default: return nil
        }
        if let denied = needs(tier) { return denied }
        return ok(StoreSample.engine(name, language: language))
    }

    /// A client over this backend (the session is irrelevant here; the header is still checked).
    public static func service(_ backend: FixtureBackend) -> DincrService {
        DincrService(client: APIClient(baseURL: baseURL, tokens: FixtureTokens(), transport: backend, backoff: { _ in }))
    }

    // MARK: Transport

    public func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        if latency > .zero { try await Task.sleep(for: latency) }
        requests.append(request)
        let url = request.url!
        let path = url.path
        let method = request.httpMethod ?? "GET"
        func reply(_ status: Int, _ data: Data) -> (Data, HTTPURLResponse) {
            (data, HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!)
        }
        if request.value(forHTTPHeaderField: "Authorization") == nil && path != "/product-ops/release-policy" {
            return reply(401, Self.errorBody("Falta Authorization"))
        }
        if scenario == .failing && path != "/product-ops/release-policy" {
            return reply(500, Self.errorBody("Ocurrió un error interno. Intentá nuevamente."))
        }
        // Like core/idempotency.py: the same key replays the stored answer; another body is a 409.
        let key = ["POST", "PUT", "PATCH"].contains(method) ? request.value(forHTTPHeaderField: "X-Idempotency-Key") : nil
        if let key, let stored = replays[key] {
            return stored.body == request.httpBody ? reply(stored.status, stored.response) : reply(409, Self.errorBody("La referencia de recuperación ya pertenece a otro cambio."))
        }
        let query = Dictionary(URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.map { ($0.name, $0.value ?? "") } ?? [], uniquingKeysWith: { $1 })
        let body = request.httpBody.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
        let (status, object) = route(method, path, query, body)
        let data = (try? JSONSerialization.data(withJSONObject: object)) ?? Data("{}".utf8)
        if let key, (200..<300).contains(status) { replays[key] = (request.httpBody, status, data) }
        return reply(status, data)
    }

    // MARK: Routing

    private typealias Answer = (Int, Any)

    private func route(_ method: String, _ path: String, _ query: [String: String], _ body: [String: Any]) -> Answer {
        if let answer = storeEngine(method, path) { return answer }
        let parts = path.split(separator: "/").map(String.init)
        func id(at index: Int) -> Int { parts.indices.contains(index) ? Int(parts[index]) ?? -1 : -1 }
        switch (method, path) {
        // Identity and account
        case ("GET", "/auth/me"): return ok(profile)
        case ("DELETE", "/auth/me"): return ok(["status": "OK", "deletion_id": "del_demo"])
        // JARVIS chat: /jarvis/* admits owner and admin, like the backend.
        case ("POST", "/jarvis/chat"): return jarvisChat(body["message"] as? String ?? "")
        case ("GET", "/auth/me/export"): return ok(["format_version": 1, "account": ["id": 1], "data": [String: Any]()])
        case ("POST", "/auth/profile-setup"):
            profile["display_name"] = body["display_name"]
            profile["profile_setup_completed"] = true
            profile["base_currency"] = body["base_currency"] ?? "CRC"
            profile["number_format"] = body["number_format"]
            profile["currency_placement"] = body["currency_placement"]
            return ok(["status": "ok", "profile": profile])
        case ("POST", "/auth/legal/accept"):
            let legal = profile["legal"] as? [String: Any] ?? [:]
            guard body["terms_version"] as? String == legal["terms_version"] as? String,
                  body["privacy_version"] as? String == legal["privacy_version"] as? String else {
                return error(409, "Las versiones legales cambiaron.")
            }
            profile["legal"] = legal.merging(["required": false, "accepted_at": "2026-09-29T12:00:00Z"]) { $1 }
            return ok(["status": "accepted", "required": false])
        case ("GET", "/auth/plans"): return ok(Self.plans)
        case ("GET", "/product-ops/billing/catalog"):
            return ok(["plans": [["code": "basic", "regular_price_crc": 2990], ["code": "vip", "regular_price_crc": 4990]], "promotion": NSNull(), "notice": NSNull()])
        case ("POST", "/auth/plan"):
            // Without an active promotion the backend accepts only Free here; paid plans come from a store.
            guard body["plan"] as? String == "free" else { return error(402, "Este plan se activa desde la tienda.") }
            profile["plan_selected"] = true
            profile["subscription"] = ["plan": "free", "plan_name": "Free", "status": "active", "access_source": "self_service"]
            return ok(["status": "ok", "plan": "free", "profile": profile])
        // Operations
        case ("GET", "/product-ops/feature-flags"): return ok(["flags": OpsFlag.allCases.map { ["flag_key": $0.rawValue, "enabled": $0 != .storeBilling] }])
        case ("GET", "/product-ops/health"): return ok(["status": "operational", "active_incidents": 0])
        case ("GET", "/product-ops/release-policy"): return ok(["platform": "ios", "status": "current", "required": false, "active": false])
        case ("GET", "/product-ops/feedback"): return ok(tickets)
        case ("POST", "/product-ops/feedback"):
            let ticketID = nextId()
            let ticket: [String: Any] = ["id": ticketID, "category": body["category"] ?? "other", "subject": body["subject"] ?? "", "status": "open",
                                         "created_at": "\(day(0))T12:00:00Z", "public_id": String(format: "DINCR-%06d", ticketID)]
            tickets.insert(ticket, at: 0)
            return ok(["id": ticketID, "public_id": ticket["public_id"]!, "email_sent": true])
        // Movements
        case ("GET", "/user-product/free/dashboard"): return ok(freeDashboard())
        case ("GET", "/user-product/free/monthly-summary"): return ok(monthlySummary(query["period"] ?? String(day(0).prefix(7))))
        case ("GET", "/user-product/free/movements"):
            return ok(movements.sorted { ($0["transaction_date"] as? String ?? "") > ($1["transaction_date"] as? String ?? "") })
        case ("POST", "/user-product/finance/income"), ("POST", "/user-product/finance/expenses"):
            return createMovement(income: path.hasSuffix("income"), body)
        // Debts
        case ("GET", "/user-product/finance/debts"): return ok(debts)
        case ("POST", "/user-product/finance/debts"):
            var debt = body
            debt["id"] = nextId()
            let remaining = body["remaining_amount"]
            debt["total_amount"] = body["total_amount"] ?? remaining
            debts.append(debt)
            return ok(debt)
        // Goals and savings
        case ("GET", "/user-product/goals"): return ok(goals)
        case ("POST", "/user-product/goals"):
            var goal = body
            goal["id"] = nextId(); goal["status"] = "active"
            goals.append(goal)
            return ok(goal)
        case ("GET", "/user-product/savings-plans"): return ok(savings)
        case ("POST", "/user-product/savings-plans"):
            var plan = body
            plan["id"] = nextId(); plan["status"] = "active"
            savings.append(plan)
            return ok(plan)
        // Situation
        case ("GET", "/user-product/financial-situation"): return ok(financialSituation())
        case ("PUT", "/user-product/financial-situation"):
            situation = body
            return ok(financialSituation())
        default: break
        }

        if parts.starts(with: ["user-product", "free", "movements"]), parts.count == 4 { return editMovement(method, parts[3].removingPercentEncoding ?? parts[3], body) }
        if parts.starts(with: ["user-product", "finance", "debts"]), parts.count >= 4 { return debt(method, id(at: 3), parts.count == 5 ? parts[4] : nil, body) }
        if parts.starts(with: ["user-product", "goals"]), parts.count >= 3 { return goal(method, id(at: 2), parts.count == 4 ? parts[3] : nil, body) }
        if parts.starts(with: ["user-product", "savings-plans"]), parts.count >= 3 { return savingsPlan(method, id(at: 2), parts.count == 4 ? parts[3] : nil, body) }
        if parts.starts(with: ["product-ops", "feedback"]), parts.count == 4 {
            guard let index = tickets.firstIndex(where: { $0["id"] as? Int == id(at: 2) }) else { return error(404, "No encontrado") }
            tickets[index]["user_resolution"] = body["resolution"]
            return ok(["status": "ok"])
        }
        if path.hasPrefix("/user-product/basic") || path == "/user-product/finance/strategy-basic" {
            if let denied = needs(.basic) { return denied }
            return basic(method, path, parts, query, body)
        }
        if path.hasPrefix("/user-product/vip/gmail") || path.hasPrefix("/user-product/vip/mail") || path.hasPrefix("/user-product/vip/financial-identity") {
            if let denied = needs(.vip) { return denied }
            return mail(method, path, parts, query, body)
        }
        if path.hasPrefix("/user-product/vip") || path.hasPrefix("/user-product/finance/strategy-vip") {
            if let denied = needs(.vip) { return denied }
            return vip(path)
        }
        return error(404, "Not Found")
    }

    // MARK: Movements

    private func createMovement(income: Bool, _ body: [String: Any]) -> Answer {
        guard let typed = decimal(body["amount"]), typed > 0 else { return error(422, "Monto inválido") }
        let base = profile["base_currency"] as? String ?? "CRC"
        let currency = body["currency"] as? String
        let rate = decimal(body["exchange_rate"])
        let foreign = currency != nil && currency != base
        if foreign && rate == nil { return error(422, "Indicá el tipo de cambio (colones por 1 dólar) para registrar un monto en otra moneda.") }
        let stored = foreign ? (ConversionPreview.baseAmount(typed: typed, currency: currency!, base: base, rate: rate) ?? typed) : typed
        let origin = income ? "salary" : "expense"
        let sid = nextId()
        var row: [String: Any] = ["movement_id": "\(origin):\(sid)", "source_id": sid, "origin": origin, "transaction_date": body["entry_date"] ?? day(0),
                                  "description": body["description"] ?? "", "amount": number(stored), "transaction_type": income ? "income" : "expense",
                                  "category": body["category"] ?? "", "notes": "", "editable": true]
        if foreign { row["original_amount"] = number(typed); row["original_currency"] = currency; row["exchange_rate"] = number(rate!) }
        movements.append(row)
        return ok(["id": sid])
    }

    private func editMovement(_ method: String, _ movementID: String, _ body: [String: Any]) -> Answer {
        guard let index = movements.firstIndex(where: { $0["movement_id"] as? String == movementID }), movements[index]["editable"] as? Bool == true else {
            return error(404, "Movimiento no encontrado o no editable.")
        }
        if method == "DELETE" {
            movements.remove(at: index)
            return ok(["status": "ok", "movement_id": movementID])
        }
        guard let typed = decimal(body["amount"]) else { return error(422, "Monto inválido") }
        let base = profile["base_currency"] as? String ?? "CRC"
        let currency = body["currency"] as? String
        let rate = decimal(body["exchange_rate"])
        let foreign = currency != nil && currency != base
        let origin = movements[index]["origin"] as? String ?? ""
        if foreign && !["salary", "expense"].contains(origin) { return error(422, "Este movimiento solo se puede registrar en tu moneda principal.") }
        if foreign && rate == nil { return error(422, "Indicá el tipo de cambio.") }
        var row = movements[index]
        row["transaction_date"] = body["transaction_date"]; row["description"] = body["description"]; row["category"] = body["category"]
        row["amount"] = number(foreign ? (ConversionPreview.baseAmount(typed: typed, currency: currency!, base: base, rate: rate) ?? typed) : typed)
        // Like the backend: without a currency the row becomes a plain base-currency amount.
        row["original_amount"] = foreign ? number(typed) : NSNull()
        row["original_currency"] = foreign ? currency! : NSNull()
        row["exchange_rate"] = foreign ? number(rate!) : NSNull()
        movements[index] = row
        return ok(["status": "ok", "movement_id": movementID])
    }

    // MARK: Planning

    private func debt(_ method: String, _ debtID: Int, _ action: String?, _ body: [String: Any]) -> Answer {
        guard let index = debts.firstIndex(where: { $0["id"] as? Int == debtID }) else { return error(404, "Deuda no encontrada.") }
        switch (method, action) {
        case ("POST", "payments"?):
            let remaining = decimal(debts[index]["remaining_amount"]) ?? 0
            let paid = min(decimal(body["amount"]) ?? 0, remaining)
            debts[index]["remaining_amount"] = number(remaining - paid)
            return ok(["status": "OK", "debt_id": debtID, "payment_amount": number(paid), "new_remaining_amount": number(remaining - paid)])
        case ("DELETE", nil):
            debts.remove(at: index)
            return ok(["status": "ok", "id": debtID])
        case ("PUT", nil):
            if let denied = needs(.basic) { return denied }
            debts[index] = body.merging(["id": debtID]) { $1 }
            return ok(debts[index])
        default: return error(405, "Método no permitido")
        }
    }

    private func goal(_ method: String, _ goalID: Int, _ action: String?, _ body: [String: Any]) -> Answer {
        guard let index = goals.firstIndex(where: { $0["id"] as? Int == goalID }) else { return error(404, "Meta no encontrada.") }
        switch (method, action) {
        case ("POST", "contributions"?):
            let target = decimal(goals[index]["target_amount"]) ?? 0
            let current = decimal(goals[index]["current_amount"]) ?? 0
            if current >= target { return error(409, "La meta ya está completa.") }
            let next = min(current + (decimal(body["amount"]) ?? 0), target)
            goals[index]["current_amount"] = number(next)
            if next >= target { goals[index]["status"] = "completed" }
            return ok(goals[index])
        case ("DELETE", nil):
            goals.remove(at: index)
            return ok(["status": "ok", "id": goalID])
        case ("PUT", nil):
            if let denied = needs(.basic) { return denied }
            goals[index] = goals[index].merging(body) { $1 }
            return ok(goals[index])
        default: return error(405, "Método no permitido")
        }
    }

    private func savingsPlan(_ method: String, _ planID: Int, _ action: String?, _ body: [String: Any]) -> Answer {
        guard let index = savings.firstIndex(where: { $0["id"] as? Int == planID }) else { return error(404, "Plan no encontrado.") }
        switch (method, action) {
        case ("POST", "contributions"?):
            savings[index]["saved_amount"] = number((decimal(savings[index]["saved_amount"]) ?? 0) + (decimal(body["amount"]) ?? 0))
            return ok(savings[index])
        case ("DELETE", nil):
            savings.remove(at: index)
            return ok(["status": "ok", "id": planID])
        default: return error(405, "Método no permitido")
        }
    }

    // MARK: Basic

    private func basic(_ method: String, _ path: String, _ parts: [String], _ query: [String: String], _ body: [String: Any]) -> Answer {
        let month = String(day(0).prefix(7))
        switch (method, path) {
        case ("GET", "/user-product/basic/dashboard"):
            let (income, expenses) = totals(month)
            return ok(["month": month, "income": number(income), "expenses": number(expenses), "debt_paid": 0, "balance": number(income - expenses),
                       "debt": ["original": number(sum(debts, "total_amount")), "remaining": number(sum(debts, "remaining_amount")), "monthly": number(sum(debts, "monthly_payment")), "progress": 35.0],
                       "savings": number(sum(savings, "saved_amount")),
                       "goals": ["current": number(sum(goals, "current_amount")), "target": number(sum(goals, "target_amount")), "progress": 40.0, "active": goals.count],
                       "categories": categories(month), "monthly_history": history()])
        case ("GET", "/user-product/basic/budget"): return ok(budgetView())
        case ("PUT", "/user-product/basic/budget"):
            let items = body["items"] as? [[String: Any]] ?? []
            let names = items.compactMap { ($0["category"] as? String)?.lowercased() }
            if Set(names).count != names.count { return error(422, "Categorías repetidas.") }
            budget = items
            return ok(budgetView())
        case ("GET", "/user-product/basic/calendar"):
            let period = query["period"] ?? month
            let events: [[String: Any]] = recurring.filter { $0["is_active"] as? Bool ?? true }.map {
                ["date": "\(period)-\(String(format: "%02d", min(max($0["due_day"] as? Int ?? 1, 1), 28)))", "kind": $0["item_type"] ?? "expense", "name": $0["name"] ?? "", "amount": $0["amount"] ?? 0, "source": "recurring"]
            }
            return ok(["period": period, "events": events, "summary": ["income_events": 1, "payments": number(sum(recurring, "amount")), "commitments": events.count]])
        case ("GET", "/user-product/basic/recurring"):
            return ok(["items": recurring, "monthly_expenses": number(sum(recurring, "amount")), "annual_expenses": number(sum(recurring, "amount") * 12)])
        case ("POST", "/user-product/basic/recurring"):
            var item = body
            item["id"] = nextId()
            recurring.append(item)
            return ok(item)
        case ("GET", "/user-product/basic/reports"):
            let period = query["period"] ?? month
            let (income, expenses) = totals(period)
            return ok(["period": period, "income": number(income), "expenses": number(expenses), "debt_paid": 0, "goal_contributions": 0,
                       "saved": number(income - expenses), "balance": number(income - expenses), "categories": categories(period),
                       "comparison": ["income": number(income), "expenses": number(expenses), "debt_paid": 0]])
        case ("GET", "/user-product/finance/strategy-basic"): return ok(Self.strategy)
        default:
            if parts.starts(with: ["user-product", "basic", "recurring"]), parts.count == 4, let index = recurring.firstIndex(where: { $0["id"] as? Int == Int(parts[3]) }) {
                if method == "DELETE" { recurring.remove(at: index); return ok(["status": "ok"]) }
                recurring[index] = body.merging(["id": recurring[index]["id"]!]) { $1 }
                return ok(recurring[index])
            }
            return error(404, "Not Found")
        }
    }

    // MARK: VIP

    private func vip(_ path: String) -> Answer {
        switch path {
        case "/user-product/vip/command-center":
            return ok(["as_of": day(0),
                       "director": ["priority": "debt", "headline": "Tu prioridad es bajar la tarjeta", "next_action": "Pagá ₡40.000 extra a la tarjeta este mes", "data_complete": true],
                       "score": ["value": 72, "label": "Estable", "factors": [["label": "Ahorro de emergencia", "impact": "warning"]]],
                       "debt_planner": ["recommended": ["method": "finva", "target": "Tarjeta de ejemplo", "monthly_to_target": 95_000, "months": 14, "interest": 84_000]],
                       "safe_to_spend": ["amount": 118_000, "monthly_margin": 214_000, "next_45_days_minimum": 96_000],
                       "alerts": [["severity": "medium", "title": "Pago de tarjeta en 5 días", "context": "El pago mínimo vence pronto.", "action": "Revisá la deuda"]],
                       "projections": [1, 3, 6].map { ["months": $0, "cash": 200_000 * $0, "debt": 900_000 - 90_000 * $0, "net_worth": -700_000 + 290_000 * $0, "confidence": "medium"] },
                       "roadmap": [["order": 1, "title": "Completá tu fondo de emergencia inicial", "amount": 50_000, "why": "Te protege de imprevistos."],
                                   ["order": 2, "title": "Pagá extra a la tarjeta", "amount": 40_000, "why": "Tiene la tasa más alta."]],
                       "automation": ["confirmed": 4, "review": pendingCount(), "duplicates": 0]])
        case "/user-product/finance/strategy-vip":
            return ok(Self.strategy.merging(["director_note": "Priorizamos la deuda con la tasa más alta."]) { $1 })
        case "/user-product/finance/strategy-vip/simulate":
            return ok(["current": Self.strategy, "scenario": Self.strategy.merging(["strategic_margin": 260_000]) { $1 },
                       "delta": ["strategic_margin": 46_000, "monthly_income": 50_000, "essential_expenses": 4_000]])
        case "/user-product/vip/aguinaldo":
            guard mailConnected else { return error(409, "Conectá tu correo para calcular el aguinaldo.") }
            return ok(["status": "OK", "period": ["start": "2025-12-01", "end": "2026-11-30"], "earned_salary_total": 5_190_000, "accrued_aguinaldo": 432_500])
        case "/user-product/vip/lifecycle/monthly-review":
            return ok(["status": "BASELINE", "period": String(day(0).prefix(7)), "headline": "Tu primer mes con DINCR", "summary": "Todavía no hay suficiente historia para comparar."])
        case "/user-product/vip/lifecycle/proactive-advisor":
            return ok(["status": "BASELINE", "as_of": day(0), "alerts": [Any](), "message": "DINCR necesita unos días de historia para avisarte de cambios."])
        default: return error(404, "Not Found")
        }
    }

    // MARK: Email Monitor

    private func mail(_ method: String, _ path: String, _ parts: [String], _ query: [String: String], _ body: [String: Any]) -> Answer {
        switch (method, path) {
        case ("GET", "/user-product/vip/gmail/status"):
            let mailbox = scenario == .store ? "ana.demo@example.com" : "persona@ejemplo.test"
            let connections: [[String: Any]] = mailConnected
                ? [["id": 1, "provider": "gmail", "google_email": mailbox, "status": "active", "automatic_updates": true, "import_since": "2026-01-01"],
                   ["id": 9, "provider": "gmail", "google_email": "antes@ejemplo.test", "status": "disabled", "automatic_updates": false]]
                : [["id": 9, "provider": "gmail", "google_email": "antes@ejemplo.test", "status": "disabled", "automatic_updates": false]]
            return ok(["status": mailConnected ? "active" : "disabled", "connected": mailConnected, "needs_reauthorization": false, "pending": pendingCount(),
                       "microsoft_available": true, "connections": connections,
                       "consent": ["required": !mailConsentAccepted, "version": Self.mailConsentVersion, "accepted_at": mailConsentAccepted ? "2026-09-01T12:00:00Z" : NSNull()],
                       "retention": ["review_evidence_days": 30, "email_metadata_days": 90, "canonical_history": "until_account_deletion"]])
        case ("POST", "/user-product/vip/gmail/consent"):
            guard body["accepted"] as? Bool == true else { return error(422, "Tenés que aceptar para continuar.") }
            guard body["version"] as? String == Self.mailConsentVersion else { return error(409, "La versión del consentimiento cambió.") }
            mailConsentAccepted = true
            return ok(["status": "accepted", "required": false, "version": Self.mailConsentVersion])
        case ("POST", "/user-product/vip/gmail/connect"), ("POST", "/user-product/vip/mail/microsoft/connect"):
            guard mailConsentAccepted else { return error(409, "Aceptá el consentimiento antes de conectar tu correo.") }
            guard ["current_month", "current_year"].contains(body["import_scope"] as? String ?? "current_year") else { return error(422, "Periodo inválido.") }
            let flow = UUID().uuidString.lowercased()
            let completion = "cmp_" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
            pendingFlows[flow] = completion
            let provider = path.contains("microsoft") ? "microsoft" : "gmail"
            // What the provider + backend callback would send back to the app (Debug fixture only).
            var back = URLComponents()
            back.scheme = "com.finva.app"; back.host = "gmail"; back.path = "/callback"
            back.queryItems = [URLQueryItem(name: provider, value: "authorized"), URLQueryItem(name: "flow", value: flow),
                               URLQueryItem(name: "completion", value: completion), URLQueryItem(name: "ret", value: UUID().uuidString.lowercased())]
            // Same parameters as the real Google URL (scope gmail.readonly only), on an invalid host.
            var parts = URLComponents()
            parts.scheme = "https"; parts.host = Self.authorizeHost; parts.path = "/\(provider)/authorize"
            parts.queryItems = [URLQueryItem(name: "scope", value: provider == "gmail" ? Self.gmailScope : "offline_access User.Read Mail.Read"),
                                URLQueryItem(name: "state", value: flow), URLQueryItem(name: "hl", value: body["locale"] as? String ?? "en"),
                                URLQueryItem(name: "fixture_return", value: back.url!.absoluteString)]
            return ok(["authorization_url": parts.url!.absoluteString])
        case ("POST", "/user-product/vip/mail/oauth/complete"):
            guard let flow = body["flow"] as? String, let completion = body["completion"] as? String,
                  pendingFlows[flow] == completion else { return error(409, "Ese enlace de conexión ya no es válido.") }
            pendingFlows[flow] = nil
            mailConnected = true
            return ok(["status": "connected", "provider": "gmail"])
        case ("POST", "/user-product/vip/gmail/sync"):
            guard mailConnected else { return error(404, "Primero conectá Gmail.") }
            if candidates.isEmpty { candidates = Self.sampleCandidates(today: today) }
            return ok(["status": "ok", "connections": 1, "failed_connections": [Int](), "scan_scope": "year_to_date", "initial_scan_complete": true,
                       "found": candidates.count, "auto_saved": 0, "pending": pendingCount(), "payroll_reports": 0, "duplicates": 0])
        case ("DELETE", "/user-product/vip/gmail"):
            mailConnected = false
            return ok(["status": "disconnected"])
        case ("GET", "/user-product/vip/gmail/emails"):
            let filter = query["status"] ?? ""
            return ok(["status": "ok", "items": filter.isEmpty ? candidates : candidates.filter { $0["review_status"] as? String == filter }])
        case ("GET", "/user-product/vip/gmail/own-transfer-suggestions"): return ok(["items": [Any]()])
        case ("GET", "/user-product/vip/financial-identity"):
            return ok(["status": "ok", "items": [["id": 1, "account_name": "Cuenta de ejemplo", "bank_name": "Banco de ejemplo", "currency": "CRC", "account_last4": "1234", "ownership_status": "pending"]],
                       "summary": ["total": 1, "pending": 1, "owned": 0, "not_mine": 0]])
        default: break
        }
        if parts.starts(with: ["user-product", "vip", "financial-identity", "accounts"]) {
            guard ["own", "not_mine"].contains(body["ownership_status"] as? String ?? "") else { return error(422, "Estado inválido.") }
            return ok(["status": "ok"])
        }
        if parts.starts(with: ["user-product", "vip", "gmail", "candidates"]), parts.count == 6, let candidateID = Int(parts[4]) {
            return review(method, candidateID, parts[5], body)
        }
        return error(404, "Not Found")
    }

    private func review(_ method: String, _ candidateID: Int, _ action: String, _ body: [String: Any]) -> Answer {
        guard let index = candidates.firstIndex(where: { $0["candidate_id"] as? Int == candidateID }) else { return error(404, "Correo financiero no encontrado.") }
        let candidate = candidates[index]
        let status = candidate["review_status"] as? String ?? "pending"
        // Like gmail_service.review_candidate: a reviewed candidate answers its stored status and writes nothing.
        if status != "pending" { return ok(["status": status, "candidate_id": candidateID, "transaction_id": candidate["transaction_id"] ?? NSNull(), "already_reviewed": true]) }
        switch (method, action) {
        case ("POST", "reject"):
            candidates[index]["review_status"] = "rejected"
            return ok(["status": "rejected", "candidate_id": candidateID, "transaction_id": NSNull()])
        case ("POST", "accept"), ("PUT", "accept"):
            let originalCurrency = candidate["original_currency"] as? String
            let currency = candidate["currency"] as? String
            let native = originalCurrency ?? currency ?? "CRC"
            let base = candidate["account_base_currency"] as? String ?? "CRC"
            if !MailCandidate.convertible.contains(native) { return error(422, "Este aviso está en una moneda que DINCR no puede convertirlo.") }
            // Precomputed: the right side of || and ?? is an autoclosure, which must not capture JSON dictionaries.
            let rate = decimal(body["exchange_rate"])
            if native != base && (method == "POST" || rate == nil) {
                return error(422, "Este movimiento está en \(native). Tocá Corregir e indicá el tipo de cambio.")
            }
            let transactionID = nextId()
            candidates[index]["review_status"] = "confirmed"
            candidates[index]["transaction_id"] = transactionID
            if method == "PUT" {
                candidates[index]["description"] = body["description"]; candidates[index]["category"] = body["category"]
            }
            let storedDate = candidate["transaction_date"] as? String ?? day(0)
            let storedDescription = candidate["description"] as? String ?? ""
            let storedCategory = candidate["category"] as? String ?? "general"
            let amount = decimal(candidate["amount"]) ?? 0
            let type = candidate["transaction_type"] as? String ?? "expense"
            let date = body["transaction_date"] as? String ?? storedDate
            let description = body["description"] as? String ?? storedDescription
            let category = body["category"] as? String ?? storedCategory
            movements.append(["movement_id": "transaction:\(transactionID)", "source_id": transactionID, "origin": "transaction",
                              "transaction_date": date, "description": description, "amount": number(amount),
                              "transaction_type": type, "category": category, "editable": false])
            return ok(["status": "confirmed", "candidate_id": candidateID, "transaction_id": transactionID])
        default: return error(405, "Método no permitido")
        }
    }

    // MARK: Read models

    private func totals(_ period: String) -> (Decimal, Decimal) {
        let rows = movements.filter { ($0["transaction_date"] as? String ?? "").hasPrefix(period) }
        let income = rows.filter { $0["transaction_type"] as? String == "income" }.reduce(Decimal(0)) { $0 + (decimal($1["amount"]) ?? 0) }
        let expenses = rows.filter { $0["transaction_type"] as? String != "income" }.reduce(Decimal(0)) { $0 + (decimal($1["amount"]) ?? 0) }
        return (income, expenses)
    }

    private func categories(_ period: String) -> [[String: Any]] {
        var byCategory: [String: Decimal] = [:]
        for row in movements {
            let inPeriod = (row["transaction_date"] as? String ?? "").hasPrefix(period)
            let isIncome = row["transaction_type"] as? String == "income"
            guard inPeriod, !isIncome else { continue }
            byCategory[row["category"] as? String ?? "Sin categoría", default: 0] += decimal(row["amount"]) ?? 0
        }
        return byCategory.sorted { $0.value > $1.value }.map { ["category": $0.key, "amount": number($0.value)] }
    }

    private func history() -> [[String: Any]] {
        let calendar = Calendar(identifier: .gregorian)
        return (0..<6).reversed().map { back in
            let date = calendar.date(byAdding: .month, value: -back, to: today) ?? today
            let parts = calendar.dateComponents([.year, .month], from: date)
            let period = String(format: "%04d-%02d", parts.year!, parts.month!)
            let (income, expenses) = totals(period)
            return ["month": period, "income": number(income), "expenses": number(expenses), "debt_paid": 0, "balance": number(income - expenses)]
        }
    }

    private func freeDashboard() -> [String: Any] {
        let month = String(day(0).prefix(7))
        let (income, expenses) = totals(month)
        return ["month": month, "income": number(income), "expenses": number(expenses), "debt_paid": 0, "debt_balance": number(sum(debts, "remaining_amount")),
                "balance": number(income - expenses), "available_after_commitments": number(income - expenses),
                "categories": categories(month).map { ["category": $0["category"]!, "amount": $0["amount"]!] }, "monthly_history": history()]
    }

    private func monthlySummary(_ period: String) -> [String: Any] {
        let (income, expenses) = totals(period)
        let cats = categories(period)
        return ["period": period, "income": number(income), "expenses": number(expenses), "debt_paid": 0, "balance": number(income - expenses),
                "top_category": cats.first ?? NSNull(), "categories": cats, "savings": number(sum(savings, "saved_amount")),
                "goals": ["current": number(sum(goals, "current_amount")), "target": number(sum(goals, "target_amount")), "progress": 40.0]]
    }

    private func budgetView() -> [String: Any] {
        let month = String(day(0).prefix(7))
        let spent = Dictionary(categories(month).map { (($0["category"] as? String ?? "").lowercased(), $0["amount"]!) }, uniquingKeysWith: { a, _ in a })
        let items = budget.map { item -> [String: Any] in
            var row = item
            row["spent"] = spent[(item["category"] as? String ?? "").lowercased()] ?? 0
            return row
        }
        return ["items": items, "total_budgeted": number(sum(budget, "monthly_limit")), "available_for_categories": 420_000, "period": month]
    }

    private func financialSituation() -> [String: Any] {
        ["financial_profile": situation ?? NSNull(),
         "observed": ["window_days": 90, "income_count": 3, "monthly_income_average": 865_000, "expense_count": 12],
         "debts": ["count": debts.count, "balance": number(sum(debts, "remaining_amount"))],
         "goals": ["count": goals.count, "current": number(sum(goals, "current_amount"))]]
    }

    private func pendingCount() -> Int { candidates.filter { $0["review_status"] as? String == "pending" }.count }

    // MARK: Helpers

    /// A scripted stand-in for the JARVIS engine (fixtures only, never real answers): "horas extra"
    /// / "horas de OT" shows a payroll change and waits for "sí" / "no", "falla" answers 500 and
    /// "respuesta rara" answers without a message. Anything else gets a plain reply.
    private func jarvisChat(_ message: String) -> Answer {
        guard ["owner", "admin"].contains(profile["role"] as? String ?? "") else { return error(403, "No tienes permisos para realizar esta acción.") }
        let text = message.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        if text.contains("falla") { return error(500, "Error interno.") }
        if jarvisClarifying {
            jarvisClarifying = false
            if text == "es la respuesta" {
                jarvisAsksGoalName = false
                return ok(["message": "¿Cuál es el monto objetivo de la meta?", "intent": "pending_action", "action_type": "create_goal",
                           "status": "PENDING", "pending": true, "data": ["current_field": "target_amount"]])
            }
            if text == "es otra consulta" {
                return ok(["message": "Señor, este es su análisis financiero.\n\nTenés una pregunta pendiente: ¿Cómo se llama la meta? Podés responderla o decir «cancelar».",
                           "intent": "financial_engine", "status": "OK", "pending": true, "data": ["status": "OK"],
                           "pending_action": ["action_type": "create_goal", "current_field": "name"]])
            }
        }
        if text == "quiero crear una meta" {
            jarvisAsksGoalName = true
            return ok(["message": "¿Cómo se llama la meta?", "intent": "create_goal", "action_type": "create_goal", "status": "PENDING", "pending": true,
                       "data": ["current_field": "name"]])
        }
        if jarvisAsksGoalName, text == "fondo de emergencia" {
            jarvisClarifying = true
            return ok(["message": "Tenés una pregunta pendiente: ¿Cómo se llama la meta? ¿\"Fondo de emergencia\" es la respuesta o querés hacer otra consulta?",
                       "intent": "pending_action", "action_type": "create_goal", "status": "PENDING", "pending": true,
                       "data": ["current_field": "clarify", "held_message": "Fondo de emergencia"]])
        }
        if text.contains("respuesta rara") { return ok(["unexpected": true]) }
        if jarvisPending, ["sí", "si", "no"].contains(text) {
            jarvisPending = false
            if text == "no" {
                return ok(["message": "Listo, cancelé el registro. No guardé nada.", "intent": "pending_action", "status": "CANCELLED", "pending": false])
            }
            return ok(["message": "Señor, OT registrado: 3.0 horas. Ingreso proyectado actualizado: ₡900.000. Sobrante proyectado: ₡120.000.",
                       "intent": "pending_action", "action_type": "create_payroll_event", "status": "OK", "pending": false])
        }
        if text.contains("horas"), text.contains("extra") || text.contains(" ot") {
            jarvisPending = true
            return ok(["message": "Voy a guardar esta evento de planilla:\n- tipo de evento: ot\n- horas: 3.0\n- monto: ₡9,000.00\n¿Confirmo y guardo? Responde sí o no.",
                       "intent": "create_payroll_event", "action_type": "create_payroll_event", "status": "PENDING", "pending": true,
                       "data": ["current_field": "confirm", "payload": ["event_type": "ot", "hours": 3.0]]])
        }
        return ok(["message": "Señor, esto es una respuesta de ejemplo.", "intent": "general", "status": "UNSUPPORTED", "pending": false, "data": NSNull()])
    }

    private func ok(_ value: Any) -> Answer { (200, value) }
    private func error(_ status: Int, _ detail: String) -> Answer { (status, ["detail": detail]) }
    static func errorBody(_ detail: String) -> Data { (try? JSONSerialization.data(withJSONObject: ["detail": detail])) ?? Data() }

    private func needs(_ tier: PlanTier) -> Answer? {
        let plan = PlanTier.from((profile["subscription"] as? [String: Any])?["plan"] as? String)
        return plan.rank < tier.rank ? error(403, "Esta función no está incluida en tu plan.") : nil
    }

    private func nextId() -> Int { nextID += 1; return nextID }

    private func decimal(_ value: Any?) -> Decimal? {
        switch value {
        case let number as NSNumber: return Decimal(string: number.stringValue, locale: Locale(identifier: "en_US_POSIX"))
        case let text as String: return Decimal(string: text, locale: Locale(identifier: "en_US_POSIX"))
        default: return nil
        }
    }

    private func number(_ value: Decimal) -> NSDecimalNumber { Self.number(value) }
    static func number(_ value: Decimal) -> NSDecimalNumber { NSDecimalNumber(decimal: value) }

    private func sum(_ rows: [[String: Any]], _ key: String) -> Decimal { rows.reduce(0) { $0 + (decimal($1[key]) ?? 0) } }

    private func day(_ offset: Int) -> String { Self.day(offset, today: today) }

    static func day(_ offset: Int, today: Date) -> String {
        let calendar = Calendar(identifier: .gregorian)
        let date = calendar.date(byAdding: .day, value: -offset, to: today) ?? today
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year!, parts.month!, parts.day!)
    }

    typealias Seed = (movements: [[String: Any]], debts: [[String: Any]], goals: [[String: Any]], savings: [[String: Any]], recurring: [[String: Any]])

    static func seed(today: Date) -> Seed {
        func day(_ offset: Int) -> String { Self.day(offset, today: today) }
        func row(_ origin: String, _ id: Int, _ offset: Int, _ description: String, _ amount: Decimal, _ type: String, _ category: String, editable: Bool = true) -> [String: Any] {
            ["movement_id": "\(origin):\(id)", "source_id": id, "origin": origin, "transaction_date": day(offset), "description": description,
             "amount": number(amount), "transaction_type": type, "category": category, "notes": "", "editable": editable]
        }
        var movements: [[String: Any]] = [
            row("expense", 11, 0, "Supermercado", 18_450, "expense", "Comida"),
            row("expense", 10, 0, "Café", 2_300, "expense", "Restaurante"),
            // Cents and a category outside the editor's list: editing must keep both.
            row("expense", 12, 1, "Feria del agricultor", Decimal(string: "12345.5")!, "expense", "Feria"),
            row("transaction", 9, 1, "Aviso bancario · Gasolinera", 25_000, "expense", "Gasolina", editable: false),
            row("salary", 8, 3, "Salario quincenal", 432_500, "income", "Salario"),
            row("expense", 7, 4, "Internet del hogar", 24_900, "expense", "Internet"),
            row("expense", 6, 6, "Farmacia", 9_800, "expense", "Salud"),
            row("expense", 5, 9, "Alquiler", 210_000, "expense", "Vivienda"),
            row("salary", 4, 18, "Salario quincenal", 432_500, "income", "Salario"),
        ]
        var dollars = row("expense", 13, 2, "Suscripción en dólares", Decimal(string: "5075.00")!, "expense", "Entretenimiento")
        dollars["original_amount"] = 10; dollars["original_currency"] = "USD"; dollars["exchange_rate"] = number(Decimal(string: "507.5")!)
        movements.append(dollars)
        let debts: [[String: Any]] = [["id": 31, "name": "Tarjeta de crédito", "debt_type": "credit_card", "total_amount": 600_000, "remaining_amount": 420_000, "monthly_payment": 45_000,
                  "interest_rate": 36, "payment_day": 15, "progress_percent": 30.0],
                 ["id": 32, "name": "Préstamo del carro", "debt_type": "loan", "total_amount": 2_400_000, "remaining_amount": 820_000, "monthly_payment": 50_000,
                  "interest_rate": 12, "payment_day": 1, "progress_percent": 65.8]]
        let goals: [[String: Any]] = [["id": 41, "name": "Fondo de emergencia", "target_amount": 1_500_000, "current_amount": 380_000, "target_date": "2027-06-30", "priority": "high", "status": "active"],
                 ["id": 42, "name": "Viaje", "target_amount": 400_000, "current_amount": 90_000, "priority": "medium", "status": "active"]]
        let savings: [[String: Any]] = [["id": 44, "name": "Vacaciones", "monthly_amount": 25_000, "saved_amount": 75_000, "start_date": "2026-07-01", "end_date": "2027-07-01", "status": "active"]]
        let recurring: [[String: Any]] = [["id": 45, "name": "Internet", "amount": 24_900, "category": "Internet", "item_type": "expense", "frequency": "monthly", "due_day": 4, "is_active": true]]
        return (movements, debts, goals, savings, recurring)
    }

    static func sampleCandidates(today: Date) -> [[String: Any]] {
        func day(_ offset: Int) -> String { Self.day(offset, today: today) }
        return [
            ["candidate_id": 21, "email_id": 21, "bank": "Banco de ejemplo", "sender": "avisos@banco.test", "subject": "Notificación de compra", "received_at": "\(day(1))T10:00:00Z",
             "description": "Compra en supermercado", "amount": 15_300, "currency": "CRC", "account_base_currency": "CRC", "transaction_date": day(1),
             "transaction_type": "expense", "category": "Comida", "review_status": "pending"],
            ["candidate_id": 22, "email_id": 22, "bank": "Banco de ejemplo", "sender": "avisos@banco.test", "subject": "Compra internacional", "received_at": "\(day(2))T10:00:00Z",
             "description": "Tienda en línea", "amount": 25, "currency": "USD", "account_base_currency": "CRC", "transaction_date": day(2),
             "transaction_type": "expense", "category": "Compras", "review_status": "pending"],
            ["candidate_id": 23, "email_id": 23, "bank": "Banco de ejemplo", "sender": "avisos@banco.test", "subject": "Compra en euros", "received_at": "\(day(3))T10:00:00Z",
             "description": "Museo", "amount": 12, "currency": "EUR", "account_base_currency": "CRC", "transaction_date": day(3),
             "transaction_type": "expense", "category": "Entretenimiento", "review_status": "pending"],
        ]
    }

    static func sampleProfile(scenario: Scenario, plan: PlanTier) -> [String: Any] {
        [
            // Every field /auth/me always sends (auth/saas.py enrich_identity).
            "id": 4201, "email": "persona@ejemplo.test", "display_name": scenario == .newUser ? NSNull() : "Ana Solís", "role": "user",
            "plan_selected": scenario != .newUser && scenario != .choosePlan, "profile_setup_completed": scenario != .newUser,
            "base_currency": "CRC", "number_format": "dot_comma", "currency_placement": "before", "entry_currencies": ["CRC", "USD"],
            "subscription": ["plan": plan.rawValue, "plan_name": plan.rawValue.capitalized, "status": "active", "access_source": plan == .free ? "self_service" : "courtesy"],
            "legal": ["required": scenario == .legalRequired, "terms_version": "2026-09-23-v3", "privacy_version": "2026-09-25-v4"],
        ]
    }

    public static let gmailScope = "https://www.googleapis.com/auth/gmail.readonly"
    public static let mailConsentVersion = "mail-monitor-2026-09-v2"

    // Immutable JSON samples; `[String: Any]` is not Sendable, but nothing ever mutates these.
    nonisolated(unsafe) static let plans: [[String: Any]] = [
        ["code": "free", "name": "Free", "tagline": "Ordená lo esencial", "features": ["Ingresos y gastos", "Deudas", "Metas"], "regular_price_crc": 0],
        ["code": "basic", "name": "Basic", "tagline": "Planificá tu mes", "features": ["Presupuesto guiado", "Calendario financiero", "Pagos recurrentes"], "regular_price_crc": 2990],
        ["code": "vip", "name": "VIP", "tagline": "Tu director financiero", "features": ["Monitor de correo", "Estrategia y proyecciones", "Escenarios"], "regular_price_crc": 4990],
    ]

    nonisolated(unsafe) static let strategy: [String: Any] = [
        "status": "tight", "priority": "debt", "monthly_income": 865_000, "essential_expenses": 420_000, "minimum_debt_payments": 95_000, "strategic_margin": 214_000,
        "allocations": [["bucket": "emergency", "label": "Fondo de emergencia", "amount": 60_000], ["bucket": "debt_extra", "label": "Extra a la tarjeta", "amount": 100_000],
                        ["bucket": "flex", "label": "Libre", "amount": 54_000]],
        "recommendation": "Destiná ₡100.000 extra a la tarjeta y ₡60.000 a tu fondo de emergencia.",
        "projection": ["name": "Tarjeta de crédito", "months": 14, "baseline_months": 31, "monthly_to_target": 195_000],
    ]
}

/// Tokens for the fixture backend: a constant, never a real credential.
public struct FixtureTokens: AccessTokenProvider {
    public init() {}
    public func accessToken(forceRefresh: Bool) async throws -> String { "fixture-session" }
}
