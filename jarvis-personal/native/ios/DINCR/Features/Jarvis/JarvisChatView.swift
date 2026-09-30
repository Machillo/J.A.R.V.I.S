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

    private var intro: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(tx("Hablale a JARVIS como siempre", "Talk to JARVIS as usual")).font(DincrFont.title2).foregroundStyle(DincrColor.text)
            Text(tx("Preguntá por tus deudas, tu estrategia o tu agenda, o contale lo que pasó: “Hoy hice 3 horas extra”. Antes de guardar algo, JARVIS te muestra qué va a registrar.",
                    "Ask about your debts, your strategy or your calendar, or tell it what happened: “Today I did 3 hours of overtime”. Before saving anything, JARVIS shows you what it will record."))
                .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
        }
        .dincrCard()
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("jarvis.chat.empty")
    }

    private var thinking: some View {
        HStack(spacing: DincrSpacing.s2) {
            ProgressView().tint(DincrColor.tint)
            Text(tx("JARVIS está pensando…", "JARVIS is thinking…")).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
        }
        .padding(.vertical, DincrSpacing.s2)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("jarvis.chat.sending")
    }

    private var confirmation: some View {
        HStack(spacing: DincrSpacing.s3) {
            Button(tx("Cancelar", "Cancel")) { Task { await chat.cancel() } }
                .buttonStyle(.dincrSecondary)
                .accessibilityIdentifier("jarvis.chat.cancel")
            Button(tx("Confirmar", "Confirm")) { Task { await chat.confirm() } }
                .buttonStyle(.dincrPrimary)
                .accessibilityIdentifier("jarvis.chat.confirm")
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(tx("¿Guardar este cambio?", "Save this change?"))
    }

    /// The backend could not tell whether the last message answers its question or is another request.
    private var clarification: some View {
        HStack(spacing: DincrSpacing.s3) {
            Button(tx("Es otra consulta", "It’s another question")) { Task { await chat.anotherRequest() } }
                .buttonStyle(.dincrSecondary)
                .accessibilityIdentifier("jarvis.chat.clarify.other")
            Button(tx("Es la respuesta", "It’s the answer")) { Task { await chat.itIsTheAnswer() } }
                .buttonStyle(.dincrPrimary)
                .accessibilityIdentifier("jarvis.chat.clarify.answer")
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(tx("¿Es la respuesta o es otra consulta?", "Is it the answer or another question?"))
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: DincrSpacing.s2) {
            TextField(tx("Escribile a JARVIS", "Message JARVIS"), text: $draft, axis: .vertical)
                .lineLimit(1...5)
                .font(DincrFont.body)
                .padding(.horizontal, DincrSpacing.s3).padding(.vertical, DincrSpacing.s2)
                .background(DincrColor.surface, in: RoundedRectangle(cornerRadius: DincrRadius.lg, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: DincrRadius.lg, style: .continuous).stroke(DincrColor.fieldBorder))
                .focused($composing)
                .submitLabel(.send)
                .onSubmit(sendDraft)
                .accessibilityIdentifier("jarvis.chat.input")
            Button(action: sendDraft) {
                Image(systemName: "arrow.up.circle.fill").font(.system(size: 34)).foregroundStyle(canSend ? DincrColor.tint : DincrColor.textMuted)
            }
            .disabled(!canSend)
            .frame(minWidth: 44, minHeight: 44)
            .accessibilityLabel(tx("Enviar", "Send"))
            .accessibilityIdentifier("jarvis.chat.send")
        }
        .padding(.horizontal, DincrSpacing.s4).padding(.vertical, DincrSpacing.s2)
        .frame(maxWidth: 640)
        .frame(maxWidth: .infinity)
        .background(DincrColor.bg)
    }

    private var canSend: Bool { !chat.isSending && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    private func sendDraft() {
        guard canSend else { return }
        let text = draft
        draft = ""
        Task { await chat.submit(text) }
    }
}

/// One message: the Owner's on the right in the brand color, JARVIS's on the left on a card.
private struct MessageRow: View {
    let message: JarvisChatSession.Message
    let canRetry: Bool
    let retry: () -> Void

    private var fromOwner: Bool { message.author == .owner }

    var body: some View {
        VStack(alignment: fromOwner ? .trailing : .leading, spacing: DincrSpacing.s1) {
            Text(message.text)
                .font(DincrFont.body)
                .foregroundStyle(fromOwner ? DincrColor.onTint : DincrColor.text)
                .textSelection(.enabled)
                .padding(.horizontal, DincrSpacing.s3).padding(.vertical, DincrSpacing.s2)
                .background(fromOwner ? DincrColor.tint : DincrColor.surface,
                            in: RoundedRectangle(cornerRadius: DincrRadius.lg, style: .continuous))
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
                            .foregroundStyle(DincrColor.tint)
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
