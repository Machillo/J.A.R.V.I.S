import Foundation

/// The Owner's agenda (JARVIS recovery, J2): the historical "Próximos eventos" of JARVIS.
///
/// `GET /jarvis/calendar/upcoming?days=45` answers `{"events": [...]}`: rows of the historical
/// `events` table, from today to 45 days out, in chronological order. The same events the chat
/// answers "¿qué tengo?" with, and the ones a confirmed chat event adds; events are created only
/// through the chat, as they always were. Android twin: `JarvisAgenda.kt`.
public enum JarvisAgenda {
    /// The horizon of the historical agenda card (backend `AGENDA_DAYS`).
    public static let days = 45

    /// One day of the agenda: its events, in the backend's order.
    public struct Day: Identifiable, Equatable, Sendable {
        public let day: String
        public let events: [JarvisEvent]
        public var id: String { day }
    }

    /// Groups the events by day (presentation only), keeping the backend's chronological order.
    public static func days(_ events: [JarvisEvent]) -> [Day] {
        var order: [String] = []
        var grouped: [String: [JarvisEvent]] = [:]
        for event in events {
            if grouped[event.day] == nil { order.append(event.day) }
            grouped[event.day, default: []].append(event)
        }
        return order.map { Day(day: $0, events: grouped[$0] ?? []) }
    }
}

/// One row of the `events` table as the backend sends it. Only `id`, `title` and `event_date` are
/// required; `event_date` is the stored text ("YYYY-MM-DD" or "YYYY-MM-DD HH:MM") and is shown, not
/// reinterpreted.
public struct JarvisEvent: Decodable, Identifiable, Equatable, Sendable {
    public let id: Int
    public let title: String
    public let eventDate: String
    public let eventType: String?
    public let description: String?

    public init(id: Int, title: String, eventDate: String, eventType: String? = nil, description: String? = nil) {
        self.id = id; self.title = title; self.eventDate = eventDate; self.eventType = eventType; self.description = description
    }

    /// "YYYY-MM-DD": the day the backend filtered and sorted by.
    public var day: String { String(eventDate.trimmingCharacters(in: .whitespaces).prefix(10)) }

    /// "HH:MM" when the stored date carries a time, nil otherwise.
    public var time: String? {
        let text = eventDate.trimmingCharacters(in: .whitespaces)
        guard text.count > 10 else { return nil }
        let rest = text.dropFirst(10).trimmingCharacters(in: CharacterSet(charactersIn: " T"))
        return rest.isEmpty ? nil : String(rest.prefix(5))
    }

    /// The day as a calendar date (presentation), nil if the text is not a real day.
    public var date: Date? {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = .current
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.isLenient = false
        return formatter.date(from: day)
    }
}

/// `{"events": [...]}`; a row that cannot be read is left out instead of failing the whole agenda.
public struct JarvisAgendaResponse: Decodable, Sendable {
    public let events: [JarvisEvent]

    enum CodingKeys: String, CodingKey { case events }

    private struct Row: Decodable {
        let event: JarvisEvent?
        init(from decoder: Decoder) throws { event = try? JarvisEvent(from: decoder) }
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        events = try container.decode([Row].self, forKey: .events).compactMap(\.event)
    }
}
