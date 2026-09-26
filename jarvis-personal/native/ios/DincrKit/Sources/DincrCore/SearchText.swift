import Foundation

/// Presentation-only search over rows the backend already returned: case- and accent-insensitive
/// ("credito" finds "Crédito"). It narrows what is on screen; it never classifies or decides.
public enum SearchText {
    public static func matches(_ query: String, in fields: [String?]) -> Bool {
        let term = normalize(query)
        guard !term.isEmpty else { return true }
        return fields.contains { normalize($0 ?? "").contains(term) }
    }

    static func normalize(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive, .widthInsensitive], locale: Locale(identifier: "es"))
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
