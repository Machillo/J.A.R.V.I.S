import DincrCore
import DincrDesign
import SwiftUI

/// What DINCR is and what it's for, once per account on this device, right before the first profile
/// setup. Only words and drawings: it asks nothing and writes nothing but its own "seen" mark.
/// Android twin: `WelcomeStoryScreen`.
struct WelcomeStoryView: View {
    let finish: () -> Void
    @State private var page = 0

    private static let pages: [(title: String, message: String, art: WelcomeArt.Kind)] = [
        (tx("Tu dinero, con propósito", "Your money, with purpose"),
         tx("DINCR reúne tus ingresos, gastos, deudas y metas en un solo lugar.", "DINCR brings your income, expenses, debts and goals into one place."), .together),
        (tx("Sabé dónde estás", "Know where you stand"),
         tx("Mirá de un vistazo cuánto entra, cuánto sale y cómo va tu mes.", "See at a glance what comes in, what goes out and how your month is going."), .month),
        (tx("Sabé qué sigue", "Know what comes next"),
         tx("Con tus datos, DINCR te muestra qué atender primero, paso a paso.", "With your data, DINCR shows you what to take care of first, step by step."), .steps),
        (tx("Tus datos, tus decisiones", "Your data, your decisions"),
         tx("Vos decidís qué registrar. DINCR nunca te pide la contraseña de tu banco.", "You decide what to record. DINCR never asks for your bank password."), .safe),
    ]

    var body: some View {
        VStack(spacing: DincrSpacing.s4) {
            HStack {
                Spacer()
                Button(tx("Omitir", "Skip"), action: finish)
                    .font(DincrFont.body.weight(.semibold))
                    .foregroundStyle(OwnerColor.onHero2)
                    .frame(minWidth: 44, minHeight: 44)
                    .accessibilityIdentifier("welcome.skip")
            }
            TabView(selection: $page) {
                ForEach(Self.pages.indices, id: \.self) { index in
                    let content = Self.pages[index]
                    VStack(spacing: DincrSpacing.s6) {
                        WelcomeArt(kind: content.art, active: page == index)
                            .frame(height: 220)
                        VStack(spacing: DincrSpacing.s2) {
                            Text(content.title)
                                .font(.title.weight(.bold))
                                .foregroundStyle(OwnerColor.onHero)
                                .accessibilityAddTraits(.isHeader)
                            Text(content.message)
                                .font(DincrFont.body)
                                .foregroundStyle(OwnerColor.onHero2)
                        }
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.horizontal, DincrSpacing.s2)
                    .tag(index)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))
            HStack(spacing: DincrSpacing.s2) {
                ForEach(Self.pages.indices, id: \.self) { index in
                    Capsule().fill(index == page ? OwnerColor.onHero : OwnerColor.heroControl)
                        .frame(width: index == page ? 22 : 8, height: 8)
                }
            }
            .animation(.easeOut(duration: 0.2), value: page)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(tx("Paso \(page + 1) de \(Self.pages.count)", "Step \(page + 1) of \(Self.pages.count)"))
            let last = page == Self.pages.count - 1
            Button {
                if last { finish() } else { withAnimation { page += 1 } }
            } label: {
                Text(last ? tx("Empezar", "Get started") : tx("Continuar", "Continue"))
            }
            .buttonStyle(OwnerHeroButtonStyle(prominent: true))
            .accessibilityIdentifier("welcome.next")
        }
        .padding(DincrSpacing.s4)
        .frame(maxWidth: 600)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OwnerColor.hero.ignoresSafeArea())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("welcome.story")
    }
}

/// A page's drawing: its parts arrive one after another when the page comes on screen. Decorative;
/// with Reduce Motion everything is simply there.
private struct WelcomeArt: View {
    enum Kind { case together, month, steps, safe }

    let kind: Kind
    let active: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dincrDecorativeMotion) private var decorativeMotion

    private var moves: Bool { !reduceMotion && decorativeMotion }
    private var shown: Bool { active || !moves }

    var body: some View {
        Group {
            switch kind {
            case .together: together
            case .month: month
            case .steps: steps
            case .safe: safe
            }
        }
        .frame(maxWidth: .infinity)
        .accessibilityHidden(true)
    }

    private func arrive(_ order: Int) -> Animation? {
        moves ? .spring(duration: 0.55, bounce: 0.3).delay(Double(order) * 0.09) : nil
    }

    private func tile(_ symbol: String, _ order: Int) -> some View {
        Image(systemName: symbol)
            .font(.system(size: 30, weight: .medium))
            .foregroundStyle(OwnerColor.onHero)
            .frame(width: 76, height: 76)
            .background(OwnerColor.heroControl, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .scaleEffect(shown ? 1 : 0.4)
            .opacity(shown ? 1 : 0)
            .animation(arrive(order), value: shown)
    }

    private var together: some View {
        VStack(spacing: DincrSpacing.s3) {
            HStack(spacing: DincrSpacing.s3) { tile("arrow.down", 0); tile("cart", 1) }
            HStack(spacing: DincrSpacing.s3) { tile("creditcard", 2); tile("target", 3) }
        }
    }

    private var month: some View {
        HStack(alignment: .bottom, spacing: DincrSpacing.s3) {
            ForEach(Array([0.45, 0.7, 0.55, 0.95].enumerated()), id: \.offset) { index, height in
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(index == 3 ? OwnerColor.onHero : OwnerColor.heroControl)
                    .frame(width: 44, height: shown ? 190 * height : 8)
                    .animation(arrive(index), value: shown)
            }
        }
        .frame(height: 190, alignment: .bottom)
    }

    private var steps: some View {
        VStack(spacing: DincrSpacing.s3) {
            ForEach(0..<3, id: \.self) { index in
                HStack(spacing: DincrSpacing.s3) {
                    Image(systemName: "checkmark").font(.body.weight(.bold))
                        .foregroundStyle(index == 0 ? OwnerColor.hero : OwnerColor.onHero)
                        .frame(width: 36, height: 36)
                        .background(index == 0 ? OwnerColor.onHero : OwnerColor.heroControl, in: Circle())
                    Capsule().fill(OwnerColor.heroControl).frame(width: 150 - CGFloat(index) * 30, height: 12)
                    Spacer(minLength: 0)
                }
                .frame(width: 220)
                .offset(x: shown ? 0 : 40)
                .opacity(shown ? 1 : 0)
                .animation(arrive(index), value: shown)
            }
        }
    }

    private var safe: some View {
        ZStack {
            Circle().fill(OwnerColor.heroControl.opacity(0.5)).frame(width: 190, height: 190)
                .scaleEffect(shown ? 1 : 0.5).opacity(shown ? 1 : 0).animation(arrive(1), value: shown)
            Circle().fill(OwnerColor.heroControl).frame(width: 130, height: 130)
                .scaleEffect(shown ? 1 : 0.5).opacity(shown ? 1 : 0).animation(arrive(0), value: shown)
            Image(systemName: "lock.shield.fill").font(.system(size: 54)).foregroundStyle(OwnerColor.onHero)
                .scaleEffect(shown ? 1 : 0.4).opacity(shown ? 1 : 0).animation(arrive(2), value: shown)
        }
    }
}

/// The first profile setup, after the story the first time. Per account and device: only its own mark
/// is stored. On fixture data it shows only when a test asks, so other flows go straight to the setup.
struct WelcomeThenProfileSetup: View {
    @Environment(AppModel.self) private var model
    @State private var finished = false

    private var key: String { "dincr.welcomeSeen.\(model.profile?.id ?? 0)" }

    private var showsStory: Bool {
        if finished { return false }
        if model.environment.isFixtures && !ProcessInfo.processInfo.arguments.contains("-DincrWelcomeStory") { return false }
        return !UserDefaults.standard.bool(forKey: key)
    }

    var body: some View {
        if showsStory {
            WelcomeStoryView {
                UserDefaults.standard.set(true, forKey: key)
                finished = true
            }
        } else {
            ProfileSetupView()
        }
    }
}
