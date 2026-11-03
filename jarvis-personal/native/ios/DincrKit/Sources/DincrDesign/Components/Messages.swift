import DincrCore
import SwiftUI

/// A message with its meaning (DESIGN.md → Messages): technical error, attention, opportunity or
/// positive. Each kind has its own icon, color and shape, and VoiceOver reads the kind first.
public struct DincrMessage: View {
    let kind: MessageKind
    let title: String
    let message: String
    @Environment(\.dincrOwnerAppearance) private var owner

    public init(_ kind: MessageKind, title: String, message: String = "") {
        self.kind = kind; self.title = title; self.message = message
    }

    public var body: some View {
        if owner { ownerBody } else { regularBody }
    }

    /// The Owner's message: a plain row on its surface. The icon's color says what it means, so a
    /// fact never looks like a failure. VoiceOver still reads the kind first.
    private var ownerBody: some View {
        let style = DincrMessageStyle(kind)
        return HStack(alignment: .top, spacing: DincrSpacing.s3) {
            Image(systemName: style.symbol)
                .font(.body)
                .foregroundStyle(kind == .opportunity ? OwnerColor.accent : style.color)
                .frame(width: 28)
                .accessibilityLabel(style.spokenKind)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(DincrFont.body).foregroundStyle(OwnerColor.text)
                if !message.isEmpty {
                    Text(message).font(DincrFont.bodySmall).foregroundStyle(OwnerColor.text2)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, DincrSpacing.s4)
        .padding(.vertical, DincrSpacing.s3)
        .background(OwnerColor.surface, in: RoundedRectangle(cornerRadius: OwnerRadius.card, style: .continuous))
        .accessibilityElement(children: .combine)
    }

    private var regularBody: some View {
        let style = DincrMessageStyle(kind)
        return HStack(alignment: .top, spacing: DincrSpacing.s3) {
            // The icon carries the spoken kind, so VoiceOver reads it before the title.
            Image(systemName: style.symbol)
                .font(.system(size: DincrIconSize.md, weight: .medium))
                .foregroundStyle(style.color)
                .frame(width: 36, height: 36)
                .background(OwnerColor.surface, in: Circle())
                .accessibilityLabel(style.spokenKind)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(DincrFont.title2).foregroundStyle(.dincrText)
                if !message.isEmpty {
                    Text(message).font(DincrFont.bodySmall).foregroundStyle(.dincrText2)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, DincrSpacing.s4)
        .padding(.vertical, DincrSpacing.s3)
        .background {
            // Attention carries a leading accent bar: it reads as "look here", never as a failure.
            ZStack(alignment: .leading) {
                style.fill
                if kind == .attention { style.color.frame(width: 4) }
            }
            .clipShape(RoundedRectangle(cornerRadius: DincrRadius.lg, style: .continuous))
        }
        .accessibilityElement(children: .combine)
    }
}

/// Icon, colors and spoken name of each message kind. Technical errors are neutral (no financial
/// red or amber), so they can't be mistaken for a situation in the user's money.
struct DincrMessageStyle {
    let symbol: String
    let color: Color
    let fill: Color
    let spokenKind: String

    init(_ kind: MessageKind) {
        let language = AppLanguage.current
        switch kind {
        case .technicalError:
            (symbol, color, fill) = ("exclamationmark.icloud", OwnerColor.text2, OwnerColor.surface2)
            spokenKind = language.pick("Problema técnico", "Technical problem")
        case .attention:
            (symbol, color, fill) = ("bell.badge", DincrColor.warning, DincrColor.warningContainer)
            spokenKind = language.pick("Para atender", "Needs attention")
        case .opportunity:
            (symbol, color, fill) = ("sparkles", OwnerColor.accent, OwnerColor.accentContainer)
            spokenKind = language.pick("Recomendación", "Suggestion")
        case .positive:
            (symbol, color, fill) = ("checkmark.seal", DincrColor.positive, DincrColor.positiveContainer)
            spokenKind = language.pick("Buenas noticias", "Good news")
        }
    }
}
