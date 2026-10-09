package com.dincr.data

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.async
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * B17 — pull to refresh on Plan, Patrimonio and Perfil: a failed refresh keeps what the screen
 * showed, one refresh runs at a time, and the fixture used by the UI tests fails only the identity
 * read again. The Swift twin is `PullRefreshTests`. Synthetic data.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PullRefreshTest {
    @Test fun aSuccessfulRefreshShowsTheNewAnswer() {
        assertEquals(listOf(3), PullRefresh.kept(listOf(1, 2), Result.success(listOf(3))))
        assertEquals(listOf(3), PullRefresh.kept(null, Result.success(listOf(3))))
    }

    @Test fun aFailedRefreshKeepsWhatTheScreenShowed() {
        assertEquals(listOf(1, 2), PullRefresh.kept(listOf(1, 2), Result.failure(IllegalStateException("unreachable"))))
    }

    @Test fun aFailedFirstReadHasNothingToKeep() {
        assertNull(PullRefresh.kept<List<Int>>(null, Result.failure(IllegalStateException("unreachable"))))
    }

    @Test fun theFailureNoticeIsTheSameOnBothPlatforms() {
        assertEquals("No pudimos actualizar. Seguís viendo la información anterior.", PullRefresh.failureNotice(AppLanguage.SPANISH))
        assertEquals("We couldn’t refresh. You’re still seeing the previous information.", PullRefresh.failureNotice(AppLanguage.ENGLISH))
    }

    @Test fun aSecondRefreshWhileOneRunsJoinsItInsteadOfAskingAgain() = runTest {
        val flight = SingleFlight(this)
        var calls = 0
        val gate = CompletableDeferred<Unit>()
        val first = async { flight.run { calls += 1; gate.await(); true } }
        runCurrent()
        assertTrue(flight.isRunning)
        val second = async { flight.run { calls += 1; false } }
        runCurrent()
        gate.complete(Unit)
        assertTrue(first.await())
        assertTrue("the second pull gets the running refresh's result", second.await())
        assertEquals("one read, not two", 1, calls)
        assertFalse(flight.isRunning)
    }

    @Test fun aRefreshAfterTheLastOneEndedReadsAgain() = runTest {
        val flight = SingleFlight(this)
        var calls = 0
        assertFalse(flight.run { calls += 1; false })
        assertTrue(flight.run { calls += 1; true })
        assertEquals(2, calls)
    }

    private fun api(refreshFails: Boolean) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP, identityRefreshFails = refreshFails), AppLanguage.SPANISH, backoff = {}))

    @Test fun theFixtureFailsOnlyTheIdentityReadAgain() = runTest {
        val failing = api(refreshFails = true)
        failing.me()
        try {
            failing.me()
            fail("the second identity read should fail")
        } catch (error: ApiError) {
            assertTrue("like an unreachable server: the app keeps the user where they were", error.isTransient)
        }
        failing.debts()

        val normal = api(refreshFails = false)
        normal.me()
        normal.me()
    }
}
