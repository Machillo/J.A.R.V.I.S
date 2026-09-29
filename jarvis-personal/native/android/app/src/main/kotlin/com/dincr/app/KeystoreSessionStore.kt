package com.dincr.app

import android.content.Context
import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.dincr.data.AuthSession
import com.dincr.data.Pkce
import com.dincr.data.SessionStore
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * Strings sealed with an AES-GCM key that never leaves the Android Keystore. The preferences file
 * is excluded from backup and device transfer (res/xml/data_extraction_rules.xml). A value that
 * cannot be opened (key reset, restored elsewhere) is dropped, never trusted.
 */
class SecureBox(context: Context, fileName: String) {
    private val prefs: SharedPreferences = context.getSharedPreferences(fileName, Context.MODE_PRIVATE)

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return generator.generateKey()
    }

    fun read(name: String): String? = runCatching {
        val payload = prefs.getString(name, null) ?: return null
        val bytes = Base64.decode(payload, Base64.NO_WRAP)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes, 0, IV_SIZE))
        String(cipher.doFinal(bytes, IV_SIZE, bytes.size - IV_SIZE), Charsets.UTF_8)
    }.getOrElse {
        remove(name)
        null
    }

    fun write(name: String, value: String) {
        val cipher = Cipher.getInstance(TRANSFORMATION).apply { init(Cipher.ENCRYPT_MODE, key()) }
        val sealed = cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        prefs.edit().putString(name, Base64.encodeToString(sealed, Base64.NO_WRAP)).commit()
    }

    fun remove(name: String) {
        prefs.edit().remove(name).commit()
    }

    private companion object {
        const val ALIAS = "dincr.session.key"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val IV_SIZE = 12
    }
}

/** The Supabase session, sealed by [SecureBox]. */
class KeystoreSessionStore(context: Context) : SessionStore {
    private val box = SecureBox(context, "dincr.session")
    private val json = Json { ignoreUnknownKeys = true }

    override fun load(): AuthSession? =
        box.read(KEY)?.let { runCatching { json.decodeFromString<AuthSession>(it) }.getOrNull() }

    override fun save(session: AuthSession) = box.write(KEY, json.encodeToString(AuthSession.serializer(), session))

    override fun clear() = box.remove(KEY)

    private companion object {
        const val KEY = "session"
    }
}

/**
 * The PKCE verifier of a sign-in in progress. Android may end the process while the browser is
 * open; keeping the verifier (sealed, for ten minutes, one attempt) lets the return complete.
 */
class PendingSignInStore(context: Context, private val now: () -> Long = System::currentTimeMillis) {
    private val box = SecureBox(context, "dincr.session")
    private val json = Json { ignoreUnknownKeys = true }

    @Serializable
    private data class Pending(val verifier: String, val createdAtMs: Long)

    fun save(pkce: Pkce) = box.write(KEY, json.encodeToString(Pending.serializer(), Pending(pkce.verifier, now())))

    /** The pending verifier, consumed: a second return can never reuse it. */
    fun take(): Pkce? {
        val pending = box.read(KEY)?.let { runCatching { json.decodeFromString<Pending>(it) }.getOrNull() }
        box.remove(KEY)
        return pending?.takeIf { now() - it.createdAtMs in 0..TTL_MS }?.let { Pkce(it.verifier) }
    }

    fun clear() = box.remove(KEY)

    private companion object {
        const val KEY = "pending_sign_in"
        const val TTL_MS = 10 * 60 * 1000L
    }
}
