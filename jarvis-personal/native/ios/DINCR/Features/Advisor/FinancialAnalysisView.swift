import DincrCore
import DincrDesign
import SwiftUI

/// FA-1 — Movimientos → Análisis → Análisis financiero (VIP and the Owner): the user's last twelve
/// months in plain words, for people who do not know finance. A normal month (what is left, how much
/// is saved and how much goes to debts, each with one line saying what it means), the months side by
/// side, and where this month already spends more than usual. The backend counts
/// (`/vip/financial-analysis`); `FinancialReading` writes the sentences. The Owner's full historical
/// analysis stays in JARVIS. Android twin: `FinancialAnalysisScreen.kt`.
struct FinancialAnalysisView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScreenScroll(title: tx("Análisis financiero", "Financial analysis")) {
            AsyncContent(load: { () async throws -> Loaded in
                // The Salvavidas is optional: without it the reading leaves its coverage out.
                async let analysis = model.service.financialAnalysis()
                let coverage = (try? await model.service.salvavidas())?.coverageMonths
                return Loaded(analysis: try await analysis, coverageMonths: coverage)
            }) { loaded, _ in
                if let health = HealthReading.reading(FinancialReading.normal(loaded.analysis), coverageMonths: loaded.coverageMonths) {
                    HealthCard(reading: health)
                }
                FinancialAnalysisContent(analysis: loaded.analysis)
            }
        }
    }
}

private struct Loaded: Equatable {
    let analysis: FinancialAnalysis
    let coverageMonths: Double?
}

/// HS-1 — "Tu salud financiera": one word, the main reason and one thing to do (`HealthReading`).
private struct HealthCard: View {
    let reading: HealthReading.Reading

    private var color: Color {
        switch reading.level {
        case .good: DincrColor.positive
        case .fair: DincrColor.warning
        case .atRisk: DincrColor.negative
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(tx("Tu salud financiera", "Your financial health")).font(DincrFont.label).foregroundStyle(DincrColor.text2).accessibilityAddTraits(.isHeader)
            Text(reading.word).font(DincrFont.title1).foregroundStyle(color).accessibilityIdentifier("health.word")
            Text(reading.reason).font(DincrFont.body).foregroundStyle(DincrColor.text).fixedSize(horizontal: false, vertical: true)
            Text(reading.action).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .dincrCard()
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("analysis.financial.health")
    }
}

private struct FinancialAnalysisContent: View {
    @Environment(AppModel.self) private var model
    let analysis: FinancialAnalysis

    var body: some View {
        let format = model.moneyFormat
        if let normal = FinancialReading.normal(analysis) {
            ReadingCard(title: tx("Tu mes normal", "Your normal month"), sentence: FinancialReading.leftSentence(normal, format: format),
                        explanation: FinancialReading.leftExplanation(normal, format: format), id: "analysis.financial.left")
            if let saved = FinancialReading.savedSentence(normal) {
                ReadingCard(title: tx("¿Cuánto guardás?", "How much do you save?"), sentence: saved,
                            explanation: FinancialReading.savedExplanation(), id: "analysis.financial.saved")
            }
            if let debt = FinancialReading.debtSentence(normal) {
                ReadingCard(title: tx("¿Cuánto se va a deudas?", "How much goes to debts?"), sentence: debt,
                            explanation: FinancialReading.debtExplanation(), id: "analysis.financial.debts")
            }
        } else {
            ReadingCard(title: tx("Tu mes normal", "Your normal month"),
                        sentence: tx("Todavía no hay un mes completo con ingresos y gastos registrados.",
                                     "There is no complete month with income and expenses recorded yet."),
                        explanation: tx("Cuando lo haya, acá vas a ver cuánto te sobra en un mes normal, cuánto guardás y cuánto se va a deudas.",
                                        "When there is, you will see here how much is left in a normal month, how much you save and how much goes to debts."),
                        id: "analysis.financial.none")
        }
        let months = FinancialReading.chartMonths(analysis)
        if !months.isEmpty {
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                SectionHeader(title: tx("Mes a mes", "Month by month"))
                Text(tx("Lo que entró y lo que salió cada mes. Los meses sin nada registrado no aparecen.",
                        "What came in and went out each month. Months with nothing recorded are not shown."))
                    .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                IncomeExpenseChart(months: months)
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("analysis.financial.months")
        }
        if FinancialReading.canCompare(analysis) {
            RisesCard(rises: FinancialReading.rises(analysis))
        }
    }
}

/// A title, the sentence that answers it, and one line saying what it means.
private struct ReadingCard: View {
    let title: String
    let sentence: String
    let explanation: String
    let id: String

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(title).font(DincrFont.label).foregroundStyle(DincrColor.text2).accessibilityAddTraits(.isHeader)
            Text(sentence).font(DincrFont.title2).foregroundStyle(DincrColor.text).fixedSize(horizontal: false, vertical: true)
            Text(explanation).font(DincrFont.bodySmall).foregroundStyle(DincrColor.textMuted).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .dincrCard()
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(id)
    }
}

/// "¿En qué gastás más de lo normal este mes?": only categories already above their average.
private struct RisesCard: View {
    @Environment(AppModel.self) private var model
    let rises: [FinancialAnalysis.Category]

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(tx("¿En qué gastás más de lo normal este mes?", "Where are you spending more than usual this month?"))
                .font(DincrFont.label).foregroundStyle(DincrColor.text2).accessibilityAddTraits(.isHeader)
            if rises.isEmpty {
                Text(tx("En nada, por ahora: ninguna categoría pasa de lo que gastás normalmente.",
                        "Nothing so far: no category is above what you usually spend."))
                    .font(DincrFont.body).foregroundStyle(DincrColor.text)
            } else {
                ForEach(Array(rises.enumerated()), id: \.offset) { _, row in
                    Text(FinancialReading.riseLine(row, format: model.moneyFormat)).font(DincrFont.body).foregroundStyle(DincrColor.text)
                }
            }
            Text(tx("Comparamos este mes con el promedio de tus últimos meses. El mes todavía no termina.",
                    "We compare this month with the average of your last months. The month is not over yet."))
                .font(DincrFont.bodySmall).foregroundStyle(DincrColor.textMuted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .dincrCard()
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("analysis.financial.rises")
    }
}
