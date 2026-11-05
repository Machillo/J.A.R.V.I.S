import Foundation

/// When to offer the store's own rating dialog. A person is asked only after real use and never
/// often; the store still decides whether the dialog shows, and DINCR never learns the answer.
/// Android twin: `RatingPrompt.kt`.
public enum RatingPrompt {
    public static let minimumDays = 7
    public static let minimumSaves = 5
    public static let daysBetweenAsks = 120

    public static func shouldAsk(firstOpen: Date, saves: Int, lastAsked: Date?, now: Date) -> Bool {
        guard saves >= minimumSaves, days(from: firstOpen, to: now) >= minimumDays else { return false }
        guard let lastAsked else { return true }
        return days(from: lastAsked, to: now) >= daysBetweenAsks
    }

    private static func days(from start: Date, to end: Date) -> Int {
        Int(end.timeIntervalSince(start) / 86_400)
    }
}
