import DincrCore
import DincrDesign
import SwiftUI

/// Public pages on dincr.com (the landing owns legal and support content).
enum LegalLinks {
    static let terms = URL(string: "https://dincr.com/terminos/")!
    static let privacy = URL(string: "https://dincr.com/privacidad/")!
    static let support = URL(string: "https://dincr.com/soporte/")!
}

/// PARITY A8 — updated terms and privacy policy. Both must be accepted, with the versions
/// `/auth/me` asked for; nothing else opens until the backend records it.
struct LegalConsentView: View {
    @Environment(AppModel.self) private var model
    @State private var terms = false
    @State private var privacy = false
    @State private var saving = false
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DincrSpacing.s4) {
                BrandMark(size: 48)
                Text(tx("Actualizamos nuestros términos", "We updated our terms"))
                    .font(DincrFont.title1).foregroundStyle(DincrColor.text)
                    .accessibilityAddTraits(.isHeader)
                Text(tx("Para seguir usando DINCR, leé y aceptá los documentos vigentes.", "To keep using DINCR, read and accept the current documents."))
                    .font(DincrFont.body).foregroundStyle(DincrColor.text2)
                consentRow(tx("Acepto los Términos y Condiciones", "I accept the Terms and Conditions"), version: model.profile?.legal?.termsVersion, isOn: $terms, link: LegalLinks.terms, id: "legal.terms")
                consentRow(tx("Acepto la Política de Privacidad", "I accept the Privacy Policy"), version: model.profile?.legal?.privacyVersion, isOn: $privacy, link: LegalLinks.privacy, id: "legal.privacy")
                if let error { ErrorStateView(message: error) }
                Button(tx("Aceptar y continuar", "Accept and continue")) {
                    saving = true; error = nil
                    Task { error = await model.acceptLegal(); saving = false }
                }
                .buttonStyle(.dincrPrimary(loading: saving))
                .disabled(!(terms && privacy) || saving)
                .accessibilityIdentifier("legal.accept")
                Button(tx("Cerrar sesión", "Sign out")) { Task { await model.signOut() } }
                    .font(DincrFont.title2).foregroundStyle(DincrColor.tint)
                    .frame(maxWidth: .infinity, minHeight: 44)
            }
            .padding(DincrSpacing.s6)
            .frame(maxWidth: 600)
            .frame(maxWidth: .infinity)
        }
        .dincrScreenBackground()
    }

    private func consentRow(_ label: String, version: String?, isOn: Binding<Bool>, link: URL, id: String) -> some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Toggle(isOn: isOn) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(label).font(DincrFont.body).foregroundStyle(DincrColor.text)
                    if let version {
                        Text(tx("Versión \(version)", "Version \(version)")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                    }
                }
            }
            .tint(DincrColor.tint)
            .accessibilityIdentifier(id)
            Link(tx("Leer documento", "Read document"), destination: link)
                .font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(DincrColor.tint)
                .frame(minHeight: 44)
        }
        .dincrCard()
    }
}

/// PARITY A11 — first plan choice. Paid plans can be chosen here only while the launch promotion
/// is active; otherwise they arrive through the App Store (not available in this build).
struct PlanChooserView: View {
    @Environment(AppModel.self) private var model
    @State private var state: LoadState<Offer> = .loading
    @State private var busy: String?
    @State private var error: String?

    struct Offer: Equatable {
        let options: [PlanOption]
        let catalog: BillingCatalog?
        var promotionActive: Bool { PlanOffer.promotionActive(options: options, catalog: catalog) }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DincrSpacing.s4) {
                Text(tx("Elegí tu plan", "Choose your plan"))
                    .font(DincrFont.title1).foregroundStyle(DincrColor.text)
                    .accessibilityAddTraits(.isHeader)
                switch state {
                case .loading:
                    SkeletonView(rows: 3)
                case .failed(let message):
                    ErrorStateView(message: message) { Task { await load() } }
                case .loaded(let offer):
                    if offer.promotionActive, let notice = offer.catalog?.promotion?.message ?? offer.catalog?.notice {
                        StatusBanner(tone: .info, title: tx("Promoción de lanzamiento", "Launch promotion"), message: notice)
                    }
                    ForEach(offer.options) { option in
                        PlanCardView(option: option, catalog: offer.catalog,
                                     canChoose: PlanOffer.canChoose(option, promotionActive: offer.promotionActive),
                                     busy: busy == option.code, enabled: busy == nil) {
                            busy = option.code; error = nil
                            Task { error = await model.choosePlan(option.code); busy = nil }
                        }
                    }
                }
                if let error { ErrorStateView(message: error) }
                Button(tx("Cerrar sesión", "Sign out")) { Task { await model.signOut() } }
                    .font(DincrFont.title2).foregroundStyle(DincrColor.tint)
                    .frame(maxWidth: .infinity, minHeight: 44)
            }
            .padding(DincrSpacing.s6)
            .frame(maxWidth: 600)
            .frame(maxWidth: .infinity)
        }
        .dincrScreenBackground()
        .task { if case .loading = state { await load() } }
    }

    private func load() async {
        state = .loading
        let epoch = model.currentEpoch
        do {
            let options = try await model.service.plans()
            // Prices and the promotion are optional: without the catalog, paid plans stay unavailable.
            let catalog = try? await model.service.billingCatalog()
            state = .loaded(Offer(options: options, catalog: catalog))
        } catch is CancellationError {
            return
        } catch {
            if let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar los planes.", "We couldn’t load the plans.")) {
                state = .failed(message)
            }
        }
    }
}

struct PlanCardView: View {
    let option: PlanOption
    let catalog: BillingCatalog?
    let canChoose: Bool
    let busy: Bool
    let enabled: Bool
    let choose: () -> Void

    var body: some View {
        let paid = option.code != PlanTier.free.rawValue
        let price = catalog?.plans?.first { $0.code == option.code }?.regularPriceCrc ?? option.regularPriceCrc
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(option.name ?? option.code.uppercased()).font(DincrFont.title1).foregroundStyle(DincrColor.text)
            if let tagline = option.tagline {
                Text(tagline).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
            }
            if !paid {
                Text(tx("Gratis", "Free")).font(DincrFont.title2)
            } else if let price {
                Text(MoneyFormat(currency: "CRC").string(Decimal(price)) + tx(" al mes", " per month")).font(DincrFont.title2)
            }
            ForEach(option.features ?? [], id: \.self) { feature in
                Label(feature, systemImage: "checkmark").font(DincrFont.bodySmall).foregroundStyle(DincrColor.text)
            }
            if canChoose {
                Button(tx("Elegir \(option.name ?? option.code)", "Choose \(option.name ?? option.code)"), action: choose)
                    .buttonStyle(.dincrPrimary(loading: busy))
                    .disabled(!enabled)
                    .padding(.top, DincrSpacing.s2)
            } else {
                Text(tx("Próximamente en las tiendas", "Coming soon to the stores"))
                    .font(DincrFont.bodySmall).foregroundStyle(DincrColor.textMuted)
            }
        }
        .dincrCard()
    }
}
