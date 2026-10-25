package com.dincr.data

import com.dincr.data.generated.AppearanceCatalog
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * A personal appearance (APP-1): one closed id per option of the shared catalog
 * (`design-tokens/appearance.json` → [AppearanceCatalog]). The backend accepts exactly these ids
 * (`/user-product/appearance`); iOS: `AppearancePreferences` in DincrCore.
 */
@Serializable
data class AppearancePrefs(
    val theme: String,
    val palette: String,
    val accent: String,
    @SerialName("text_size") val textSize: String,
    val typeface: String,
    val density: String,
    val surfaces: String,
) {
    private fun value(key: String) = when (key) {
        "theme" -> theme
        "palette" -> palette
        "accent" -> accent
        "text_size" -> textSize
        "typeface" -> typeface
        "density" -> density
        "surfaces" -> surfaces
        else -> error("unknown appearance option $key")
    }

    /** The same choice with one option changed (the caller passes an id of that option). */
    fun with(key: String, id: String): AppearancePrefs = when (key) {
        "theme" -> copy(theme = id)
        "palette" -> copy(palette = id)
        "accent" -> copy(accent = id)
        "text_size" -> copy(textSize = id)
        "typeface" -> copy(typeface = id)
        "density" -> copy(density = id)
        "surfaces" -> copy(surfaces = id)
        else -> error("unknown appearance option $key")
    }

    fun id(key: String): String = value(key)

    /** Every option a catalog id; one the app can't draw (an old cache, a newer server) becomes the default. */
    fun sanitized(): AppearancePrefs = AppearanceCatalog.options.fold(this) { prefs, option ->
        if (option.has(prefs.value(option.key))) prefs else prefs.with(option.key, option.default)
    }

    /** The text size factor on top of the system font scale. */
    val textScale: Float get() = AppearanceCatalog.option("text_size").values.first { it.id == sanitized().textSize }.scale ?: 1f

    companion object {
        private fun from(pick: (com.dincr.data.generated.AppearanceOption) -> String) =
            AppearanceCatalog.options.fold(AppearancePrefs("", "", "", "", "", "", "")) { prefs, option -> prefs.with(option.key, pick(option)) }

        /** The Owner's starting point (the Owner identity: Océano + Cian, outlined surfaces). */
        val OWNER_DEFAULT: AppearancePrefs = from { it.default }

        /** Today's DINCR, exactly (DESIGN.md): what every account that does not personalize sees. */
        val CLASSIC: AppearancePrefs = from { it.classic }
    }
}

/** `GET/PUT/DELETE /user-product/appearance`. */
@Serializable
data class AppearanceState(
    val version: Int = AppearanceCatalog.VERSION,
    val preferences: AppearancePrefs,
    val stored: Boolean = false,
    @SerialName("updated_at") val updatedAt: String? = null,
)

/** The last appearance the Owner saved on this device, tied to the account that saved it. */
@Serializable
data class CachedAppearance(@SerialName("account_id") val accountId: Long, val preferences: AppearancePrefs) {
    fun encode(): String = cacheJson.encodeToString(serializer(), this)

    companion object {
        private val cacheJson = Json { ignoreUnknownKeys = true }

        /** A missing or unreadable cache is no cache (never an error). */
        fun decode(raw: String?): CachedAppearance? = raw?.let { runCatching { cacheJson.decodeFromString(serializer(), it) }.getOrNull() }
    }
}

/**
 * Who personalizes and what each account sees (APP-1, phase 1: the Owner only). The backend
 * refuses the routes to everyone else; this keeps the apps from drawing anything but the classic
 * look for them, whatever is stored on the device.
 */
object AppearancePolicy {
    fun isPersonalizable(profile: Profile?): Boolean = profile?.isOwner == true

    /**
     * Everyone else: [AppearancePrefs.CLASSIC]. The Owner: what the server returned, else the
     * cache of the same account (so the app starts in the Owner's look before the network), else
     * the Owner default. A cache from another account is never applied.
     */
    fun effective(profile: Profile?, saved: AppearancePrefs?, cached: CachedAppearance?): AppearancePrefs = when {
        !isPersonalizable(profile) -> AppearancePrefs.CLASSIC
        saved != null -> saved.sanitized()
        cached != null && cached.accountId == profile!!.id -> cached.preferences.sanitized()
        else -> AppearancePrefs.OWNER_DEFAULT
    }
}
