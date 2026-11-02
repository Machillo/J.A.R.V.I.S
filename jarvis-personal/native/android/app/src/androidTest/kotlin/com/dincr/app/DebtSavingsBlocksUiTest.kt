package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelectable
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test

/**
 * DB-1 — Plan → Ahorro para deudas: the Owner reads the strategy's next locked saving, records the one he
 * created at the bank and sees it with its progress; no plan sees the row. iOS twin:
 * `DebtSavingsBlocksUITests`. FakeBackend only.
 */
class DebtSavingsBlocksUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun launch(plan: String, role: String? = null) {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
    }
    private fun present(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun tagged(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun waitUntil(what: String, condition: () -> Boolean) {
        repeat(150) { if (condition()) return; Thread.sleep(100); compose.waitForIdle() }
        throw AssertionError("timed out waiting for $what")
    }
    private fun click(text: String, selectable: Boolean = false) {
        val matcher = if (selectable) hasText(text) and isSelectable() else hasText(text) and hasClickAction()
        waitUntil(text) { compose.onAllNodes(matcher).fetchSemanticsNodes().isNotEmpty() }
        val node = compose.onAllNodes(matcher).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun clickTag(tag: String) {
        waitUntil(tag) { tagged(tag) }
        val node = compose.onAllNodes(hasTestTag(tag)).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }

    @Test fun theOwnerRecordsTheProposedSavingAndSeesItsProgress() {
        launch("vip", role = "owner")
        click(tx("Plan", "Plan"), selectable = true)
        click(tx("Ahorro para deudas", "Savings for debts"))
        waitUntil("the proposal") { tagged("debtBlocks.headline") && present(tx("cada jueves por 6 meses", "every Thursday for 6 months")) }
        clickTag("debtBlocks.create")
        clickTag("debtBlocks.save")
        // Recorded: the debt is taken, so nothing is left to lock, and the block shows its progress.
        waitUntil("the recorded block") { tagged("debtBlocks.block.fixture-block-1") && present(tx("ya usan todo tu sobrante", "already use all of your safe")) }
    }

    @Test fun aMaturedSavingIsPaidIntoItsDebtAndLeavesTheList() {
        launch("vip", role = "owner")
        click(tx("Plan", "Plan"), selectable = true)
        click(tx("Ahorro para deudas", "Savings for debts"))
        clickTag("debtBlocks.pay.fixture-matured-1")
        // The bank shortened the term: the installments left, as the bank says them.
        waitUntil("the installments field") { tagged("debtBlocks.remaining") }
        compose.onAllNodes(hasTestTag("debtBlocks.remaining")).onFirst().performTextInput("12")
        clickTag("debtBlocks.applySave")
        waitUntil("the abono") { tagged("debtBlocks.notice") && present(tx("Listo", "Done")) && !tagged("debtBlocks.block.fixture-matured-1") }
    }

    @Test fun anExtraPaymentWaitsForTheBankAndIsAnsweredLater() {
        launch("vip")
        click(tx("Plan", "Plan"), selectable = true)
        click(tx("Deudas", "Debts"))
        click(tx("Registrar pago", "Record payment"))
        waitUntil("the amount") { tagged("amount.field") }
        compose.onAllNodes(hasTestTag("amount.field")).onFirst().performTextInput("100000")   // above the installment
        click(tx("Me avisa después", "Tells me later"))
        clickTag("amount.save")
        waitUntil("waiting for the bank") { tagged("debts.waitingForBank") }
        clickTag("debts.afterExtra.1")
        waitUntil("the installments field") { tagged("debts.afterExtra.remaining") }
        compose.onAllNodes(hasTestTag("debts.afterExtra.remaining")).onFirst().performTextInput("6")
        clickTag("debts.afterExtra.save")
        waitUntil("answered") { !tagged("debts.waitingForBank") }
    }

    @Test fun noPlanSeesTheRow() {
        for (plan in listOf("free", "basic", "vip")) {
            launch(plan)
            click(tx("Plan", "Plan"), selectable = true)
            waitUntil("Plan") { present(tx("Ingresos y base", "Income and base")) }
            assertFalse(plan, present(tx("Ahorro para deudas", "Savings for debts")))
        }
    }
}
