import Foundation

/// How far a scheduled day is from today, in words: "Hoy", "Mañana", "En 5 días", "Hace 2 días".
/// Only the distance: a past day doesn't say whether it was paid. A value that isn't a day has no
/// label (never a guess). Android: `DaysLeft.kt`.
public enum DaysLeft {
    public static func label(_ day: String?, today: String, language: AppLanguage = .current) -> String? {
        guard let from = date(today), let to = date(day),
              let days = calendar.dateComponents([.day], from: from, to: to).day else { return nil }
        switch days {
        case 0: return language.pick("Hoy", "Today")
        case 1: return language.pick("Mañana", "Tomorrow")
        case -1: return language.pick("Ayer", "Yesterday")
        case 2...: return language.pick("En \(days) días", "In \(days) days")
        default: return language.pick("Hace \(-days) días", "\(-days) days ago")
        }
    }

    private static let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC") ?? .current
        return calendar
    }()

    private static func date(_ day: String?) -> Date? {
        guard let day else { return nil }
        let formatter = DateFormatter()
        formatter.calendar = calendar
        formatter.timeZone = calendar.timeZone
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: String(day.prefix(10)))
    }
}
