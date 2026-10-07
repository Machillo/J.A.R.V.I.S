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
