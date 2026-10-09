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
import androidx.compose.ui.test.printToLog
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import org.junit.After
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

/**
 * Store screenshots (jarvis-personal/store-assets/CAPTURE.md). Opt-in: runs only with the
 * instrumentation argument `storeScreenshots=true`, so the regular UI-test run skips it.
 *
 * Each test opens the real app on the STORE sample (FakeBackend, Debug only) with the lowest plan
 * that includes the screen, navigates like a user, waits for the loaded content and saves the
 * screen to `<app external files>/store/<es|en>/<id>.png`. The device's per-app language picks es
 * or en; store-assets/scripts/capture-android.mjs sets it, cleans the status bar and pulls the files.
 */
class StoreScreenshots {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    @Before fun optIn() = assumeTrue(InstrumentationRegistry.getArguments().getString("storeScreenshots") == "true")

    @After fun close() { scenario?.close() }

    private fun advance() { compose.mainClock.advanceTimeBy(100) }

    private fun launch(plan: String) {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "STORE").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        scenario = ActivityScenario.launch(intent)
    }

    private fun waitForText(text: String) {
        try {
            compose.waitUntil(20_000) { advance(); compose.onAllNodes(hasText(text), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
        } catch (error: Throwable) {
            runCatching { compose.onAllNodes(isRoot()).printToLog("DINCR-STORE") }
            throw AssertionError("timed out waiting for \"$text\"", error)
        }
    }

    private fun click(text: String) {
        waitForText(text)
        val node = compose.onAllNodesWithText(text).onFirst()
        runCatching { node.performScrollTo() }
        node.performClick()
    }

    /** Lets transitions and progress animations finish, then saves exactly what is on screen. */
    private fun capture(id: String) {
        repeat(30) { advance() }
        Thread.sleep(800)
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot() ?: error("no screenshot for $id")
        val dir = File(ApplicationProvider.getApplicationContext<android.content.Context>().getExternalFilesDir(null), "store/${tx("es", "en")}")
        check(dir.isDirectory || dir.mkdirs()) { "cannot create $dir" }
        File(dir, "$id.png").outputStream().use { check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
    }

    private val today get() = tx("Hoy", "Today")

    @Test fun s01Home() {
        launch("vip")
        waitForText(tx("Podés gastar con tranquilidad", "Safe to spend"))
        waitForText(tx("Qué sigue", "What’s next"))
        capture("01-home")
    }

    @Test fun s02Overview() {
        launch("free")
        waitForText(tx("Resultado del mes", "This month’s result"))
        waitForText(tx("Accesos rápidos", "Quick access"))
        capture("02-overview")
    }

    @Test fun s03Movements() {
        launch("free")
        waitForText(tx("Resultado del mes", "This month’s result"))
        click(tx("Movimientos", "Transactions"))
        waitForText(tx("Supermercado", "Groceries"))
        capture("03-movements")
    }

    @Test fun s04Debts() {
        launch("free")
        waitForText(today)
        click(tx("Deudas", "Debts"))
        waitForText(tx("Préstamo del carro", "Car loan"))
        capture("04-debts")
    }

    @Test fun s05Goals() {
        launch("free")
        waitForText(today)
        click(tx("Metas y ahorros", "Goals and savings"))
        waitForText(tx("Vacaciones", "Vacation"))
        capture("05-goals")
    }

    @Test fun s06Budget() {
        launch("basic")
        waitForText(today)
        click(tx("Plan", "Plan"))
        click(tx("Tu plan del mes", "Your plan for the month"))
        click(tx("Presupuesto", "Budget"))
        waitForText(tx("Entretenimiento", "Entertainment"))
        capture("06-budget")
    }

    @Test fun s07Strategy() {
        launch("basic")
        waitForText(today)
        click(tx("Plan", "Plan"))
        click(tx("Tu plan del mes", "Your plan for the month"))
        waitForText(tx("Libre después de tus compromisos", "Left after your commitments"))
        capture("07-strategy")
    }

    @Test fun s08Mail() {
        launch("vip")
        waitForText(today)
        click(tx("Patrimonio", "Wealth"))
        click(tx("Conexiones de correo", "Mail connections"))
        waitForText(tx("Por revisar", "To review"))
        capture("08-mail")
    }
}
