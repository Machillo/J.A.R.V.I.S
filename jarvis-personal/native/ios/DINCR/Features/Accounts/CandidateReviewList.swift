import DincrCore
import DincrDesign
import SwiftUI

/// The notices of a bank or an account in Cuentas, reviewed exactly like the Email Monitor: the same
/// card (`CandidateCard`), correction sheet, endpoints and states (pending, auto_saved, confirmed,
/// rejected, duplicate). A notice already reviewed answers `already_reviewed` and changes nothing.
/// It reloads from the backend every time it appears and after every review.
struct CandidateReviewList: View {
    let identifier: String
    let load: @MainActor () async throws -> [MailCandidate]
    @Environment(AppModel.self) private var model
    @State private var state: LoadState<[MailCandidate]> = .loading
    @State private var generation = 0
    @State private var appeared = false
    @State private var busy: String?
    @State private var notice: String?
    @State private var errorMessage: String?
    @State private var correcting: MailCandidate?

    init(identifier: String, load: @escaping @MainActor () async throws -> [MailCandidate]) {
        self.identifier = identifier; self.load = load
    }

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            if let notice { StatusBanner(tone: .info, title: notice, message: "").accessibilityIdentifier("accounts.notice") }
            if let errorMessage { ErrorStateView(message: errorMessage) }
            switch state {
            case .loading:
                SkeletonView(rows: 2, showsFigure: false)
            case .failed(let message):
                ErrorStateView(message: message) { generation += 1 }
            case .loaded(let candidates):
                if candidates.isEmpty {
                    EmptyStateView(symbol: "tray", title: tx("Sin movimientos", "No transactions"),
                                   message: tx("Cuando lleguen avisos de este banco, aparecerán acá.", "Notices from this bank will appear here.")) { EmptyView() }
                }
                ForEach(candidates) { candidate in
                    CandidateCard(candidate: candidate, busy: busy == candidate.id,
                                  confirm: { Task { await review(candidate, .accept) } },
                                  correct: { correcting = candidate },
                                  reject: { Task { await review(candidate, .reject) } })
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("accounts.movements.\(identifier)")
        .task(id: generation) { await reload() }
        .onAppear { if appeared { generation += 1 } else { appeared = true } }
        .sheet(item: $correcting) { candidate in
            CorrectionSheet(candidate: candidate) { correction in await review(candidate, .correct(correction)) ? nil : errorMessage }
        }
    }

    private func reload() async {
        let epoch = model.currentEpoch
        do {
            let rows = try await load()
            if epoch == model.currentEpoch { state = .loaded(rows) }
        } catch is CancellationError {
            return
        } catch {
            if let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar los movimientos.", "We couldn’t load the transactions.")) {
                state = .failed(message)
            }
        }
    }

    enum Review { case accept, reject, correct(CandidateCorrection) }

    /// Same calls and outcomes as the Email Monitor's review; returns whether it was saved.
    @discardableResult
    private func review(_ candidate: MailCandidate, _ review: Review) async -> Bool {
        guard let id = candidate.candidateId else { return false }
        guard busy == nil else {
            errorMessage = tx("Esperá a que termine la acción anterior.", "Wait for the previous action to finish.")
            return false
        }
        busy = candidate.id; errorMessage = nil; notice = nil
        defer { busy = nil }
        let epoch = model.currentEpoch
        do {
            let result: CandidateReviewResult
            switch review {
            case .accept: result = try await model.service.acceptCandidate(id: id)
            case .reject: result = try await model.service.rejectCandidate(id: id)
            case .correct(let correction): result = try await model.service.correctCandidate(id: id, correction)
            }
            notice = CandidateReviewNotice.text(for: result)
            correcting = nil
            generation += 1
            return true
        } catch {
            errorMessage = model.message(for: error, epoch: epoch, fallback: tx("No pudimos revisar el aviso.", "We couldn’t review the notice."))
            return false
        }
    }
}

/// The outcome of a review, in the Email Monitor's words.
enum CandidateReviewNotice {
    static func text(for result: CandidateReviewResult) -> String {
        if result.alreadyReviewed == true { return tx("Este aviso ya estaba revisado; no cambió nada.", "This notice was already reviewed; nothing changed.") }
        if result.status == "rejected" { return tx("Aviso descartado.", "Notice dismissed.") }
        if result.isInternalTransfer == true { return tx("Marcado como transferencia entre tus cuentas.", "Marked as a transfer between your accounts.") }
        return tx("Movimiento guardado.", "Transaction saved.")
    }
}

/// The review state of a notice that is no longer pending.
struct CandidateStatusLabel: View {
    let status: String?
    let internalTransfer: Bool

    var body: some View {
        let look = appearance
        Label(look.text, systemImage: look.symbol).font(DincrFont.caption.weight(.semibold)).foregroundStyle(look.color)
    }

    private var appearance: (text: String, symbol: String, color: Color) {
        switch status {
        case "confirmed"?:
            if internalTransfer { return (tx("Transferencia entre tus cuentas", "Transfer between your accounts"), "arrow.left.arrow.right", DincrColor.positive) }
            return (tx("Confirmado", "Confirmed"), "checkmark.circle", DincrColor.positive)
        case "auto_saved"?: return (tx("Guardado automáticamente", "Saved automatically"), "checkmark.circle", DincrColor.positive)
        case "rejected"?: return (tx("Descartado", "Dismissed"), "xmark.circle", DincrColor.textMuted)
        case "duplicate"?: return (tx("Repetido", "Duplicate"), "doc.on.doc", DincrColor.textMuted)
        default: return (tx("Revisado", "Reviewed"), "checkmark.circle", DincrColor.textMuted)
        }
    }
}
