import DincrCore
import DincrDesign
import SwiftUI

/// A bank's logo from the historical assets (`BankBrand.logoAsset`), or its initials on a neutral
/// tile when DINCR has no logo for it. The bank's name is always the accessible label.
struct BankLogo: View {
    let brand: BankBrand
    var size: CGFloat = 40

    var body: some View {
        Group {
            if let asset = brand.logoAsset {
                Image(asset)
                    .resizable()
                    .scaledToFit()
                    .padding(size * 0.12)
            } else if brand.isKnown || !brand.name.isEmpty {
                Text(brand.short)
                    .font(.system(size: size * 0.32, weight: .bold))
                    .foregroundStyle(DincrColor.text2)
                    .minimumScaleFactor(0.5)
                    .lineLimit(1)
                    .padding(size * 0.08)
            } else {
                Image(systemName: "building.columns").foregroundStyle(DincrColor.text2)
            }
        }
        .frame(width: size, height: size)
        .background(Color.white, in: RoundedRectangle(cornerRadius: DincrRadius.sm, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: DincrRadius.sm, style: .continuous).strokeBorder(DincrColor.line, lineWidth: 1))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(brand.name.isEmpty ? tx("Institución", "Institution") : brand.name)
    }
}
