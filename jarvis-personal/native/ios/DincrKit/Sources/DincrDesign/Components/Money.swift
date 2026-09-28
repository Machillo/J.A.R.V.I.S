import DincrCore
import SwiftUI

/// Formatting preferences flow through the environment from the signed-in profile.
private struct MoneyFormatKey: EnvironmentKey {
    static let defaultValue = MoneyFormat()
}

public extension EnvironmentValues {
    var moneyFormat: MoneyFormat {
        get { self[MoneyFormatKey.self] }
        set { self[MoneyFormatKey.self] = newValue }
    }
}

/// An amount with tabular digits, an explicit sign when it is a movement, and a spoken label.
/// Unknown values render "—" and say "sin dato" — never zero (PRODUCT.md: truth before comfort).
public struct MoneyText: View {
    let amount: Decimal?
    let sign: MoneyFormat.Sign
    let currency: String?
    let font: Font
    @Environment(\.moneyFormat) private var format

    public init(_ amount: Decimal?, sign: MoneyFormat.Sign = .none, currency: String? = nil, font: Font = DincrFont.amount) {
        self.amount = amount; self.sign = sign; self.currency = currency; self.font = font
    }

    public var body: some View {
        Text(amount.map { format.string($0, sign: sign, currency: currency) } ?? "—")
            .font(font)
            .foregroundStyle(sign == .income ? DincrColor.positive : DincrColor.text)
            .lineLimit(1)
            .minimumScaleFactor(0.6)
            .accessibilityLabel(amount.map { format.spoken($0, sign: sign, currency: currency) } ?? AppLanguage.current.pick("sin dato", "no data"))
    }
}

/// The signature row (DESIGN.md → Money row): category icon, description, date · category,
/// signed amount. Read-only rows carry a lock caption instead of a disabled look.
public struct MoneyRow: View {
    let title: String
    let subtitle: String
    let amount: Decimal
    let kind: Movement.Kind
    let symbol: String
    let isReadOnly: Bool
    let currency: String?

    public init(title: String, subtitle: String, amount: Decimal, kind: Movement.Kind, symbol: String, isReadOnly: Bool = false, currency: String? = nil) {
        self.title = title; self.subtitle = subtitle; self.amount = amount; self.kind = kind
        self.symbol = symbol; self.isReadOnly = isReadOnly; self.currency = currency
    }

    public var body: some View {
        HStack(spacing: DincrSpacing.s3) {
            Image(systemName: symbol)
                .font(.system(size: DincrIconSize.md, weight: .medium))
                .foregroundStyle(kind == .income ? DincrColor.positive : DincrColor.text2)
                .frame(width: 40, height: 40)
                .background(DincrColor.surface2, in: Circle())
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(DincrFont.body)
                    .foregroundStyle(DincrColor.text)
                    .lineLimit(2)
                HStack(spacing: 4) {
                    if isReadOnly {
                        Image(systemName: "lock.fill").imageScale(.small).accessibilityHidden(true)
                    }
                    Text(subtitle)
                }
                .font(DincrFont.caption)
                .foregroundStyle(DincrColor.textMuted)
            }
            Spacer(minLength: DincrSpacing.s2)
            MoneyText(amount, sign: kind == .income ? .income : .expense, currency: currency)
                .layoutPriority(1)
        }
        .padding(.vertical, DincrSpacing.s2)
        .frame(minHeight: 56)
        .accessibilityElement(children: .combine)
    }
}
