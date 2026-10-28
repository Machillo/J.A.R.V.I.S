import DincrCore
import DincrDesign
import SwiftUI

/// JARVIS → Control de dinero → "Tarjetas adicionales" (Owner only): the cards billed to the Owner
/// but carried by someone else. A purchase on one of them is that person's debt (it shows up under
/// them above), never the Owner's expense. Opening it only reads; adding or removing a card is an
/// explicit Owner command, sent once. Android: `AdditionalCardsSection` in `MoneyControlScreen.kt`.
struct AdditionalCardsSection: View {
    @Environment(AppModel.self) private var model
    let reloadToken: Int
    let onDone: (String) -> Void
    @State private var adding = false
    @State private var removing: AdditionalCard?
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            HStack {
                Text(tx("Tarjetas adicionales", "Additional cards")).font(DincrFont.body.weight(.semibold))
                Spacer()
                Button(tx("Agregar", "Add")) { adding = true }
                    .font(DincrFont.label).foregroundStyle(DincrColor.tint)
                    .accessibilityIdentifier("money.cards.add")
            }
            Text(tx("Lo que se compre con estas tarjetas se le cobra a esa persona y no cuenta como gasto tuyo.",
                    "Purchases with these cards are charged to that person and don’t count as your spending."))
                .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            AsyncContent(fallback: tx("No pudimos cargar tus tarjetas adicionales.", "We couldn’t load your additional cards."),
                         load: { try await model.service.additionalCards() }) { list, _ in
                if list.items.isEmpty {
                    Text(tx("Todavía no marcaste ninguna.", "You haven’t marked any yet."))
                        .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                        .accessibilityIdentifier("money.cards.empty")
                }
                ForEach(list.items) { card in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("•••• \(card.cardLast4)").font(DincrFont.bodySmall)
                            Text(card.personName ?? tx("Persona", "Person")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                        }
                        .accessibilityElement(children: .combine)
                        Spacer()
                        Button(tx("Quitar", "Remove")) { removing = card }
                            .font(DincrFont.label).foregroundStyle(DincrColor.negative)
                            .accessibilityIdentifier("money.cards.remove.\(card.cardLast4)")
                    }
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("money.cards.card.\(card.cardLast4)")
                }
            }
            .id(reloadToken)
            if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("money.cards")
        .sheet(isPresented: $adding) { AdditionalCardSheet { onDone($0) } }
        .confirmationDialog(tx("¿Quitar esta tarjeta adicional?", "Remove this additional card?"),
                            isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }),
                            titleVisibility: .visible, presenting: removing) { card in
            Button(tx("Quitar", "Remove"), role: .destructive) { Task { await stop(card) } }
                .accessibilityIdentifier("money.cards.remove.confirm")
        } message: { _ in
            Text(tx("Sus compras vuelven a «Por revisar» para que decidás. No se borra nada.",
                    "Its purchases go back to “To review” for you to decide. Nothing is deleted."))
        }
    }

    private func stop(_ card: AdditionalCard) async {
        error = nil
        let epoch = model.currentEpoch
        do {
            try await model.service.stopAdditionalCard(last4: card.cardLast4)
            onDone(tx("Tarjeta •••• \(card.cardLast4) ya no es adicional", "Card •••• \(card.cardLast4) is no longer additional"))
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos quitarla.", "We couldn’t remove it."))
        }
    }
}

/// "Agregar tarjeta adicional": the card's last 4 digits and who carries it. Sent once.
private struct AdditionalCardSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let onDone: (String) -> Void
    @State private var last4 = ""
    @State private var person = ""
    @State private var error: String?
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(tx("Últimos 4 dígitos", "Last 4 digits"), text: $last4)
                        .keyboardType(.numberPad).accessibilityIdentifier("money.cards.last4")
                    TextField(tx("Quién la usa", "Who uses it"), text: $person).accessibilityIdentifier("money.cards.person")
                    if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
                } footer: {
                    Text(tx("Las compras pendientes de esta tarjeta pasan a lo que esa persona te debe.",
                            "This card’s pending purchases become what that person owes you."))
                }
            }
            .navigationTitle(tx("Tarjeta adicional", "Additional card"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Guardar", "Save")) { Task { await submit() } }.disabled(saving).accessibilityIdentifier("money.cards.save")
                }
            }
        }
        .presentationDetents([.medium])
        .interactiveDismissDisabled(saving)
    }

    private func submit() async {
        guard !saving else { return }
        guard let digits = AdditionalCardRequest.last4(last4) else {
            error = tx("Escribí los últimos 4 dígitos de la tarjeta.", "Enter the card’s last 4 digits."); return
        }
        let name = person.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { error = tx("Escribí quién usa la tarjeta.", "Enter who uses the card."); return }
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            let result = try await model.service.saveAdditionalCard(last4: digits, personName: name)
            let settled = result.settledPurchases ?? 0
            onDone(settled > 0 ? tx("Tarjeta guardada · \(settled) compra(s) pasaron a \(name)", "Card saved · \(settled) purchase(s) moved to \(name)")
                               : tx("Tarjeta guardada", "Card saved"))
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardarla. Revisá la lista antes de intentar de nuevo.", "We couldn’t save it. Check the list before trying again."))
        }
    }
}
