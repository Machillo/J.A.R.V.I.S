import DincrCore
import DincrDesign
import SwiftUI

/// Perfil → Atajos de iPhone (VIP and the Owner; Free and Basic see the row locked, `ProfileHubView`).
/// Activating issues a limited token kept only in this iPhone's Keychain; two Shortcuts automations
/// (Transacción and Mensaje) then send purchases and bank notices to Movimientos → Por revisar.
/// iOS only (Android has no Shortcuts).
struct ShortcutsSettingsView: View {
    @Environment(AppModel.self) private var model
    @State private var state: ShortcutLinkState?
    @State private var working = false
    @State private var error: String?

    var body: some View {
        List {
            Section {
                HStack {
                    Label(tx("Estado", "Status"), systemImage: "bolt.horizontal")
                    Spacer()
                    if let state {
                        Text(statusText(state))
                            .foregroundStyle(state == .linked ? DincrColor.positive : DincrColor.textMuted)
                            .accessibilityIdentifier("shortcuts.status")
                    } else {
                        ProgressView()
                    }
                }
                if let state {
                    if state == .linked {
                        Button(tx("Desactivar en este iPhone", "Turn off on this iPhone"), role: .destructive) { Task { await deactivate() } }
                            .disabled(working)
                            .accessibilityIdentifier("shortcuts.deactivate")
                    } else {
                        Button(state == .linkedElsewhere ? tx("Activar en este iPhone", "Turn on for this iPhone") : tx("Activar Atajos de iPhone", "Turn on iPhone Shortcuts")) {
                            Task { await activate() }
                        }
                        .disabled(working)
                        .accessibilityIdentifier("shortcuts.activate")
                    }
                }
            } footer: {
                Text(footer)
            }
            .dincrRowBackground()

            if let error {
                Section { Text(error).foregroundStyle(DincrColor.negative).accessibilityIdentifier("shortcuts.error") }.dincrRowBackground()
            }

            Section {
                steps([
                    tx("Abrí la app Atajos → Automatización → Nueva automatización → Transacción.", "Open the Shortcuts app → Automation → New Automation → Transaction."),
                    tx("Elegí tus tarjetas de Wallet y marcá «Ejecutar inmediatamente».", "Pick your Wallet cards and choose “Run Immediately”."),
                    tx("Agregá la acción «Registrar compra en DINCR».", "Add the “Registrar compra en DINCR” action."),
                    tx("Usá Monto para Monto, Comercio para Comercio y, si querés, Tarjeta para Tarjeta. Elegí la Moneda de la tarjeta (si el monto trae ₡ o $, DINCR la toma de ahí).",
                       "Use Amount for Monto, Merchant for Comercio and, optionally, Card for Tarjeta. Pick the card’s Moneda (if the amount shows ₡ or $, DINCR uses that)."),
                ])
            } header: {
                Text(tx("Compras con Apple Pay", "Apple Pay purchases"))
            }
            .dincrRowBackground()

            Section {
                steps([
                    tx("En Atajos → Automatización → Nueva automatización → Mensaje.", "In Shortcuts → Automation → New Automation → Message."),
                    tx("En Remitente elegí el número de tu banco (una automatización por banco). Opcional: «El mensaje contiene» una palabra como «compra».",
                       "In Sender pick your bank’s number (one automation per bank). Optional: “Message Contains” a word such as “compra”."),
                    tx("Marcá «Ejecutar inmediatamente».", "Choose “Run Immediately”."),
                    tx("Agregá «Enviar aviso bancario a DINCR» y usá Mensaje como Texto del mensaje.", "Add “Enviar aviso bancario a DINCR” and use Message as Texto del mensaje."),
                ])
            } header: {
                Text(tx("Avisos SMS del banco", "Bank SMS notices"))
            } footer: {
                Text(tx("Si DINCR todavía no reconoce el formato de un banco, el atajo te lo dice y no se registra nada.",
                        "If DINCR doesn’t recognize a bank’s format yet, the shortcut tells you and nothing is recorded."))
            }
            .dincrRowBackground()
        }
        .scrollContentBackground(.hidden)
        .dincrScreenBackground()
        .navigationTitle(tx("Atajos de iPhone", "iPhone Shortcuts"))
        .task { await load() }
    }

    private var footer: String {
        tx("DINCR guarda una llave limitada solo en este iPhone. Sirve únicamente para enviar compras y avisos a Movimientos → Por revisar: no puede leer tus datos, y nada se registra hasta que lo revisés.",
           "DINCR keeps a limited key on this iPhone only. It can only send purchases and notices to Movements → To review: it can’t read your data, and nothing is recorded until you review it.")
    }

    private func statusText(_ state: ShortcutLinkState) -> String {
        switch state {
        case .linked: tx("Vinculado", "Linked")
        case .notLinked: tx("No vinculado", "Not linked")
        case .linkedElsewhere: tx("Vinculado en otro dispositivo", "Linked on another device")
        }
    }

    private func steps(_ items: [String]) -> some View {
        ForEach(Array(items.enumerated()), id: \.offset) { index, item in
            HStack(alignment: .firstTextBaseline, spacing: DincrSpacing.s3) {
                Text("\(index + 1).").font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(DincrColor.textMuted)
                Text(item).font(DincrFont.bodySmall)
            }
            .accessibilityElement(children: .combine)
        }
    }

    private var accountID: Int? { model.profile?.id }

    private func load() async {
        guard let accountID else { return }
        let linking = model.shortcutLinking
        // What this iPhone knows first; the backend's answer then corrects it.
        if state == nil { state = linking.localState(accountID: accountID) }
        let epoch = model.currentEpoch
        do {
            let loaded = try await linking.status(accountID: accountID)
            if epoch == model.currentEpoch { state = loaded; error = nil }
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos leer el estado de Atajos de iPhone.", "We couldn’t read the iPhone Shortcuts status."))
        }
    }

    private func activate() async {
        guard let accountID else { return }
        working = true; error = nil
        defer { working = false }
        let epoch = model.currentEpoch
        do {
            let linked = try await model.shortcutLinking.activate(accountID: accountID)
            if epoch == model.currentEpoch { state = linked }
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos activar Atajos de iPhone.", "We couldn’t turn on iPhone Shortcuts."))
        }
    }

    private func deactivate() async {
        working = true; error = nil
        defer { working = false }
        let epoch = model.currentEpoch
        do {
            let unlinked = try await model.shortcutLinking.deactivate()
            if epoch == model.currentEpoch { state = unlinked }
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos desactivar Atajos de iPhone.", "We couldn’t turn off iPhone Shortcuts."))
        }
    }
}
