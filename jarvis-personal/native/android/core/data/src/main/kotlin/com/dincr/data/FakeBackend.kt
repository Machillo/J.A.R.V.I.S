package com.dincr.data

import java.math.BigDecimal
import java.math.RoundingMode
import java.time.LocalDate
import kotlinx.coroutines.delay
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * An in-memory DINCR backend behind the HTTP transport, for Debug demos and UI tests only
 * (`LaunchPolicy` never selects it in a Release build). The real [ApiClient] and [DincrApi] run
 * against it, so headers, errors and JSON are exercised exactly as against FastAPI. Every name and
 * amount is invented; nothing here is a real person or account.
 */
class FakeBackend(
    private val scenario: Scenario = Scenario.POPULATED,
    plan: PlanTier = PlanTier.FREE,
    private val latencyMs: Long = 0,
    currentDate: LocalDate = LocalDate.now(),
    language: AppLanguage = AppLanguage.current(),
    private val role: Role = Role.USER,
) : HttpTransport {
    /** STORE: the account of the store screenshots ([StoreSample]). */
    enum class Scenario { POPULATED, EMPTY, FAILING, NEW_USER, LEGAL_REQUIRED, CHOOSE_PLAN, STORE }

    /**
     * The role this fake server gives its account in `/auth/me` (UI tests of the role matrix). The
     * app still learns the role only from `/auth/me`, exactly as with the real backend.
     */
    /** LEGACY_ADMIN: a stored role DINCR no longer admits, only to prove the app refuses it. */
    enum class Role(val wire: String) { USER("user"), OWNER("owner"), LEGACY_ADMIN("admin") }

    private val store = if (scenario == Scenario.STORE) StoreSample(language) else null
    private val today: LocalDate = if (store != null) StoreSample.TODAY else currentDate

    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }
    private var profile = sampleProfile(plan)
    private val movements = mutableListOf<Movement>()
    private val debts = mutableListOf<Debt>()
    private val goals = mutableListOf<Goal>()
    private val savings = mutableListOf<SavingsPlan>()
    private val recurring = mutableListOf<RecurringItem>()
    private var budget = store?.budget() ?: listOf(BudgetItem("Comida", BigDecimal(150000)), BudgetItem("Transporte", BigDecimal(60000)))
    private var situation: FinancialProfile? = store?.situation()
    private val candidates = mutableListOf<MailCandidate>()
    /** Accounts detected in the notices (`account_balances`): no balance is ever served (unknown, not zero). */
    private val accounts = mutableListOf<FinancialIdentity.Account>()
    private val tickets = mutableListOf<SupportTicket>()
    /** A VIP sample account starts with a connected mailbox and notices to review. */
    private var mailConnected = (scenario == Scenario.POPULATED || scenario == Scenario.STORE) && plan == PlanTier.VIP
    private var nextId = 500L
    val requests = mutableListOf<HttpRequest>()
    private val planRoutes = FakePlanRoutes(json, today)
    private fun snapshot() = FakePlanRoutes.Snapshot(movements.toList(), debts.toList(), goals.toList(), savings.toList(), recurring.toList(), situation)
    private val isOwner get() = profile.role == "owner"
    private val isInternal get() = profile.role == "owner"

    init {
        if (scenario == Scenario.POPULATED) seed()
        store?.let {
            movements += it.movements(); debts += it.debts(); goals += it.goals(); savings += it.savings()
            recurring += it.recurring(); candidates += it.candidates()
        }
    }

    override suspend fun send(request: HttpRequest): HttpResponse {
        if (latencyMs > 0) delay(latencyMs)
        requests += request
        if (request.headers["Authorization"] == null && !request.url.contains("/product-ops/release-policy")) return error(401, "Falta Authorization")
        if (scenario == Scenario.FAILING && !request.url.contains("release-policy")) {
            return error(500, "Ocurrió un error interno. Intentá nuevamente.")
        }
        val path = request.url.substringAfter("://").substringAfter("/").let { "/" + it.substringBefore("?") }
        val query = request.url.substringAfter("?", "").split("&").filter { it.contains("=") }.associate { it.substringBefore("=") to java.net.URLDecoder.decode(it.substringAfter("="), "UTF-8") }
        val body = request.body?.takeIf { it.isNotBlank() }?.let { runCatching { json.parseToJsonElement(it).jsonObject }.getOrNull() }
        // Like core/idempotency.py: the same key replays the stored answer; another body is a 409.
        val key = request.headers["X-Idempotency-Key"]?.takeIf { request.method in setOf("POST", "PUT", "PATCH") }
        key?.let { k -> replays[k]?.let { (storedBody, response) -> return if (storedBody == request.body) response else error(409, "La referencia de recuperación ya pertenece a otro cambio.") } }
        val response = runCatching { route(request.method, path, query, body) }.getOrElse { error(422, "Datos inválidos: ${it.message}") }
        if (key != null && response.status in 200..299) replays[key] = request.body to response
        return response
    }

    private val replays = mutableMapOf<String, Pair<String?, HttpResponse>>()
    /** The change the scripted JARVIS chat waits a "sí" / "no" for. */
    private var jarvisPending = false
    /** The Owner's agenda (`events` table) and the event the scripted chat waits a "sí" for. */
    private val jarvisEvents = mutableListOf<JarvisEvent>().apply {
        if (scenario == Scenario.POPULATED) {
            add(JarvisEvent(1, "Reunión con el contador", "${today.plusDays(2)} 10:00", "personal"))
            add(JarvisEvent(2, "Cita médica", today.plusDays(9).toString(), "personal"))
        }
    }
    private var jarvisPendingEvent: JarvisEvent? = null

    private fun agendaBody() = buildJsonObject {
        put("events", kotlinx.serialization.json.buildJsonArray {
            jarvisEvents.forEach { event ->
                add(buildJsonObject {
                    put("id", event.id); put("title", event.title); put("event_date", event.eventDate)
                    put("event_type", event.eventType); put("description", event.description)
                })
            }
        })
    }.toString()
    /** The scripted pending question (a goal's name), and whether it is asking about "Fondo de emergencia". */
    private var jarvisAsksGoalName = false
    private var jarvisClarifying = false

    /**
     * A scripted stand-in for the JARVIS engine (fixtures only, never real answers): "horas extra" /
     * "horas de OT" shows a payroll change and waits for "sí" / "no", "falla" answers 500 and
     * "respuesta rara" answers without a message. Anything else gets a plain reply.
     */
    private fun jarvisChat(message: String): HttpResponse {
        if (profile.role != "owner") return error(403, "No tienes permisos para realizar esta acción.")
        val text = message.lowercase().trim()
        if ("falla" in text) return error(500, "Error interno.")
        if (jarvisClarifying) {
            jarvisClarifying = false
            if (text == "es la respuesta") {
                jarvisAsksGoalName = false
                return ok("""{"message":"¿Cuál es el monto objetivo de la meta?","intent":"pending_action","action_type":"create_goal","status":"PENDING","pending":true,"data":{"current_field":"target_amount"}}""")
            }
            if (text == "es otra consulta") {
                return ok("""{"message":"Señor, este es su análisis financiero.\n\nTenés una pregunta pendiente: ¿Cómo se llama la meta? Podés responderla o decir «cancelar».","intent":"financial_engine","status":"OK","pending":true,"data":{"status":"OK"},"pending_action":{"action_type":"create_goal","current_field":"name"}}""")
            }
        }
        if (text == "quiero crear una meta") {
            jarvisAsksGoalName = true
            return ok("""{"message":"¿Cómo se llama la meta?","intent":"create_goal","action_type":"create_goal","status":"PENDING","pending":true,"data":{"current_field":"name"}}""")
        }
        if (jarvisAsksGoalName && text == "fondo de emergencia") {
            jarvisClarifying = true
            return ok("""{"message":"Tenés una pregunta pendiente: ¿Cómo se llama la meta? ¿\"Fondo de emergencia\" es la respuesta o querés hacer otra consulta?","intent":"pending_action","action_type":"create_goal","status":"PENDING","pending":true,"data":{"current_field":"clarify","held_message":"Fondo de emergencia"}}""")
        }
        if ("respuesta rara" in text) return ok("""{"unexpected":true}""")
        jarvisPendingEvent?.takeIf { text in setOf("sí", "si", "no") }?.let { event ->
            jarvisPendingEvent = null
            if (text == "no") return ok("""{"message":"Listo, cancelé el registro. No guardé nada.","intent":"pending_action","status":"CANCELLED","pending":false}""")
            jarvisEvents += event
            return ok(buildJsonObject {
                put("message", "Señor, listo. Guardé en calendario: ${event.title} · ${event.eventDate}.")
                put("intent", "pending_action"); put("action_type", "create_calendar_event"); put("status", "OK"); put("pending", false)
            }.toString())
        }
        if ("dentista" in text) {
            // Like the engine: the chat shows the event first; it reaches the agenda only on "sí".
            val event = JarvisEvent(jarvisEvents.size + 100L, "dentista", "${today.plusDays(10)} 15:00", "personal", message)
            jarvisPendingEvent = event
            return ok(buildJsonObject {
                put("message", "Voy a guardar este evento:\n- título: dentista\n- fecha y hora: ${event.eventDate}\n¿Confirmo y guardo? Responde sí o no.")
                put("intent", "create_calendar_event"); put("action_type", "create_calendar_event"); put("status", "PENDING"); put("pending", true)
                put("data", buildJsonObject { put("current_field", "confirm") })
            }.toString())
        }
        if (jarvisPending && text in setOf("sí", "si", "no")) {
            jarvisPending = false
            return if (text == "no") ok("""{"message":"Listo, cancelé el registro. No guardé nada.","intent":"pending_action","status":"CANCELLED","pending":false}""")
            else ok("""{"message":"Señor, OT registrado: 3.0 horas. Ingreso proyectado actualizado: ₡900.000. Sobrante proyectado: ₡120.000.","intent":"pending_action","action_type":"create_payroll_event","status":"OK","pending":false}""")
        }
        if ("horas" in text && ("extra" in text || " ot" in text)) {
            jarvisPending = true
            return ok("""{"message":"Voy a guardar esta evento de planilla:\n- tipo de evento: ot\n- horas: 3.0\n- monto: ₡9,000.00\n¿Confirmo y guardo? Responde sí o no.","intent":"create_payroll_event","action_type":"create_payroll_event","status":"PENDING","pending":true,"data":{"current_field":"confirm","payload":{"event_type":"ot","hours":3.0}}}""")
        }
        return ok("""{"message":"Señor, esto es una respuesta de ejemplo.","intent":"general","status":"UNSUPPORTED","pending":false,"data":null}""")
    }

    private fun ok(value: String) = HttpResponse(200, value)
    private inline fun <reified T> ok(value: T) = HttpResponse(200, json.encodeToString(value))
    private fun error(status: Int, detail: String) = HttpResponse(status, buildJsonObject { put("detail", detail) }.toString())
    private fun id() = ++nextId
    private fun needs(tier: PlanTier): HttpResponse? = if (profile.planTier.rank < tier.rank) error(403, "Esta función no está incluida en tu plan.") else null

    @Suppress("CyclomaticComplexMethod")
    private fun route(method: String, path: String, query: Map<String, String>, body: JsonObject?): HttpResponse {
        val segments = path.trim('/').split('/')
        fun money(key: String) = body?.get(key)?.jsonPrimitive?.content?.takeIf { it != "null" }?.let(::BigDecimal)
        fun text(key: String) = body?.get(key)?.jsonPrimitive?.content?.takeIf { it != "null" }
        fun int(key: String) = text(key)?.toIntOrNull()
        val idAt = { index: Int -> segments.getOrNull(index)?.toLongOrNull() ?: -1L }
        return when {
            // Identity
            path == "/auth/me" && method == "GET" -> ok(profile)
            path == "/auth/me" && method == "DELETE" -> ok("""{"status":"OK","message":"Cuenta eliminada","deletion_id":"del_demo"}""")
            // JARVIS chat: /jarvis/* admits only the verified Owner, like the backend.
            path == "/jarvis/chat" && method == "POST" -> jarvisChat(text("message").orEmpty())
            path == "/jarvis/calendar/upcoming" && method == "GET" ->
                if (profile.role != "owner") error(403, "No tienes permisos para realizar esta acción.") else ok(agendaBody())
            // The Owner's strategy: this fake serves it to the Owner role only.
            path == "/jarvis/premium/strategy-dashboard" && method == "GET" ->
                if (!isOwner) error(403, "No tienes permisos para realizar esta acción.") else ok(planRoutes.strategyDashboard(snapshot(), owner = true, role = profile.role))
            // JARVIS "Análisis financiero": the internal routers admit only the verified Owner (main.py INTERNAL_ONLY).
            path == "/transactions/analysis/summary" || path == "/finance/net-worth" || path == "/finance/engine" -> when {
                !isInternal -> error(403, "No tienes permisos para realizar esta acción.")
                path == "/finance/net-worth" -> ok(planRoutes.netWorth(snapshot()))
                path == "/finance/engine" -> ok(planRoutes.engine(snapshot()))
                else -> ok(planRoutes.analysis(snapshot()))
            }
            path == "/auth/me/export" -> ok("""{"format_version":1,"generated_at":"${today}T12:00:00Z","account":{"id":1},"workspaces":[],"data":{},"truncated_tables":[],"notes":[]}""")
            path == "/auth/profile-setup" -> {
                profile = profile.copy(displayName = text("display_name"), profileSetupCompleted = true, baseCurrency = text("base_currency") ?: "CRC",
                    numberFormat = text("number_format"), currencyPlacement = text("currency_placement"))
                ok(buildJsonObject { put("status", "ok"); put("profile", json.encodeToJsonElement(Profile.serializer(), profile)) }.toString())
            }
            path == "/auth/legal/accept" -> {
                profile = profile.copy(legal = profile.legal?.copy(required = false))
                ok("""{"status":"accepted","required":false,"terms_version":"2026-09-23-v3","privacy_version":"2026-09-25-v4"}""")
            }
            path == "/auth/plans" -> ok(PLANS)
            path == "/auth/plan" -> {
                val plan = text("plan") ?: "free"
                profile = profile.copy(planSelected = true, subscription = profile.subscription?.copy(plan = plan, accessSource = if (plan == "free") "self_service" else "courtesy"))
                ok(buildJsonObject {
                    put("status", if (plan == "free") "ok" else "promotion_active")
                    put("profile", json.encodeToJsonElement(Profile.serializer(), profile))
                }.toString())
            }
            path == "/product-ops/billing/catalog" -> ok("""{"plans":[{"code":"basic","regular_price_crc":2990},{"code":"vip","regular_price_crc":4990}],"promotion":$PROMOTION,"notice":"Basic y VIP gratis hasta el 31 de diciembre de 2026."}""")
            path == "/product-ops/feature-flags" -> ok(FLAGS)
            path == "/product-ops/health" -> ok("""{"status":"operational","active_incidents":0}""")
            path == "/product-ops/release-policy" -> ok("""{"platform":"android","current_version":"${query["version"]}","status":"current","required":false,"active":false}""")
            path == "/product-ops/events" -> ok("""{"status":"recorded"}""")
            path == "/product-ops/incidents" -> ok("""{"status":"recorded"}""")
            path == "/product-ops/feedback" && method == "GET" -> ok(tickets.toList())
            path == "/product-ops/feedback" && method == "POST" -> {
                val ticket = SupportTicket(id(), text("category"), text("subject"), "open", null, "${today}T12:00:00Z", "DINCR-%06d".format(nextId))
                tickets.add(0, ticket)
                ok("""{"id":${ticket.id},"public_id":"${ticket.publicId}","email_sent":true}""")
            }
            segments.take(2) == listOf("product-ops", "feedback") && segments.getOrNull(3) == "resolution" -> {
                val index = tickets.indexOfFirst { it.id == idAt(2) }
                if (index < 0) error(404, "No encontrado") else { tickets[index] = tickets[index].copy(userResolution = text("resolution")); ok("""{"status":"ok"}""") }
            }
            path.startsWith("/product-ops/billing/store") -> HttpResponse(503, """{"detail":"Las compras en la tienda están en pausa.","code":"feature_temporarily_unavailable","feature":"store_billing"}""")

            // Movements
            path == "/user-product/free/dashboard" -> ok(freeDashboard())
            path == "/user-product/free/monthly-summary" -> ok(monthlySummary(query["period"] ?: today.toString().take(7)))
            path == "/user-product/free/movements" -> ok(movements.sortedWith(compareByDescending<Movement> { it.transactionDate }.thenByDescending { it.sourceId }))
            (path == "/user-product/finance/income" || path == "/user-product/finance/expenses") && method == "POST" -> {
                val income = path.endsWith("income")
                val typed = money("amount") ?: return error(422, "Monto inválido")
                val currency = text("currency")
                val rate = money("exchange_rate")
                val base = profile.baseCurrency ?: "CRC"
                if (currency != null && currency != base && rate == null) return error(422, "Indicá el tipo de cambio (colones por 1 dólar) para registrar un monto en otra moneda.")
                val converted = if (currency == null || currency == base) typed else convert(typed, currency, base, rate!!)
                val origin = if (income) "salary" else "expense"
                val sid = id()
                movements += Movement("$origin:$sid", sid, origin, text("entry_date") ?: today.toString(), text("description"), converted,
                    if (income) "income" else "expense", text("category"), "", true,
                    if (currency != null && currency != base) typed else null, if (currency != null && currency != base) currency else null, if (currency != null && currency != base) rate else null)
                ok("""{"id":$sid}""")
            }
            segments.take(3) == listOf("user-product", "free", "movements") && segments.size == 4 -> {
                val movementId = java.net.URLDecoder.decode(segments[3], "UTF-8")
                val index = movements.indexOfFirst { it.movementId == movementId }
                if (index < 0 || !movements[index].editable) return error(404, "Movimiento no encontrado o no editable.")
                if (method == "DELETE") { movements.removeAt(index); return ok("""{"status":"ok","movement_id":"$movementId"}""") }
                val old = movements[index]
                val typed = money("amount") ?: return error(422, "Monto inválido")
                val currency = text("currency")
                val rate = money("exchange_rate")
                val base = profile.baseCurrency ?: "CRC"
                val foreign = currency != null && currency != base
                if (foreign && old.origin !in setOf("salary", "expense")) return error(422, "Este movimiento solo se puede registrar en tu moneda principal.")
                if (foreign && rate == null) return error(422, "Indicá el tipo de cambio.")
                movements[index] = old.copy(transactionDate = text("transaction_date"), description = text("description"), category = text("category"),
                    amount = if (foreign) convert(typed, currency!!, base, rate!!) else typed,
                    originalAmount = if (foreign) typed else null, originalCurrency = if (foreign) currency else null, exchangeRate = if (foreign) rate else null)
                ok("""{"status":"ok","movement_id":"$movementId"}""")
            }

            // Debts
            path == "/user-product/finance/debts" && method == "GET" -> ok(debts.map { it.copy(progressPercent = progress(it)) })
            path == "/user-product/finance/debts" && method == "POST" -> {
                val debt = Debt(id(), text("name"), text("debt_type") ?: "other", money("total_amount") ?: money("remaining_amount"), money("remaining_amount"),
                    money("monthly_payment"), money("interest_rate"), int("term_months"), int("payment_day"), text("next_payment_date"))
                debts += debt; ok(debt)
            }
            segments.take(3) == listOf("user-product", "finance", "debts") && segments.size == 4 -> {
                needs(if (method == "PUT") PlanTier.BASIC else PlanTier.FREE)?.let { return it }
                val index = debts.indexOfFirst { it.id == idAt(3) }
                if (index < 0) return error(404, "Deuda no encontrada.")
                if (method == "DELETE") { debts.removeAt(index); return ok("""{"status":"ok","id":${idAt(3)}}""") }
                debts[index] = debts[index].copy(name = text("name"), debtType = text("debt_type"), totalAmount = money("total_amount"), remainingAmount = money("remaining_amount"),
                    monthlyPayment = money("monthly_payment"), interestRate = money("interest_rate"), termMonths = int("term_months"), paymentDay = int("payment_day"), nextPaymentDate = text("next_payment_date"))
                ok(debts[index])
            }
            segments.take(3) == listOf("user-product", "finance", "debts") && segments.getOrNull(4) == "payments" -> {
                val index = debts.indexOfFirst { it.id == idAt(3) }
                if (index < 0) return error(404, "Deuda no encontrada.")
                val remaining = debts[index].remainingAmount ?: BigDecimal.ZERO
                val paid = (money("amount") ?: BigDecimal.ZERO).min(remaining)
                debts[index] = debts[index].copy(remainingAmount = remaining - paid)
                ok("""{"status":"OK","debt_id":${debts[index].id},"payment_amount":$paid,"new_remaining_amount":${remaining - paid}}""")
            }

            // Goals and savings plans
            path == "/user-product/goals" && method == "GET" -> ok(goals.toList())
            path == "/user-product/goals" && method == "POST" -> {
                val goal = Goal(id(), text("name"), money("target_amount"), money("current_amount") ?: BigDecimal.ZERO, text("target_date"), text("priority") ?: "medium", "active")
                goals += goal; ok(goal)
            }
            segments.take(2) == listOf("user-product", "goals") && segments.size == 3 -> {
                needs(if (method == "PUT") PlanTier.BASIC else PlanTier.FREE)?.let { return it }
                val index = goals.indexOfFirst { it.id == idAt(2) }
                if (index < 0) return error(404, "Meta no encontrada.")
                if (method == "DELETE") { goals.removeAt(index); return ok("""{"status":"ok","id":${idAt(2)}}""") }
                val target = money("target_amount")
                goals[index] = goals[index].copy(name = text("name"), targetAmount = target, currentAmount = money("current_amount")?.let { c -> target?.let { c.min(it) } ?: c },
                    targetDate = text("target_date"), priority = text("priority"), status = text("status") ?: goals[index].status)
                ok(goals[index])
            }
            segments.take(2) == listOf("user-product", "goals") && segments.getOrNull(3) == "contributions" -> {
                val index = goals.indexOfFirst { it.id == idAt(2) }
                if (index < 0) return error(404, "Meta no encontrada.")
                val goal = goals[index]
                val target = goal.targetAmount ?: BigDecimal.ZERO
                val current = goal.currentAmount ?: BigDecimal.ZERO
                if (current >= target) return error(409, "La meta ya está completa.")
                val next = (current + (money("amount") ?: BigDecimal.ZERO)).min(target)
                goals[index] = goal.copy(currentAmount = next, status = if (next >= target) "completed" else goal.status)
                ok(goals[index])
            }
            path == "/user-product/savings-plans" && method == "GET" -> ok(savings.toList())
            path == "/user-product/savings-plans" && method == "POST" -> {
                val plan = SavingsPlan(id(), text("name"), money("monthly_amount"), money("saved_amount") ?: BigDecimal.ZERO, text("start_date"), text("end_date"), "active")
                savings += plan; ok(plan)
            }
            segments.take(2) == listOf("user-product", "savings-plans") && segments.size == 3 -> {
                val index = savings.indexOfFirst { it.id == idAt(2) }
                if (index < 0) return error(404, "Plan no encontrado.")
                if (method == "DELETE") { savings.removeAt(index); return ok("""{"status":"ok","id":${idAt(2)}}""") }
                savings[index] = savings[index].copy(name = text("name"), monthlyAmount = money("monthly_amount"), savedAmount = money("saved_amount"),
                    startDate = text("start_date"), endDate = text("end_date"), status = text("status") ?: savings[index].status)
                ok(savings[index])
            }
            segments.take(2) == listOf("user-product", "savings-plans") && segments.getOrNull(3) == "contributions" -> {
                val index = savings.indexOfFirst { it.id == idAt(2) }
                if (index < 0) return error(404, "Plan no encontrado.")
                savings[index] = savings[index].copy(savedAmount = (savings[index].savedAmount ?: BigDecimal.ZERO) + (money("amount") ?: BigDecimal.ZERO))
                ok(savings[index])
            }

            // Situation
            path == "/user-product/financial-situation" && method == "PUT" -> {
                // Like FinancialSituationRequest: work_days_per_week is required (1–7) for every income type.
                if (int("work_days_per_week")?.takeIf { it in 1..7 } == null) return error(422, "work_days_per_week: Field required")
                situation = json.decodeFromString(FinancialProfile.serializer(), body.toString()); ok(financialSituation())
            }
            path == "/user-product/financial-situation" -> ok(financialSituation())

            // Basic
            path.startsWith("/user-product/basic") || path.startsWith("/user-product/finance/strategy-basic") -> needs(PlanTier.BASIC) ?: basic(method, path, segments, query, body)

            // VIP
            path.startsWith("/user-product/vip/gmail") || path.startsWith("/user-product/vip/mail") || path.startsWith("/user-product/vip/financial-identity") ->
                needs(PlanTier.VIP) ?: mail(method, path, segments, query, body)
            path == "/user-product/vip/salvavidas" -> needs(PlanTier.VIP) ?: salvavidas(method, body)
            path.startsWith("/user-product/vip") || path.startsWith("/user-product/finance/strategy-vip") -> needs(PlanTier.VIP) ?: vip(path)
            else -> error(404, "Not Found")
        }
    }

    private fun basic(method: String, path: String, segments: List<String>, query: Map<String, String>, body: JsonObject?): HttpResponse {
        fun money(key: String) = body?.get(key)?.jsonPrimitive?.content?.takeIf { it != "null" }?.let(::BigDecimal)
        fun text(key: String) = body?.get(key)?.jsonPrimitive?.content?.takeIf { it != "null" }
        return when {
            path == "/user-product/basic/dashboard" -> {
                val totals = totals(today.toString().take(7))
                ok(BasicDashboard(today.toString().take(7), totals.first, totals.second, BigDecimal.ZERO, totals.first - totals.second,
                    BasicDashboard.DebtProgress(debts.sumOf { it.totalAmount ?: BigDecimal.ZERO }, debts.sumOf { it.remainingAmount ?: BigDecimal.ZERO }, debts.sumOf { it.monthlyPayment ?: BigDecimal.ZERO }, 35.0),
                    savings.sumOf { it.savedAmount ?: BigDecimal.ZERO }, GoalProgress(goals.sumOf { it.currentAmount ?: BigDecimal.ZERO }, goals.sumOf { it.targetAmount ?: BigDecimal.ZERO }, 40.0, goals.size),
                    monthlyHistory = freeDashboard().monthlyHistory))
            }
            path == "/user-product/basic/budget" && method == "PUT" -> {
                val items = body?.get("items")?.let { json.decodeFromJsonElement(kotlinx.serialization.builtins.ListSerializer(BudgetLimit.serializer()), it) }.orEmpty()
                if (items.map { it.category.lowercase() }.toSet().size != items.size) return error(422, "Categorías repetidas.")
                budget = items.map { BudgetItem(it.category, it.monthlyLimit) }
                ok(budgetView())
            }
            // STORE: the backend's guided budget for the sample, until the limits are edited.
            path == "/user-product/basic/budget" -> if (store != null && budget == store.budget()) ok(store.engine("budget")) else ok(budgetView())
            path == "/user-product/basic/calendar" -> ok(FinancialCalendar(query["period"], recurring.filter { it.isActive == true }.map {
                FinancialCalendar.Event("${query["period"] ?: today.toString().take(7)}-%02d".format((it.dueDay ?: 1).coerceIn(1, 28)), it.itemType, it.name, it.amount, "recurring")
            } + debts.mapNotNull { d -> d.paymentDay?.let { FinancialCalendar.Event("${query["period"] ?: today.toString().take(7)}-%02d".format(it.coerceIn(1, 28)), "debt", d.name, d.monthlyPayment, "debt") } },
                FinancialCalendar.Summary(1, recurring.filter { it.itemType == "expense" }.sumOf { it.amount ?: BigDecimal.ZERO }, recurring.size + debts.size)))
            path == "/user-product/basic/recurring" && method == "GET" -> ok(RecurringList(recurring.toList(), recurring.filter { it.itemType == "expense" && it.isActive == true }.sumOf { it.amount ?: BigDecimal.ZERO }))
            path == "/user-product/basic/recurring" && method == "POST" -> {
                val item = RecurringItem(id(), text("name"), money("amount"), text("category"), text("item_type"), text("frequency"), text("due_day")?.toIntOrNull(), text("is_active")?.toBoolean() ?: true)
                recurring += item; ok(item)
            }
            segments.take(3) == listOf("user-product", "basic", "recurring") && segments.size == 4 -> {
                val index = recurring.indexOfFirst { it.id == segments[3].toLongOrNull() }
                if (index < 0) return error(404, "No encontrado.")
                if (method == "DELETE") { recurring.removeAt(index); return ok("""{"status":"ok"}""") }
                recurring[index] = recurring[index].copy(name = text("name"), amount = money("amount"), category = text("category"), itemType = text("item_type"),
                    frequency = text("frequency"), dueDay = text("due_day")?.toIntOrNull(), isActive = text("is_active")?.toBoolean())
                ok(recurring[index])
            }
            path == "/user-product/basic/reports" -> {
                val period = query["period"] ?: today.toString().take(7)
                val (income, expenses) = totals(period)
                ok(MonthReport(period, income, expenses, BigDecimal.ZERO, BigDecimal.ZERO, income - expenses, income - expenses, categories(period), MonthReport.Comparison(income, expenses, BigDecimal.ZERO)))
            }
            path == "/user-product/finance/strategy-basic" -> store?.let { ok(it.engine("strategy_basic")) } ?: ok(strategy())
            else -> error(404, "Not Found")
        }
    }

    /** GET, or PUT with only the fields to change (users vs owner by the server role, like the backend). */
    private fun salvavidas(method: String, body: JsonObject?): HttpResponse {
        if (method != "PUT") return ok(planRoutes.salvavidas(snapshot(), isOwner))
        fun field(key: String) = body?.get(key)?.takeIf { it !is kotlinx.serialization.json.JsonNull }
        val ids = field("protected_expense_ids")?.let { (it as? kotlinx.serialization.json.JsonArray)?.mapNotNull { id -> id.jsonPrimitive.content.toLongOrNull() } }
        val (status, answer, updated) = planRoutes.updateSalvavidas(snapshot(), isOwner, field("target_months")?.jsonPrimitive?.content?.toIntOrNull(),
            field("current_amount")?.jsonPrimitive?.content?.let(::BigDecimal), ids)
        if (status != 200) return error(status, answer)
        updated?.let { situation = it }
        return ok(answer)
    }

    private fun vip(path: String): HttpResponse = when (path) {
        "/user-product/vip/strategy-dashboard" -> ok(planRoutes.strategyDashboard(snapshot(), owner = isOwner, role = profile.role))
        "/user-product/vip/command-center" -> store?.let { ok(it.engine("command_center")) } ?: ok(CommandCenter(
            today.toString(),
            CommandCenter.Director("debt", "Tu prioridad es bajar la tarjeta", "Pagá ₡40.000 extra a la tarjeta este mes", true),
            CommandCenter.Score(72, "Estable", listOf(CommandCenter.Factor("Ahorro de emergencia", "warning"))),
            CommandCenter.DebtPlanner(CommandCenter.Plan("finva", "Tarjeta de ejemplo", BigDecimal(95000), 14, BigDecimal(84000))),
            CommandCenter.SafeToSpend(BigDecimal(118000), BigDecimal(214000), BigDecimal(96000)),
            // More than Hoy's three (UX-5), including the backend's own pending-review alert.
            listOf(CommandCenter.Alert("medium", "Pago de tarjeta en 5 días", "El pago mínimo vence pronto.", "Revisá la deuda"),
                CommandCenter.Alert("high", "Reserva menor a un mes", "La cobertura estimada es 0.7 meses.", "Protegé el siguiente excedente en el fondo de emergencia."),
                CommandCenter.Alert("medium", "Recurrente con variación", "Servicio de ejemplo cambió más de 10% entre cobros.", "Confirmá si fue un aumento, consumo variable o cargo incorrecto.")) +
                candidates.count { it.isPending }.let { pending ->
                    if (pending > 0) listOf(CommandCenter.Alert("medium", "Movimientos por revisar", "Hay $pending movimientos importados sin confirmar.", "Revisalos antes de confiar en el cierre mensual.")) else emptyList()
                },
            listOf(1, 3, 6).map { CommandCenter.ProjectionPoint(it, BigDecimal(200000 * it), BigDecimal(900000 - 90000 * it), BigDecimal(-700000 + 290000 * it), "medium") },
            listOf(CommandCenter.RoadmapStep(1, "Completá tu fondo de emergencia inicial", BigDecimal(50000), "Te protege de imprevistos."),
                CommandCenter.RoadmapStep(2, "Pagá extra a la tarjeta", BigDecimal(40000), "Tiene la tasa más alta.")),
            automation = CommandCenter.Automation(4, candidates.count { it.isPending }, 0),
            reports = today.toString().take(7).let { month -> totals(month).let { (income, expenses) ->
                CommandCenter.Reports(MonthTotals(month, income, expenses, BigDecimal.ZERO, income - expenses)) } },
        ))
        "/user-product/finance/strategy-vip" -> store?.let { ok(it.engine("strategy_vip")) } ?: ok(strategy().copy(directorNote = "Priorizamos la deuda con tasa más alta."))
        "/user-product/finance/strategy-vip/simulate" -> ok(ScenarioResult(strategy(), strategy().copy(strategicMargin = BigDecimal(260000)), ScenarioResult.Delta(BigDecimal(46000), BigDecimal(50000), BigDecimal(4000))))
        "/user-product/vip/aguinaldo" -> if (!mailConnected) error(409, "Conectá tu correo para calcular el aguinaldo.") else ok(Aguinaldo("OK", Aguinaldo.Period("${today.year - 1}-12-01", "${today.year}-11-30"), BigDecimal(5_190_000), BigDecimal(432_500)))
        "/user-product/vip/lifecycle/monthly-review" -> ok(MonthlyReview("BASELINE", today.toString().take(7), "Tu primer mes con DINCR", "Todavía no hay suficiente historia para comparar."))
        "/user-product/vip/lifecycle/proactive-advisor" -> ok(ProactiveAdvisor("BASELINE", today.toString(), emptyList(), "DINCR necesita unos días de historia para avisarte de cambios."))
        else -> error(404, "Not Found")
    }

    private fun mail(method: String, path: String, segments: List<String>, query: Map<String, String>, body: JsonObject?): HttpResponse {
        fun text(key: String) = body?.get(key)?.jsonPrimitive?.content?.takeIf { it != "null" }
        return when {
            path == "/user-product/vip/gmail/status" -> ok(MailStatus(mailConnected, false, candidates.count { it.isPending }, true,
                MailStatus.Consent(required = !mailConnected, version = "mail-monitor-2026-09-v2"),
                // Like the server, the status also lists a mailbox the user disconnected earlier (hidden by the app).
                if (mailConnected) listOf(MailStatus.Connection(1, "gmail", if (store != null) profile.email else "ejemplo@correo.test", "active", true, "${today.year}-01-01"),
                    MailStatus.Connection(2, "gmail", "anterior@correo.test", "disabled", false, "${today.year}-01-01")) else emptyList()))
            path == "/user-product/vip/gmail/consent" -> ok("""{"status":"accepted"}""")
            path == "/user-product/vip/gmail/connect" || path == "/user-product/vip/mail/microsoft/connect" -> ok("""{"authorization_url":"https://accounts.example.test/authorize?state=demo"}""")
            path == "/user-product/vip/mail/oauth/complete" -> { mailConnected = true; ok("""{"status":"connected","provider":"gmail"}""") }
            path == "/user-product/vip/gmail/sync" -> if (!mailConnected) error(404, "No hay un correo conectado.") else ok(
                """{"status":"ok","connections":1,"failed_connections":[],"scan_scope":"year_to_date","initial_scan_complete":true,""" +
                    """"found":3,"auto_saved":1,"pending":${candidates.count { it.isPending }},"payroll_reports":0,"duplicates":0}""")
            path == "/user-product/vip/gmail" && method == "DELETE" -> { mailConnected = false; ok("""{"status":"disconnected"}""") }
            // One candidate store for Email Monitor and Cuentas; the same filters as list_gmail_emails.
            path == "/user-product/vip/gmail/emails" -> ok(MailCandidateList("ok", candidates.filter { c ->
                query["status"].isNullOrEmpty() || c.reviewStatus == query["status"]
            }.filter { c -> query["bank"].isNullOrBlank() || c.bank.orEmpty().equals(query["bank"]!!.trim(), ignoreCase = true) }
                .filter { c -> query["financial_account_id"]?.toLongOrNull()?.let { c.financialAccountId == it } ?: true }))
            path == "/user-product/vip/gmail/own-transfer-suggestions" -> ok(OwnTransferSuggestions())
            path == "/user-product/vip/financial-identity" -> ok(FinancialIdentity(accounts.toList(), FinancialIdentity.Summary(accounts.size, accounts.count { it.ownershipStatus == "pending" })))
            segments.take(4) == listOf("user-product", "vip", "financial-identity", "accounts") -> {
                val index = accounts.indexOfFirst { it.id == segments.getOrNull(4)?.toLongOrNull() }
                val status = text("ownership_status")
                if (index < 0) return error(404, "Cuenta financiera no encontrada.")
                if (status !in setOf("own", "not_mine")) return error(422, "La propiedad debe confirmarse como propia o ajena.")
                accounts[index] = accounts[index].copy(ownershipStatus = status)
                ok("""{"status":"ok"}""")
            }
            segments.take(4) == listOf("user-product", "vip", "gmail", "candidates") -> {
                val id = segments.getOrNull(4)?.toLongOrNull()
                val index = candidates.indexOfFirst { it.candidateId == id }
                if (index < 0) return error(404, "No encontrado.")
                val candidate = candidates[index]
                if (!candidate.isPending) return ok(CandidateReviewResult(candidate.reviewStatus, id, null, alreadyReviewed = true))
                val action = segments.getOrNull(5)
                when {
                    action == "reject" -> { candidates[index] = candidate.copy(reviewStatus = "rejected"); ok(CandidateReviewResult("rejected", id)) }
                    action == "accept" && method == "POST" && candidate.needsRate -> error(422, "Este aviso está en otra moneda. Tocá Corregir e indicá el tipo de cambio.")
                    action == "accept" -> {
                        if (method == "PUT" && candidate.needsRate && text("exchange_rate") == null) return error(422, "Indicá el tipo de cambio.")
                        candidates[index] = candidate.copy(reviewStatus = "confirmed")
                        // Accepting records one movement; a second accept answers already_reviewed above.
                        val sid = id()
                        movements += Movement("transaction:$sid", sid, "transaction", candidate.transactionDate ?: today.toString(), candidate.description,
                            candidate.amount ?: BigDecimal.ZERO, candidate.transactionType ?: "expense", candidate.category, "", false)
                        ok(CandidateReviewResult("confirmed", id, sid))
                    }
                    else -> error(404, "Not Found")
                }
            }
            else -> error(404, "Not Found")
        }
    }

    // --- read models ----------------------------------------------------------------------------------

    private fun totals(period: String): Pair<BigDecimal, BigDecimal> {
        val rows = movements.filter { it.transactionDate?.startsWith(period) == true }
        return rows.filter { it.kind == MovementKind.INCOME }.sumOf { it.amount } to rows.filter { it.kind == MovementKind.EXPENSE }.sumOf { it.amount }
    }

    private fun categories(period: String) = movements.filter { it.kind == MovementKind.EXPENSE && it.transactionDate?.startsWith(period) == true }
        .groupBy { it.category ?: "Sin categoría" }.map { (category, rows) -> CategoryTotal(category, rows.sumOf { it.amount }) }.sortedByDescending { it.amount }

    private fun freeDashboard(): FreeDashboard {
        val month = today.toString().take(7)
        val (income, expenses) = totals(month)
        val history = (5 downTo 0).map { back ->
            val period = today.minusMonths(back.toLong()).toString().take(7)
            val (i, e) = totals(period)
            MonthTotals(period, i, e, BigDecimal.ZERO, i - e)
        }
        return FreeDashboard(month, income, expenses, BigDecimal.ZERO, debts.sumOf { it.remainingAmount ?: BigDecimal.ZERO }, income - expenses, income - expenses,
            categories(month).map { CategoryAmount(it.category ?: "", it.amount ?: BigDecimal.ZERO) }, history)
    }

    private fun monthlySummary(period: String): MonthlySummary {
        val (income, expenses) = totals(period)
        val cats = categories(period)
        return MonthlySummary(period, income, expenses, BigDecimal.ZERO, income - expenses, cats.firstOrNull(), cats, savings.sumOf { it.savedAmount ?: BigDecimal.ZERO },
            GoalProgress(goals.sumOf { it.currentAmount ?: BigDecimal.ZERO }, goals.sumOf { it.targetAmount ?: BigDecimal.ZERO }, 40.0))
    }

    private fun budgetView(): Budget {
        val month = today.toString().take(7)
        val spent = categories(month).associate { (it.category ?: "").lowercase() to (it.amount ?: BigDecimal.ZERO) }
        val items = budget.map { it.copy(spent = spent[it.category.lowercase()] ?: BigDecimal.ZERO) }
        // As the backend: the user's own items are never a proposal.
        return Budget(items, items.sumOf { it.monthlyLimit ?: BigDecimal.ZERO }, BigDecimal(420000), month, isProposal = budget.isEmpty())
    }

    private fun financialSituation() = FinancialSituation(situation, FinancialSituation.Observed(90, 3, BigDecimal(865000), 12),
        FinancialSituation.DebtSummary(debts.size, debts.sumOf { it.remainingAmount ?: BigDecimal.ZERO }, debts.count { it.interestRate == null }),
        FinancialSituation.GoalSummary(goals.size, goals.sumOf { it.currentAmount ?: BigDecimal.ZERO }))

    /** Like `get_strategy_basic`: the declared income first, else the observed one (said so), else needs_income. */
    private fun strategy(): Strategy {
        val (source, _) = planRoutes.basicIncome(snapshot())
        val basis = Strategy.IncomeBasis(source, if (source == "declared") null else "income-policy-v1", if (source == "observed") "transactions" else null)
        if (source == "none") return Strategy("needs_income", recommendation = "Registrá tus ingresos o completá tu situación financiera para armar tu estrategia.",
            incomeSource = source, incomeBasis = basis)
        return Strategy(
            "tight", "debt", BigDecimal(865000), BigDecimal(420000), BigDecimal(95000), BigDecimal(214000),
            listOf(Strategy.Allocation("emergency", "Fondo de emergencia", BigDecimal(60000)), Strategy.Allocation("debt_extra", "Extra a la tarjeta", BigDecimal(100000), 1), Strategy.Allocation("flex", "Libre", BigDecimal(54000))),
            recommendation = "Destiná ₡100.000 extra a la tarjeta y ₡60.000 a tu fondo de emergencia.",
            projection = Strategy.Projection("Tarjeta de ejemplo", 14, 31, BigDecimal(195000)),
            incomeSource = source, incomeBasis = basis,
        )
    }

    private fun progress(debt: Debt): Double {
        val total = debt.totalAmount ?: return 0.0
        if (total.signum() <= 0) return 0.0
        return BigDecimal.ONE.subtract((debt.remainingAmount ?: total).divide(total, 6, RoundingMode.HALF_UP)).multiply(BigDecimal(100)).setScale(1, RoundingMode.HALF_UP).toDouble()
    }

    private fun convert(amount: BigDecimal, currency: String, base: String, rate: BigDecimal): BigDecimal =
        (if (currency == "USD" && base == "CRC") amount * rate else amount.divide(rate, 10, RoundingMode.HALF_UP)).setScale(2, RoundingMode.HALF_UP)

    private fun seed() {
        fun day(offset: Long) = today.minusDays(offset).toString()
        movements += listOf(
            Movement("salary:8", 8, "salary", day(3), "Salario quincenal", BigDecimal(432500), "income", "Salario", "", true),
            Movement("salary:4", 4, "salary", day(18), "Salario quincenal", BigDecimal(432500), "income", "Salario", "", true),
            Movement("expense:11", 11, "expense", day(0), "Supermercado", BigDecimal(18450), "expense", "Comida", "", true),
            Movement("expense:10", 10, "expense", day(0), "Café", BigDecimal(2300), "expense", "Restaurante", "", true),
            Movement("expense:12", 12, "expense", day(1), "Feria del agricultor", BigDecimal("12345.5"), "expense", "Feria", "", true),
            Movement("transaction:9", 9, "transaction", day(1), "Aviso bancario · Gasolinera", BigDecimal(25000), "expense", "Gasolina", "", false),
            Movement("expense:13", 13, "expense", day(2), "Suscripción en dólares", BigDecimal("5075.00"), "expense", "Entretenimiento", "", true, BigDecimal(10), "USD", BigDecimal("507.5")),
            Movement("expense:7", 7, "expense", day(4), "Internet del hogar", BigDecimal(24900), "expense", "Internet", "", true),
            Movement("expense:6", 6, "expense", day(6), "Farmacia", BigDecimal(9800), "expense", "Salud", "", true),
            Movement("expense:5", 5, "expense", day(9), "Alquiler", BigDecimal(210000), "expense", "Vivienda", "", true),
        )
        debts += Debt(1, "Tarjeta de ejemplo", "credit_card", BigDecimal(900000), BigDecimal(585000), BigDecimal(45000), BigDecimal("36.0"), null, 15, today.plusDays(5).toString())
        debts += Debt(2, "Préstamo de ejemplo", "loan", BigDecimal(2400000), BigDecimal(1560000), BigDecimal(50000), BigDecimal("14.5"), 48, 1, null)
        goals += Goal(3, "Fondo de emergencia", BigDecimal(600000), BigDecimal(240000), today.plusMonths(8).toString(), "high", "active")
        savings += SavingsPlan(4, "Vacaciones", BigDecimal(25000), BigDecimal(75000), today.minusMonths(3).withDayOfMonth(1).toString(), today.plusMonths(9).withDayOfMonth(1).toString(), "active")
        recurring += RecurringItem(5, "Internet", BigDecimal(24900), "Internet", "expense", "monthly", 4, true)
        // Like the backend: a candidate's `bank` is the institution CODE; detected accounts carry the
        // label (`bank_name`) plus `institution_code`. Notices of a known bank with an account, of a
        // bank whose label differs from its code (Banco Popular / popular), of a known bank without
        // a detected account, and of an institution DINCR does not identify.
        candidates += MailCandidate(21, 21, null, "bac", "avisos@banco.test", "Notificación de compra", "${day(1)}T10:00:00Z", "Compra en supermercado", BigDecimal(15300), "CRC",
            accountBaseCurrency = "CRC", transactionDate = day(1), transactionType = "expense", category = "Comida", reviewStatus = "pending",
            financialAccountId = 1, bankMovement = "purchase", financialEffect = "expense")
        candidates += MailCandidate(22, 22, null, "bac", "avisos@banco.test", "Compra internacional", "${day(2)}T10:00:00Z", "Tienda en línea", BigDecimal(25), "USD",
            accountBaseCurrency = "CRC", transactionDate = day(2), transactionType = "expense", category = "Compras", reviewStatus = "pending",
            financialAccountId = 1, bankMovement = "purchase", financialEffect = "expense")
        candidates += MailCandidate(23, 23, null, "popular", "avisos@banco.test", "Transferencia recibida", "${day(3)}T10:00:00Z", "Transferencia de ejemplo", BigDecimal(50000), "CRC",
            accountBaseCurrency = "CRC", transactionDate = day(3), transactionType = "income", category = "Transferencias", reviewStatus = "pending",
            financialAccountId = 2, bankMovement = "transfer_in", financialEffect = "income")
        candidates += MailCandidate(25, 25, null, "multimoney", "avisos@billetera.test", "Pago con billetera", "${day(4)}T10:00:00Z", "Recarga de ejemplo", BigDecimal(5000), "CRC",
            accountBaseCurrency = "CRC", transactionDate = day(4), transactionType = "expense", category = "Servicios", reviewStatus = "pending")
        candidates += MailCandidate(24, 24, null, "cooperativa_ejemplo", "avisos@cooperativa.test", "Pago de servicio", "${day(5)}T10:00:00Z", "Pago de agua", BigDecimal(8200), "CRC",
            accountBaseCurrency = "CRC", transactionDate = day(5), transactionType = "expense", category = "Servicios", reviewStatus = "confirmed")
        accounts += FinancialIdentity.Account(1, "Cuenta de ejemplo", "BAC", "bac", "CR", "checking", "CRC", "1234", "pending")
        accounts += FinancialIdentity.Account(2, "Ahorro de ejemplo", "Banco Popular", "popular", "CR", "savings", "CRC", "5678", "own")
    }

    private fun sampleProfile(plan: PlanTier) = Profile(
        id = 1, email = if (scenario == Scenario.STORE) "ana.demo@example.com" else "persona@ejemplo.test",
        displayName = when (scenario) { Scenario.NEW_USER -> null; Scenario.STORE -> "Ana"; else -> "Persona Ejemplo" }, role = role.wire,
        planSelected = scenario != Scenario.NEW_USER && scenario != Scenario.CHOOSE_PLAN, profileSetupCompleted = scenario != Scenario.NEW_USER,
        baseCurrency = "CRC", numberFormat = store?.numberFormat ?: "dot_comma", currencyPlacement = "before", entryCurrencies = listOf("CRC", "USD"), enabledCurrencies = listOf("CRC", "USD"),
        // STORE: a paid plan bought in the store (the backend records it as self_service), not a courtesy grant.
        // Owner: like the backend seed, the plan is VIP, granted with access_source owner.
        subscription = if (role == Role.OWNER) Profile.Subscription("vip", "VIP", "active", "owner")
        else Profile.Subscription(plan.wire, plan.name.lowercase().replaceFirstChar { it.uppercase() }, "active",
            if (plan == PlanTier.FREE || scenario == Scenario.STORE) "self_service" else "courtesy"),
        legal = Profile.Legal(required = scenario == Scenario.LEGAL_REQUIRED, termsVersion = "2026-09-23-v3", privacyVersion = "2026-09-25-v4"),
    )

    private companion object {
        const val PROMOTION = """{"code":"launch-free-2026","active":true,"ends_at":"2027-01-01T06:00:00Z","message":"Basic y VIP gratis hasta el 31 de diciembre de 2026."}"""
        val PLANS = """[{"code":"free","name":"Free","tagline":"Ordená lo esencial","features":["Ingresos y gastos","Deudas","Metas"],"regular_price_crc":0,"promotion":null},""" +
            """{"code":"basic","name":"Basic","tagline":"Planificá tu mes","features":["Presupuesto guiado","Calendario financiero","Pagos recurrentes","Estrategia básica"],"regular_price_crc":2990,"promotion":$PROMOTION},""" +
            """{"code":"vip","name":"VIP","tagline":"Tu director financiero","features":["Avisos bancarios del correo","Estrategia y proyecciones","Escenarios","Aguinaldo"],"regular_price_crc":4990,"promotion":$PROMOTION}]"""
        val FLAGS = """{"flags":[""" + listOf("financial_writes", "gmail_automation", "vip_intelligence", "advanced_reports").joinToString(",") {
            """{"flag_key":"$it","enabled":true}"""
        } + """,{"flag_key":"store_billing","enabled":false,"disabled_message_es":"Las compras en la tienda estarán disponibles pronto."}],"cache_seconds":30}"""
    }
}
