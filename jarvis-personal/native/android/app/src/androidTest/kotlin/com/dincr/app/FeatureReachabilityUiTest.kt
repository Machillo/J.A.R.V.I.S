package com.dincr.app

import android.content.Intent
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.printToLog
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * Functional protection gate (master plan R1 / P0.0): every feature in the shared reachability spec
 * (`native/feature-reachability.json`, packaged as a test asset by app/build.gradle.kts) is reachable,
 * locked or absent for each plan exactly as the spec says, on the FakeBackend. A PR that removes,
 * hides or moves a feature fails here unless it changes the spec with an explicit decision.
 * iOS walks the same spec in `FeatureReachabilityUITests`.
 */
class FeatureReachabilityUiTest {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private val features: List<JsonObject> = run {
        val text = InstrumentationRegistry.getInstrumentation().context.assets.open("feature-reachability.json").bufferedReader().readText()
        Json.parseToJsonElement(text).jsonObject.getValue("features").jsonArray.map { it.jsonObject }
    }

    /** The app follows the device language (`tx`): the spec carries each Android label in Spanish and under `en`. */
    private fun JsonObject.string(key: String): String? {
        val english = (this["en"] as? JsonObject)?.takeIf { tx("es", "en") == "en" }
        return ((english?.get(key) ?: this[key]) as? kotlinx.serialization.json.JsonPrimitive)?.content
    }

    private fun JsonObject.list(key: String): List<String> {
        val english = (this["en"] as? JsonObject)?.takeIf { tx("es", "en") == "en" }
        return ((english?.get(key) ?: this[key]) as? JsonArray)?.map { it.jsonPrimitive.content } ?: emptyList()
    }

    private fun state(feature: JsonObject, plan: String): String {
        val override = (feature["platform_states"] as? JsonObject)?.get("android")?.jsonObject?.get(plan)
        return (override ?: feature.getValue("plans").jsonObject.getValue(plan)).jsonPrimitive.content
    }

    private fun launch(plan: String) {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L)
        when (plan) {
            "owner" -> intent.putExtra("dincrRole", "owner").putExtra("dincrPlan", "free")
            else -> intent.putExtra("dincrPlan", plan)
        }
        scenario = ActivityScenario.launch(intent)
    }

    private fun present(text: String) = compose.onAllNodes(hasText(text), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()

    private fun tagged(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()

    private fun waitFor(timeoutMs: Long = 15_000, condition: () -> Boolean): Boolean = try {
        compose.waitUntil(timeoutMs) { compose.mainClock.advanceTimeBy(100); condition() }
        true
    } catch (_: Throwable) {
        false
    }

    private fun click(text: String) {
        val node = compose.onAllNodesWithText(text).onFirst()
        runCatching { node.performScrollTo() }
        node.performClick()
    }

    private fun check(feature: JsonObject, plan: String, failures: MutableList<String>) {
        val location = feature["android"] as? JsonObject ?: return
        val id = feature.getValue("id").jsonPrimitive.content
        val expected = state(feature, plan)
        val text = location.string("tab_button") ?: location.string("text")
        val tag = location.string("tag")
        val visible = if (tag != null) waitFor(5_000) { tagged(tag) } else waitFor(if (expected == "AVAILABLE") 5_000 else 1_000) { present(text!!) }
        when (expected) {
            "AVAILABLE" -> if (!visible) failures += "$id [$plan]: not reachable"
            "VISIBLE_LOCKED" -> {
                val locked = location.string("locked_text")
                if (locked == null || !waitFor(5_000) { present(locked) }) failures += "$id [$plan]: the locked entry is missing"
            }
            else -> if (visible && location.string("tab_button") == null) failures += "$id [$plan]: shown to a plan that must not see it ($expected)"
        }
    }

    private fun back() {
        scenario?.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        compose.waitForIdle()
    }

    /** One launch per plan; each screen (tab, then its sub-path) is checked, then the walk returns to the tab. */
    private fun walk(plan: String) {
        val failures = mutableListOf<String>()
        val located = features.filter { it["android"] is JsonObject }
        val groups = located.groupBy { feature ->
            val location = feature.getValue("android").jsonObject
            val tab = if (location.string("tab_button") != null) tx("Hoy", "Today") else location.string("tab") ?: tx("Hoy", "Today")
            "$tab|${location.list("via").joinToString(">")}"
        }
        launch(plan)
        if (!waitFor { present(tx("Hoy", "Today")) }) {
            runCatching { compose.onAllNodes(isRoot()).printToLog("DINCR-REACH") }
            error("the app did not open Hoy for $plan")
        }
        groups.keys.sorted().forEach { key ->
            val (tab, via) = key.split("|")
            click(tab)
            var reached = true
            var depth = 0
            via.split(">").filter { it.isNotEmpty() }.forEach { step ->
                if (reached && waitFor(5_000) { present(step) }) { click(step); depth++ } else reached = false
            }
            groups.getValue(key).forEach { feature ->
                if (reached) check(feature, plan, failures)
                else if (state(feature, plan) in setOf("AVAILABLE", "VISIBLE_LOCKED"))
                    failures += "${feature.getValue("id").jsonPrimitive.content} [$plan]: its path $via is not reachable"
            }
            repeat(depth) { back() }
        }
        if (failures.isNotEmpty()) runCatching { compose.onAllNodes(isRoot()).printToLog("DINCR-REACH") }
        assertTrue(failures.joinToString("\n"), failures.isEmpty())
    }

    @Test fun freeReachesExactlyTheSpec() = walk("free")
    @Test fun basicReachesExactlyTheSpec() = walk("basic")
    @Test fun vipReachesExactlyTheSpec() = walk("vip")
    @Test fun ownerReachesExactlyTheSpec() = walk("owner")
}
