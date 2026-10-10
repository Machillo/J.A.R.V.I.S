package com.dincr.data

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * BIL-03 parity: a store subscription is live exactly in the backend's states
 * (`product_ops.store_billing.ACTIVE_STATES`). It used to read `grace` instead of the backend's
 * `grace_period`, so a subscription in its grace period could start a second purchase. iOS:
 * `StoreModelsTests.aStoreSubscriptionIsLiveExactlyInTheBackendsStates`.
 */
class StoreEntitlementTest {
    @Test fun aStoreSubscriptionIsLiveExactlyInTheBackendsStates() {
        for (status in listOf("trialing", "active", "grace_period")) {
            assertTrue(status, StoreEntitlement(status = status, provider = "google").isLive)
            assertTrue(status, StoreEntitlement(status = status, provider = "apple").isLive)
        }
        for (status in listOf("free", "expired", "revoked", "cancel_requested", "grace", "paused")) {
            assertFalse(status, StoreEntitlement(status = status, provider = "google").isLive)
        }
        assertFalse("a courtesy or Owner plan is not a store subscription", StoreEntitlement(status = "active", provider = null).isLive)
        assertFalse(StoreEntitlement(status = "active", provider = "sandbox").isLive)
    }
}
