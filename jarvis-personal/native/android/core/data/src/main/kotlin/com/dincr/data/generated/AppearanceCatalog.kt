// GENERATED from jarvis-personal/native/design-tokens/appearance.json (DINCR 3.0.0) by generate.mjs.
// Do not edit. Change appearance.json and run the generator.
package com.dincr.data.generated

data class AppearanceOptionValue(val id: String, val es: String, val en: String, val scale: Float? = null)

data class AppearanceOption(val key: String, val default: String, val classic: String, val values: List<AppearanceOptionValue>) {
    fun has(id: String?) = values.any { it.id == id }
}

object AppearanceCatalog {
    const val VERSION = 1

    val options: List<AppearanceOption> = listOf(
        AppearanceOption(
            key = "theme", default = "system", classic = "system",
            values = listOf(
                AppearanceOptionValue("system", "Automático", "Automatic"),
                AppearanceOptionValue("light", "Claro", "Light"),
                AppearanceOptionValue("dark", "Oscuro", "Dark"),
            ),
        ),
        AppearanceOption(
            key = "palette", default = "oceano", classic = "clasico",
            values = listOf(
                AppearanceOptionValue("oceano", "Océano", "Ocean"),
                AppearanceOptionValue("clasico", "Clásico", "Classic"),
                AppearanceOptionValue("arena", "Arena", "Sand"),
                AppearanceOptionValue("grafito", "Grafito", "Graphite"),
            ),
        ),
        AppearanceOption(
            key = "accent", default = "cian", classic = "teal",
            values = listOf(
                AppearanceOptionValue("cian", "Cian", "Cyan"),
                AppearanceOptionValue("teal", "Verde azulado", "Teal"),
                AppearanceOptionValue("ciruela", "Ciruela", "Plum"),
                AppearanceOptionValue("tinta", "Tinta", "Ink"),
            ),
        ),
        AppearanceOption(
            key = "text_size", default = "m", classic = "m",
            values = listOf(
                AppearanceOptionValue("s", "Pequeño", "Small", scale = 0.9f),
                AppearanceOptionValue("m", "Estándar", "Standard", scale = 1.0f),
                AppearanceOptionValue("l", "Grande", "Large", scale = 1.15f),
                AppearanceOptionValue("xl", "Muy grande", "Extra large", scale = 1.3f),
            ),
        ),
        AppearanceOption(
            key = "typeface", default = "system", classic = "system",
            values = listOf(
                AppearanceOptionValue("system", "Sistema", "System"),
                AppearanceOptionValue("editorial", "Editorial (títulos con serifa)", "Editorial (serif headings)"),
            ),
        ),
        AppearanceOption(
            key = "density", default = "comfortable", classic = "comfortable",
            values = listOf(
                AppearanceOptionValue("comfortable", "Cómoda", "Comfortable"),
                AppearanceOptionValue("compact", "Compacta", "Compact"),
            ),
        ),
        AppearanceOption(
            key = "surfaces", default = "outlined", classic = "tonal",
            values = listOf(
                AppearanceOptionValue("outlined", "Con contorno", "Outlined"),
                AppearanceOptionValue("tonal", "Tonal", "Tonal"),
            ),
        ),
    )

    fun option(key: String): AppearanceOption = options.first { it.key == key }
}
