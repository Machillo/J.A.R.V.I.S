package com.dincr.data

import java.text.Normalizer
import java.util.Locale

/**
 * Presentation-only search over rows the backend already returned: case- and accent-insensitive
 * ("credito" finds "Crédito"), same as iOS. It narrows what is on screen; it never decides.
 */
object SearchText {
    private val marks = Regex("\\p{M}+")

    fun matches(query: String, fields: List<String?>): Boolean {
        val term = normalize(query)
        if (term.isEmpty()) return true
        return fields.any { normalize(it.orEmpty()).contains(term) }
    }

    internal fun normalize(text: String): String =
        Normalizer.normalize(text, Normalizer.Form.NFD).replace(marks, "").lowercase(Locale.ROOT).trim()
}
