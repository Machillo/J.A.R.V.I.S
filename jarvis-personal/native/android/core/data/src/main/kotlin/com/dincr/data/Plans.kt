package com.dincr.data

/**
 * Plans the public app serves. The backend is authoritative (`require_feature` answers 402/403);
 * this only decides what the app offers, with the same minimums as `auth/saas.py`
 * `BUILTIN_FEATURE_MIN_PLAN`, so a screen is never shown to a plan the server would refuse.
 */
enum class PlanTier(val wire: String, val rank: Int) {
    FREE("free", 0), BASIC("basic", 1), VIP("vip", 2);

    fun allows(feature: Feature): Boolean = rank >= feature.minimum.rank

    companion object {
        fun from(wire: String?): PlanTier = entries.firstOrNull { it.wire == wire?.lowercase() } ?: FREE
    }
}

enum class Feature(val minimum: PlanTier) {
    FINANCE_OVERVIEW(PlanTier.FREE),
    SPENDING(PlanTier.FREE),
    DEBTS(PlanTier.FREE),
    GOALS(PlanTier.FREE),
    TRANSACTIONS(PlanTier.FREE),
    /** Also edits of debts and goals (`PUT /finance/debts/{id}`, `PUT /goals/{id}`). */
    STRATEGY_BASIC(PlanTier.BASIC),
    BASIC_DASHBOARD(PlanTier.BASIC),
    GUIDED_BUDGET(PlanTier.BASIC),
    FINANCIAL_CALENDAR(PlanTier.BASIC),
    RECURRING_ITEMS(PlanTier.BASIC),
    BASIC_REPORTS(PlanTier.BASIC),
    STRATEGY_VIP(PlanTier.VIP),
    GMAIL_AUTOMATION(PlanTier.VIP),
}

/**
 * Operational kill switches (`GET /product-ops/feature-flags`). Unknown means the backend's safe
 * default: writes, mail and store purchases paused; VIP intelligence and reports on.
 */
enum class OpsFlag(val key: String, val safeDefault: Boolean) {
    FINANCIAL_WRITES("financial_writes", false),
    GMAIL_AUTOMATION("gmail_automation", false),
    VIP_INTELLIGENCE("vip_intelligence", true),
    ADVANCED_REPORTS("advanced_reports", true),
    STORE_BILLING("store_billing", false),
}

/**
 * Local app lock (biometrics or the device's screen lock). It locks at launch and after five
 * minutes in the background, like the Capacitor app.
 */
object AppLockPolicy {
    const val TIMEOUT_MS = 5 * 60 * 1000L

    fun shouldLock(enabled: Boolean, backgroundedAtMs: Long?, nowMs: Long): Boolean =
        enabled && backgroundedAtMs != null && nowMs - backgroundedAtMs >= TIMEOUT_MS
}
