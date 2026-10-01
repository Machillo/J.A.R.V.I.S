package com.dincr.data

import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AnalyticsTest {
    private class MemoryStore : AnalyticsStore {
        val values = mutableMapOf<String, String>()
        override fun read(key: String) = values[key]
        override fun write(key: String, value: String?) { if (value == null) values.remove(key) else values[key] = value }
    }

    private var now = 0L
    private val sent = mutableListOf<AnalyticsEvent>()
    private val store = MemoryStore()
    private val analytics = NativeAnalytics(store, "2.0.0-rc.1", "release", TestScope(UnconfinedTestDispatcher()), { now }) { sent += it }

    @Test fun nothingIsSentUntilEnabled() {
        analytics.appOpened()
        analytics.screen("home")
        analytics.writeSucceeded("POST", "/user-product/goals")
        assertTrue(sent.isEmpty())
    }

    @Test fun eventsCarryOnlyClosedValuesAndAnAnonymousInstallId() {
        analytics.enabled = true
        analytics.appOpened()
        analytics.screen("movements")
        analytics.screen("some_new_screen")
        analytics.jarvisSection(Jarvis.Section.CALENDAR)
        assertEquals(listOf("app_opened", "screen_viewed", "jarvis_section_viewed"), sent.map { it.event })
        assertEquals(mapOf("screen" to "transactions"), sent[1].properties)
        assertEquals(mapOf("jarvis_section" to "calendar"), sent[2].properties)
        val installId = sent[0].installId
        assertTrue(Regex("^[0-9a-f-]{36}$").matches(installId))
        assertTrue(sent.all { it.installId == installId && it.platform == "android" && it.appVersion == "2.0.0" && it.build == "release" })
        for (event in sent) {
            assertTrue(event.event in AnalyticsContract.EVENTS)
            for ((name, value) in event.properties) {
                assertTrue(name in setOf("screen", "jarvis_section", "action_type"))
                assertTrue(Regex("^[a-z_-]+$").matches(value))
            }
        }
    }

    @Test fun usefulActionsAreTypesOfSuccessfulWritesNeverPaths() {
        analytics.enabled = true
        analytics.writeSucceeded("PUT", "/user-product/financial-situation")
        analytics.writeSucceeded("POST", "/user-product/goals/7/contributions?x=1")
        analytics.writeSucceeded("GET", "/user-product/goals")
        analytics.writeSucceeded("POST", "/user-product/finance/strategy-vip/simulate")
        analytics.writeSucceeded("POST", "/product-ops/analytics")
        assertEquals(listOf("financial_profile_saved", "useful_action", "useful_action"), sent.map { it.event })
        assertEquals(listOf("financial_profile_saved", "goal_contribution_recorded"), sent.drop(1).map { it.properties["action_type"] })
        assertTrue(sent.none { event -> event.properties.values.any { it.contains('/') } })
    }

    @Test fun signOutRotatesTheInstallIdAndStops() {
        analytics.enabled = true
        analytics.appOpened()
        val first = sent.single().installId
        analytics.reset()
        analytics.appOpened()
        assertEquals(1, sent.size)
        analytics.enabled = true
        analytics.appOpened()
        assertNotEquals(first, sent.last().installId)
    }

    @Test fun anEventRecordedBeforeSignOutIsNeverSentAfterIt() {
        val scope = TestScope(StandardTestDispatcher())
        val queued = mutableListOf<AnalyticsEvent>()
        val delayed = NativeAnalytics(MemoryStore(), "2.0.0", "release", scope, { 0L }) { queued += it }
        delayed.enabled = true
        delayed.appOpened()
        delayed.reset()
        scope.advanceUntilIdle()
        assertTrue(queued.isEmpty())
    }

    @Test fun aSessionEndsAfterThirtyIdleMinutes() {
        analytics.enabled = true
        analytics.appOpened(); now += 29 * 60_000L
        analytics.screen("home"); now += 31 * 60_000L
        analytics.screen("home")
        assertEquals(sent[0].sessionId, sent[1].sessionId)
        assertNotEquals(sent[1].sessionId, sent[2].sessionId)
    }

    @Test fun appVersionIsXyzOnly() {
        assertEquals("2.0.0", AnalyticsContract.appVersion("2.0.0-rc.1"))
        assertNull(AnalyticsContract.appVersion("dev"))
    }
}
