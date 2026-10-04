import Foundation
import Testing
@testable import DincrCore

/// Visualize information; do not invent information (DESIGN.md → Data visualization).
/// Android checks the same rules in `VisualModelsTest.kt`.
@Suite struct VisualModelsTests {
    let format = MoneyFormat()

    // MARK: Composition

    @Test func anEmptyCompositionHasNothingToDraw() {
        let composition = Composition([])
        #expect(composition.status == .empty)
        #expect(!composition.isDrawable && composition.total == nil && composition.segments.isEmpty)
    }

    @Test func aSinglePartIsTheWhole() {
        let composition = Composition([CompositionItem(id: "card", label: "Tarjeta", value: 250_000)])
        #expect(composition.status == .complete)
        #expect(composition.total == 250_000)
        #expect(composition.segments.first?.share == 1)
    }

    @Test func sharesAreExactAndKeepTheCallersOrderAndValues() {
        let composition = Composition([
            CompositionItem(id: "a", label: "Tarjeta", value: 50),
            CompositionItem(id: "b", label: "Préstamo", value: 150),
        ])
        #expect(composition.segments.map(\.id) == ["a", "b"])
        #expect(composition.segments.map(\.value) == [50, 150])
        #expect(composition.segments.map(\.share) == [0.25, 0.75])
        #expect(composition.total == 200)
    }

    @Test func zeroTotalHasNoSharesButKeepsTheRealZeros() {
        let composition = Composition([CompositionItem(id: "a", label: "A", value: 0), CompositionItem(id: "b", label: "B", value: 0)])
        #expect(composition.status == .zeroTotal)
        #expect(!composition.isDrawable && composition.total == nil)
        #expect(composition.segments.map(\.value) == [0, 0])
        #expect(composition.segments.allSatisfy { $0.share == nil })
    }

    @Test func anUnknownPartIsNeverZeroAndBlocksSharesAndTotal() {
        let composition = Composition([
            CompositionItem(id: "a", label: "Tarjeta", value: 100),
            CompositionItem(id: "b", label: "Préstamo", value: nil),
        ])
        #expect(composition.status == .partial)
        #expect(!composition.isDrawable && composition.total == nil)
        #expect(composition.segments.map(\.id) == ["a"])
        #expect(composition.segments.first?.share == nil)
        #expect(composition.unknown.map(\.id) == ["b"])
        let parts = composition.spokenParts(format: format, language: .spanish)
        #expect(parts.last == "Préstamo: sin dato")
        #expect(!parts.joined().contains("%"))
    }

    @Test func negativePartsOrMixedCurrenciesAreNotAComposition() {
        let negative = Composition([CompositionItem(id: "a", label: "A", value: 100), CompositionItem(id: "b", label: "B", value: -5)])
        #expect(negative.status == .invalid && negative.segments.isEmpty && negative.total == nil)
        let mixed = Composition([
            CompositionItem(id: "a", label: "A", value: 100, currency: "CRC"),
            CompositionItem(id: "b", label: "B", value: 100, currency: "USD"),
        ])
        #expect(mixed.status == .invalid && mixed.total == nil)
        let same = Composition([
            CompositionItem(id: "a", label: "A", value: 100, currency: "USD"),
            CompositionItem(id: "b", label: "B", value: 300, currency: "USD"),
        ])
        #expect(same.status == .complete && same.total == 400)
    }

    /// Amounts are read and shown in the parts' own currency: USD is never read as colones, and a
    /// part without a currency is never added to parts with one.
    @Test func thePartsCurrencyIsKeptAndNeverMixed() {
        let usd = Composition([
            CompositionItem(id: "a", label: "Inversión", value: 100, currency: "USD"),
            CompositionItem(id: "b", label: "Ahorro", value: 300, currency: "USD"),
        ])
        #expect(usd.currency == "USD")
        let spoken = usd.spokenParts(format: format, language: .spanish).joined()
        #expect(spoken.contains("dólares") && !spoken.contains("colones"), "\(spoken)")
        let partial = Composition([CompositionItem(id: "a", label: "A", value: 100, currency: "USD"), CompositionItem(id: "b", label: "B", value: 100)])
        #expect(partial.status == .invalid && partial.total == nil && partial.currency == nil)
        #expect(Composition([CompositionItem(id: "a", label: "A", value: 100)]).currency == nil)
    }

    @Test func aZeroPartHasNoArcToTap() {
        let composition = Composition([
            CompositionItem(id: "zero", label: "Cero", value: 0),
            CompositionItem(id: "a", label: "A", value: 50),
            CompositionItem(id: "b", label: "B", value: 50),
        ])
        #expect(composition.status == .complete)
        #expect(composition.segment(atFraction: 0)?.id == "a")
        #expect(composition.segment(atFraction: 1)?.id == "b")
        #expect(composition.segment(id: "zero")?.share == 0)   // still listed, with its real 0 %
    }

    @Test func selectionFindsTheSegmentUnderATapOrById() {
        let composition = Composition([
            CompositionItem(id: "a", label: "A", value: 25),
            CompositionItem(id: "b", label: "B", value: 75),
        ])
        #expect(composition.segment(atFraction: 0)?.id == "a")
        #expect(composition.segment(atFraction: 0.2)?.id == "a")
        #expect(composition.segment(atFraction: 0.3)?.id == "b")
        #expect(composition.segment(atFraction: 1)?.id == "b")
        #expect(composition.segment(atFraction: 1.2) == nil)
        #expect(composition.segment(id: "b")?.share == 0.75)
        #expect(composition.segment(id: "missing") == nil)
        #expect(Composition([CompositionItem(id: "a", label: "A", value: nil)]).segment(atFraction: 0.5) == nil)
    }

    /// A tap on the ring maps to its position around the circle (0 at the top, clockwise); taps in
    /// the hole or beyond the ring select nothing.
    @Test func aTapOnTheRingMapsToItsPosition() {
        let top = Composition.ringFraction(dx: 0, dy: -90, radius: 100)
        let right = Composition.ringFraction(dx: 90, dy: 0, radius: 100)
        let bottom = Composition.ringFraction(dx: 0, dy: 90, radius: 100)
        let left = Composition.ringFraction(dx: -90, dy: 0, radius: 100)
        #expect(abs((top ?? -1) - 0) < 0.0001)
        #expect(abs((right ?? -1) - 0.25) < 0.0001)
        #expect(abs((bottom ?? -1) - 0.5) < 0.0001)
        #expect(abs((left ?? -1) - 0.75) < 0.0001)
        #expect(Composition.ringFraction(dx: 10, dy: 10, radius: 100) == nil)    // the hole
        #expect(Composition.ringFraction(dx: 120, dy: 0, radius: 100) == nil)    // outside
        #expect(Composition.ringFraction(dx: 1, dy: 1, radius: 0) == nil)
        let composition = Composition([CompositionItem(id: "a", label: "A", value: 25), CompositionItem(id: "b", label: "B", value: 75)])
        #expect(composition.segment(atFraction: right!)?.id == "a")
        #expect(composition.segment(atFraction: bottom!)?.id == "b")
    }

    @Test func spokenPartsCarryLabelValueAndShare() {
        let composition = Composition([
            CompositionItem(id: "a", label: "Tarjeta", value: 30_000),
            CompositionItem(id: "b", label: "Préstamo", value: 90_000),
        ])
        let parts = composition.spokenParts(format: format, language: .spanish)
        #expect(parts.count == 2)
        #expect(parts[0].hasPrefix("Tarjeta: ") && parts[0].hasSuffix(", 25 %"))
        #expect(parts[1].hasPrefix("Préstamo: ") && parts[1].hasSuffix(", 75 %"))
        // Formatting reads the values; it never changes them.
        #expect(composition.segments.map(\.value) == [30_000, 90_000])
    }

    // MARK: Trend

    @Test func anEmptySeriesHasNoTrend() {
        let series = TrendSeries([])
        #expect(!series.hasTrend && series.runs.isEmpty && series.range == nil)
        #expect(series.direction == .insufficient)
        #expect(series.spokenSummary(format: format, language: .spanish) == "sin dato")
    }

    @Test func aSingleValueIsNotATrend() {
        let series = TrendSeries([TrendPoint(period: "2026-09", label: "set", value: 100)])
        #expect(!series.hasTrend)
        #expect(series.direction == .insufficient)
        #expect(series.spokenSummary(format: format, language: .spanish).contains("Todavía no hay tendencia"))
    }

    @Test func pointsAreSortedChronologicallyAndDuplicatesKeepTheFirst() {
        let series = TrendSeries([
            TrendPoint(period: "2026-09", label: "set", value: 3),
            TrendPoint(period: "2026-07", label: "jul", value: 1),
            TrendPoint(period: "2026-08", label: "ago", value: 2),
            TrendPoint(period: "2026-07", label: "jul", value: 99),
        ])
        #expect(series.points.map(\.period) == ["2026-07", "2026-08", "2026-09"])
        #expect(series.points.first?.value == 1)
    }

    @Test func missingPeriodsStayGapsAndAreNeverZero() {
        let series = TrendSeries([
            TrendPoint(period: "2026-06", label: "jun", value: 100),
            TrendPoint(period: "2026-07", label: "jul", value: nil),
            TrendPoint(period: "2026-08", label: "ago", value: 80),
            TrendPoint(period: "2026-09", label: "set", value: 90),
        ])
        #expect(series.points.count == 4)
        #expect(series.points[1].value == nil)
        #expect(series.runs.map { $0.map(\.period) } == [["2026-06"], ["2026-08", "2026-09"]])
        #expect(series.runs.flatMap { $0.map(\.value) } == [100, 80, 90])   // only real values are drawn
        #expect(series.range == 80...100)
        let spoken = series.spokenPoints(format: format, language: .spanish)
        #expect(spoken.contains("jul: sin dato"))
        #expect(series.spokenSummary(format: format, language: .spanish).hasSuffix("1 sin dato"))
    }

    @Test func negativeValuesAreAllowedInASeries() {
        let series = TrendSeries([
            TrendPoint(period: "2026-08", label: "ago", value: -50),
            TrendPoint(period: "2026-09", label: "set", value: 20),
        ])
        #expect(series.range == -50...20)
        #expect(series.direction == .up)
    }

    // MARK: Direction and meaning

    @Test func directionComparesValuesOnly() {
        #expect(TrendDirection.between(10, 20) == .up)
        #expect(TrendDirection.between(20, 10) == .down)
        #expect(TrendDirection.between(10, 10) == .flat)
        #expect(TrendDirection.between(nil, 10) == .insufficient)
        #expect(TrendDirection.between(10, nil) == .insufficient)
    }

    /// Debt going down is good and savings going down is not: the direction is the same, so the
    /// look can only come from the meaning the caller gives.
    @Test func directionNeverImpliesMeaning() {
        let debtDown = TrendSignal(direction: .between(500, 400), meaning: .favorable)
        let savingsDown = TrendSignal(direction: .between(500, 400), meaning: .unfavorable)
        #expect(debtDown.direction == savingsDown.direction)
        #expect(debtDown.tone == .positive)
        #expect(savingsDown.tone == .attention)
        // The same meaning gives the same tone whichever way the value moved.
        for direction in [TrendDirection.up, .down, .flat] {
            #expect(TrendSignal(direction: direction, meaning: .favorable).tone == .positive)
            #expect(TrendSignal(direction: direction, meaning: .unfavorable).tone == .attention)
            #expect(TrendSignal(direction: direction, meaning: .neutral).tone == .neutral)
        }
        // With nothing to compare, no meaning is claimed.
        for meaning in TrendMeaning.allCases {
            #expect(TrendSignal(direction: .insufficient, meaning: meaning).tone == .unavailable)
        }
    }

    @Test func aSignalIsReadableWithoutThePicture() {
        #expect(TrendSignal(direction: .down, meaning: .favorable).spoken(label: "Deuda", language: .spanish) == "Deuda: baja, buena señal")
        #expect(TrendSignal(direction: .down, meaning: .unfavorable).spoken(label: "Ahorro", language: .spanish) == "Ahorro: baja, merece atención")
        #expect(TrendSignal(direction: .up, meaning: .neutral).spoken(label: "Gastos", language: .spanish) == "Gastos: sube")
        #expect(TrendSignal(direction: .insufficient, meaning: .favorable).spoken(label: "Deuda", language: .spanish) == "Deuda: sin comparación")
    }

    // MARK: Progress

    @Test func progressHandlesZeroNormalCompleteAndOver() {
        #expect(ProgressValue(current: 0, target: 100).fraction == 0)
        #expect(ProgressValue(current: 0, target: 100).percent == 0)
        #expect(ProgressValue(current: 40, target: 100).displayFraction == 0.4)
        let done = ProgressValue(current: 100, target: 100)
        #expect(done.isComplete && !done.isOver && done.percent == 100)
        let over = ProgressValue(current: 150, target: 100)
        #expect(over.isOver && over.displayFraction == 1 && over.percent == 150)
    }

    @Test func progressNeverDividesByZeroOrShowsUnknownAsZero() {
        #expect(ProgressValue(current: 50, target: 0).status == .invalidTarget)
        #expect(ProgressValue(current: 50, target: -10).fraction == nil)
        #expect(ProgressValue(current: nil, target: 100).status == .unknown)
        #expect(ProgressValue(current: 50, target: nil).percent == nil)
        #expect(ProgressValue(current: -1, target: 100).status == .invalidCurrent)
        #expect(ProgressValue(fraction: nil).displayFraction == nil)
        #expect(ProgressValue(fraction: .nan).fraction == nil)
        #expect(ProgressValue(fraction: 0.5).percent == 50)
    }

    /// Binary floating point must not turn a whole percent into the one below it.
    @Test func wholePercentsAreNotLostToFloatingPoint() {
        for value in [29, 57, 58] {
            #expect(ProgressValue(current: Decimal(value), target: 100).percent == value)
            #expect(ProgressValue(fraction: Double(value) / 100).percent == value)
        }
        #expect(ProgressValue(fraction: 1e300).percent == 1_000_000_000)   // capped, never a crash
    }

    @Test func almostDoneNeverReadsAsDone() {
        let almost = ProgressValue(current: 996, target: 1000)
        #expect(almost.percent == 99)
        #expect(!almost.isComplete)
    }
}
