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
        @Environment(\.dincrOwnerAppearance) private var owner

        var body: some View {
            let tint = owner ? (configuration.isPressed ? OwnerColor.accentActive : OwnerColor.accent)
                             : (configuration.isPressed ? DincrColor.tintPressed : DincrColor.tint)
            let fill = role == .destructive ? DincrColor.negative : tint
            let label = owner && role != .destructive ? OwnerColor.onAccent : DincrColor.onTint
            ZStack {
                configuration.label.opacity(isLoading ? 0 : 1)
                if isLoading { ProgressView().tint(label) }
            }
            .font(DincrFont.title2)
            .foregroundStyle(label)
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
        SecondaryBody(configuration: configuration)
    }

    private struct SecondaryBody: View {
        let configuration: Configuration
        @Environment(\.dincrOwnerAppearance) private var owner

        var body: some View {
            configuration.label
                .font(DincrFont.title2)
                .foregroundStyle(owner ? OwnerColor.onAccentContainer : DincrColor.onTintContainer)
                .frame(maxWidth: .infinity, minHeight: 52)
                .padding(.horizontal, DincrSpacing.s5)
                .background(owner ? OwnerColor.accentContainer : DincrColor.tintContainer,
                            in: RoundedRectangle(cornerRadius: DincrRadius.md, style: .continuous))
                .opacity(configuration.isPressed ? 0.85 : 1)
                .contentShape(Rectangle())
        }
    }
}

public extension ButtonStyle where Self == DincrPrimaryButtonStyle {
    static var dincrPrimary: DincrPrimaryButtonStyle { DincrPrimaryButtonStyle() }
    static func dincrPrimary(loading: Bool) -> DincrPrimaryButtonStyle { DincrPrimaryButtonStyle(isLoading: loading) }
}

public extension ButtonStyle where Self == DincrSecondaryButtonStyle {
    static var dincrSecondary: DincrSecondaryButtonStyle { DincrSecondaryButtonStyle() }
}

/// A row of filter pills, one selected. Each is a real button of at least 44 pt that says it is selected;
/// scrolls sideways instead of squeezing at large text sizes.
public struct DincrFilterChips<Value: Hashable>: View {
    let options: [Value]
    @Binding var selection: Value
    let title: (Value) -> String
    @Environment(\.dincrOwnerAppearance) private var owner

    public init(_ options: [Value], selection: Binding<Value>, title: @escaping (Value) -> String) {
        self.options = options; _selection = selection; self.title = title
    }

    public var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: DincrSpacing.s2) {
                ForEach(options, id: \.self) { option in
                    let selected = option == selection
                    Button { selection = option } label: {
                        Text(title(option))
                            .font(DincrFont.bodySmall.weight(.semibold))
                            .foregroundStyle(selected ? (owner ? OwnerColor.onAccent : DincrColor.onTint) : (owner ? OwnerColor.text2 : DincrColor.text2))
                            .padding(.horizontal, DincrSpacing.s4)
                            .frame(minHeight: 44)
                            .background(selected ? (owner ? OwnerColor.accent : DincrColor.tint) : (owner ? OwnerColor.surface : DincrColor.surface), in: Capsule())
                            .contentShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(selected ? .isSelected : [])
                }
            }
        }
        .scrollBounceBehavior(.basedOnSize, axes: .horizontal)
    }
}
