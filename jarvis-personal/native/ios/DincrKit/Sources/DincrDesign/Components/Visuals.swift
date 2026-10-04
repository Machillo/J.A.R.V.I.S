import Charts
import DincrCore
import SwiftUI

// Shared visual components (DESIGN.md → Data visualization). They draw what the models in
// `DincrCore/VisualModels.swift` describe and never compute or fill in financial values: unknown
// stays "no data", a gap stays a gap, a proportion appears only when it is exact. Every component
// is readable without the picture (VoiceOver gets the values, not just a title). Android draws the
// same components in `com.dincr.design.Visuals`.

// MARK: - Donut

/// Composition of a whole: one hue in steps (no rainbow; parts are told apart by the legend's
/// direct labels, never by color alone), a center label, and a legend whose rows select a part.
/// When the parts can't form an exact whole, the donut is not drawn and the legend still lists
/// every known part and every unknown one as "no data". Amounts are shown in the parts' currency.
public struct CompositionDonut: View {
    let title: String
    let composition: Composition
    let color: Color
    let showsLegend: Bool
    let showsTotal: Bool
    @Environment(\.moneyFormat) private var format
    @State private var selectedID: String?

    /// `showsTotal: false` when the caller has its own total and the sum of the parts must not be
    /// shown as one (the center then shows only a selected part).
    public init(title: String, composition: Composition, color: Color = DincrColor.chartExpense, showsLegend: Bool = true,
                showsTotal: Bool = true) {
        self.title = title; self.composition = composition; self.color = color; self.showsLegend = showsLegend
        self.showsTotal = showsTotal
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            if composition.isDrawable {
                chart
            } else {
                VisualNotice(text: notice).accessibilityLabel("\(title). \(notice)")
            }
            if showsLegend { legend }
        }
    }

    private var chart: some View {
        Chart(composition.segments) { segment in
            SectorMark(angle: .value("Monto", Self.double(segment.value)), innerRadius: .ratio(0.62), angularInset: 1.5)
                .cornerRadius(3)
                .foregroundStyle(shade(for: segment.id))
        }
        .chartBackground { proxy in
            GeometryReader { geometry in
                if let anchor = proxy.plotFrame {
                    let frame = geometry[anchor]
                    center.frame(width: frame.width * 0.55).position(x: frame.midX, y: frame.midY)
                }
            }
        }
        // A plain tap selects a part (Charts' own selection needs a long press inside a scroll view).
        .chartOverlay { proxy in
            GeometryReader { geometry in
                if let anchor = proxy.plotFrame {
                    let frame = geometry[anchor]
                    Color.clear.contentShape(Rectangle())
                        .onTapGesture { location in
                            guard let fraction = Composition.ringFraction(dx: location.x - frame.midX, dy: location.y - frame.midY,
                                                                          radius: min(frame.width, frame.height) / 2) else { return }
                            let id = composition.segment(atFraction: fraction)?.id
                            selectedID = id == selectedID ? nil : id
                        }
                }
            }
        }
        .frame(height: 200)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(title)
        .accessibilityValue(composition.spokenParts(format: format).joined(separator: "; "))
        .accessibilityHidden(showsLegend)   // the legend rows already read every part
    }

    @ViewBuilder private var center: some View {
        if let segment = composition.segment(id: selectedID) {
            VStack(spacing: 2) {
                Text(segment.label).font(DincrFont.caption).foregroundStyle(DincrColor.text2).lineLimit(2).multilineTextAlignment(.center)
                MoneyText(segment.value, currency: composition.currency, font: DincrFont.title2.monospacedDigit())
                if let share = segment.share { Text(VisualText.percent(share)).font(DincrFont.caption).foregroundStyle(DincrColor.text2) }
            }
        } else if showsTotal, let total = composition.total {
            VStack(spacing: 2) {
                Text(AppLanguage.current.pick("Total", "Total")).font(DincrFont.caption).foregroundStyle(DincrColor.text2)
                MoneyText(total, currency: composition.currency, font: DincrFont.title2.monospacedDigit())
            }
        }
    }

    private var legend: some View {
        VStack(spacing: 0) {
            ForEach(Array(composition.segments.enumerated()), id: \.element.id) { index, segment in
                let row = HStack(spacing: DincrSpacing.s3) {
                    if composition.isDrawable {
                        Circle().fill(shade(for: segment.id)).frame(width: 10, height: 10).accessibilityHidden(true)
                    }
                    Text(segment.label).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text).multilineTextAlignment(.leading)
                    Spacer(minLength: DincrSpacing.s2)
                    VStack(alignment: .trailing, spacing: 0) {
                        MoneyText(segment.value, currency: composition.currency, font: DincrFont.bodySmall.weight(.semibold).monospacedDigit())
                        if let share = segment.share {
                            Text(VisualText.percent(share)).font(DincrFont.caption).foregroundStyle(DincrColor.text2)
                        }
                    }
                }
                .frame(minHeight: 44)
                .contentShape(Rectangle())
                Group {
                    if composition.isDrawable {
                        // Selecting a part highlights it in the donut and the center label.
                        Button { selectedID = selectedID == segment.id ? nil : segment.id } label: { row }
                            .buttonStyle(.plain)
                    } else {
                        row
                    }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(composition.spokenParts(format: format)[index])
                .accessibilityAddTraits(composition.isDrawable ? .isButton : [])
                .accessibilityAddTraits(selectedID == segment.id ? .isSelected : [])
            }
            ForEach(composition.unknown) { item in
                HStack {
                    Text(item.label).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text)
                    Spacer()
                    Text(VisualText.noData().capitalizedFirst).font(DincrFont.bodySmall).foregroundStyle(DincrColor.textMuted)
                }
                .frame(minHeight: 44)
                .accessibilityElement(children: .combine)
            }
        }
    }

    /// One hue in steps of decreasing strength, in the caller's order; a selection keeps its part
    /// strong and quiets the rest.
    private func shade(for id: String) -> Color {
        guard let index = composition.segments.firstIndex(where: { $0.id == id }) else { return color }
        if let selectedID { return color.opacity(id == selectedID ? 1 : 0.4) }
        return color.opacity(VisualShade.opacity(at: index))
    }

    private var notice: String {
        let language = AppLanguage.current
        switch composition.status {
        case .empty: return language.pick("Todavía no hay datos.", "No data yet.")
        case .zeroTotal: return language.pick("Todo suma cero: no hay partes que comparar.", "Everything adds up to zero: nothing to compare.")
        case .partial: return language.pick("Faltan datos de algunas partes, así que no mostramos proporciones.", "Some parts have no data, so proportions aren’t shown.")
        case .invalid: return language.pick("Estos valores no se pueden sumar en un solo total.", "These values can’t be added into one total.")
        case .complete: return ""
        }
    }

    static func double(_ value: Decimal) -> Double { NSDecimalNumber(decimal: value).doubleValue }
}

/// Opacity steps for the parts of one hue: strong first, never fainter than readable.
enum VisualShade {
    static func opacity(at index: Int) -> Double { max(0.3, 1 - Double(index) * 0.17) }
}

// MARK: - Line

/// Evolution over time (DESIGN_SYSTEM.md §8: 2 pt line, baseline at 0, markers on selection).
/// Each run of consecutive known periods is one line; a period without data stays on the axis as a
/// gap, and a value isolated between gaps keeps a small marker so it is never hidden. Fewer than
/// two known values show a notice instead of a trend.
public struct TrendLineChart: View {
    let title: String
    let series: TrendSeries
    let color: Color
    @Environment(\.moneyFormat) private var format
    @State private var selectedPeriod: String?

    public init(title: String, series: TrendSeries, color: Color = DincrColor.chartExpense) {
        self.title = title; self.series = series; self.color = color
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            if series.hasTrend {
                chart
                if let point = selectedPoint {
                    HStack {
                        Text(point.label).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                        Spacer()
                        if let value = point.value {
                            MoneyText(value, font: DincrFont.bodySmall.weight(.semibold).monospacedDigit())
                        } else {
                            Text(VisualText.noData().capitalizedFirst).font(DincrFont.bodySmall).foregroundStyle(DincrColor.textMuted)
                        }
                    }
                    .accessibilityElement(children: .combine)
                }
            } else {
                let notice = AppLanguage.current.pick("Todavía no hay suficientes datos para ver una tendencia.", "Not enough data yet to show a trend.")
                VisualNotice(text: notice).accessibilityLabel("\(title). \(notice)")
                if let only = series.knownPoints.first, let value = only.value {
                    HStack {
                        Text(only.label).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                        Spacer()
                        MoneyText(value, font: DincrFont.bodySmall.weight(.semibold).monospacedDigit())
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        }
    }

    private var selectedPoint: TrendPoint? { series.points.first { $0.period == selectedPeriod } }

    private var chart: some View {
        Chart {
            ForEach(Array(series.runs.enumerated()), id: \.offset) { run, points in
                ForEach(points) { point in
                    LineMark(x: .value("Periodo", point.period), y: .value("Monto", CompositionDonut.double(point.value)),
                             series: .value("Tramo", run))
                        .foregroundStyle(color)
                        .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                    if point.period == selectedPeriod {
                        PointMark(x: .value("Periodo", point.period), y: .value("Monto", CompositionDonut.double(point.value)))
                            .symbol { Circle().fill(color).frame(width: 10, height: 10).overlay(Circle().stroke(DincrColor.surface, lineWidth: 2)) }
                    } else if points.count == 1 {
                        PointMark(x: .value("Periodo", point.period), y: .value("Monto", CompositionDonut.double(point.value)))
                            .foregroundStyle(color).symbolSize(30)
                    }
                }
            }
            RuleMark(y: .value("Cero", 0)).foregroundStyle(DincrColor.lineStrong)
            if let point = selectedPoint, point.value != nil {
                RuleMark(x: .value("Periodo", point.period)).foregroundStyle(DincrColor.line)
            }
        }
        .chartXScale(domain: series.points.map(\.period))
        .chartYScale(domain: VisualAxis.domainWithZero(series.range))
        // A plain tap selects the nearest period (Charts' own selection needs a long press inside a
        // scroll view).
        .chartOverlay { proxy in
            GeometryReader { geometry in
                if let anchor = proxy.plotFrame {
                    let frame = geometry[anchor]
                    Color.clear.contentShape(Rectangle())
                        .onTapGesture { location in
                            guard let period = proxy.value(atX: location.x - frame.minX, as: String.self) else { return }
                            selectedPeriod = period == selectedPeriod ? nil : period
                        }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: series.points.map(\.period)) { value in
                AxisValueLabel {
                    if let period = value.as(String.self) {
                        Text(series.points.first { $0.period == period }?.label ?? period)
                            .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) { value in
                AxisGridLine().foregroundStyle(DincrColor.line)
                AxisValueLabel {
                    if let number = value.as(Double.self) {
                        Text(VisualAxis.compact(number)).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                    }
                }
            }
        }
        .frame(height: 180)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(title)
        .accessibilityValue(series.spokenPoints(format: format))
    }
}

enum VisualAxis {
    /// The known values' own range (a flat series gets a little room so it sits in the middle).
    static func dataDomain(_ range: ClosedRange<Decimal>?) -> ClosedRange<Double> {
        guard let range else { return 0...1 }
        let low = CompositionDonut.double(range.lowerBound), high = CompositionDonut.double(range.upperBound)
        return low == high ? (low - 1)...(high + 1) : low...high
    }

    /// The y domain always includes 0, so the baseline is real and a small change is not magnified.
    static func domainWithZero(_ range: ClosedRange<Decimal>?) -> ClosedRange<Double> {
        guard let range else { return 0...1 }
        let low = min(CompositionDonut.double(range.lowerBound), 0)
        let high = max(CompositionDonut.double(range.upperBound), 0)
        return low == high ? low...(high + 1) : low...high
    }

    /// Short axis labels ("1.2M", "350k", "−80k"); the values themselves stay in the table/selection.
    static func compact(_ value: Double) -> String {
        let sign = value < 0 ? "−" : ""
        let magnitude = abs(value)
        if magnitude >= 1_000_000 { return sign + String(format: "%.1fM", magnitude / 1_000_000) }
        if magnitude >= 1_000 { return sign + "\(Int(magnitude / 1_000))k" }
        return sign + "\(Int(magnitude))"
    }
}

// MARK: - Sparkline

/// A small trend for a card: no axes or legend, gaps kept, and a spoken summary (first and last
/// values, direction, periods without data). With fewer than two values it says so in text.
public struct Sparkline: View {
    let label: String
    let series: TrendSeries
    let color: Color
    @Environment(\.moneyFormat) private var format

    public init(label: String, series: TrendSeries, color: Color = DincrColor.chartExpense) {
        self.label = label; self.series = series; self.color = color
    }

    public var body: some View {
        Group {
            if series.hasTrend {
                Chart {
                    ForEach(Array(series.runs.enumerated()), id: \.offset) { run, points in
                        ForEach(points) { point in
                            LineMark(x: .value("Periodo", point.period), y: .value("Monto", CompositionDonut.double(point.value)),
                                     series: .value("Tramo", run))
                                .foregroundStyle(color)
                                .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                            if points.count == 1 {
                                PointMark(x: .value("Periodo", point.period), y: .value("Monto", CompositionDonut.double(point.value)))
                                    .foregroundStyle(color).symbolSize(16)
                            }
                        }
                    }
                }
                .chartXScale(domain: series.points.map(\.period))
                // A sparkline spans its own range (unlike the full line chart, no baseline at 0), the
                // same on both platforms; its spoken summary carries the actual values.
                .chartYScale(domain: VisualAxis.dataDomain(series.range))
                .chartXAxis(.hidden)
                .chartYAxis(.hidden)
                .chartLegend(.hidden)
                .frame(height: 32)
            } else {
                Text(AppLanguage.current.pick("Sin tendencia todavía", "No trend yet"))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(label)
        .accessibilityValue(series.spokenSummary(format: format))
    }
}

// MARK: - Trend indicator

/// Which way something moved (arrow and word) and what the caller says it means (color and, when
/// it has one, a word: never color alone). The direction never picks the color: debt going down
/// and savings going down look different.
public struct TrendIndicator: View {
    let label: String
    let signal: TrendSignal

    public init(label: String, signal: TrendSignal) {
        self.label = label; self.signal = signal
    }

    public var body: some View {
        let (foreground, fill) = Self.colors(signal.tone)
        HStack(spacing: DincrSpacing.s1) {
            Image(systemName: Self.symbol(signal.direction)).font(DincrFont.caption.weight(.semibold))
            Text(visibleText).font(DincrFont.caption.weight(.semibold))
        }
        .foregroundStyle(foreground)
        .padding(.horizontal, DincrSpacing.s2)
        .padding(.vertical, 3)
        .background(fill, in: Capsule())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(signal.spoken(label: label))
    }

    private var visibleText: String {
        let direction = VisualText.direction(signal.direction).capitalizedFirst
        let meaning = signal.direction == .insufficient ? "" : VisualText.meaning(signal.meaning)
        return meaning.isEmpty ? direction : "\(direction) · \(meaning)"
    }

    static func symbol(_ direction: TrendDirection) -> String {
        switch direction {
        case .up: "arrow.up.right"
        case .down: "arrow.down.right"
        case .flat: "arrow.right"
        case .insufficient: "minus"
        }
    }

    static func colors(_ tone: TrendSignal.Tone) -> (Color, Color) {
        switch tone {
        case .positive: (DincrColor.positive, DincrColor.positiveContainer)
        case .attention: (DincrColor.warning, DincrColor.warningContainer)
        case .neutral: (DincrColor.text2, DincrColor.surface2)
        case .unavailable: (DincrColor.textMuted, DincrColor.surface2)
        }
    }
}

// MARK: - Shared pieces

/// Why a chart isn't drawn, in words.
struct VisualNotice: View {
    let text: String

    var body: some View {
        Label {
            Text(text).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
        } icon: {
            Image(systemName: "chart.pie").foregroundStyle(DincrColor.textMuted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(DincrSpacing.s3)
        .background(DincrColor.surface2, in: RoundedRectangle(cornerRadius: DincrRadius.md, style: .continuous))
    }
}

extension String {
    /// "sin dato" → "Sin dato".
    var capitalizedFirst: String { prefix(1).uppercased() + dropFirst() }
}
