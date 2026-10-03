package com.dincr.data

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.util.UUID

/**
 * Product analytics contract v2 for the native app (docs/analytics/posthog-event-taxonomy.md).
 *
 * The native app has no PostHog SDK and no PostHog key: it sends closed-list events to
 * `POST /product-ops/analytics`, and the backend checks them against the same contract as the
 * Capacitor app, decides the audience (Users / Owner / nothing) from its own records and relays
 * them to PostHog. Only fixed names and categories leave the device: never an amount, a name, an
 * email, a bank or account, chat or calendar content, free text or an internal identifier.
 * Parity with `frontend/src/lib/analyticsContract.js` is checked by `test_analytics_relay.py`.
 */
object AnalyticsContract {
    /** Every event this app sends (a subset of the v2 contract). */
    val EVENTS = setOf(
        "app_opened", "screen_viewed", "useful_action", "financial_profile_saved",
        "jarvis_opened", "jarvis_section_viewed",
    )

    /** Native screen name → contract `screen` value. */
    val SCREENS = mapOf(
        "home" to "overview", "movements" to "transactions", "debts" to "debts", "goals" to "goals",
        "strategy" to "strategy", "budget" to "budget", "calendar" to "calendar", "recurring" to "recurring",
        "reports" to "reports", "settings" to "settings",
    )

    /** Same rules, in the same order, as `usefulActionRules` in analyticsContract.js. */
    val USEFUL_ACTION_RULES = listOf(
        Rule("PUT", """^/user-product/financial-situation$""", "financial_profile_saved"),
        Rule("POST", """^/user-product/finance/income$""", "income_added"),
        Rule("PUT", """^/user-product/finance/income/[^/]+$""", "income_updated"),
        Rule("POST", """^/user-product/finance/expenses$""", "expense_added"),
        Rule("PUT", """^/user-product/finance/expenses/[^/]+$""", "expense_updated"),
        Rule("POST", """^/user-product/finance/debts$""", "debt_added"),
        Rule("PUT", """^/user-product/finance/debts/[^/]+$""", "debt_updated"),
        Rule("POST", """^/user-product/finance/debts/[^/]+/payments$""", "debt_payment_recorded"),
        Rule("PUT", """^/user-product/vip/salvavidas$""", "salvavidas_saved"),
        Rule("POST", """^/user-product/goals$""", "goal_created"),
        Rule("PUT", """^/user-product/goals/[^/]+$""", "goal_updated"),
        Rule("POST", """^/user-product/goals/[^/]+/contributions$""", "goal_contribution_recorded"),
        Rule("POST", """^/user-product/savings-plans$""", "savings_plan_created"),
        Rule("PUT", """^/user-product/savings-plans/[^/]+$""", "savings_plan_updated"),
        Rule("POST", """^/user-product/savings-plans/[^/]+/contributions$""", "savings_contribution_recorded"),
        Rule("POST", """^/user-product/transactions$""", "transaction_added"),
        Rule("PUT", """^/user-product/free/movements/[^/]+$""", "transaction_updated"),
        Rule("PUT", """^/user-product/basic/budget$""", "budget_saved"),
        Rule("POST", """^/user-product/basic/recurring$""", "recurring_added"),
        Rule("PUT", """^/user-product/basic/recurring/[^/]+$""", "recurring_updated"),
    )

    data class Rule(val method: String, val pattern: String, val actionType: String) {
        val regex = Regex(pattern)
    }

    /** The action type of a successful write, or null. The path itself never leaves the device. */
    fun usefulActionFor(method: String, path: String): String? {
        val clean = path.substringBefore('?').substringBefore('#').trimEnd('/')
        return USEFUL_ACTION_RULES.firstOrNull { it.method == method.uppercase() && it.regex.matches(clean) }?.actionType
    }

    /** `x.y.z` only (a pre-release suffix such as `-rc.1` is dropped), or null. */
    fun appVersion(versionName: String): String? = Regex("""^(\d+\.\d+\.\d+)""").find(versionName)?.groupValues?.get(1)
}

/** `POST /product-ops/analytics`: one native event. Properties are closed-list strings only. */
@Serializable
data class AnalyticsEvent(
    val event: String,
    val properties: Map<String, String> = emptyMap(),
    @SerialName("install_id") val installId: String,
    @SerialName("session_id") val sessionId: String? = null,
    val platform: String = "android",
    @SerialName("app_version") val appVersion: String? = null,
    val build: String = "release",
)

/** Where the install and session IDs are kept (SharedPreferences in the app, a map in tests). */
interface AnalyticsStore {
    fun read(key: String): String?
    fun write(key: String, value: String?)
}

/**
 * The native app's product analytics. Off until [enabled] (identity ready, live backend).
 *
 * Identity is a random install UUID: the native equivalent of posthog-js's anonymous device ID.
 * It is rotated on sign-out, so two accounts on one phone are never joined, and it is never
 * derived from an account, an email or any other identifier.
 */
class NativeAnalytics(
    private val store: AnalyticsStore,
    versionName: String,
    private val build: String,
    private val scope: CoroutineScope,
    private val clock: () -> Long = System::currentTimeMillis,
    private val send: suspend (AnalyticsEvent) -> Unit,
) {
    private val appVersion = AnalyticsContract.appVersion(versionName)
    private var sessionId: String? = null
    private var lastEventAt = 0L
    /** Bumped on sign-out: an event recorded for one account is never sent after it signed out. */
    @Volatile private var generation = 0

    @Volatile var enabled = false

    fun appOpened() = record("app_opened")

    /** A Users screen, by its native name; unknown names are not sent. */
    fun screen(nativeName: String) {
        val screen = AnalyticsContract.SCREENS[nativeName] ?: return
        record("screen_viewed", mapOf("screen" to screen))
    }

    fun jarvisOpened() = record("jarvis_opened")

    fun jarvisSection(section: Jarvis.Section) = record("jarvis_section_viewed", mapOf("jarvis_section" to section.wire))

    /** Called by the API client after every successful write; only matching writes are sent. */
    fun writeSucceeded(method: String, path: String) {
        val action = AnalyticsContract.usefulActionFor(method, path) ?: return
        if (action == "financial_profile_saved") record("financial_profile_saved")
        record("useful_action", mapOf("action_type" to action))
    }

    /** Sign-out: stop, and start the next account with a new anonymous install ID. */
    @Synchronized
    fun reset() {
        enabled = false
        generation += 1
        sessionId = null
        store.write(INSTALL_ID, null)
    }

    @Synchronized
    private fun nextEvent(name: String, properties: Map<String, String>): AnalyticsEvent? {
        if (!enabled || name !in AnalyticsContract.EVENTS) return null
        val installId = store.read(INSTALL_ID) ?: UUID.randomUUID().toString().also { store.write(INSTALL_ID, it) }
        val now = clock()
        if (sessionId == null || now - lastEventAt > SESSION_IDLE_MS) sessionId = UUID.randomUUID().toString()
        lastEventAt = now
        return AnalyticsEvent(name, properties, installId, sessionId, appVersion = appVersion, build = build)
    }

    private fun record(name: String, properties: Map<String, String> = emptyMap()) {
        val event = nextEvent(name, properties) ?: return
        val recordedIn = generation
        // Analytics never blocks or breaks the app.
        scope.launch { if (recordedIn == generation) runCatching { send(event) } }
    }

    companion object {
        const val INSTALL_ID = "analytics_install_id"
        const val SESSION_IDLE_MS = 30 * 60 * 1000L
    }
}

/** Sends a native event to the backend relay. Uses its own client, so it never reports itself. */
class AnalyticsRelay(private val client: ApiClient) {
    suspend fun send(event: AnalyticsEvent) {
        client.send<AnalyticsEvent, Acknowledgement>("POST", "/product-ops/analytics", event)
    }
}
