import Foundation

// Models behind the shared visual components (DESIGN.md → Data visualization).
// Visualize information; do not invent information: these types only describe values the caller
// already has. An unknown value stays unknown (never 0), a proportion exists only when the whole
// is known and positive, gaps in a series stay gaps, and a direction never decides by itself
// whether something is good or bad. Android mirrors them in `com.dincr.data.VisualModels`.

// MARK: - Composition (donut)

/// One part of a whole. `value == nil` means unknown. `currency`, when given, must match the other
/// parts: values in different currencies are never added together.
public struct CompositionItem: Sendable, Equatable, Identifiable {
    public let id: String
    public let label: String
    public let value: Decimal?
    public let currency: String?

    public init(id: String, label: String, value: Decimal?, currency: String? = nil) {
        self.id = id; self.label = label; self.value = value; self.currency = currency
    }
}

/// A whole split into parts, with each part's share only when it can be computed honestly.
public struct Composition: Sendable, Equatable {
    public enum Status: Sendable, Equatable {
        /// Every part is known and the total is positive: shares are exact.
        case complete
        /// No parts.
        case empty
        /// Every part is known and they add up to zero: there is nothing to divide.
        case zeroTotal
        /// Some parts are unknown: the known ones are listed, but no total or share is shown.
        case partial
        /// A negative part, or parts in different currencies (or only some with a currency): not a
        /// composition. Nothing is drawn or totalled; the reason is shown in words.
        case invalid
    }

    public struct Segment: Sendable, Equatable, Identifiable {
        public let id: String
        public let label: String
        public let value: Decimal
        /// value / total, only when `status == .complete`.
        public let share: Double?
    }

    public let status: Status
    /// Parts with a known value, in the caller's order.
    public let segments: [Segment]
    /// Parts whose value is unknown: listed as "no data", never drawn as 0.
    public let unknown: [CompositionItem]
    /// Sum of the parts, only when `status == .complete`.
    public let total: Decimal?
    /// The parts' currency when they carry one; every amount is shown in it, never in another.
    public let currency: String?

    public init(_ items: [CompositionItem]) {
        let known = items.compactMap { item in item.value.map { (item, $0) } }
        unknown = items.filter { $0.value == nil }
        let currencies = Set(items.compactMap(\.currency))
        let someWithoutCurrency = !currencies.isEmpty && items.contains { $0.currency == nil }
        currency = currencies.count == 1 && !someWithoutCurrency ? currencies.first : nil
        let status: Status
        if items.isEmpty {
            status = .empty
        } else if known.contains(where: { $0.1 < 0 }) || currencies.count > 1 || someWithoutCurrency {
            status = .invalid
        } else if !unknown.isEmpty {
            status = .partial
        } else if known.reduce(Decimal(0), { $0 + $1.1 }) == 0 {
            status = .zeroTotal
        } else {
            status = .complete
        }
        let sum = known.reduce(Decimal(0)) { $0 + $1.1 }
        self.status = status
        total = status == .complete ? sum : nil
        segments = status == .invalid ? [] : known.map { item, value in
            Segment(id: item.id, label: item.label, value: value,
                    share: status == .complete ? NSDecimalNumber(decimal: value / sum).doubleValue : nil)
        }
    }

    /// Whether the parts can be drawn as a donut: only an exact composition is.
    public var isDrawable: Bool { status == .complete }

    public func segment(id: String?) -> Segment? { segments.first { $0.id == id } }

    /// The segment at a position around the circle (0 = start, 1 = full turn), for taps.
    public func segment(atFraction fraction: Double) -> Segment? {
        guard isDrawable, fraction >= 0, fraction <= 1 else { return nil }
        var end = 0.0
        for segment in segments {
            guard let share = segment.share, share > 0 else { continue }   // a zero part has no arc to tap
            end += share
            if fraction <= end { return segment }
        }
        return segments.last { ($0.share ?? 0) > 0 }
    }

    /// Position around a ring (0 at the top, clockwise, as the parts are drawn) of a tap at
    /// (`dx`, `dy`) from the ring's center, or nil when it is in the hole or beyond the ring.
    public static func ringFraction(dx: Double, dy: Double, radius: Double, innerRatio: Double = 0.55) -> Double? {
        let distance = (dx * dx + dy * dy).squareRoot()
        guard radius > 0, distance >= radius * innerRatio, distance <= radius else { return nil }
        let degrees = (atan2(dy, dx) * 180 / .pi + 90 + 360).truncatingRemainder(dividingBy: 360)
        return degrees / 360
    }

    /// "Tarjeta: ₡120.000, 48 %" / "Préstamo: sin dato" — one line per part, for screen readers
    /// and the legend.
    public func spokenParts(format: MoneyFormat, language: AppLanguage = .current) -> [String] {
        segments.map { segment in
            var text = "\(segment.label): \(format.spoken(segment.value, currency: currency, language: language))"
            if let share = segment.share { text += ", \(VisualText.percent(share, language: language))" }
            return text
        } + unknown.map { "\($0.label): \(VisualText.noData(language))" }
    }
}

// MARK: - Trend (line chart, sparkline)

/// One period of a series. `period` sorts chronologically ("2026-09", "2026-09-30");
/// `value == nil` means no data for that period.
public struct TrendPoint: Sendable, Equatable, Identifiable {
    public let period: String
    public let label: String
    public let value: Decimal?
    public var id: String { period }

    public init(period: String, label: String, value: Decimal?) {
        self.period = period; self.label = label; self.value = value
    }
}

/// A series in chronological order. Missing periods are never filled in: a period without data is
/// a gap, and the line is drawn only between consecutive known points.
public struct TrendSeries: Sendable, Equatable {
    public let points: [TrendPoint]

    /// Sorted by period; when a period repeats, the first one given is kept.
    public init(_ points: [TrendPoint]) {
        var seen = Set<String>()
        self.points = points.filter { seen.insert($0.period).inserted }.sorted { $0.period < $1.period }
    }

    /// A period that has a value: what a line can be drawn through.
    public struct KnownPoint: Sendable, Equatable, Identifiable {
        public let period: String
        public let label: String
        public let value: Decimal
        public var id: String { period }
    }

    public var knownPoints: [TrendPoint] { points.filter { $0.value != nil } }

    /// A trend needs at least two known values.
    public var hasTrend: Bool { knownPoints.count >= 2 }

    /// Runs of consecutive known points: each run is drawn as one line, so a gap stays a gap.
    public var runs: [[KnownPoint]] {
        var runs: [[KnownPoint]] = []
        var current: [KnownPoint] = []
        for point in points {
            if let value = point.value {
                current.append(KnownPoint(period: point.period, label: point.label, value: value))
            } else if !current.isEmpty {
                runs.append(current); current = []
            }
        }
        if !current.isEmpty { runs.append(current) }
        return runs
    }

    /// Lowest and highest known values (negative values are allowed), for scaling.
    public var range: ClosedRange<Decimal>? {
        let values = knownPoints.compactMap(\.value)
        guard let low = values.min(), let high = values.max() else { return nil }
        return low...high
    }

    /// Direction from the first to the last known value.
    public var direction: TrendDirection {
        TrendDirection.between(knownPoints.first?.value, hasTrend ? knownPoints.last?.value : nil)
    }

    /// "ene: ₡100.000; feb: sin dato; mar: ₡80.000" — every period, gaps included.
    public func spokenPoints(format: MoneyFormat, language: AppLanguage = .current) -> String {
        points.map { point in
            "\(point.label): \(point.value.map { format.spoken($0, language: language) } ?? VisualText.noData(language))"
        }.joined(separator: "; ")
    }

    /// One-sentence summary for a sparkline: where the series started, where it ended, and how
    /// many periods have no data.
    public func spokenSummary(format: MoneyFormat, language: AppLanguage = .current) -> String {
        let known = knownPoints
        guard let first = known.first, let firstValue = first.value else { return VisualText.noData(language) }
        guard hasTrend, let last = known.last, let lastValue = last.value else {
            return language.pick("Solo un dato: \(first.label), \(format.spoken(firstValue, language: language)). Todavía no hay tendencia.",
                                 "Only one value: \(first.label), \(format.spoken(firstValue, language: language)). No trend yet.")
        }
        var text = language.pick(
            "De \(format.spoken(firstValue, language: language)) en \(first.label) a \(format.spoken(lastValue, language: language)) en \(last.label): \(VisualText.direction(direction, language: language))",
            "From \(format.spoken(firstValue, language: language)) in \(first.label) to \(format.spoken(lastValue, language: language)) in \(last.label): \(VisualText.direction(direction, language: language))")
        let gaps = points.count - known.count
        if gaps > 0 { text += language.pick(". \(gaps) sin dato", ". \(gaps) without data") }
        return text
    }
}

// MARK: - Direction and its meaning

/// Which way a value moved. It says nothing about whether that is good: debt going down is good,
/// savings going down is not. The caller gives the meaning (`TrendMeaning`).
public enum TrendDirection: String, Sendable, CaseIterable {
    case up, down, flat
    /// Fewer than two known values: there is nothing to compare.
    case insufficient

    public static func between(_ previous: Decimal?, _ current: Decimal?) -> TrendDirection {
        guard let previous, let current else { return .insufficient }
        return current > previous ? .up : current < previous ? .down : .flat
    }
}

/// What a movement means for the user, decided by the caller for that metric.
public enum TrendMeaning: String, Sendable, CaseIterable {
    case favorable, unfavorable, neutral
}

/// A direction plus the meaning the caller gives it. The look (tone) comes only from the meaning;
/// the arrow comes only from the direction.
public struct TrendSignal: Sendable, Equatable {
    public enum Tone: Sendable, Equatable { case positive, attention, neutral, unavailable }

    public let direction: TrendDirection
    public let meaning: TrendMeaning

    public init(direction: TrendDirection, meaning: TrendMeaning) {
        self.direction = direction; self.meaning = meaning
    }

    public var tone: Tone {
        guard direction != .insufficient else { return .unavailable }
        switch meaning {
        case .favorable: return .positive
        case .unfavorable: return .attention
        case .neutral: return .neutral
        }
    }

    /// "Deuda: baja, buena señal" — what changed and what it means, without the picture.
    public func spoken(label: String, language: AppLanguage = .current) -> String {
        let meaningText = direction == .insufficient ? "" : VisualText.meaning(meaning, language: language)
        return [label, [VisualText.direction(direction, language: language), meaningText].filter { !$0.isEmpty }.joined(separator: ", ")]
            .filter { !$0.isEmpty }.joined(separator: ": ")
    }
}

// MARK: - Progress

/// Progress toward a target. `fraction` exists only when both values are known, the current value
/// is not negative and the target is positive: there is no division by zero and no unknown shown
/// as 0 %. Above 100 % is kept (`isOver`); the bar itself is clamped.
public struct ProgressValue: Sendable, Equatable {
    public enum Status: Sendable, Equatable { case valid, unknown, invalidTarget, invalidCurrent }

    public let status: Status
    public let fraction: Double?

    public init(current: Decimal?, target: Decimal?) {
        guard let current, let target else { status = .unknown; fraction = nil; return }
        guard target > 0 else { status = .invalidTarget; fraction = nil; return }
        guard current >= 0 else { status = .invalidCurrent; fraction = nil; return }
        status = .valid
        fraction = NSDecimalNumber(decimal: current / target).doubleValue
    }

    /// A known ratio given directly (for example a backend percentage / 100).
    public init(fraction: Double?) {
        if let fraction, fraction.isFinite, fraction >= 0 {
            status = .valid; self.fraction = fraction
        } else {
            status = fraction == nil ? .unknown : .invalidCurrent; self.fraction = nil
        }
    }

    /// The bar's fill, 0...1.
    public var displayFraction: Double? { fraction.map { min(max($0, 0), 1) } }
    public var isOver: Bool { (fraction ?? 0) > 1 }
    public var isComplete: Bool { (fraction ?? 0) >= 1 }
    /// Whole percent rounded down, so 99.6 % never reads as done. A tiny tolerance keeps binary
    /// floating point from turning 29 % into 28 %; very large ratios are capped instead of trapping.
    public var percent: Int? { fraction.map { Int(min(($0 * 100 + 1e-9).rounded(.down), 1_000_000_000)) } }
}

// MARK: - Shared wording

public enum VisualText {
    public static func noData(_ language: AppLanguage = .current) -> String { language.pick("sin dato", "no data") }

    /// "48 %": whole percent, rounded to nearest (a share, not a completion).
    public static func percent(_ share: Double, language: AppLanguage = .current) -> String {
        let value = (share * 100).rounded()
        return "\(Int(value)) %"
    }

    public static func direction(_ direction: TrendDirection, language: AppLanguage = .current) -> String {
        switch direction {
        case .up: language.pick("sube", "up")
        case .down: language.pick("baja", "down")
        case .flat: language.pick("estable", "steady")
        case .insufficient: language.pick("sin comparación", "no comparison")
        }
    }

    public static func meaning(_ meaning: TrendMeaning, language: AppLanguage = .current) -> String {
        switch meaning {
        case .favorable: language.pick("buena señal", "good sign")
        case .unfavorable: language.pick("merece atención", "worth attention")
        case .neutral: ""
        }
    }
}
