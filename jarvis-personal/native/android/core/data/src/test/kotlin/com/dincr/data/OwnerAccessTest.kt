package com.dincr.data

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Where a signed-in identity lands in the public app, and what it offers. The server decides the
 * role and the plan; the app only routes. The Swift twin is `OwnerAccessTests`.
 */
class OwnerAccessTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    private fun profile(role: String?, plan: String?, planSelected: Boolean? = true, profileSetup: Boolean? = true, legalRequired: Boolean = false) =
        Profile(
            id = 1, role = role, planSelected = planSelected, profileSetupCompleted = profileSetup,
            subscription = plan?.let { Profile.Subscription(plan = it, status = "active") },
            legal = Profile.Legal(required = legalRequired),
        )

    @Test fun freeBasicAndVipEnterTheirOwnExperience() {
        listOf("free" to PlanTier.FREE, "basic" to PlanTier.BASIC, "vip" to PlanTier.VIP).forEach { (plan, tier) ->
            val user = profile("user", plan)
            assertEquals(IdentityGate.READY, IdentityGate.of(user))
            assertEquals(tier, user.planTier)
        }
    }

    @Test fun ownerEntersThePublicAppWithAtLeastVip() {
        // Whatever the stored plan code (the backend seeds Owner as vip with access_source owner).
        listOf("vip", "owner", "free", null).forEach { plan ->
            val owner = profile("owner", plan, planSelected = false)
            assertEquals("Owner's plan is granted by the backend, never chosen", IdentityGate.READY, IdentityGate.of(owner))
            assertEquals(PlanTier.VIP, owner.planTier)
            assertTrue(Feature.entries.all { owner.planTier.allows(it) })
        }
        // Owner still goes through the legal and profile steps like anyone else.
        assertEquals(IdentityGate.LEGAL_REQUIRED, IdentityGate.of(profile("owner", "vip", legalRequired = true)))
        assertEquals(IdentityGate.PROFILE_SETUP, IdentityGate.of(profile("owner", "vip", profileSetup = false)))
    }

    @Test fun ownerGetsNoInternalScreens() {
        // The public app has no tier above VIP and no internal feature: Owner sees exactly VIP.
        assertEquals(listOf(PlanTier.FREE, PlanTier.BASIC, PlanTier.VIP), PlanTier.entries.toList())
        val owner = profile("owner", "owner")
        assertEquals(Feature.entries.filter { PlanTier.VIP.allows(it) }, Feature.entries.filter { owner.planTier.allows(it) })
        // Admin sessions stay out of the public app, as before.
        assertEquals(IdentityGate.UNSUPPORTED_ROLE, IdentityGate.of(profile("admin", "vip")))
        assertFalse(profile("admin", "vip").isOwner)
    }

    @Test fun theOwnerAccountIsNeverDeletedFromThePublicApp() {
        // DELETE /auth/me has no Owner guard on the server; the public app never offers it to Owner.
        assertFalse(profile("owner", "vip").canDeleteAccountInApp)
        listOf("free", "basic", "vip").forEach { assertTrue(profile("user", it).canDeleteAccountInApp) }
    }

    @Test fun noClientPathTurnsAUserIntoOwner() {
        // A plan code alone never elevates: only the server's role does.
        val user = profile("user", "owner")
        assertFalse(user.isOwner)
        assertEquals(PlanTier.FREE, user.planTier)
        assertEquals(PlanTier.FREE, PlanTier.from("owner"))
        // The role is read-only data from the server, and a missing role is not Owner.
        assertEquals("user", user.copy(planSelected = true, subscription = Profile.Subscription(plan = "vip")).role)
        val unknown = json.decodeFromString<Profile>("""{"id":1,"subscription":{"plan":"owner"}}""")
        assertFalse(unknown.isOwner)
        assertEquals(PlanTier.FREE, unknown.planTier)
        // The plans a user can pick never include Owner.
        assertFalse(PlanTier.entries.any { it.wire == "owner" })
    }
}
