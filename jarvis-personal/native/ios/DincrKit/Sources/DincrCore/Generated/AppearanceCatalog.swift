// GENERATED from jarvis-personal/native/design-tokens/appearance.json (DINCR 2.0.0) by generate.mjs.
// Do not edit. Change appearance.json and run the generator.
import Foundation

public struct AppearanceOptionValue: Sendable, Equatable {
    public let id: String
    public let es: String
    public let en: String
    public let scale: Double?

    public init(id: String, es: String, en: String, scale: Double? = nil) {
        self.id = id; self.es = es; self.en = en; self.scale = scale
    }
}

public struct AppearanceOption: Sendable, Equatable {
    public let key: String
    public let defaultValue: String
    public let classic: String
    public let values: [AppearanceOptionValue]

    public func has(_ id: String?) -> Bool { values.contains { $0.id == id } }
}

public enum AppearanceCatalog {
    public static let version = 1

    public static let options: [AppearanceOption] = [
        AppearanceOption(
            key: "theme", defaultValue: "system", classic: "system",
            values: [
                AppearanceOptionValue(id: "system", es: "Automático", en: "Automatic"),
                AppearanceOptionValue(id: "light", es: "Claro", en: "Light"),
                AppearanceOptionValue(id: "dark", es: "Oscuro", en: "Dark"),
            ]
        ),
        AppearanceOption(
            key: "palette", defaultValue: "oceano", classic: "clasico",
            values: [
                AppearanceOptionValue(id: "oceano", es: "Océano", en: "Ocean"),
                AppearanceOptionValue(id: "clasico", es: "Clásico", en: "Classic"),
                AppearanceOptionValue(id: "arena", es: "Arena", en: "Sand"),
                AppearanceOptionValue(id: "grafito", es: "Grafito", en: "Graphite"),
            ]
        ),
        AppearanceOption(
            key: "accent", defaultValue: "cian", classic: "teal",
            values: [
                AppearanceOptionValue(id: "cian", es: "Cian", en: "Cyan"),
                AppearanceOptionValue(id: "teal", es: "Verde azulado", en: "Teal"),
                AppearanceOptionValue(id: "ciruela", es: "Ciruela", en: "Plum"),
                AppearanceOptionValue(id: "tinta", es: "Tinta", en: "Ink"),
            ]
        ),
        AppearanceOption(
            key: "text_size", defaultValue: "m", classic: "m",
            values: [
                AppearanceOptionValue(id: "s", es: "Pequeño", en: "Small", scale: 0.9),
                AppearanceOptionValue(id: "m", es: "Estándar", en: "Standard", scale: 1),
                AppearanceOptionValue(id: "l", es: "Grande", en: "Large", scale: 1.15),
                AppearanceOptionValue(id: "xl", es: "Muy grande", en: "Extra large", scale: 1.3),
            ]
        ),
        AppearanceOption(
            key: "typeface", defaultValue: "system", classic: "system",
            values: [
                AppearanceOptionValue(id: "system", es: "Sistema", en: "System"),
                AppearanceOptionValue(id: "editorial", es: "Editorial (títulos con serifa)", en: "Editorial (serif headings)"),
            ]
        ),
        AppearanceOption(
            key: "density", defaultValue: "comfortable", classic: "comfortable",
            values: [
                AppearanceOptionValue(id: "comfortable", es: "Cómoda", en: "Comfortable"),
                AppearanceOptionValue(id: "compact", es: "Compacta", en: "Compact"),
            ]
        ),
        AppearanceOption(
            key: "surfaces", defaultValue: "outlined", classic: "tonal",
            values: [
                AppearanceOptionValue(id: "outlined", es: "Con contorno", en: "Outlined"),
                AppearanceOptionValue(id: "tonal", es: "Tonal", en: "Tonal"),
            ]
        ),
    ]

    public static func option(_ key: String) -> AppearanceOption? { options.first { $0.key == key } }
}
