import DincrCore
import DincrDesign
import SwiftUI

/// RV-1 — Movimientos → Análisis → Revisión del mes (every plan): the month that just closed in three
/// short cards, easy to read (how it went, what you achieved, one thing to do this month), from the
/// same summary Resumen del mes counts (`MonthReview`). Android twin: `MonthReviewScreen.kt`.
struct MonthReviewView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScreenScroll(title: tx("Revisión del mes", "Monthly review")) {
            AsyncContent(load: { () async throws -> [MonthReview.Card] in
                let months = MonthReview.closedMonths(today: Date())
                async let closed = model.service.monthlySummary(period: months.closed)
                // The month before is optional: without it there is no comparison.
                let before = try? await model.service.monthlySummary(period: months.before)
                return MonthReview.cards(try await closed, previous: before, format: model.moneyFormat)
            }) { cards, _ in
                ForEach(Array(cards.enumerated()), id: \.offset) { index, card in
                    VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                        Text(card.title).font(DincrFont.label).foregroundStyle(DincrColor.text2).accessibilityAddTraits(.isHeader)
                        ForEach(Array(card.lines.enumerated()), id: \.offset) { line, text in
                            Text(text).font(line == 0 ? DincrFont.title2 : DincrFont.bodySmall)
                                .foregroundStyle(line == 0 ? DincrColor.text : DincrColor.text2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .dincrCard()
                    .accessibilityElement(children: .combine)
                    .accessibilityIdentifier("review.card.\(index)")
                }
            }
        }
    }
}
