import DincrCore
import DincrDesign
import SwiftUI
import UIKit

/// PARITY G1 — the Profile hub.
struct ProfileHubView: View {
    @Environment(AppModel.self) private var model
    @AppStorage("dincr.appearance") private var appearance = Appearance.system.rawValue
    @State private var confirmingSignOut = false
    @State private var confirmingDelete = false
    @State private var deleting = false
    @State private var exporting = false
    @State private var exportFile: ExportFile?
    @State private var error: String?

    var body: some View {
        List {
            Section { header }.dincrRowBackground()
            if Jarvis.isAvailable(to: model.profile) {
                // The Owner's personal space (JARVIS recovery, J0); no plan or other role sees it.
                Section {
                    NavigationLink(value: ProfileRoute.jarvis) {
                        Label {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("JARVIS")
                                Text(tx("Tu espacio personal", "Your personal space")).font(DincrFont.caption).foregroundStyle(DincrColor.text2)
                            }
                        } icon: { Image(systemName: "person.badge.key") }
                    }
                    .accessibilityIdentifier("profile.jarvis")
                }
                .dincrRowBackground()
            }
            // UX-7: the declared situation lives in Plan → Ingresos y base and Tu plan del mes → Ajustes.
            if model.planTier == .vip {
                Section {
                    NavigationLink(value: ProfileRoute.mail) { Label(tx("Monitor de correo", "Email Monitor"), systemImage: "envelope") }
                        .accessibilityIdentifier("profile.mail")
                    // Cuentas: the detected accounts by bank, with their movements (same review as the monitor).
                    NavigationLink { AccountsView() } label: { Label(tx("Cuentas", "Accounts"), systemImage: "building.columns") }
                        .accessibilityIdentifier("profile.accounts")
                }
                .dincrRowBackground()
            }
            if model.planTier.rank >= PlanTier.basic.rank {
                // Basic tools, moved here from the Plan tab (navigation only).
                Section(tx("Finanzas", "Finances")) {
                    NavigationLink { BudgetView() } label: { Label(tx("Presupuesto", "Budget"), systemImage: "chart.pie") }
                        .accessibilityIdentifier("profile.budget")
                    NavigationLink { CalendarView() } label: { Label(tx("Calendario financiero", "Financial calendar"), systemImage: "calendar") }
                        .accessibilityIdentifier("profile.calendar")
                    NavigationLink { RecurringView() } label: { Label(tx("Recurrentes", "Recurring"), systemImage: "repeat") }
                        .accessibilityIdentifier("profile.recurring")
                }
                .dincrRowBackground()
            }
            Section(tx("Cuenta", "Account")) {
                NavigationLink { PlanSettingsView() } label: { Label(tx("Plan", "Plan"), systemImage: "star") }
                    .accessibilityIdentifier("profile.plan")
                NavigationLink { SecurityView() } label: { Label(tx("Seguridad", "Security"), systemImage: "lock") }
                    .accessibilityIdentifier("profile.security")
                Picker(selection: $appearance) {
                    Text(tx("Automático", "Automatic")).tag(Appearance.system.rawValue)
                    Text(tx("Claro", "Light")).tag(Appearance.light.rawValue)
                    Text(tx("Oscuro", "Dark")).tag(Appearance.dark.rawValue)
                } label: { Label(tx("Apariencia", "Appearance"), systemImage: "circle.lefthalf.filled") }
            }
            .dincrRowBackground()
            Section(tx("Ayuda y legal", "Help and legal")) {
                NavigationLink { SupportView() } label: { Label(tx("Soporte", "Support"), systemImage: "questionmark.bubble") }
                Link(destination: LegalLinks.terms) { Label(tx("Términos y condiciones", "Terms and conditions"), systemImage: "doc.text") }
                Link(destination: LegalLinks.privacy) { Label(tx("Política de privacidad", "Privacy policy"), systemImage: "hand.raised") }
            }
            .dincrRowBackground()
            Section {
                Button { Task { await export() } } label: {
                    Label(exporting ? tx("Preparando…", "Preparing…") : tx("Descargar mis datos", "Download my data"), systemImage: "square.and.arrow.down")
                }
                .disabled(exporting)
                Button(tx("Cerrar sesión", "Sign out"), role: .destructive) { confirmingSignOut = true }
                    .accessibilityIdentifier("profile.signOut")
            }
            .dincrRowBackground()
            if model.profile?.canDeleteAccountInApp == true {
                Section {
                    Button(tx("Eliminar mi cuenta", "Delete my account"), role: .destructive) { confirmingDelete = true }.disabled(deleting)
                } footer: {
                    Text(tx("Se programa la eliminación de tus datos en DINCR y se cierra la sesión. No se puede deshacer.", "Your DINCR data is scheduled for deletion and you are signed out. This can’t be undone."))
                }
                .dincrRowBackground()
            }
            if let error { Section { Text(error).foregroundStyle(DincrColor.negative) }.dincrRowBackground() }
        }
        .scrollContentBackground(.hidden)
        .dincrScreenBackground()
        .navigationTitle(tx("Perfil", "Profile"))
        .sheet(item: $exportFile) { file in ShareSheet(items: [file.url]) }
        .confirmationDialog(tx("¿Cerrar sesión en este dispositivo?", "Sign out on this device?"), isPresented: $confirmingSignOut, titleVisibility: .visible) {
            Button(tx("Cerrar sesión", "Sign out"), role: .destructive) { Task { await model.signOut() } }
            Button(tx("Cancelar", "Cancel"), role: .cancel) {}
        }
        .confirmationDialog(tx("¿Eliminar tu cuenta de DINCR?", "Delete your DINCR account?"), isPresented: $confirmingDelete, titleVisibility: .visible) {
            Button(tx("Eliminar cuenta", "Delete account"), role: .destructive) {
                deleting = true; error = nil
                Task { error = await model.deleteAccount(); deleting = false }
            }
            Button(tx("Cancelar", "Cancel"), role: .cancel) {}
        } message: {
            Text(tx("Tus datos se eliminan de DINCR. No se puede deshacer.", "Your data is removed from DINCR. This can’t be undone."))
        }
    }

    private var header: some View {
        HStack(spacing: DincrSpacing.s3) {
            Text(String(model.profile?.firstName?.prefix(1) ?? "D"))
                .font(DincrFont.title2).foregroundStyle(DincrColor.onTintContainer)
                .frame(width: 44, height: 44).background(DincrColor.tintContainer, in: Circle())
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(model.profile?.displayName ?? tx("Tu cuenta", "Your account")).font(DincrFont.title2)
                Text(model.profile?.email ?? "").font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
            Spacer()
            if model.profile?.isOwner == true {
                // The Owner is not a plan: no plan badge, the Owner mark instead.
                Text("Owner")
                    .font(DincrFont.caption.weight(.semibold))
                    .foregroundStyle(OwnerColor.onAccentContainer)
                    .padding(.horizontal, 8).padding(.vertical, 2)
                    .background(OwnerColor.accentContainer, in: Capsule())
                    .accessibilityLabel("DINCR Owner")
            } else {
                PlanBadge(plan: model.profile?.plan ?? "free")
            }
        }
        .accessibilityElement(children: .combine)
    }

    /// G8 — the export goes to a protected temporary file for the share sheet; it is removed at
    /// launch, sign-out and deletion.
    private func export() async {
        exporting = true; error = nil
        defer { exporting = false }
        let epoch = model.currentEpoch
        do {
            let data = try await model.service.exportData()
            guard epoch == model.currentEpoch else { return }
            exportFile = ExportFile(url: try DataExport.write(data))
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos preparar tus datos.", "We couldn’t prepare your data."))
        }
    }
}

private struct ExportFile: Identifiable {
    let id = UUID()
    let url: URL
}

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems: items, applicationActivities: nil) }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}

/// PARITY G3 — current plan and plan change. Paid plans are chosen here only while the launch
/// promotion is active; App Store purchases are not in this build (store identity gate).
struct PlanSettingsView: View {
    @Environment(AppModel.self) private var model
    @State private var busy: String?
    @State private var error: String?

    var body: some View {
        ScreenScroll(title: tx("Plan", "Plan")) {
            if let subscription = model.profile?.subscription {
                VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                    InfoRow(label: tx("Plan actual", "Current plan"), value: PlanLabel.name(subscription.plan))
                    if model.profile?.isCourtesy == true { InfoRow(label: tx("Acceso", "Access"), value: tx("Cortesía", "Courtesy")) }
                    if let expires = subscription.expiresAt { InfoRow(label: tx("Vence", "Expires"), value: Day.label(expires)) }
                    if let pending = subscription.pendingPlan {
                        InfoRow(label: tx("Cambio programado", "Scheduled change"), value: "\(PlanLabel.name(pending)) · \(Day.label(subscription.pendingEffectiveAt))")
                    }
                    if let notice = subscription.accessNotice, let message = notice.message {
                        Text(message).font(DincrFont.caption).foregroundStyle(DincrColor.text2)
                    }
                }
                .dincrCard()
            }
            if let error { ErrorStateView(message: error) }
            AsyncContent(load: { () async throws -> PlanChooserView.Offer in
                let options = try await model.service.plans()
                let catalog = try? await model.service.billingCatalog()
                return PlanChooserView.Offer(options: options, catalog: catalog)
            }) { offer, _ in
                ForEach(offer.options) { option in
                    PlanCardView(option: option, catalog: offer.catalog,
                                 canChoose: option.code != model.profile?.plan && PlanOffer.canChoose(option, promotionActive: offer.promotionActive),
                                 busy: busy == option.code, enabled: busy == nil) {
                        busy = option.code; error = nil
                        Task { error = await model.choosePlan(option.code); busy = nil }
                    }
                }
            }
            Text(tx("Las suscripciones desde el App Store llegan en una próxima versión.", "App Store subscriptions arrive in a coming version."))
                .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
        }
    }
}

/// PARITY A12/A13/G6 — local app lock.
struct SecurityView: View {
    @Environment(AppModel.self) private var model
    @State private var message: String?
    @State private var working = false

    var body: some View {
        let lock = model.appLock
        List {
            Section {
                switch lock.availability {
                case .unavailable:
                    Text(tx("Configurá un código en tu iPhone para poder bloquear DINCR.", "Set up a passcode on your iPhone to lock DINCR.")).foregroundStyle(DincrColor.text2)
                case .biometrics(let name):
                    toggle(tx("Bloquear con \(name)", "Lock with \(name)"))
                case .passcodeOnly:
                    toggle(tx("Bloquear con el código del iPhone", "Lock with the iPhone passcode"))
                }
            } footer: {
                Text(tx("DINCR se bloquea al abrirla y después de 5 minutos fuera de la app.", "DINCR locks when it opens and after 5 minutes away from the app."))
            }
            if lock.isEnabled {
                Section { Button(tx("Bloquear ahora", "Lock now")) { lock.lockNow() } }
            }
            if let message, !message.isEmpty { Section { Text(message).foregroundStyle(DincrColor.negative) } }
        }
        .scrollContentBackground(.hidden)
        .dincrScreenBackground()
        .navigationTitle(tx("Seguridad", "Security"))
    }

    private func toggle(_ title: String) -> some View {
        Toggle(title, isOn: Binding(get: { model.appLock.isEnabled }, set: { value in
            working = true
            Task { message = await model.appLock.setEnabled(value); working = false }
        }))
        .disabled(working)
        .accessibilityIdentifier("security.lock")
    }
}

/// PARITY I2/I3 — support tickets: create (type, subject, details) and mark resolved.
struct SupportView: View {
    @Environment(AppModel.self) private var model
    @State private var generation = 0
    @State private var category = "error"
    @State private var subject = ""
    @State private var message = ""
    @State private var error: String?
    @State private var sent: String?
    @State private var sending = false

    var body: some View {
        ScreenScroll(title: tx("Soporte", "Support")) {
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                Picker(tx("Tipo", "Type"), selection: $category) {
                    Text(tx("Un problema", "A problem")).tag("error")
                    Text(tx("Una idea", "An idea")).tag("improvement")
                    Text(tx("Pagos", "Payments")).tag("payment")
                    Text(tx("Mi cuenta", "My account")).tag("account")
                }
                .pickerStyle(.segmented)
                TextField(tx("Asunto", "Subject"), text: $subject).textFieldStyle(.roundedBorder)
                TextField(tx("Detalle", "Details"), text: $message, axis: .vertical).lineLimit(4...8).textFieldStyle(.roundedBorder)
                Text(tx("No incluyas contraseñas, códigos ni números completos de tarjeta.", "Don’t include passwords, codes or full card numbers."))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
                if let sent { Label(sent, systemImage: "checkmark.circle").foregroundStyle(DincrColor.positive) }
                Button(tx("Enviar", "Send")) { Task { await send() } }.buttonStyle(.dincrPrimary(loading: sending)).disabled(sending)
            }
            .dincrCard()
            SectionHeader(title: tx("Mis reportes", "My reports"))
            AsyncContent(load: { try await model.service.supportTickets() }) { tickets, _ in
                TicketList(tickets: tickets) { ticket, resolved in Task { await resolve(ticket, resolved) } }
            }
            .id(generation)
        }
    }

    private func send() async {
        let subjectText = subject.trimmingCharacters(in: .whitespacesAndNewlines)
        let body = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard subjectText.count >= 3, body.count >= 10 else {
            error = tx("Escribí un asunto y al menos una frase de detalle.", "Write a subject and at least one sentence of detail."); return
        }
        sending = true; error = nil; sent = nil
        defer { sending = false }
        let epoch = model.currentEpoch
        do {
            let created = try await model.service.createSupportTicket(SupportRequest(category: category, subject: subjectText, message: body, appVersion: model.appVersion))
            sent = tx("Recibido. Tu referencia es \(created.publicId ?? "—").", "Received. Your reference is \(created.publicId ?? "—").")
            subject = ""; message = ""
            generation += 1
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos enviarlo.", "We couldn’t send it."))
        }
    }

    private func resolve(_ ticket: SupportTicket, _ resolved: Bool) async {
        let epoch = model.currentEpoch
        do {
            try await model.service.resolveTicket(id: ticket.id, resolved: resolved)
            generation += 1
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardarlo.", "We couldn’t save it."))
        }
    }
}

private struct TicketList: View {
    let tickets: [SupportTicket]
    let resolve: (SupportTicket, Bool) -> Void

    var body: some View {
        if tickets.isEmpty {
            Text(tx("Todavía no enviaste reportes.", "You haven’t sent any reports yet.")).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
        }
        ForEach(tickets) { ticket in
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                Text(ticket.subject ?? "").font(DincrFont.body.weight(.semibold))
                Text([ticket.publicId, Day.label(ticket.createdAt), ticket.status].compactMap { $0 }.joined(separator: " · "))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                if ticket.status == "resolved" && ticket.userResolution == nil {
                    HStack {
                        Button(tx("Se resolvió", "It’s solved")) { resolve(ticket, true) }.buttonStyle(.dincrSecondary)
                        Button(tx("Sigue pasando", "Still happening")) { resolve(ticket, false) }.frame(minHeight: 44)
                    }
                }
            }
            .dincrCard()
        }
    }
}
