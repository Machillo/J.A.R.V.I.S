import DincrCore
import DincrDesign
import SwiftUI

/// JARVIS chat (recovery roadmap J1): the Owner talks to JARVIS in plain words and gets the engine's
/// answer (`POST /jarvis/chat`). A change JARVIS understood is shown first and saved only on
/// Confirmar (the backend waits for "sí"). The conversation lives for the session only, like the
/// web Owner app's. Android: `JarvisChatScreen` (`JarvisScreens.kt`).
struct JarvisChatView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var draft = ""
    @FocusState private var composing: Bool

    private var chat: JarvisChatSession { model.jarvisChat }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: DincrSpacing.s3) {
                    if chat.messages.isEmpty { intro }
                    ForEach(chat.messages) { message in
                        MessageRow(message: message, canRetry: chat.canRetry(message)) {
                            Task { await chat.retry(message.id) }
                        }
                        .id(message.id)
                    }
                    if chat.isSending { thinking }
                    if chat.awaitingConfirmation { confirmation }
                    if chat.awaitingClarification { clarification }
                    Color.clear.frame(height: 1).id(Self.bottom)
                }
                .padding(.horizontal, DincrSpacing.s4)
                .padding(.vertical, DincrSpacing.s4)
                .frame(maxWidth: 640)
                .frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: chat.messages.count) { scroll(proxy) }
            .onChange(of: chat.isSending) { scroll(proxy) }
            .onChange(of: chat.awaitingClarification) { scroll(proxy) }
            .onAppear { proxy.scrollTo(Self.bottom, anchor: .bottom) }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) { composer }
        .dincrScreenBackground()
        .navigationTitle(tx("Chat", "Chat"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private static let bottom = "jarvis.chat.bottom"

    private func scroll(_ proxy: ScrollViewProxy) {
        withAnimation(DincrMotion.standard(reduceMotion)) { proxy.scrollTo(Self.bottom, anchor: .bottom) }
    }

    /// The empty chat says exactly what JARVIS does (payroll records and the agenda) and offers only
    /// that. A quick action puts a starting phrase in the composer; nothing is sent until the Owner
    /// sends it, and every change still waits for Confirmar.
    private var intro: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s4) {
            HStack(spacing: DincrSpacing.s3) {
                JarvisMark(size: 48)
                VStack(alignment: .leading, spacing: 2) {
                    Text(tx("¿Qué registramos?", "What shall we record?")).font(DincrFont.title2).foregroundStyle(OwnerColor.text)
                    Text(tx("Horas extra, VGH, feriados, bonos o tu agenda.", "Overtime, VGH, holidays, bonuses or your calendar."))
                        .font(DincrFont.bodySmall).foregroundStyle(OwnerColor.text2)
                }
            }
            .accessibilityElement(children: .combine)
            Text(tx("Escribilo como siempre: “Hoy hice 3 horas extra”, “Agendá dentista el 10 de octubre a las 3pm”. Antes de guardar, JARVIS te muestra qué va a registrar.",
                    "Write it as usual: “Hoy hice 3 horas extra”, “Agendá dentista el 10 de octubre a las 3pm”. Before saving, JARVIS shows you what it will record."))
                .font(DincrFont.bodySmall).foregroundStyle(OwnerColor.text2)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: DincrSpacing.s2)], alignment: .leading, spacing: DincrSpacing.s2) {
                ForEach(JarvisQuickAction.allCases) { action in quickAction(action) }
            }
        }
        .padding(.top, DincrSpacing.s2)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("jarvis.chat.empty")
    }

    @ViewBuilder
    private func quickAction(_ action: JarvisQuickAction) -> some View {
        let label = Label(action.title, systemImage: action.symbol)
        if action.opensAgenda {
            NavigationLink(value: ProfileRoute.jarvisSection(.calendar)) { label }
                .buttonStyle(.ownerQuickAction)
                .accessibilityIdentifier("jarvis.chat.quick.\(action.rawValue)")
        } else {
            Button {
                draft = action.composerText ?? ""
                composing = true
            } label: { label }
                .buttonStyle(.ownerQuickAction)
                .accessibilityHint(tx("Escribe el inicio del mensaje; vos lo completás y lo enviás.", "Writes the start of the message; you complete and send it."))
                .accessibilityIdentifier("jarvis.chat.quick.\(action.rawValue)")
        }
    }

    private var thinking: some View {
        HStack(spacing: DincrSpacing.s2) {
            ProgressView().tint(OwnerColor.accent)
            Text(tx("JARVIS está pensando…", "JARVIS is thinking…")).font(DincrFont.bodySmall).foregroundStyle(OwnerColor.text2)
        }
        .padding(.vertical, DincrSpacing.s2)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("jarvis.chat.sending")
    }

    /// Native, compact choice under JARVIS's summary: the change is saved only on Confirmar.
    private var confirmation: some View {
        decision(prompt: tx("¿Guardar este cambio?", "Save this change?")) {
            Button(tx("Cancelar", "Cancel")) { Task { await chat.cancel() } }
                .buttonStyle(.bordered)
                .accessibilityIdentifier("jarvis.chat.cancel")
            Button(tx("Confirmar", "Confirm")) { Task { await chat.confirm() } }
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier("jarvis.chat.confirm")
        }
    }

    /// The backend could not tell whether the last message answers its question or is another request.
    private var clarification: some View {
        decision(prompt: tx("¿Es la respuesta o es otra consulta?", "Is it the answer or another question?")) {
            Button(tx("Es otra consulta", "It’s another question")) { Task { await chat.anotherRequest() } }
                .buttonStyle(.bordered)
                .accessibilityIdentifier("jarvis.chat.clarify.other")
            Button(tx("Es la respuesta", "It’s the answer")) { Task { await chat.itIsTheAnswer() } }
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier("jarvis.chat.clarify.answer")
        }
    }

    private func decision<Buttons: View>(prompt: String, @ViewBuilder buttons: () -> Buttons) -> some View {
        let choices = buttons()
        return VStack(alignment: .trailing, spacing: DincrSpacing.s2) {
            Text(prompt).font(DincrFont.caption).foregroundStyle(OwnerColor.textMuted)
            // Side by side when they fit; stacked at large text sizes.
            ViewThatFits(in: .horizontal) {
                HStack(spacing: DincrSpacing.s2) { choices }
                VStack(alignment: .trailing, spacing: DincrSpacing.s2) { choices }
            }
            .controlSize(.large)
            .tint(OwnerColor.accent)
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(prompt)
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: DincrSpacing.s2) {
            TextField(tx("Escribile a JARVIS", "Message JARVIS"), text: $draft, axis: .vertical)
                .lineLimit(1...5)
                .font(DincrFont.body)
                .padding(.horizontal, DincrSpacing.s3).padding(.vertical, DincrSpacing.s2)
                .background(OwnerColor.surface, in: RoundedRectangle(cornerRadius: OwnerRadius.control, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: OwnerRadius.control, style: .continuous).stroke(DincrColor.fieldBorder))
                .focused($composing)
                .submitLabel(.send)
                .onSubmit(sendDraft)
                .accessibilityIdentifier("jarvis.chat.input")
            Button(action: sendDraft) {
                // A text style, so the send button grows with Dynamic Type.
                Image(systemName: "arrow.up.circle.fill").font(.largeTitle).foregroundStyle(canSend ? OwnerColor.accent : OwnerColor.textMuted)
            }
            .disabled(!canSend)
            .frame(minWidth: 44, minHeight: 44)
            .accessibilityLabel(tx("Enviar", "Send"))
            .accessibilityIdentifier("jarvis.chat.send")
        }
        .padding(.horizontal, DincrSpacing.s4).padding(.vertical, DincrSpacing.s2)
        .frame(maxWidth: 640)
        .frame(maxWidth: .infinity)
        // The system bar material: the conversation reads through it, like any iOS composer.
        .background(.bar)
    }

    private var canSend: Bool { !chat.isSending && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    private func sendDraft() {
        guard canSend else { return }
        let text = draft
        draft = ""
        Task { await chat.submit(text) }
    }
}

extension JarvisQuickAction {
    var title: String {
        switch self {
        case .overtime: tx("Registrar horas extra", "Record overtime")
        case .bonus: tx("Registrar bono", "Record a bonus")
        case .schedule: tx("Agendar algo", "Schedule something")
        case .agenda: tx("Ver mi agenda", "See my calendar")
        }
    }

    var symbol: String {
        switch self {
        case .overtime: "clock"
        case .bonus: "gift"
        case .schedule: "calendar.badge.plus"
        case .agenda: "calendar"
        }
    }
}

/// One message: the Owner's on the right in the Owner accent, JARVIS's on the left on a surface.
private struct MessageRow: View {
    let message: JarvisChatSession.Message
    let canRetry: Bool
    let retry: () -> Void

    private var fromOwner: Bool { message.author == .owner }

    var body: some View {
        VStack(alignment: fromOwner ? .trailing : .leading, spacing: DincrSpacing.s1) {
            Text(message.text)
                .font(DincrFont.body)
                .foregroundStyle(fromOwner ? OwnerColor.onAccent : OwnerColor.text)
                .textSelection(.enabled)
                .padding(.horizontal, DincrSpacing.s3).padding(.vertical, DincrSpacing.s2)
                .background(fromOwner ? OwnerColor.accent : OwnerColor.surface,
                            in: RoundedRectangle(cornerRadius: OwnerRadius.control, style: .continuous))
                .overlay {
                    if !fromOwner {
                        RoundedRectangle(cornerRadius: OwnerRadius.control, style: .continuous).strokeBorder(OwnerColor.border, lineWidth: 1)
                    }
                }
                .opacity(message.delivery == .sending ? 0.7 : 1)
                .accessibilityLabel(fromOwner ? tx("Vos: \(message.text)", "You: \(message.text)") : "JARVIS: \(message.text)")
                .accessibilityIdentifier(fromOwner ? "jarvis.chat.owner" : "jarvis.chat.reply")
            if case .failed(let reason) = message.delivery {
                HStack(spacing: DincrSpacing.s2) {
                    Image(systemName: "exclamationmark.circle").foregroundStyle(DincrColor.negative).accessibilityHidden(true)
                    Text(reason).font(DincrFont.caption).foregroundStyle(DincrColor.negative)
                    if canRetry {
                        Button(tx("Reintentar", "Retry"), action: retry)
                            .font(DincrFont.caption.weight(.semibold))
                            .foregroundStyle(OwnerColor.accent)
                            .frame(minHeight: 44)
                            .accessibilityIdentifier("jarvis.chat.retry")
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("jarvis.chat.failed")
            }
        }
        .frame(maxWidth: .infinity, alignment: fromOwner ? .trailing : .leading)
        .padding(fromOwner ? .leading : .trailing, DincrSpacing.s8)
    }
}
