import Foundation

/// UX-14 — what Patrimonio → Proyecciones shows. Presentation only: it reads what the command center
/// states and never computes money. Figures are shown only when the backend says the projection is
/// complete; an answer without that status (or without points) is never read as complete, so an
/// unknown is never shown as a certain figure. Android: `com.dincr.data.Projections`.
public enum Projections: Sendable, Equatable {
    /// The 1, 3, 6 and 12-month points, in order. `lowConfidence`: the income has no recorded
    /// movements behind it yet (the backend's `confidence: low`).
    case complete(points: [CommandCenter.ProjectionPoint], lowConfidence: Bool)
    /// No figures: the inputs DINCR needs, in the backend's order (empty when it named none it knows).
    case incomplete(missing: [ProjectionInput])

    public static func state(_ center: CommandCenter) -> Projections {
        let points = (center.projections ?? []).sorted { ($0.months ?? 0) < ($1.months ?? 0) }
        guard center.projectionStatus?.complete == true, !points.isEmpty else {
            return .incomplete(missing: ProjectionInput.codes(center.projectionStatus?.missing))
        }
        return .complete(points: points, lowConfidence: points.contains { $0.confidence == "low" })
    }
}

/// An input a projection needs (the backend's `missing` codes) and the existing screen where the
/// user gives it: income and essential expenses in Plan → Ingresos y base, savings in Tus ahorros,
/// debt payments in Deudas. No other form is offered.
public enum ProjectionInput: String, Sendable, Equatable, CaseIterable {
    case income
    case essentialExpenses = "essential_expenses"
    case debtPayments = "debt_payments"
    case savings

    public enum Destination: String, Sendable, Equatable {
        case incomeBase, declaredSavings, debts
    }

    public var destination: Destination {
        switch self {
        case .income, .essentialExpenses: .incomeBase
        case .savings: .declaredSavings
        case .debtPayments: .debts
        }
    }

    /// Known codes in the backend's order; codes this app doesn't know are skipped.
    public static func codes(_ codes: [String]?) -> [ProjectionInput] { (codes ?? []).compactMap(ProjectionInput.init(rawValue:)) }
}

/// UX-14 / I09 — the charts of Patrimonio → Proyecciones: projected cash, debt and net worth over the
/// projection's own points (1, 3, 6 and 12 months), exactly as the backend sent them. Nothing is
/// interpolated or filled in: only a complete projection has series, and a series is drawn only when
/// every one of its points is known. Android: `com.dincr.data.ProjectionSeries`.
public struct ProjectionSeries: Sendable, Equatable {
    public enum Kind: String, Sendable, CaseIterable { case cash, debt, netWorth }

    public let kind: Kind
    public let series: TrendSeries

    /// The series to draw for `state`, in the order cash, debt, net worth; none when incomplete.
    public static func of(_ state: Projections, language: AppLanguage = .current) -> [ProjectionSeries] {
        guard case .complete(let points, _) = state else { return [] }
        return Kind.allCases.compactMap { kind in
            let values = points.map { value(of: $0, kind) }
            guard !values.contains(where: { $0 == nil }) else { return nil }
            return ProjectionSeries(kind: kind, series: TrendSeries(zip(points, values).map { point, value in
                let months = point.months ?? 0
                return TrendPoint(period: String(format: "%02d", months), label: label(months, language: language), value: value)
            }))
        }
    }

    static func label(_ months: Int, language: AppLanguage) -> String {
        months == 1 ? language.pick("1 mes", "1 month") : language.pick("\(months) meses", "\(months) months")
    }

    private static func value(of point: CommandCenter.ProjectionPoint, _ kind: Kind) -> Decimal? {
        switch kind {
        case .cash: point.cash
        case .debt: point.debt
        case .netWorth: point.netWorth
        }
    }
}
