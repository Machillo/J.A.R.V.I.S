import Foundation

/// Movimientos shows one month at a time (the current one when it opens), not the whole history.
/// The backend still returns every movement; this narrows what is on screen. A search looks
/// through every month, so an old movement can still be found by name. Android: `MovementMonth.kt`.
public enum MovementMonth {
    /// The rows to list: with a search, every month that matches; without one, only `month` ("YYYY-MM").
    public static func rows(_ rows: [Movement], month: String, query: String) -> [Movement] {
        let searching = !query.trimmingCharacters(in: .whitespaces).isEmpty
        return rows.filter { searching || ($0.day ?? "").hasPrefix(month) }
    }
}
