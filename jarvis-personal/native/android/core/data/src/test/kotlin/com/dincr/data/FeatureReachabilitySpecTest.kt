package com.dincr.data

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The plan gates core/data decides agree with the shared reachability spec
 * (`native/feature-reachability.json`, master plan R1 / P0.0). The UI reachability itself is walked by
 * `FeatureReachabilityUiTest`; the Swift twin is `FeatureReachabilitySpecTests`.
 */
class FeatureReachabilitySpecTest {
    private val features: Map<String, JsonObject> = run {
        // Unit tests run in native/android/core/data: the spec is native/feature-reachability.json.
        val native = File(System.getProperty("user.dir")).absoluteFile.parentFile.parentFile.parentFile
        val spec = Json.parseToJsonElement(File(native, "feature-reachability.json").readText()).jsonObject
        spec.getValue("features").jsonArray.associate { it.jsonObject.getValue("id").jsonPrimitive.content to it.jsonObject }
    }

    private fun state(id: String, plan: String): String {
        val feature = features[id] ?: error("spec has no feature $id")
        val override = (feature["platform_states"] as? JsonObject)?.get("android")?.jsonObject?.get(plan)
        return (override ?: feature.getValue("plans").jsonObject.getValue(plan)).jsonPrimitive.content
    }

    /** Each spec entry whose plan gate lives in core/data, with the feature that gates it. */
    private val gated = mapOf(
        "plan.aguinaldo" to Feature.GMAIL_AUTOMATION, "plan.strategy" to Feature.STRATEGY_BASIC, "plan.debts" to Feature.DEBTS,
        "plan.salvavidas" to Feature.STRATEGY_VIP, "plan.distribution" to Feature.STRATEGY_BASIC,
        // UX-13: the former DINCR tab's entries, in Movimientos → Análisis, Patrimonio and Hoy.
        "analysis.reports" to Feature.BASIC_REPORTS, "home.attention" to Feature.STRATEGY_VIP,
        "wealth.projections" to Feature.STRATEGY_VIP, "wealth.scenarios" to Feature.STRATEGY_VIP,
        "analysis.review" to Feature.STRATEGY_VIP,
        // §15 PR 6: the same mail review, from Movimientos → Por revisar.
        "movements.review" to Feature.GMAIL_AUTOMATION,
        // §15 PR 5: Presupuesto and Calendario inside Tu plan del mes, Movimientos recurrentes inside Ingresos y base.
        "month.budget" to Feature.GUIDED_BUDGET, "month.calendar" to Feature.GUIDED_BUDGET, "incomeBase.recurring" to Feature.RECURRING_ITEMS,
        // §15 PR 8: Patrimonio → Cuentas, Conexiones de correo and Deudas.
        "wealth.accounts" to Feature.GMAIL_AUTOMATION, "wealth.connections" to Feature.GMAIL_AUTOMATION, "wealth.debts" to Feature.DEBTS,
    )

    @Test fun planGatesFollowTheSpec() {
        gated.forEach { (id, feature) ->
            PlanTier.entries.forEach { tier ->
                val expected = state(id, tier.wire)
                assertEquals("$id ${tier.wire}: $expected", expected == "AVAILABLE", tier.allows(feature))
            }
            assertEquals(id, "AVAILABLE", state(id, "owner"))
        }
    }

    @Test fun jarvisSectionsAreOwnerOnlyAndPortedOnesAreNotPlaceholders() {
        Jarvis.Section.entries.forEach { section ->
            val id = "jarvis.${section.wire}"
            assertEquals(id, "AVAILABLE", state(id, "owner"))
            listOf("free", "basic", "vip").forEach { assertEquals("$id $it", "OWNER_ONLY", state(id, it)) }
            assertEquals("$id: ported state differs from the spec", section.isAvailable, features.getValue(id)["placeholder"] == null)
        }
        fun profile(role: String, plan: String?) =
            Profile(id = 1, role = role, planSelected = true, profileSetupCompleted = true, subscription = plan?.let { Profile.Subscription(plan = it, status = "active") })
        assertTrue(Jarvis.isAvailable(profile("owner", null)))
        listOf("free", "basic", "vip").forEach { assertFalse(it, Jarvis.isAvailable(profile("user", it))) }
        assertEquals("HIDDEN_BY_SECURITY", state("profile.delete", "owner"))
        assertFalse(profile("owner", null).canDeleteAccountInApp)
        assertTrue(profile("user", "vip").canDeleteAccountInApp)
    }
}
