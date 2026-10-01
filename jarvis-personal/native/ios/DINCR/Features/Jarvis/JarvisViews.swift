import DincrCore
import DincrDesign
import SwiftUI

/// JARVIS: the Owner's personal space inside DINCR, opened from the Profile hub. Only the server's
/// role opens it (`Jarvis.isAvailable`), and the backend still decides every JARVIS request. The
/// chat is ported (J1); a section not ported yet says so instead of showing sample content
/// (Android: `JarvisScreens.kt`).
struct JarvisHubView: View {
    var body: some View {
        OwnerOnly {
            ScreenScroll(title: "JARVIS") {
                Text(tx("Tus funciones personales vuelven a DINCR por etapas.",
                        "Your personal features are coming back to DINCR step by step."))
                    .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                VStack(spacing: DincrSpacing.s2) {
                    ForEach(Jarvis.Section.allCases) { section in
                        NavigationLink(value: ProfileRoute.jarvisSection(section)) {
                            HubRow(symbol: section.symbol, title: section.title, subtitle: section.isAvailable ? section.summary : tx("En restauración", "Being restored"))
                        }
                        .buttonStyle(.plain)
                        .dincrCard(padding: DincrSpacing.s3)
                        .accessibilityIdentifier("jarvis.section.\(section.rawValue)")
                    }
                }
            }
        }
    }
}

/// A JARVIS section: a ported one (chat, agenda, analysis), or a "being restored" screen that never shows sample data.
struct JarvisSectionView: View {
    let section: Jarvis.Section

    var body: some View {
        OwnerOnly {
            switch section {
            case .chat: JarvisChatView()
            case .calendar: JarvisAgendaView()
            case .analysis: OwnerAnalysisView()
            default: restoring
            }
        }
    }

    private var restoring: some View {
        ScreenScroll(title: section.title) {
            EmptyStateView(
                symbol: section.symbol,
                title: tx("En restauración", "Being restored"),
                message: tx("\(section.summary). Esta función todavía no está disponible en la app.",
                            "\(section.summary). This feature isn’t available in the app yet.")
            ) { EmptyView() }
            .accessibilityIdentifier("jarvis.restoring")
        }
    }
}

/// Renders JARVIS only for the Owner. The routes are reachable only from the Owner's Profile hub;
/// this also closes a screen left on the stack if the identity stops being the Owner.
private struct OwnerOnly<Content: View>: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @ViewBuilder let content: () -> Content

    var body: some View {
        if Jarvis.isAvailable(to: model.profile) {
            content()
        } else {
            Color.clear.onAppear { dismiss() }
        }
    }
}

extension Jarvis.Section {
    var title: String {
        switch self {
        case .chat: tx("Chat", "Chat")
        case .memory: tx("Memoria", "Memory")
        case .calendar: tx("Agenda", "Calendar")
        case .strategy: tx("Estrategia personal", "Personal strategy")
        case .money: tx("Mi dinero", "My money")
        case .moneyControl: tx("Control de dinero", "Money control")
        case .wealth: tx("Patrimonio", "Wealth")
        case .records: tx("Registros", "Records")
        case .analysis: tx("Análisis financiero", "Financial analysis")
        }
    }

    var summary: String {
        switch self {
        case .chat: tx("Conversar con JARVIS y registrar con tu confirmación", "Talk to JARVIS and record with your confirmation")
        case .memory: tx("Lo que JARVIS recuerda de vos", "What JARVIS remembers about you")
        case .calendar: tx("Tus eventos y recordatorios", "Your events and reminders")
        case .strategy: tx("Tu estrategia con tus ingresos reales", "Your strategy with your real income")
        case .money: tx("Tu ciclo, tus cuentas y los pagos de tus deudas", "Your cycle, your accounts and your debt payments")
        case .moneyControl: tx("Cobros pendientes y tarjetas adicionales", "Money owed to you and additional cards")
        case .wealth: tx("Patrimonio, inversiones y negocios", "Net worth, investments and businesses")
        case .records: tx("Importar, conciliar y tu línea de tiempo", "Import, reconcile and your timeline")
        case .analysis: tx("Gasto por categoría, flujo mensual, patrimonio y salud financiera", "Spending by category, monthly flow, net worth and financial health")
        }
    }

    var symbol: String {
        switch self {
        case .chat: "bubble.left.and.text.bubble.right"
        case .memory: "brain"
        case .calendar: "calendar"
        case .strategy: "map"
        case .money: "banknote"
        case .moneyControl: "arrow.left.arrow.right.circle"
        case .wealth: "chart.pie"
        case .records: "tray.and.arrow.down"
        case .analysis: "chart.bar.xaxis"
        }
    }
}
