import SwiftUI

/// Filled tint button: the one action that completes the task (DESIGN.md → Buttons).
public struct DincrPrimaryButtonStyle: ButtonStyle {
    var isLoading: Bool
    var role: Role

    public enum Role: Sendable { case standard, destructive }

    public init(isLoading: Bool = false, role: Role = .standard) {
        self.isLoading = isLoading; self.role = role
    }

    public func makeBody(configuration: Configuration) -> some View {
        ButtonBody(configuration: configuration, isLoading: isLoading, role: role)
    }

    private struct ButtonBody: View {
        let configuration: Configuration
        let isLoading: Bool
        let role: Role
        @Environment(\.isEnabled) private var isEnabled

        var body: some View {
            let fill = role == .destructive ? DincrColor.negative : (configuration.isPressed ? DincrColor.tintPressed : DincrColor.tint)
            ZStack {
                configuration.label.opacity(isLoading ? 0 : 1)
                if isLoading { ProgressView().tint(DincrColor.onTint) }
            }
            .font(DincrFont.title2)
            .foregroundStyle(DincrColor.onTint)
            .frame(maxWidth: .infinity, minHeight: 52)
            .padding(.horizontal, DincrSpacing.s5)
            .background(fill, in: RoundedRectangle(cornerRadius: DincrRadius.md, style: .continuous))
            .opacity(isEnabled || isLoading ? 1 : 0.4)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeOut(duration: 0.1), value: configuration.isPressed)
            .contentShape(Rectangle())
        }
    }
}

/// Tonal secondary button.
public struct DincrSecondaryButtonStyle: ButtonStyle {
    public init() {}

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(DincrFont.title2)
            .foregroundStyle(DincrColor.onTintContainer)
            .frame(maxWidth: .infinity, minHeight: 52)
            .padding(.horizontal, DincrSpacing.s5)
            .background(DincrColor.tintContainer, in: RoundedRectangle(cornerRadius: DincrRadius.md, style: .continuous))
            .opacity(configuration.isPressed ? 0.85 : 1)
            .contentShape(Rectangle())
    }
}

public extension ButtonStyle where Self == DincrPrimaryButtonStyle {
    static var dincrPrimary: DincrPrimaryButtonStyle { DincrPrimaryButtonStyle() }
    static func dincrPrimary(loading: Bool) -> DincrPrimaryButtonStyle { DincrPrimaryButtonStyle(isLoading: loading) }
}

public extension ButtonStyle where Self == DincrSecondaryButtonStyle {
    static var dincrSecondary: DincrSecondaryButtonStyle { DincrSecondaryButtonStyle() }
}
