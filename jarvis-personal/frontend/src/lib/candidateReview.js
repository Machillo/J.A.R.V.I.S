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

// After an unknown outcome only the refreshed list tells what the backend
// stored. `rows` is that list, or null when the refresh failed too. Only a
// stored status equal to the action's target is reported as done.
export function reconcileReview(action, candidateId, rows, failure) {
  if (!rows) {
    return {
      applied: false,
      message: tx(
        "No pudimos confirmar la revisión ni actualizar la lista. Revisá tu conexión e intentá de nuevo: si ya se había guardado, no se duplicará.",
        "We couldn’t confirm the review or refresh the list. Check your connection and try again: if it was already saved, it won’t be duplicated.",
      ),
    };
  }
  const row = rows.find((item) => item.candidate_id === candidateId);
  if (!row) {
    return {
      applied: false,
      message: failure?.message && Number(failure?.status) === 404 ? failure.message : tx(
        "Este movimiento ya no está pendiente. Abrí Todos para ver cómo quedó.",
        "This transaction is no longer pending. Open All to see how it ended up.",
      ),
    };
  }
  if (row.review_status === "pending") {
    return {
      applied: false,
      message: tx("La revisión no se completó: el movimiento sigue pendiente. Podés intentarlo de nuevo.", "The review didn’t go through: the transaction is still pending. You can try again."),
    };
  }
  return reviewOutcome(action, { status: row.review_status });
}

// Refreshes overlap (a review, returning to the app, a sync, a filter change).
// Only the most recent one may write the list, so a slower older response never
// brings back a candidate that a newer one already removed.
export function createLatestOnly() {
  let latest = 0;
  return {
    start() {
      latest += 1;
      const ticket = latest;
      return () => ticket === latest;
    },
  };
}

// Statuses a review can answer; anything else is an unexpected response.
const STORED_STATUSES = new Set(["confirmed", "auto_saved", "rejected", "duplicate"]);

// The Accept/Reject flow, free of React so it can be tested. `ui` applies the
// result to the screen and is never called once the screen is gone; the gate
// is released on every path.
export async function runCandidateReview({ gate, item, action, send, reload, isMounted, onApplied, ui }) {
  if (!gate.begin(item.candidate_id, action)) return "dropped";
  ui.begin();
  // Unknown outcome: the refreshed list decides, never the request.
  const reconcile = async (failure) => {
    ui.pageError(failure.message);
    const rows = await reload();
    if (!isMounted()) return "unmounted";
    const settled = reconcileReview(action, item.candidate_id, rows, failure);
    // A stored status settles the card; otherwise it stays open for a retry.
    if (settled.status) ui.settle(settled);
    else ui.pageError(settled.message);
    return settled.applied ? "applied" : settled.status ? "stale" : "unknown";
  };
  try {
    let result;
    try {
      result = await send();
    } catch (error) {
      if (!isMounted()) return "unmounted";
      const failure = { ...reviewFailure(error), status: Number(error?.status || 0) };
      if (failure.ambiguous) return await reconcile(failure);
      ui.cardError(failure.message);
      return "failed";
    }
    if (!STORED_STATUSES.has(String(result?.status || ""))) {
      return isMounted() ? await reconcile(reviewFailure({ status: 0 })) : "unmounted";
    }
    const outcome = reviewOutcome(action, result, { internalTransfer: Boolean(item.is_internal_transfer) });
    if (outcome.applied) onApplied();
    if (!isMounted()) return "unmounted";
    // A stale outcome (another device, a racing tap) settles the card but is not a success.
    ui.settle(outcome);
    // The candidate leaves the list only when the refreshed list says so.
    await reload();
    return outcome.applied ? "applied" : "stale";
  } finally {
    gate.end();
    if (isMounted()) ui.end();
  }
}
