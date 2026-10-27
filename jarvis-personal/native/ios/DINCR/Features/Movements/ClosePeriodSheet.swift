import DincrCore
import DincrDesign
import SwiftUI

/// The close (3d): one rate converts every dollar expense waiting in one period (a card's statement
/// cycle, or a calendar month). The user types their own rate — DINCR never looks one up — and sees
/// the colones total before confirming. Single-flight; a retry reuses the same idempotency key.
struct ClosePeriodSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.moneyFormat) private var format
    let period: PendingConversion.Period
    var latestRate: Decimal?
    let onClosed: (String) -> Void

    @State private var rateText = ""
    @State private var rateError: String?
    @State private var saveError: String?
    @State private var saving = false
    @State private var submission: (body: PendingClose, key: String)?

    private var base: String { (model.profile?.baseCurrency ?? "CRC").uppercased() }
    private var rate: Decimal? { RateInput.parse(rateText, separators: format.separators) }

    /// The colones the close records: each currency's total at the typed rate (the server converts row by row).
    private var preview: Decimal? {
        guard let rate else { return nil }
        let parts = period.totals.map { ConversionPreview.baseAmount(typed: $0.amount, currency: $0.currency, base: base, rate: rate) }
        guard parts.allSatisfy({ $0 != nil }) else { return nil }
        return parts.compactMap { $0 }.reduce(0, +)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(PendingPeriodLabel.title(period)).font(DincrFont.title2)
                    ForEach(period.totals) { total in
                        Text(tx("\(model.moneyFormat.string(total.amount, currency: total.currency)) en \(total.count) gasto(s)",
                                "\(model.moneyFormat.string(total.amount, currency: total.currency)) in \(total.count) expense(s)"))
                            .font(DincrFont.body.monospacedDigit())
                    }
                }
                Section {
                    VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                        Text(tx("Tipo de cambio (colones por 1 dólar)", "Exchange rate (colones per 1 dollar)")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                        TextField(tx("Tipo de cambio", "Exchange rate"), text: $rateText, prompt: Text(format.inputText(Decimal(string: "507.5")!)))
                            .keyboardType(.decimalPad)
                            .accessibilityIdentifier("close.rate")
                        if let rateError { Label(rateError, systemImage: "exclamationmark.circle").font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
                        if let preview {
                            Text(tx("Se registran \(format.string(preview)) en total. Usá el tipo de cambio de tu estado de cuenta; DINCR no consulta tasas.",
                                    "\(format.string(preview)) are recorded in total. Use your statement’s rate; DINCR doesn’t look rates up."))
                                .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                                .accessibilityIdentifier("close.preview")
                        }
                    }
                }
                if let saveError {
                    Section { ErrorStateView(message: saveError).listRowInsets(EdgeInsets()) }.listRowBackground(Color.clear)
                }
            }
            .scrollContentBackground(.hidden)
            .dincrScreenBackground()
            .navigationTitle(tx("Convertir a colones", "Convert to colones"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    if saving { ProgressView() } else {
                        Button(tx("Convertir", "Convert")) { Task { await close() } }
                            .fontWeight(.semibold)
                            .accessibilityIdentifier("close.save")
                    }
                }
            }
            .interactiveDismissDisabled(saving)
            .onAppear { if rateText.isEmpty, let latestRate { rateText = format.inputText(latestRate) } }
        }
        .presentationDetents([.medium, .large])
    }

    private func close() async {
        guard !saving else { return }
        guard let rate else {
            rateError = tx("Escribí cuántos colones vale 1 dólar, por ejemplo \(format.inputText(Decimal(string: "507.5")!)).",
                           "Enter how many colones 1 dollar is worth, for example \(format.inputText(Decimal(string: "507.5")!)).")
            return
        }
        rateError = nil
        saving = true
        saveError = nil
        defer { saving = false }
        let body = PendingClose(periodKey: period.key, exchangeRate: rate)
        let key = (submission?.body == body ? submission?.key : nil) ?? IdempotencyKey.new()
        submission = (body, key)
        do {
            let result = try await model.service.closePending(body, idempotencyKey: key)
            onClosed(tx("Convertidos \(result.converted) gasto(s): \(format.string(result.amount))",
                        "Converted \(result.converted) expense(s): \(format.string(result.amount))"))
            dismiss()
        } catch let error as APIError {
            saveError = error.message
        } catch is CancellationError {
            return
        } catch AuthError.signedOut {
            await model.signOut()
        } catch {
            saveError = tx("No pudimos convertir. Revisá tu conexión e intentá de nuevo.", "We couldn’t convert. Check your connection and try again.")
        }
    }
}

/// How a close is named: "Corte del 21 oct · Tarjeta ••5678" or "Octubre 2026".
enum PendingPeriodLabel {
    static func title(_ period: PendingConversion.Period) -> String {
        if period.isCard {
            let card = [period.accountName, period.accountLast4.map { "••\($0)" }].compactMap { $0 }.joined(separator: " ")
            let cut = tx("Corte del \(DayLabel.format(period.end))", "Cut of \(DayLabel.format(period.end))")
            return card.isEmpty ? cut : "\(cut) · \(card)"
        }
        let parts = period.start.prefix(7).split(separator: "-").compactMap { Int($0) }
        guard parts.count == 2, let date = Calendar(identifier: .gregorian).date(from: DateComponents(year: parts[0], month: parts[1], day: 1)) else {
            return String(period.start.prefix(7))
        }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: AppLanguage.current == .spanish ? "es_CR" : "en_US")
        formatter.setLocalizedDateFormatFromTemplate("MMMMyyyy")
        return formatter.string(from: date).capitalized(with: formatter.locale)
    }
}
