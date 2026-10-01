package com.dincr.data

import java.text.Normalizer

/**
 * Bank identification, ported from the Capacitor app (`frontend/src/lib/bankIdentity.js` +
 * `bankBranding.js`): an institution code or a bank name → a known bank. Presentation only (no data,
 * no Owner tools). A bank without a known identity keeps its initials, so a missing logo never
 * breaks a screen. Which banks have a logo is decided by the app ([Bank.hasLogo]): only the
 * historical assets of `frontend/src/assets/institutions/` exist, nothing is downloaded or invented.
 */
object BankBranding {
    data class Bank(val id: String, val name: String, val short: String, val known: Boolean) {
        /** The historical assets: bac, bcr, bn, davibank, davivienda, multimoney, popular, promerica. */
        val hasLogo: Boolean get() = known && id in LOGO_IDS

        /**
         * The historical MultiMoney logo is drawn in white on a transparent background: invisible on
         * the usual white tile. The web app put it on a dark tile (ProfileSetup.css
         * `.bank-mark--logo.bank-mark--violet`, #203046); the native tile does the same. iOS: `BankBrand.logoNeedsDarkTile`.
         */
        val logoNeedsDarkTile: Boolean get() = hasLogo && id in WHITE_LOGO_IDS
    }

    /** Logos drawn in white (see [Bank.logoNeedsDarkTile]). */
    val WHITE_LOGO_IDS = setOf("multimoney")

    private data class Identity(val id: String, val name: String, val short: String, val codes: Set<String>, val text: Regex)

    // Order matters for free text: "banco nacional de costa rica" must win over "banco de costa rica".
    private val IDENTITIES = listOf(
        Identity("bac", "BAC Credomatic", "BAC", setOf("bac", "baccredomatic", "credomatic"), Regex("""\bbac\b|credomatic""")),
        Identity("multimoney", "MultiMoney", "MM", setOf("multimoney", "mm"), Regex("""multi ?money""")),
        Identity("bn", "Banco Nacional", "BN", setOf("bn", "bncr", "banconacional", "banconacionaldecostarica"), Regex("""banco nacional|\bbncr\b""")),
        Identity("bcr", "Banco de Costa Rica", "BCR", setOf("bcr", "bancodecostarica", "bancobcr"), Regex("""banco de costa rica|\bbancobcr\b|\bbcr\b""")),
        Identity("popular", "Banco Popular", "BP", setOf("popular", "bancopopular", "bp", "bpdc"), Regex("""banco popular|bancopopular""")),
        Identity("davibank", "Davibank", "DB", setOf("davibank", "scotiabank"), Regex("""davibank|scotiabank""")),
        Identity("davivienda", "Davivienda", "DV", setOf("davivienda"), Regex("""davivienda""")),
        Identity("promerica", "Promerica", "PR", setOf("promerica", "bancopromerica"), Regex("""promerica""")),
    )

    val LOGO_IDS = setOf("bac", "bcr", "bn", "davibank", "davivienda", "multimoney", "popular", "promerica")

    /** The known banks, in the historical order. */
    val KNOWN: List<Bank> get() = IDENTITIES.map { Bank(it.id, it.name, it.short, true) }

    private fun plain(value: String?): String =
        Normalizer.normalize(value.orEmpty(), Normalizer.Form.NFD).replace(Regex("""\p{Mn}+"""), "").lowercase()

    private fun compact(value: String?): String = plain(value).replace(Regex("[^a-z0-9]"), "")

    /** Exact institution code or bank name (e.g. `institution_code`, `candidate.bank`); null when unknown. */
    fun identify(identifier: String?): Bank? {
        val key = compact(identifier)
        if (key.isEmpty() || key == "unknown") return null
        val found = IDENTITIES.firstOrNull { key in it.codes || compact(it.name) == key }
            ?: IDENTITIES.firstOrNull { it.text.containsMatchIn(plain(identifier)) }
        return found?.let { Bank(it.id, it.name, it.short, true) }
    }

    /** Free text such as an email sender or subject. */
    fun identifyInText(text: String?): Bank? {
        val value = plain(text)
        if (value.isEmpty()) return null
        return IDENTITIES.firstOrNull { it.text.containsMatchIn(value) }?.let { Bank(it.id, it.name, it.short, true) }
    }

    /** Always displayable: a known bank, or initials for an unknown institution. */
    fun describe(identifier: String?, fallbackName: String? = null): Bank {
        identify(identifier)?.let { return it }
        identify(fallbackName)?.let { return it }
        val name = (fallbackName?.takeIf { it.isNotBlank() } ?: identifier).orEmpty().trim()
        return Bank(compact(name).ifEmpty { "unknown" }, name, if (name.isNotEmpty()) initials(name) else "?", false)
    }

    fun initials(name: String): String {
        val words = plain(name).replace(Regex("[^a-z0-9 ]"), " ").split(Regex("""\s+"""))
            .filter { it.isNotEmpty() && it !in setOf("banco", "de", "del", "la", "el") }
        return (if (words.size > 1) words.take(2).joinToString("") { it.take(1) } else (words.firstOrNull() ?: "?").take(3)).uppercase()
    }

    /**
     * The institutions offered in onboarding, with the ids the profile already stores
     * (`selected_financial_institutions`): DAVIbank keeps the historical id `scotiabank`.
     */
    data class Institution(val id: String, val logoId: String, val name: String)

    fun onboardingInstitutions(language: AppLanguage): List<Institution> = listOf(
        Institution("bac", "bac", "BAC Credomatic"),
        Institution("bn", "bn", "Banco Nacional"),
        Institution("bcr", "bcr", "Banco de Costa Rica"),
        Institution("popular", "popular", "Banco Popular"),
        Institution("davivienda", "davivienda", "Davivienda"),
        Institution("scotiabank", "davibank", language.pick("DAVIbank (antes Scotiabank)", "DAVIbank (formerly Scotiabank)")),
        Institution("promerica", "promerica", "Promerica"),
        Institution("multimoney", "multimoney", "MultiMoney"),
    )
}
