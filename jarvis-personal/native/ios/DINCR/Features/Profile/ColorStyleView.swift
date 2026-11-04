import DincrCore
import DincrDesign
import SwiftUI

/// Perfil → Estilo de colores: every plan picks one, it applies at once and stays on this device.
/// Android: `ColorStyleScreen`.
struct ColorStyleView: View {
    @State private var store = DincrColorStyleStore.shared

    var body: some View {
        ScreenScroll(title: tx("Estilo de colores", "Color style")) {
            ForEach(DincrColorStyles.all) { style in
                let selected = store.id == style.id
                Button { store.select(style.id) } label: {
                    VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                        HStack {
                            Text(style.name).font(DincrFont.body.weight(.semibold)).foregroundStyle(.dincrText)
                            Spacer(minLength: DincrSpacing.s2)
                            Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                                .font(.title3).foregroundStyle(selected ? AnyShapeStyle(.dincrTint) : AnyShapeStyle(.dincrTextMuted))
                        }
                        HStack(spacing: DincrSpacing.s1) {
                            ForEach(style.swatches.indices, id: \.self) { index in
                                Capsule().fill(style.swatch(index)).frame(height: 28)
                            }
                        }
                    }
                    .dincrCard()
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(style.name)
                .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton)
                .accessibilityIdentifier("colorStyle.\(style.id)")
            }
            Text(tx("Se guarda en este teléfono. Las alertas siguen usando verde, rojo y ámbar.", "It stays on this phone. Alerts keep using green, red and amber."))
                .font(DincrFont.caption).foregroundStyle(.dincrTextMuted)
        }
    }
}
