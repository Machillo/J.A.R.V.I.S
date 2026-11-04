package com.dincr.data

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * L-2: mail is paused outside the Owner. A VIP sees no trace of it, unless a mailbox or notices
 * from before the pause are left: those stay reviewable and the mailbox stays disconnectable.
 * iOS: `MailPauseTests`.
 */
class MailPauseTest {
    private fun connection(status: String) = MailStatus.Connection(1, "gmail", "ejemplo@correo.test", status)

    private fun api(backend: FakeBackend) = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, backend, AppLanguage.SPANISH, backoff = {}))

    @Test fun nothingLeftMeansNoMail() {
        assertFalse(MailStatus().hasLeftovers)
        assertFalse(MailStatus(pending = 0).hasLeftovers)
        assertFalse("a mailbox already disconnected is not left over", MailStatus(connections = listOf(connection("disabled"))).hasLeftovers)
    }

    @Test fun aMailboxOrPendingNoticesAreLeftovers() {
        assertTrue(MailStatus(pending = 1).hasLeftovers)
        assertTrue(MailStatus(connections = listOf(connection("active"))).hasLeftovers)
        assertTrue("an expired authorization can still be disconnected", MailStatus(connections = listOf(connection("reauthorization_required"))).hasLeftovers)
    }

    @Test fun aVipWithoutHistoryHasNoMailAtAll() = runTest {
        val status = api(FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP)).mailStatus()
        assertFalse(status.hasLeftovers)
        assertFalse(status.connected)
    }

    @Test fun aVipWhoConnectedBeforeThePauseCanReviewAndDisconnect() = runTest {
        val api = api(FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP, mailLeftovers = true))
        assertTrue(api.mailStatus().hasLeftovers)
        assertTrue(api.mailCandidates(pendingOnly = true).isNotEmpty())
        api.mailStatus().visibleConnections.forEach { api.disconnectMail(it.id) }
        assertEquals(emptyList<MailStatus.Connection>(), api.mailStatus().visibleConnections)
    }
}
