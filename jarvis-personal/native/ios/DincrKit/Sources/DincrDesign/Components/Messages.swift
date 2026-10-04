import DincrCore
import SwiftUI

/// A message with its meaning (DESIGN.md → Messages): technical error, attention, opportunity or
/// positive. Each kind has its own icon, color and shape, and VoiceOver reads the kind first.
public struct DincrMessage: View {
    let kind: MessageKind
    let title: String
    let message: String

    public init(_ kind: MessageKind, title: String, message: String = "") {
        self.kind = kind; self.title = title; self.message = message
    }

    public var body: some View {
        let style = DincrMessageStyle(kind)
        HStack(alignment: .top, spacing: DincrSpacing.s3) {
            // The icon carries the spoken kind, so VoiceOver reads it before the title.
            Image(systemName: style.symbol).foregroundStyle(style.color).accessibilityLabel(style.spokenKind)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(DincrFont.title2).foregroundStyle(DincrColor.text)
                if !message.isEmpty {
                    Text(message).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
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
            .clipShape(RoundedRectangle(cornerRadius: DincrRadius.md, style: .continuous))
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
            (symbol, color, fill) = ("exclamationmark.icloud", DincrColor.text2, DincrColor.surface2)
            spokenKind = language.pick("Problema técnico", "Technical problem")
        case .attention:
            (symbol, color, fill) = ("bell.badge", DincrColor.warning, DincrColor.warningContainer)
            spokenKind = language.pick("Para atender", "Needs attention")
        case .opportunity:
            (symbol, color, fill) = ("sparkles", DincrColor.info, DincrColor.infoContainer)
            spokenKind = language.pick("Recomendación", "Suggestion")
        case .positive:
            (symbol, color, fill) = ("checkmark.seal", DincrColor.positive, DincrColor.positiveContainer)
            spokenKind = language.pick("Buenas noticias", "Good news")
        }
    }
}
