package com.dincr.data

import java.net.URLEncoder

/** Backend operations the native app uses; 1:1 with the Capacitor app's routes (parity IDs). */
interface DincrService {
    /** A5, A14 */ suspend fun me(): Profile
    /** A9 */ suspend fun completeProfileSetup(setup: ProfileSetup): Profile
    /** C1 */ suspend fun freeDashboard(): FreeDashboard
    /** D1, D5 */ suspend fun movements(): List<Movement>
    /** D3. [idempotencyKey] identifies one user submission: sending it again cannot create a second row. */
    suspend fun create(kind: MovementKind, entry: EntryCreate, idempotencyKey: String)
    /** D4, D5 */ suspend fun update(movementId: String, update: MovementUpdate)
    /** D6 */ suspend fun delete(movementId: String)
}

@kotlinx.serialization.Serializable
internal data class Acknowledgement(val status: String? = null)

class LiveDincrService(private val client: ApiClient) : DincrService {
    override suspend fun me(): Profile = client.get("/auth/me")
    override suspend fun completeProfileSetup(setup: ProfileSetup): Profile =
        client.send<ProfileSetup, ProfileEnvelope>("POST", "/auth/profile-setup", setup).profile
    override suspend fun freeDashboard(): FreeDashboard = client.get("/user-product/free/dashboard")
    override suspend fun movements(): List<Movement> = client.get("/user-product/free/movements")
    override suspend fun create(kind: MovementKind, entry: EntryCreate, idempotencyKey: String) {
        val path = if (kind == MovementKind.INCOME) "/user-product/finance/income" else "/user-product/finance/expenses"
        client.send<EntryCreate, Acknowledgement>("POST", path, entry, idempotencyKey)
    }
    override suspend fun update(movementId: String, update: MovementUpdate) {
        client.send<MovementUpdate, Acknowledgement>("PUT", "/user-product/free/movements/${encode(movementId)}", update)
    }
    override suspend fun delete(movementId: String) {
        client.send<Acknowledgement>("DELETE", "/user-product/free/movements/${encode(movementId)}")
    }

    companion object {
        /** Movement ids look like `expense:42`; keep the colon, escape anything path-breaking. */
        fun encode(id: String): String = URLEncoder.encode(id, "UTF-8").replace("%3A", ":").replace("+", "%20")
    }
}
