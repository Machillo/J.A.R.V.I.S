package com.dincr.app

import android.content.Intent
import android.graphics.Bitmap
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeUp
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.After
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

/**
 * Visual tour of the whole app, for design review (not a store asset). Opt-in: runs only with the
 * instrumentation argument `appTour=true`, so the regular UI-test run skips it.
 *
 * For each plan it opens the app on the POPULATED sample (FakeBackend, Debug only), saves every tab
 * (top and two scrolled positions), then walks the shared reachability spec
 * (`native/feature-reachability.json`): for each feature the plan can open, it follows the same path
 * as [FeatureReachabilityUiTest], opens the entry, saves the screen and goes back. Files land in
 * `<app external files>/tour/<plan>/<nn>-<id>.png`. Synthetic data only; nothing leaves the device.
 */
class AppTour {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null
    private var index = 0

    @Before fun optIn() = assumeTrue(InstrumentationRegistry.getArguments().getString("appTour") == "true")

    @After fun close() { scenario?.close() }

    private val features: List<JsonObject> = run {
        val text = InstrumentationRegistry.getInstrumentation().context.assets.open("feature-reachability.json").bufferedReader().readText()
        Json.parseToJsonElement(text).jsonObject.getValue("features").jsonArray.map { it.jsonObject }
    }

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
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        scenario = ActivityScenario.launch(intent)
    }

    private fun present(text: String) = compose.onAllNodes(hasText(text), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()

    private fun waitFor(timeoutMs: Long = 8_000, condition: () -> Boolean): Boolean = try {
        compose.waitUntil(timeoutMs) { compose.mainClock.advanceTimeBy(100); condition() }
        true
    } catch (_: Throwable) {
        false
    }

    private fun click(text: String): Boolean = runCatching {
        val node = compose.onAllNodesWithText(text).onFirst()
        runCatching { node.performScrollTo() }
        node.performClick()
    }.isSuccess

    private fun back() {
        scenario?.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        compose.waitForIdle()
    }

    private fun capture(plan: String, id: String) {
        repeat(20) { compose.mainClock.advanceTimeBy(100) }
        Thread.sleep(600)
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot() ?: return
        val dir = File(ApplicationProvider.getApplicationContext<android.content.Context>().getExternalFilesDir(null), "tour/$plan")
        check(dir.isDirectory || dir.mkdirs()) { "cannot create $dir" }
        index += 1
        File(dir, "%02d-%s.png".format(index, id.replace(Regex("[^A-Za-z0-9._-]"), "_"))).outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private fun scroll() {
        runCatching { compose.onAllNodes(isRoot()).onFirst().performTouchInput { swipeUp(startY = bottom * 0.8f, endY = bottom * 0.25f) } }
        compose.waitForIdle()
    }

    private fun tour(plan: String) {
        launch(plan)
        check(waitFor(20_000) { present(tx("Hoy", "Today")) }) { "the app did not open Hoy for $plan" }
        val tabs = listOf(tx("Hoy", "Today"), tx("Movimientos", "Transactions"), tx("Plan", "Plan"), tx("Patrimonio", "Wealth"), tx("Perfil", "Profile"))
        tabs.forEach { tab ->
            click(tab)
            waitFor(3_000) { false }
            capture(plan, "tab-$tab")
            repeat(2) { n -> scroll(); capture(plan, "tab-$tab-scroll${n + 1}") }
        }
        features.filter { it["android"] is JsonObject && state(it, plan) == "AVAILABLE" }.forEach { feature ->
            val location = feature.getValue("android").jsonObject
            val entry = location.string("text") ?: return@forEach
            val tab = location.string("tab") ?: tx("Hoy", "Today")
            // A back press from a tab root may close the app: reopen it on the same plan.
            if (!waitFor(2_000) { present(tx("Perfil", "Profile")) }) { launch(plan); waitFor(20_000) { present(tx("Hoy", "Today")) } }
            click(tab)
            var depth = 0
            for (step in location.list("via")) {
                if (!waitFor { present(step) } || !click(step)) break
                depth++
            }
            if (waitFor { present(entry) } && click(entry)) {
                capture(plan, feature.getValue("id").jsonPrimitive.content)
                back()
            }
            repeat(depth) { back() }
        }
    }

    @Test fun free() = tour("free")
    @Test fun basic() = tour("basic")
    @Test fun vip() = tour("vip")
}
