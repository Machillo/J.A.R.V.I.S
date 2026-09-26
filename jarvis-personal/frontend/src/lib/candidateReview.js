import { tx } from "./locale.js";

// Status the backend stores when each review action succeeds.
const TARGET_STATUS = { accept: "confirmed", reject: "rejected" };

// One review at a time for the whole inbox. A double tap, or Accept and Reject
// tapped in the same frame, fire before React re-renders disabled buttons, so the
// lock is a plain flag and not state.
export function createReviewGate() {
  let active = null;
  return {
    begin(candidateId, action) {
      if (active) return false;
      active = { candidateId, action };
      return true;
    },
    end() { active = null; },
    get active() { return active; },
  };
}

// The backend locks the candidate and, when it was already reviewed (another
// device, a stale list or a racing tap), answers 200 with the status it already
// has. Only the stored status proves what happened.
export function reviewOutcome(action, result, { internalTransfer = false } = {}) {
  const status = String(result?.status || "");
  if (status !== TARGET_STATUS[action]) {
    const current = status === "confirmed" || status === "auto_saved"
      ? tx("ya estaba guardado", "was already saved")
      : status === "rejected" ? tx("ya estaba rechazado", "was already rejected")
        : status === "duplicate" ? tx("ya estaba marcado como duplicado", "was already marked as a duplicate")
          : tx("ya había sido revisado", "had already been reviewed");
    return {
      applied: false,
      status,
      message: tx(`Este movimiento ${current}. No se hizo ningún cambio.`, `This transaction ${current}. Nothing was changed.`),
    };
  }
  let message = tx("Movimiento guardado.", "Transaction saved.");
  if (action === "reject") message = tx("Correo descartado.", "Email dismissed.");
  else if (internalTransfer) message = tx("Transferencia interna confirmada sin contarla como gasto o ingreso.", "Internal transfer confirmed without counting it as income or expense.");
  return { applied: true, status, message };
}

// A failed review keeps the candidate. When the request may have reached the
// server (network drop, timeout, 5xx) the result is unknown: the list is
// refreshed so it shows the stored state, and retrying is safe because the
// backend answers an already-reviewed candidate with its current status.
export function reviewFailure(error) {
  const status = Number(error?.status || 0);
  const ambiguous = status === 0 || status >= 500;
  if (ambiguous) {
    return {
      ambiguous,
      message: tx(
        "No pudimos confirmar la revisión. Actualizamos la lista: si el movimiento sigue pendiente, podés intentarlo de nuevo.",
        "We couldn’t confirm the review. We refreshed the list: if the transaction is still pending, you can try again.",
      ),
    };
  }
  if (status === 404) {
    return {
      ambiguous: true,
      message: tx("Este movimiento ya no está disponible. Actualizamos la lista.", "This transaction is no longer available. We refreshed the list."),
    };
  }
  return {
    ambiguous: false,
    message: error?.message || tx("No se pudo revisar el correo.", "Couldn’t review the email."),
  };
}
