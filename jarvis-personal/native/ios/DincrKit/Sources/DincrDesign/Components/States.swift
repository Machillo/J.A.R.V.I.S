import DincrCore
import SwiftUI

/// Loading placeholder shaped like the real content: a key-figure bar and a few rows.
/// Pulses gently; static under Reduce Motion (DESIGN_SYSTEM.md §3).
public struct SkeletonView: View {
    let rows: Int
    let showsFigure: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dincrDecorativeMotion) private var decorativeMotion
    @State private var dimmed = false

    public init(rows: Int = 4, showsFigure: Bool = true) {
        self.rows = rows; self.showsFigure = showsFigure
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s4) {
            if showsFigure {
                VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                    block(width: 120, height: 14)
                    block(width: 220, height: 36)
                }
                .dincrCard()
            }
            VStack(spacing: DincrSpacing.s4) {
                ForEach(0..<rows, id: \.self) { _ in
                    HStack(spacing: DincrSpacing.s3) {
                        Circle().fill(DincrColor.surface2).frame(width: 40, height: 40)
                        VStack(alignment: .leading, spacing: 6) {
                            block(width: 160, height: 14)
                            block(width: 100, height: 10)
                        }
                        Spacer()
                        block(width: 70, height: 14)
                    }
                }
            }
            .dincrCard()
        }
        .opacity(dimmed ? 0.55 : 1)
        .onAppear {
            guard !reduceMotion, decorativeMotion else { return }
            withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) { dimmed = true }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(AppLanguage.current.pick("Cargando", "Loading"))
    }

    private func block(width: CGFloat, height: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: DincrRadius.xs).fill(DincrColor.surface2).frame(width: width, height: height)
    }
}

/// Empty state that teaches: what will appear here and the action that fills it.
public struct EmptyStateView<Action: View>: View {
    let symbol: String
    let title: String
    let message: String
    let action: Action

    public init(symbol: String, title: String, message: String, @ViewBuilder action: () -> Action) {
        self.symbol = symbol; self.title = title; self.message = message; self.action = action()
    }

    public var body: some View {
        VStack(spacing: DincrSpacing.s3) {
            Image(systemName: symbol)
                .font(.system(size: 32, weight: .regular))
                .foregroundStyle(DincrColor.tint)
                .accessibilityHidden(true)
            Text(title).font(DincrFont.title2).foregroundStyle(DincrColor.text).multilineTextAlignment(.center)
            Text(message).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2).multilineTextAlignment(.center)
            action.padding(.top, DincrSpacing.s2)
        }
        .padding(DincrSpacing.s6)
        .frame(maxWidth: .infinity)
        .background(DincrColor.surface, in: RoundedRectangle(cornerRadius: DincrRadius.lg, style: .continuous))
    }
}

/// Inline error with the recovery next to it (DESIGN.md → Do's).
public struct ErrorStateView: View {
    let message: String
    let retry: (() -> Void)?

    public init(message: String, retry: (() -> Void)? = nil) {
        self.message = message; self.retry = retry
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            Label {
                Text(message).font(DincrFont.body).foregroundStyle(DincrColor.text)
            } icon: {
                Image(systemName: "xmark.octagon").foregroundStyle(DincrColor.negative)
            }
            if let retry {
                Button(AppLanguage.current.pick("Reintentar", "Try again"), action: retry)
                    .font(DincrFont.title2)
                    .foregroundStyle(DincrColor.tint)
                    .frame(minHeight: 44)
            }
        }
        .padding(DincrSpacing.s4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DincrColor.negativeContainer, in: RoundedRectangle(cornerRadius: DincrRadius.md, style: .continuous))
        .accessibilityElement(children: .contain)
    }
}

/// Global notice (offline, degraded service, writes paused). Status colors always come with an
/// icon and text.
public struct StatusBanner: View {
    public enum Tone: Sendable { case info, warning, error }
    let tone: Tone
    let title: String
    let message: String

    public init(tone: Tone, title: String, message: String) {
        self.tone = tone; self.title = title; self.message = message
    }

    public var body: some View {
        let (symbol, color, fill): (String, Color, Color) = switch tone {
        case .info: ("info.circle", DincrColor.info, DincrColor.infoContainer)
        case .warning: ("exclamationmark.triangle", DincrColor.warning, DincrColor.warningContainer)
        case .error: ("xmark.octagon", DincrColor.negative, DincrColor.negativeContainer)
        }
        HStack(alignment: .top, spacing: DincrSpacing.s3) {
            Image(systemName: symbol).foregroundStyle(color).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(DincrFont.title2).foregroundStyle(DincrColor.text)
                Text(message).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, DincrSpacing.s4)
        .padding(.vertical, DincrSpacing.s3)
        .background(fill, in: RoundedRectangle(cornerRadius: DincrRadius.md, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

/// Linear progress with its value in text (no rings — DESIGN.md → Shapes).
public struct DincrProgressBar: View {
    let fraction: Double
    let isOver: Bool

    public init(fraction: Double, isOver: Bool = false) {
        self.fraction = min(max(fraction, 0), 1); self.isOver = isOver
    }

    public var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule().fill(DincrColor.surface2)
                Capsule().fill(isOver ? DincrColor.negative : DincrColor.tint)
                    .frame(width: max(proxy.size.width * fraction, fraction > 0 ? 6 : 0))
            }
        }
        .frame(height: 8)
        .accessibilityHidden(true)
    }
}
