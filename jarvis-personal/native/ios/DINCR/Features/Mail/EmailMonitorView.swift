import AuthenticationServices
import DincrCore
import DincrDesign
import SwiftUI

/// PARITY H1–H7 — Email Monitor (VIP, `gmail_automation`). The backend reads the mailbox with Google's
/// read-only permission (`gmail.readonly`, pinned by the backend and never built by the app), parses
/// bank notices deterministically and keeps each one pending until the user reviews it here. Nothing
/// is written without the user's review; a notice in another currency needs the user's own rate.
struct EmailMonitorView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        Group {
            if model.planTier != .vip {
                ScreenScroll(title: tx("Monitor de correo", "Email Monitor")) {
                    PlanRequiredView(tier: .vip, feature: tx("El Monitor de correo", "The Email Monitor"))
                }
            } else if !model.flags.isEnabled(.gmailAutomation) {
                ScreenScroll(title: tx("Monitor de correo", "Email Monitor")) {
                    FeaturePausedView(message: model.flags.message(.gmailAutomation, language: model.language))
                }
            } else {
                MailMonitorContent()
            }
        }
    }
}

private struct MailMonitorContent: View {
    struct Snapshot: Equatable {
        let status: MailStatus
        let candidates: [MailCandidate]
        let transfers: [OwnTransferSuggestions.Pair]
    }

    @Environment(AppModel.self) private var model
    @Environment(\.webAuthenticationSession) private var webAuthenticationSession
    @State private var state: LoadState<Snapshot> = .loading
    @State private var generation = 0
    @State private var busy: String?
    @State private var notice: String?
    @State private var errorMessage: String?
    @State private var consentChecked = false
    @State private var scopeSheet: MailReturn.Provider?
    @State private var correcting: MailCandidate?
    @State private var disconnecting: MailStatus.Connection?
    @State private var syncSummary: String?

    var body: some View {
        ScreenScroll(title: tx("Monitor de correo", "Email Monitor")) {
            if let outcome = model.mailOutcome {
                StatusBanner(tone: .warning, title: tx("Conexión de correo", "Mail connection"), message: outcome)
                    .accessibilityIdentifier("mail.outcome")
                if model.hasPendingMailReturn {
                    Button(tx("Reintentar conexión", "Retry connection")) { Task { await model.retryPendingMailReturn(); generation += 1 } }
                        .buttonStyle(.dincrSecondary)
                }
            }
            if let notice { StatusBanner(tone: .info, title: notice, message: "").accessibilityIdentifier("mail.notice") }
            if let errorMessage { ErrorStateView(message: errorMessage) }
            switch state {
            case .loading:
                SkeletonView(rows: 3)
            case .failed(let message):
                ErrorStateView(message: message) { generation += 1 }
            case .loaded(let snapshot):
                if snapshot.status.isConnected {
                    connected(snapshot)
                } else {
                    onboarding(snapshot.status)
                }
            }
        }
        .refreshable { await load() }
        .task(id: generation) { await load() }
        .onChange(of: model.mailOutcome) { _, _ in generation += 1 }
        .sheet(item: $scopeSheet) { provider in
            ScopeSheet(provider: provider) { scope in Task { await connect(provider, scope: scope) } }
        }
        .sheet(item: $correcting) { candidate in
            CorrectionSheet(candidate: candidate) { correction in await review(candidate, .correct(correction)) ? nil : errorMessage }
        }
        .confirmationDialog(tx("¿Desconectar \(disconnecting?.googleEmail ?? "este correo")?", "Disconnect \(disconnecting?.googleEmail ?? "this mailbox")?"),
                            isPresented: Binding(get: { disconnecting != nil }, set: { if !$0 { disconnecting = nil } }), titleVisibility: .visible) {
            Button(tx("Desconectar", "Disconnect"), role: .destructive) { if let mailbox = disconnecting { Task { await disconnect(mailbox) } } }
            Button(tx("Cancelar", "Cancel"), role: .cancel) {}
        } message: {
            Text(tx("DINCR deja de leer ese correo y revoca el permiso. Los movimientos que ya guardaste se quedan.", "DINCR stops reading that mailbox and revokes the permission. Transactions you already saved stay."))
        }
    }

    // MARK: Onboarding: explanation, consent, connect

    @ViewBuilder
    private func onboarding(_ status: MailStatus) -> some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            Image(systemName: "envelope.open").font(.system(size: 32)).foregroundStyle(DincrColor.tint).accessibilityHidden(true)
            Text(tx("Tus avisos bancarios, sin escribirlos a mano", "Your bank notices, without typing them"))
                .font(DincrFont.title1).foregroundStyle(DincrColor.text).accessibilityAddTraits(.isHeader)
            Text(tx("DINCR busca en tu correo los avisos de compra, depósito y transferencia de tu banco, y te los muestra para que los confirmes.",
                    "DINCR finds your bank’s purchase, deposit and transfer notices in your mail and shows them to you to confirm."))
                .font(DincrFont.body).foregroundStyle(DincrColor.text2)
            bullet("eye", tx("Acceso de solo lectura a Gmail (gmail.readonly): DINCR no envía, borra ni modifica correos.", "Read-only Gmail access (gmail.readonly): DINCR never sends, deletes or changes email."))
                .accessibilityIdentifier("mail.readonly")
            bullet("checkmark.shield", tx("Nada se guarda sin tu revisión. Podés desconectar cuando quieras.", "Nothing is saved without your review. You can disconnect at any time."))
            if let evidence = status.retention?.reviewEvidenceDays, let metadata = status.retention?.emailMetadataDays {
                bullet("clock", tx("La evidencia de revisión se guarda \(evidence) días y los datos del correo \(metadata) días.", "Review evidence is kept \(evidence) days and mail metadata \(metadata) days."))
            }
            HStack(spacing: DincrSpacing.s4) {
                Link(tx("Privacidad", "Privacy"), destination: LegalLinks.privacy)
                Link(tx("Términos", "Terms"), destination: LegalLinks.terms)
            }
            .font(DincrFont.bodySmall.weight(.semibold))
        }
        .dincrCard()

        if status.consentRequired {
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                Toggle(isOn: $consentChecked) {
                    Text(tx("Acepto que DINCR lea mis avisos bancarios con acceso de solo lectura.", "I agree that DINCR reads my bank notices with read-only access."))
                        .font(DincrFont.body)
                }
                .tint(DincrColor.tint)
                .accessibilityIdentifier("mail.consent.toggle")
                Button(tx("Aceptar y continuar", "Accept and continue")) { Task { await acceptConsent(status) } }
                    .buttonStyle(.dincrPrimary(loading: busy == "consent"))
                    .disabled(!consentChecked || busy != nil)
                    .accessibilityIdentifier("mail.consent.accept")
            }
            .dincrCard()
        } else {
            VStack(spacing: DincrSpacing.s3) {
                Button { scopeSheet = .gmail } label: { Label(tx("Conectar Gmail", "Connect Gmail"), systemImage: "envelope") }
                    .buttonStyle(.dincrPrimary(loading: busy == "connect"))
                    .disabled(busy != nil)
                    .accessibilityIdentifier("mail.connect")
                if status.microsoftAvailable == true {
                    Button { scopeSheet = .microsoft } label: { Label(tx("Conectar Outlook", "Connect Outlook"), systemImage: "envelope.badge") }
                        .buttonStyle(.dincrSecondary)
                        .disabled(busy != nil)
                }
                Text(tx("Se abrirá una ventana segura de Google. DINCR nunca ve tu contraseña.", "A secure Google window will open. DINCR never sees your password."))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
        }
    }

    private func bullet(_ symbol: String, _ text: String) -> some View {
        Label { Text(text).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text) } icon: { Image(systemName: symbol).foregroundStyle(DincrColor.tint) }
    }

    // MARK: Connected: mailboxes, sync, review

    @ViewBuilder
    private func connected(_ snapshot: Snapshot) -> some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            SectionHeader(title: tx("Correos conectados", "Connected mailboxes"))
            ForEach(snapshot.status.mailboxes) { mailbox in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(mailbox.googleEmail ?? tx("Correo", "Mailbox")).font(DincrFont.body.weight(.semibold))
                        Text(mailbox.needsReconnect ? tx("Necesita reconectarse", "Needs to reconnect") : tx("Activo · solo lectura", "Active · read-only"))
                            .font(DincrFont.caption).foregroundStyle(mailbox.needsReconnect ? DincrColor.warning : DincrColor.positive)
                            .accessibilityIdentifier("mail.status.connected")
                    }
                    Spacer()
                    if mailbox.needsReconnect {
                        Button(tx("Reconectar", "Reconnect")) { scopeSheet = mailbox.provider == "microsoft" ? .microsoft : .gmail }
                    }
                    Menu {
                        Button(tx("Desconectar", "Disconnect"), systemImage: "xmark.circle", role: .destructive) { disconnecting = mailbox }
                    } label: { Image(systemName: "ellipsis.circle").frame(minWidth: 44, minHeight: 44) }
                    .accessibilityLabel(tx("Opciones del correo", "Mailbox options"))
                }
            }
            Button { Task { await sync() } } label: { Label(tx("Buscar avisos nuevos", "Look for new notices"), systemImage: "arrow.clockwise") }
                .buttonStyle(.dincrSecondary)
                .disabled(busy != nil)
                .accessibilityIdentifier("mail.sync")
            if let syncSummary {
                Text(syncSummary).font(DincrFont.caption).foregroundStyle(DincrColor.text2).accessibilityIdentifier("mail.syncSummary")
            }
        }
        .dincrCard()

        SectionHeader(title: tx("Por revisar", "To review"))
        let pending = snapshot.candidates.filter(\.isPending)
        if pending.isEmpty {
            EmptyStateView(symbol: "tray", title: tx("Todo revisado", "All reviewed"),
                           message: tx("Cuando lleguen avisos nuevos de tu banco, aparecerán acá.", "New notices from your bank will appear here.")) { EmptyView() }
        }
        ForEach(pending) { candidate in
            CandidateCard(candidate: candidate, busy: busy == candidate.id,
                          confirm: { Task { await review(candidate, .accept) } },
                          correct: { correcting = candidate },
                          reject: { Task { await review(candidate, .reject) } })
        }
        if !snapshot.transfers.isEmpty {
            SectionHeader(title: tx("Transferencias entre tus cuentas", "Transfers between your accounts"))
            ForEach(Array(snapshot.transfers.enumerated()), id: \.offset) { _, pair in
                OwnTransferCard(pair: pair, busy: busy != nil) { first, counterpart, direction in
                    Task { await confirmTransfer(first, counterpart, direction) }
                }
            }
        }
        NavigationLink { DetectedAccountsView() } label: {
            HubRow(symbol: "building.columns", title: tx("Cuentas detectadas", "Detected accounts"), subtitle: tx("Confirmá cuáles son tuyas", "Confirm which are yours"))
        }
        .buttonStyle(.plain)
        .dincrCard(padding: DincrSpacing.s3)
    }

    // MARK: Actions

    private func load() async {
        let epoch = model.currentEpoch
        let service = model.service
        do {
            let status = try await service.mailStatus()
            var candidates: [MailCandidate] = []
            var transfers: [OwnTransferSuggestions.Pair] = []
            if status.isConnected {
                async let list = service.mailCandidates(pendingOnly: true)
                async let suggestions = service.ownTransferSuggestions()
                candidates = try await list
                transfers = (try? await suggestions)?.items ?? []
            }
            guard epoch == model.currentEpoch else { return }
            state = .loaded(Snapshot(status: status, candidates: candidates, transfers: transfers))
        } catch {
            if let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar el Monitor de correo.", "We couldn’t load the Email Monitor.")) {
                state = .failed(message)
            }
        }
    }

    private func perform(_ tag: String, fallback: String, _ operation: () async throws -> Void) async {
        guard busy == nil else { return }
        busy = tag; errorMessage = nil
        defer { busy = nil }
        let epoch = model.currentEpoch
        do {
            try await operation()
        } catch {
            errorMessage = model.message(for: error, epoch: epoch, fallback: fallback)
        }
    }

    private func acceptConsent(_ status: MailStatus) async {
        guard let version = status.consent?.version else { errorMessage = tx("No pudimos leer la versión del consentimiento.", "We couldn’t read the consent version."); return }
        await perform("consent", fallback: tx("No pudimos guardar tu aceptación.", "We couldn’t save your acceptance.")) {
            try await model.service.acceptMailConsent(version: version)
            generation += 1
        }
    }

    /// Opens the provider's consent in the system authentication session and hands the return to the
    /// app model, which redeems the one-time completion (bound server-side to this session).
    private func connect(_ provider: MailReturn.Provider, scope: MailConnectRequest.Scope) async {
        model.consumeMailOutcome()
        await perform("connect", fallback: MailReturn.message("error", language: model.language)) {
            let url = try await model.service.connectMail(provider, MailConnectRequest(scope: scope, language: model.language))
            let callback: URL
            if model.environment.isFixtures, let simulated = FixtureOAuth.simulatedReturn(from: url) {
                callback = simulated // Debug fixture only: no provider, no browser
            } else {
                do {
                    callback = try await webAuthenticationSession.authenticate(using: url, callbackURLScheme: AppModel.mailCallbackScheme, preferredBrowserSession: .ephemeral)
                } catch let error as ASWebAuthenticationSessionError where error.code == .canceledLogin {
                    notice = tx("Cancelaste la conexión. Tu correo no se conectó.", "You cancelled. Your mail was not connected.")
                    return
                }
            }
            if !(await model.handleOpenURL(callback)) {
                errorMessage = MailReturn.message("invalid_state", language: model.language)
            }
            generation += 1
        }
    }

    private func sync() async {
        await perform("sync", fallback: tx("No pudimos buscar avisos.", "We couldn’t look for notices.")) {
            let result = try await model.service.syncMail()
            var parts = [tx("\(result.found ?? 0) encontrados", "\(result.found ?? 0) found"), tx("\(result.pending ?? 0) por revisar", "\(result.pending ?? 0) to review")]
            if let duplicates = result.duplicates, duplicates > 0 { parts.append(tx("\(duplicates) repetidos", "\(duplicates) duplicates")) }
            if let failed = result.failedConnections, !failed.isEmpty { parts.append(tx("\(failed.count) correo(s) con error", "\(failed.count) mailbox(es) failed")) }
            syncSummary = parts.joined(separator: " · ")
            generation += 1
        }
    }

    enum Review { case accept, reject, correct(CandidateCorrection) }

    /// Accept, correct or reject once; an already-reviewed notice says so and changes nothing.
    /// Returns whether it was saved (a correction sheet then closes; otherwise it shows the error).
    @discardableResult
    private func review(_ candidate: MailCandidate, _ review: Review) async -> Bool {
        guard let id = candidate.candidateId else { return false }
        guard busy == nil else {
            errorMessage = tx("Esperá a que termine la acción anterior.", "Wait for the previous action to finish.")
            return false
        }
        errorMessage = nil
        var saved = false
        await perform(candidate.id, fallback: tx("No pudimos revisar el aviso.", "We couldn’t review the notice.")) {
            let result: CandidateReviewResult
            switch review {
            case .accept: result = try await model.service.acceptCandidate(id: id)
            case .reject: result = try await model.service.rejectCandidate(id: id)
            case .correct(let correction): result = try await model.service.correctCandidate(id: id, correction)
            }
            if result.alreadyReviewed == true {
                notice = tx("Este aviso ya estaba revisado; no cambió nada.", "This notice was already reviewed; nothing changed.")
            } else if result.status == "rejected" {
                notice = tx("Aviso descartado.", "Notice dismissed.")
            } else if result.isInternalTransfer == true {
                notice = tx("Marcado como transferencia entre tus cuentas.", "Marked as a transfer between your accounts.")
            } else {
                notice = tx("Movimiento guardado.", "Transaction saved.")
            }
            correcting = nil
            saved = true
            generation += 1
        }
        return saved
    }

    private func confirmTransfer(_ candidateID: Int, _ counterpart: Int, _ direction: String?) async {
        await perform("transfer", fallback: tx("No pudimos confirmarlo.", "We couldn’t confirm it.")) {
            try await model.service.confirmOwnTransfer(candidateID: candidateID, OwnTransferRequest(counterpartId: counterpart, unknownDirection: direction))
            notice = tx("Transferencia entre tus cuentas confirmada.", "Transfer between your accounts confirmed.")
            generation += 1
        }
    }

    private func disconnect(_ mailbox: MailStatus.Connection) async {
        await perform("disconnect", fallback: tx("No pudimos desconectarlo.", "We couldn’t disconnect it.")) {
            try await model.service.disconnectMail(connectionID: mailbox.id)
            notice = tx("Correo desconectado.", "Mailbox disconnected.")
            generation += 1
        }
    }
}

extension MailReturn.Provider: @retroactive Identifiable {
    public var id: String { rawValue }
}

/// How far back the first scan reads (`import_scope`).
private struct ScopeSheet: View {
    @Environment(\.dismiss) private var dismiss
    let provider: MailReturn.Provider
    let choose: (MailConnectRequest.Scope) -> Void

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Button { dismiss(); choose(.currentMonth) } label: {
                        HubRow(symbol: "calendar", title: tx("Este mes", "This month"), subtitle: tx("Solo los avisos de este mes", "Only this month’s notices"))
                    }
                    .accessibilityIdentifier("mail.scope.month")
                    Button { dismiss(); choose(.currentYear) } label: {
                        HubRow(symbol: "calendar.badge.clock", title: tx("Este año", "This year"), subtitle: tx("Los avisos desde enero", "Notices since January"))
                    }
                    .accessibilityIdentifier("mail.scope.year")
                } footer: {
                    Text(tx("DINCR solo pide permiso de lectura. Podés desconectar cuando quieras.", "DINCR only asks for read permission. You can disconnect at any time."))
                }
            }
            .navigationTitle(provider == .gmail ? tx("Conectar Gmail", "Connect Gmail") : tx("Conectar Outlook", "Connect Outlook"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() } } }
        }
        .presentationDetents([.medium])
    }
}

/// One bank notice to review. Shared by the Email Monitor and Cuentas (the same review, the same
/// endpoints); a notice already reviewed shows its state instead of the actions.
struct CandidateCard: View {
    let candidate: MailCandidate
    let busy: Bool
    let confirm: () -> Void
    let correct: () -> Void
    let reject: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            HStack(alignment: .firstTextBaseline) {
                if let brand = candidate.identifiedBank { BankLogo(brand: brand, size: 32) }
                VStack(alignment: .leading, spacing: 2) {
                    Text(candidate.description ?? candidate.subject ?? tx("Aviso bancario", "Bank notice")).font(DincrFont.body.weight(.semibold))
                    Text([candidate.bank, Day.label(candidate.transactionDate)].compactMap { $0 }.joined(separator: " · "))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                Spacer()
                MoneyText(candidate.nativeAmount, sign: candidate.transactionType == "income" ? .income : .expense, currency: candidate.nativeCurrency)
            }
            .accessibilityElement(children: .combine)
            if !candidate.isPending {
                CandidateStatusLabel(status: candidate.reviewStatus, internalTransfer: candidate.isInternalTransfer == true)
                    .accessibilityIdentifier("candidate.status.\(candidate.candidateId ?? 0)")
            } else {
                if candidate.cannotConvert {
                    Text(tx("Está en \(candidate.nativeCurrency ?? "otra moneda"), que DINCR no puede convertir. Solo podés descartarlo.",
                            "It’s in \(candidate.nativeCurrency ?? "another currency"), which DINCR can’t convert. You can only dismiss it."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.warning)
                } else if candidate.needsRate {
                    Text(tx("Está en \(candidate.nativeCurrency ?? ""). Tocá Corregir e indicá tu tipo de cambio.", "It’s in \(candidate.nativeCurrency ?? ""). Tap Correct and enter your exchange rate."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.warning)
                }
                HStack(spacing: DincrSpacing.s2) {
                    if !candidate.needsRate && !candidate.cannotConvert {
                        Button(tx("Confirmar", "Confirm"), action: confirm).buttonStyle(.dincrPrimary(loading: busy))
                            .accessibilityIdentifier("mail.accept.\(candidate.candidateId ?? 0)")
                    }
                    if !candidate.cannotConvert {
                        Button(tx("Corregir", "Correct"), action: correct).buttonStyle(.dincrSecondary)
                            .accessibilityIdentifier("mail.correct.\(candidate.candidateId ?? 0)")
                    }
                    Button(tx("Descartar", "Dismiss"), role: .destructive, action: reject).frame(minHeight: 44)
                        .accessibilityIdentifier("mail.reject.\(candidate.candidateId ?? 0)")
                }
                .disabled(busy)
            }
        }
        .dincrCard()
    }
}

/// Accept with corrections: amount in the notice's own currency, and the user's own rate when that
/// currency is not the account's (DINCR never looks rates up).
struct CorrectionSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let candidate: MailCandidate
    /// Returns an error to show in the sheet, or nil when saved.
    let submit: (CandidateCorrection) async -> String?
    @State private var description = ""
    @State private var amount = ""
    @State private var rate = ""
    @State private var type = "expense"
    @State private var category = ""
    @State private var date = Date.now
    @State private var error: String?
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                TextField(tx("Descripción", "Description"), text: $description)
                VStack(alignment: .leading) {
                    Text(tx("Monto en \(candidate.nativeCurrency ?? "")", "Amount in \(candidate.nativeCurrency ?? "")")).font(DincrFont.label)
                    TextField(tx("Monto", "Amount"), text: $amount).keyboardType(.decimalPad).accessibilityIdentifier("correct.amount")
                }
                if candidate.needsRate {
                    VStack(alignment: .leading) {
                        Text(tx("Tipo de cambio (colones por 1 dólar)", "Exchange rate (colones per 1 dollar)")).font(DincrFont.label)
                        TextField(tx("Tipo de cambio", "Exchange rate"), text: $rate, prompt: Text(model.moneyFormat.inputText(Decimal(string: "507.5")!)))
                            .keyboardType(.decimalPad).accessibilityIdentifier("correct.rate")
                    }
                }
                Picker(tx("Tipo", "Type"), selection: $type) {
                    Text(tx("Gasto", "Expense")).tag("expense")
                    Text(tx("Ingreso", "Income")).tag("income")
                    Text(tx("Pago de deuda", "Debt payment")).tag("debt_payment")
                    Text(tx("Transferencia", "Transfer")).tag("transfer")
                }
                TextField(tx("Categoría", "Category"), text: $category)
                DatePicker(tx("Fecha", "Date"), selection: $date, in: ...Date.now, displayedComponents: .date)
                if let error { Text(error).foregroundStyle(DincrColor.negative) }
            }
            .navigationTitle(tx("Corregir aviso", "Correct notice"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Guardar", "Save")) { Task { await save() } }.disabled(saving).accessibilityIdentifier("correct.save")
                }
            }
            .onAppear(perform: prefill)
        }
        .interactiveDismissDisabled(saving)
    }

    private func prefill() {
        guard description.isEmpty else { return }
        description = candidate.description ?? ""
        amount = candidate.nativeAmount.map(model.moneyFormat.inputText) ?? ""
        type = ["expense", "income", "debt_payment", "transfer"].contains(candidate.transactionType ?? "") ? candidate.transactionType! : "expense"
        category = candidate.category ?? "general"
        if let day = candidate.transactionDate, let parsed = MovementEditor.dayFormatter.date(from: String(day.prefix(10))) { date = parsed }
    }

    private func save() async {
        let separators = model.moneyFormat.separators
        let text = description.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { error = tx("Escribí una descripción.", "Enter a description."); return }
        guard let value = CorrectionInput.amount(amount, separators: separators) else { error = model.moneyFormat.amountHint; return }
        var exchangeRate: Decimal?
        if candidate.needsRate {
            guard let parsed = CorrectionInput.rate(rate, separators: separators) else {
                error = tx("Escribí cuántos colones vale 1 dólar.", "Enter how many colones 1 dollar is worth."); return
            }
            exchangeRate = parsed
        }
        saving = true; error = nil
        error = await submit(CandidateCorrection(transactionDate: MovementEditor.dayFormatter.string(from: date), description: text, amount: value,
                                                 transactionType: type, category: category.isEmpty ? "general" : category, exchangeRate: exchangeRate))
        saving = false
    }
}

private struct OwnTransferCard: View {
    let pair: OwnTransferSuggestions.Pair
    let busy: Bool
    let confirm: (Int, Int, String?) -> Void

    var body: some View {
        if let first = pair.first, let second = pair.second, let firstID = first.candidateId, let secondID = second.candidateId {
            let declared = OwnTransferRequest.unknownDirection(first: first.direction, second: second.direction)
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                Text(tx("Estos dos avisos parecen el mismo dinero moviéndose entre cuentas tuyas.", "These two notices look like the same money moving between your accounts."))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.text2)
                side(first, declared: declared)
                side(second, declared: declared)
                if declared == OwnTransferRequest.cannotInfer {
                    Text(tx("No sabemos en qué dirección se movió el dinero. Revisá estos avisos por separado.", "We don’t know which way the money moved. Review these notices separately."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.warning)
                } else {
                    Button(tx("Son mis cuentas: no es gasto ni ingreso", "They’re my accounts: not spending or income")) { confirm(firstID, secondID, declared) }
                        .buttonStyle(.dincrSecondary)
                        .disabled(busy)
                }
            }
            .dincrCard()
        }
    }

    private func side(_ side: OwnTransferSuggestions.Side, declared: String?) -> some View {
        let known = side.direction == "in" || side.direction == "out"
        // A notice without a direction is shown with the one it will be saved with.
        let direction = known ? side.direction : (declared == OwnTransferRequest.cannotInfer ? nil : declared)
        let label = switch direction {
        case "in"?: tx("entra", "in")
        case "out"?: tx("sale", "out")
        default: "?"
        }
        let suffix = !known && direction != nil ? tx(" (deducido)", " (inferred)") : ""
        return HStack {
            Text("\(side.bank ?? "") · \(Day.label(side.date)) · \(label)\(suffix)").font(DincrFont.bodySmall)
            Spacer()
            MoneyText(side.amount, currency: side.currency, font: DincrFont.bodySmall.monospacedDigit())
        }
        .accessibilityElement(children: .combine)
    }
}

/// H7 — accounts detected in the notices: confirm which are the user's own.
struct DetectedAccountsView: View {
    @Environment(AppModel.self) private var model
    @State private var generation = 0
    @State private var error: String?

    var body: some View {
        ScreenScroll(title: tx("Cuentas detectadas", "Detected accounts")) {
            if let error { ErrorStateView(message: error) }
            AsyncContent(load: { try await model.service.financialIdentity() }) { identity, _ in
                AccountsContent(accounts: identity.items ?? []) { account, own in Task { await set(account, own) } }
            }
            .id(generation)
        }
    }

    private func set(_ account: FinancialIdentity.Account, _ own: Bool) async {
        let epoch = model.currentEpoch
        do {
            try await model.service.setAccountOwnership(id: account.id, own: own)
            generation += 1
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardarlo.", "We couldn’t save it."))
        }
    }
}

private struct AccountsContent: View {
    let accounts: [FinancialIdentity.Account]
    let set: (FinancialIdentity.Account, Bool) -> Void

    var body: some View {
        if accounts.isEmpty {
            EmptyStateView(symbol: "building.columns", title: tx("Sin cuentas todavía", "No accounts yet"),
                           message: tx("Cuando DINCR lea avisos de tus bancos, verás acá las cuentas que mencionan.", "When DINCR reads your bank notices, you’ll see the accounts they mention here.")) { EmptyView() }
        }
        ForEach(accounts) { account in
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                Text(account.accountName ?? account.bankName ?? tx("Cuenta", "Account")).font(DincrFont.body.weight(.semibold))
                Text([account.bankName, account.accountLast4.map { "•••• \($0)" }, account.currency].compactMap { $0 }.joined(separator: " · "))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                switch account.ownershipStatus {
                case "own": Label(tx("Es mía", "It’s mine"), systemImage: "checkmark.circle").foregroundStyle(DincrColor.positive)
                case "not_mine": Label(tx("No es mía", "Not mine"), systemImage: "xmark.circle").foregroundStyle(DincrColor.textMuted)
                default:
                    HStack {
                        Button(tx("Es mía", "It’s mine")) { set(account, true) }.buttonStyle(.dincrSecondary)
                        Button(tx("No es mía", "Not mine")) { set(account, false) }.frame(minHeight: 44)
                    }
                }
            }
            .dincrCard()
        }
    }
}

/// Debug fixture mode only: the fixture backend's authorization URL carries the return the real
/// provider would send, so flows run without a browser. A Release build never has fixture data.
enum FixtureOAuth {
    static func simulatedReturn(from url: URL) -> URL? {
        guard url.host == FixtureBackend.authorizeHost,
              let value = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "fixture_return" })?.value else { return nil }
        return URL(string: value)
    }
}
