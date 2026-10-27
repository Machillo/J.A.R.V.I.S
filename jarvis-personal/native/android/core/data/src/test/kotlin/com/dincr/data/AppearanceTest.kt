package com.dincr.data

import com.dincr.data.generated.AppearanceCatalog
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * APP-1 personal appearance: the catalog, the Owner-only policy, the per-account cache and the
 * fixture server's gate (the backend's is in test_appearance.py). Synthetic identities only.
 */
class AppearanceTest {
    private fun profile(id: Long, role: String, plan: String = "vip") =
        Profile(id = id, role = role, planSelected = true, profileSetupCompleted = true, subscription = Profile.Subscription(plan = plan, status = "active"))

    private val owner = profile(1, "owner")
    private val choice = AppearancePrefs("dark", "arena", "ciruela", "l", "editorial", "compact", "tonal")

    private fun api(plan: PlanTier, role: FakeBackend.Role) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, plan, role = role), AppLanguage.SPANISH, backoff = {}))

    @Test fun theClassicSetIsTodaysDincrAndTheOwnerDefaultIsTheOwnerIdentity() {
        assertEquals(AppearancePrefs("system", "clasico", "teal", "m", "system", "comfortable", "tonal"), AppearancePrefs.CLASSIC)
        assertEquals(AppearancePrefs("system", "oceano", "cian", "m", "system", "comfortable", "outlined"), AppearancePrefs.OWNER_DEFAULT)
        assertEquals(1f, AppearancePrefs.CLASSIC.textScale)
        assertEquals(1.3f, choice.with("text_size", "xl").textScale)
    }

    @Test fun anIdTheAppCannotDrawBecomesTheDefaultOptionByOption() {
        val stale = choice.copy(palette = "neon", accent = "", surfaces = "glass")
        assertEquals(choice.copy(palette = "oceano", accent = "cian", surfaces = "outlined"), stale.sanitized())
        assertEquals(choice, choice.sanitized())
        AppearanceCatalog.options.forEach { option -> assertTrue(option.key, option.values.size >= 2 && option.has(option.default) && option.has(option.classic)) }
    }

    @Test fun freeBasicAndVipAlwaysSeeTheClassicLookWhateverIsStoredOnTheDevice() {
        val cache = CachedAppearance(accountId = 7, preferences = choice)
        listOf("free", "basic", "vip").forEach { plan ->
            val user = profile(7, "user", plan)
            assertFalse(AppearancePolicy.isPersonalizable(user))
            assertEquals(AppearancePrefs.CLASSIC, AppearancePolicy.effective(user, saved = choice, cached = cache))
        }
        assertEquals(AppearancePrefs.CLASSIC, AppearancePolicy.effective(null, saved = choice, cached = cache))
        assertEquals("a role DINCR does not serve", AppearancePrefs.CLASSIC, AppearancePolicy.effective(profile(1, "admin"), choice, cache))
    }

    @Test fun theOwnerSeesItsChoiceThenItsOwnCacheThenTheDefault() {
        assertTrue(AppearancePolicy.isPersonalizable(owner))
        assertEquals(choice, AppearancePolicy.effective(owner, saved = choice, cached = null))
        assertEquals(choice, AppearancePolicy.effective(owner, saved = null, cached = CachedAppearance(1, choice)))
        assertEquals("another account's cache is never applied", AppearancePrefs.OWNER_DEFAULT,
            AppearancePolicy.effective(owner, saved = null, cached = CachedAppearance(2, choice)))
        assertEquals(AppearancePrefs.OWNER_DEFAULT, AppearancePolicy.effective(owner, saved = null, cached = null))
    }

    @Test fun theCacheRoundTripsAndAnUnreadableOneIsNoCache() {
        val cache = CachedAppearance(1, choice)
        assertEquals(cache, CachedAppearance.decode(cache.encode()))
        assertNull(CachedAppearance.decode(null))
        assertNull(CachedAppearance.decode("{not json"))
        assertNull(CachedAppearance.decode("""{"account_id":1}"""))
    }

    @Test fun theOwnerSavesReadsAndRestoresOnTheFixtureServer() = runBlocking {
        val api = api(PlanTier.FREE, FakeBackend.Role.OWNER)
        assertEquals(AppearanceState(preferences = AppearancePrefs.OWNER_DEFAULT, stored = false), api.appearance())
        assertEquals(choice, api.saveAppearance(choice).preferences)
        assertEquals(choice, api.appearance().preferences)
        assertTrue(api.appearance().stored)
        val reset = api.resetAppearance()
        assertEquals(AppearancePrefs.OWNER_DEFAULT, reset.preferences)
        assertFalse(reset.stored)
    }

    @Test fun freeBasicAndVipAreRefusedByTheFixtureServerAsByTheBackend() = runBlocking {
        listOf(PlanTier.FREE, PlanTier.BASIC, PlanTier.VIP).forEach { plan ->
            val api = api(plan, FakeBackend.Role.USER)
            listOf<suspend () -> Unit>({ api.appearance() }, { api.saveAppearance(choice) }, { api.resetAppearance() }).forEach { call ->
                try {
                    call()
                    fail("$plan reached the appearance routes")
                } catch (error: ApiError) {
                    assertEquals(403, error.status)
                }
            }
        }
    }
}
