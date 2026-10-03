package com.dincr.data

import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JARVIS (recovery roadmap J0): the Owner's personal space. Only the server's role opens it: never
 * a plan, a flag in the payload or a local copy of the profile. The Swift twin is `JarvisAccessTests`.
 */
class JarvisAccessTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    private fun profile(role: String?, plan: String?) =
        Profile(id = 1, role = role, planSelected = true, profileSetupCompleted = true, subscription = plan?.let { Profile.Subscription(plan = it, status = "active") })

    private fun api(plan: PlanTier = PlanTier.FREE, role: FakeBackend.Role = FakeBackend.Role.USER) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, plan, role = role), AppLanguage.SPANISH, backoff = {}))

    @Test fun onlyTheOwnerGetsJarvis() {
        // Free, Basic and VIP accounts never get it.
        listOf("free", "basic", "vip", null).forEach { assertFalse(it.toString(), Jarvis.isAvailable(profile("user", it))) }
        // The Owner does, whatever its stored plan code.
        listOf("vip", "owner", "free", null).forEach { assertTrue(it.toString(), Jarvis.isAvailable(profile("owner", it))) }
        // Admin is not the Owner; no identity (signed out, still loading) gets nothing.
        assertFalse(Jarvis.isAvailable(profile("admin", "vip")))
        assertFalse(Jarvis.isAvailable(null))
    }

    @Test fun theOwnerKeepsEveryDincrScreen() {
        // JARVIS is added on top of the public app: the Owner still enters it at VIP level.
        val owner = profile("owner", "vip")
        assertEquals(IdentityGate.READY, IdentityGate.of(owner))
        assertEquals(PlanTier.VIP, owner.planTier)
        assertTrue(Feature.entries.all { owner.planTier.allows(it) })
        // …and admin still stays out of the public app.
        assertEquals(IdentityGate.INTERNAL_ONLY, IdentityGate.of(profile("admin", "vip")))
    }

    @Test fun noClientStateOpensJarvis() {
        // Plan codes, look-alike roles and extra flags in the payload never elevate.
        listOf(
            """{"id":1,"role":"user","subscription":{"plan":"owner","access_source":"owner"}}""",
            """{"id":1,"role":"user","is_owner":true,"jarvis":true,"owner":true}""",
            """{"id":1,"role":"Owner"}""", """{"id":1,"role":" owner"}""", """{"id":1,"role":"OWNER"}""",
            """{"id":1}""",
        ).forEach { assertFalse(it, Jarvis.isAvailable(json.decodeFromString<Profile>(it))) }
        // A copy that changes the plan keeps the server's role.
        val user = profile("user", "vip")
        assertFalse(Jarvis.isAvailable(user.copy(subscription = Profile.Subscription(plan = "owner", status = "active"))))
    }

    @Test fun theChatTheAgendaTheAnalysisAndMoneyControlAreThePortedSections() {
        // J1 ports the chat, J2 the agenda, the analysis is the web Finanzas tab and money control its
        // cuentas por cobrar; every other section still opens a "being restored" screen.
        assertEquals(listOf(Jarvis.Section.CALENDAR, Jarvis.Section.CHAT, Jarvis.Section.MONEY_CONTROL, Jarvis.Section.ANALYSIS).sorted(),
            Jarvis.Section.entries.filter { it.isAvailable }.sorted())
        // The same sections and wire names as iOS (`Jarvis.Section`).
        assertEquals(listOf("chat", "memory", "calendar", "strategy", "money", "money_control", "wealth", "records", "analysis"), Jarvis.Section.entries.map { it.wire })
        assertEquals(Jarvis.Section.MONEY_CONTROL, Jarvis.Section.from("money_control"))
        assertEquals(null, Jarvis.Section.from("admin"))
    }

    @Test fun theFixtureServerDecidesTheRole() = runTest {
        // What the app knows about the role comes from /auth/me, as with the real backend.
        val owner = api(role = FakeBackend.Role.OWNER).me()
        assertTrue(owner.isOwner && Jarvis.isAvailable(owner))
        assertEquals("vip", owner.subscription?.plan)
        assertEquals("owner", owner.subscription?.accessSource)
        val admin = api(PlanTier.VIP, FakeBackend.Role.ADMIN).me()
        assertFalse(Jarvis.isAvailable(admin))
        assertEquals(IdentityGate.INTERNAL_ONLY, IdentityGate.of(admin))
        PlanTier.entries.forEach { plan ->
            val user = api(plan).me()
            assertEquals("user", user.role)
            assertFalse(Jarvis.isAvailable(user))
        }
    }
}
