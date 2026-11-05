package com.dincr.data

import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertTrue
import org.junit.Test

class SignOutTimeoutTest {
    @Test fun signingOutNeverWaitsLongForTheNetwork() = runBlocking {
        val client = SupabaseAuthClient("https://project.example.test", "synthetic", HttpTransport { awaitCancellation() })
        val started = System.currentTimeMillis()
        client.signOut("synthetic")
        assertTrue(System.currentTimeMillis() - started < 8_000)
    }
}
