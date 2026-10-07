import DincrCore
import DincrDesign
import SwiftUI

/// Loads one value for a screen with the loading / error (with retry) / content states of the
/// design system. An answer that arrives after the session changed is dropped (`AppModel.message`).
struct AsyncContent<Value: Equatable, Content: View>: View {
    @Environment(AppModel.self) private var model
    let fallback: String
    let load: @MainActor () async throws -> Value
    @ViewBuilder let content: (Value, @escaping () -> Void) -> Content
    @State private var state: LoadState<Value> = .loading
    @State private var generation = 0

    init(fallback: String = tx("No pudimos cargar esta información.", "We couldn’t load this information."),
         load: @escaping @MainActor () async throws -> Value,
         @ViewBuilder content: @escaping (Value, @escaping () -> Void) -> Content) {
        self.fallback = fallback; self.load = load; self.content = content
    }

    var body: some View {
        Group {
            switch state {
            case .loading:
                SkeletonView(rows: 3)
            case .failed(let message):
                ErrorStateView(message: message) { generation += 1 }
            case .loaded(let value):
                content(value) { generation += 1 }
            }
        }
        .task(id: generation) { await run() }
    }

    private func run() async {
        let epoch = model.currentEpoch
        do {
            let value = try await load()
            if epoch == model.currentEpoch { state = .loaded(value) }
        } catch is CancellationError {
            return
        } catch {
            if let message = model.message(for: error, epoch: epoch, fallback: fallback) { state = .failed(message) }
        }
    }
}

/// A scrolling screen with the DINCR background, readable width and standard padding.
struct ScreenScroll<Content: View>: View {
    let title: String
    @ViewBuilder let content: () -> Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DincrSpacing.s4) { content() }
                .padding(.horizontal, DincrSpacing.s4)
                .padding(.bottom, DincrSpacing.s8)
                .frame(maxWidth: 640)
                .frame(maxWidth: .infinity)
        }
        .dincrScreenBackground()
        .navigationTitle(title)
    }
}

struct SectionHeader: View {
    let title: String
    var body: some View {
        Text(title).font(DincrFont.title2).foregroundStyle(DincrColor.text)
            .accessibilityAddTraits(.isHeader)
            .padding(.top, DincrSpacing.s2)
    }
}

/// A label and an amount; unknown amounts show "—" and are read "sin dato" (never zero).
struct FigureRow: View {
    let label: String
    let amount: Decimal?
    var sign: MoneyFormat.Sign = .none
    var currency: String? = nil

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
            Spacer(minLength: DincrSpacing.s3)
            MoneyText(amount, sign: sign, currency: currency, font: DincrFont.amount)
        }
        .accessibilityElement(children: .combine)
    }
}

struct InfoRow: View {
    let label: String
    let value: String
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
            Spacer(minLength: DincrSpacing.s3)
            Text(value).font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(DincrColor.text).multilineTextAlignment(.trailing)
        }
        .accessibilityElement(children: .combine)
    }
}

/// A navigation row of a hub.
struct HubRow: View {
    let symbol: String
    let title: String
    let subtitle: String
    var locked: PlanTier? = nil

    var body: some View {
        HStack(spacing: DincrSpacing.s3) {
            Image(systemName: symbol).font(.system(size: 18, weight: .medium)).foregroundStyle(DincrColor.tint)
                .frame(width: 36, height: 36).background(DincrColor.tintContainer, in: RoundedRectangle(cornerRadius: DincrRadius.sm, style: .continuous))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(DincrFont.body.weight(.semibold)).foregroundStyle(DincrColor.text)
                Text(subtitle).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
            Spacer(minLength: 0)
            if let locked { PlanBadge(plan: locked.rawValue) }
            Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(DincrColor.textMuted).accessibilityHidden(true)
        }
        .padding(.vertical, DincrSpacing.s1)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

/// Shown instead of a feature the account's plan does not include (the backend would answer 403).
struct PlanRequiredView: View {
    let tier: PlanTier
    let feature: String

    var body: some View {
        EmptyStateView(
            symbol: "lock",
            title: tx("Disponible en \(PlanLabel.name(tier.rawValue))", "Available on \(PlanLabel.name(tier.rawValue))"),
            message: tx("\(feature) es parte de la suscripción \(PlanLabel.name(tier.rawValue)). Podés verla en Perfil → Suscripción.", "\(feature) is part of the \(PlanLabel.name(tier.rawValue)) subscription. See it in Profile → Subscription.")
        ) { EmptyView() }
    }
}

/// Shown when an operational switch pauses a feature (B17).
struct FeaturePausedView: View {
    let message: String?
    var body: some View {
        EmptyStateView(symbol: "pause.circle", title: tx("En pausa por mantenimiento", "Paused for maintenance"),
                       message: message ?? tx("Esta función vuelve pronto. Tus datos están a salvo.", "This feature is back soon. Your data is safe.")) { EmptyView() }
    }
}

/// B16 — under strategy and advisory screens.
struct FinancialDisclaimer: View {
    var body: some View {
        Text(tx("DINCR te orienta con tus propios datos. No es asesoría financiera, legal ni tributaria profesional.",
                "DINCR guides you with your own data. It is not professional financial, legal or tax advice."))
            .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            .padding(.top, DincrSpacing.s2)
    }
}

/// `YYYY-MM` with previous / next month buttons (never beyond the current month).
struct MonthPicker: View {
    @Binding var period: String

    var body: some View {
        HStack {
            Button { period = Period.shift(period, by: -1) } label: { Image(systemName: "chevron.left") }
                .accessibilityLabel(tx("Mes anterior", "Previous month"))
            Spacer()
            Text(Period.title(period)).font(DincrFont.title2).foregroundStyle(DincrColor.text)
            Spacer()
            Button { period = Period.shift(period, by: 1) } label: { Image(systemName: "chevron.right") }
                .accessibilityLabel(tx("Mes siguiente", "Next month"))
                .disabled(period >= Period.current)
        }
        .frame(minHeight: 44)
        .foregroundStyle(DincrColor.tint)
    }
}

enum Period {
    static var current: String { String(Day.today().prefix(7)) }

    static func shift(_ period: String, by months: Int) -> String {
        let parts = period.split(separator: "-").compactMap { Int($0) }
        guard parts.count == 2 else { return current }
        let total = parts[0] * 12 + (parts[1] - 1) + months
        return String(format: "%04d-%02d", total / 12, total % 12 + 1)
    }

    static func title(_ period: String) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: AppLanguage.current == .spanish ? "es_CR" : "en_US")
        formatter.dateFormat = "LLLL yyyy"
        let parser = DateFormatter()
        parser.locale = Locale(identifier: "en_US_POSIX")
        parser.dateFormat = "yyyy-MM"
        return parser.date(from: period).map { formatter.string(from: $0).capitalized } ?? period
    }
}

enum Day {
    /// Local calendar day `YYYY-MM-DD` (same format as `MovementEditor.dayFormatter`, but usable from
    /// any isolation).
    static func formatter() -> DateFormatter {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = .current
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }

    static func today() -> String { formatter().string(from: .now) }

    static func label(_ day: String?) -> String {
        guard let day, let date = formatter().date(from: String(day.prefix(10))) else { return "—" }
        return date.formatted(.dateTime.day().month(.abbreviated).year().locale(Locale(identifier: AppLanguage.current == .spanish ? "es_CR" : "en_US")))
    }
}

/// A money text field in the user's separators. Returns the parsed value through `AmountInput`.
struct MoneyField: View {
    let label: String
    @Binding var text: String
    var error: String? = nil
    var identifier: String? = nil
    @Environment(\.moneyFormat) private var format

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s1) {
            Text(label).font(DincrFont.label).foregroundStyle(DincrColor.text2)
            HStack(spacing: DincrSpacing.s2) {
                Text(format.symbol).foregroundStyle(DincrColor.textMuted).accessibilityHidden(true)
                TextField(label, text: $text, prompt: Text(format.inputText(18_450)))
                    .keyboardType(.decimalPad)
                    .font(DincrFont.body.monospacedDigit())
                    .accessibilityIdentifier(identifier ?? "")
            }
            if let error {
                Label(error, systemImage: "exclamationmark.circle").font(DincrFont.caption).foregroundStyle(DincrColor.negative)
            }
        }
    }
}

extension MoneyFormat {
    /// "Escribí un monto mayor que cero, por ejemplo 18.450." in the user's separators.
    var amountHint: String {
        let example = inputText(18_450)
        return tx("Escribí un monto mayor que cero, por ejemplo \(example).", "Enter an amount above zero, for example \(example).")
    }
}
