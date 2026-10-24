// Owner exact-amount distribution (phase 1): parsing the amount the Owner types.
// The backend validates again (backend/ai/models.py ExactDistributionRequest); this only keeps a
// mistyped amount from being sent. Nothing is guessed: an ambiguous text is refused.

export const EXACT_DISTRIBUTION_MAX = 1_000_000_000;

const ERRORS = {
  empty: ["Escribí el monto que tenés disponible.", "Enter the amount you have available."],
  format: ["Escribí solo números, con hasta dos decimales (por ejemplo 750.000 o 750.000,50).", "Use numbers only, with up to two decimals (for example 750,000 or 750,000.50)."],
  zero: ["El monto tiene que ser mayor que cero.", "The amount must be above zero."],
  too_large: ["El monto no puede superar ₡1.000.000.000.", "The amount can’t exceed ₡1,000,000,000."],
};

/** The message of a parse error code, in the page's language (`tx(es, en)`). */
export function exactAmountError(code, tx) {
  const [es, en] = ERRORS[code] || ERRORS.format;
  return tx(es, en);
}

const has = (object, key) => Object.prototype.hasOwnProperty.call(object || {}, key);
const num = (value) => Number(value || 0);

/**
 * What the strategy page's Distribution panel shows (PremiumStrategy.jsx). In the Owner's exact
 * mode it reads the exact answer; otherwise, and before an exact answer exists, the estimate.
 * `note` says which sentence goes under the surplus: "deficit", "exact" (never the estimate's
 * note about new expenses under a typed amount), "new_expenses" or "recalculated".
 */
export function distributionPanel({ strategy, exact, ownerExact }) {
  const estimate = strategy || {};
  const exactMode = Boolean(ownerExact) && exact?.mode === "exact";
  const shown = (exactMode && exact?.data?.strategy) || estimate;
  const items = Array.isArray(shown.allocation_items) ? shown.allocation_items : [];
  const base = num(shown.allocation_base_amount);
  const total = num(shown.allocation_total || items.reduce((sum, item) => sum + num(item.amount), 0));
  const formula = shown.distribution_formula || {};
  const manualFormula = has(formula, "manual_available");
  const deficit = Math.max(0, num(formula.deficit));
  const newExpensesCount = num(estimate.new_expenses_after_cut_count);
  return {
    exactMode,
    showDistribution: !exactMode || Boolean(exact?.data?.strategy),
    strategy: shown,
    amounts: shown.allocation_amounts || {},
    base,
    total,
    balanced: Math.abs(base - total) <= 1,
    formula,
    manualFormula,
    hasFormula: manualFormula || has(formula, "cash_available_now"),
    // The exact amount is already what is left: it shows alone, with no deduction lines.
    breakdownKeys: manualFormula
      ? ["manual_available"]
      : ["cash_available_now", "income", "statement_spending", "new_spending_after_cut", "debt_commitment", "mandatory_fixed_pending"],
    addedLines: manualFormula ? 1 : 2,
    deficit,
    note: deficit > 0 ? "deficit" : exactMode ? "exact" : newExpensesCount > 0 ? "new_expenses" : "recalculated",
    newExpensesCount,
    activeGoalName: shown.goal_portfolio?.active_goal?.name || null,
    primaryDebtName: shown.primary_debt_name || null,
  };
}

/** What the Investments panel shows: always the estimate, whatever the distribution mode. */
export function investmentPanel(strategy) {
  const base = num(strategy?.allocation_base_amount);
  const recommended = num(strategy?.investment_recommended);
  return { base, recommended, state: base <= 0 ? "blocked" : recommended > 0 ? "ready" : "limited" };
}

/**
 * The exact-amount state after the Owner edits the amount: the previous result (and error) no
 * longer describe it, so they are dropped. Android/iOS: `ExactDistributionForm`.
 */
export function editExactAmount(current, amount) {
  return { ...current, amount, error: "", data: null, confirmationKey: null, confirmation: null };
}

const newConfirmationKey = () =>
  (globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`);

/** The answer for `forAmount`; kept only when it is still the amount on screen. A new result gets a new key. */
export function applyExactResult(current, forAmount, data, key = newConfirmationKey()) {
  if (current.amount !== forAmount) return { ...current, loading: false };
  return { ...current, loading: false, error: "", data, confirmationKey: key, confirmation: null };
}

/** CONFIRMAR is offered only for a calculated result the backend says it can record, once. */
export function canConfirmExact(current) {
  return Boolean(current.data?.strategy && current.data?.confirmation_plan?.confirmable && current.confirmationKey && !current.confirmation);
}

/** The split the Owner reviewed, sent with CONFIRMAR: the backend records nothing when its own differs. */
export function confirmExactPayload(current, amount) {
  const fingerprint = current.data?.confirmation_plan?.fingerprint;
  if (!current.data?.strategy || !current.confirmationKey || !fingerprint) return null;
  const items = (current.data.strategy.allocation_items || [])
    .filter((item) => item.key && item.amount !== undefined && item.amount !== null)
    .map((item) => ({ key: item.key, amount: item.amount }));
  return { amount, currency: "CRC", confirmation_key: current.confirmationKey, expected_items: items, plan_fingerprint: fingerprint };
}

/** The backend's answer for `key`; kept only when it is still this result's key. */
export function applyConfirmation(current, key, answer) {
  if (current.confirmationKey !== key) return { ...current, confirming: false };
  return { ...current, confirming: false, error: "", confirmation: answer };
}

/** The answer's error for `forAmount`; dropped when the Owner has since typed another amount. */
export function applyExactError(current, forAmount, error) {
  if (current.amount !== forAmount) return { ...current, loading: false };
  return { ...current, loading: false, error };
}

/**
 * "750000", "750.000", "750 000", "750.000,50", "750,000.50" → a number with at most two decimals.
 * Returns { value } or { error } (a code: "empty", "format", "zero", "too_large").
 */
export function parseExactAmount(text) {
  const raw = String(text ?? "").trim().replace(/[₡\s]/g, "");
  if (!raw) return { error: "empty" };
  if (!/^\d[\d.,]*$/.test(raw)) return { error: "format" };
  const lastDot = raw.lastIndexOf(".");
  const lastComma = raw.lastIndexOf(",");
  let integer = raw;
  let fraction = "";
  const decimalAt = (() => {
    if (lastDot >= 0 && lastComma >= 0) return Math.max(lastDot, lastComma); // both: the last one is decimal
    const at = Math.max(lastDot, lastComma);
    if (at < 0) return -1;
    const separator = raw[at];
    const occurrences = raw.split(separator).length - 1;
    const digitsAfter = raw.length - at - 1;
    // One separator followed by 1–2 digits is a decimal mark; anything else must be thousands groups.
    return occurrences === 1 && digitsAfter > 0 && digitsAfter <= 2 ? at : -1;
  })();
  if (decimalAt >= 0) {
    integer = raw.slice(0, decimalAt);
    fraction = raw.slice(decimalAt + 1);
    if (!/^\d{1,2}$/.test(fraction)) return { error: "format" };
  }
  const groups = integer.split(/[.,]/);
  if (groups.length > 1) {
    const [first, ...rest] = groups;
    if (!/^\d{1,3}$/.test(first) || rest.some((group) => !/^\d{3}$/.test(group))) return { error: "format" };
  } else if (!/^\d+$/.test(integer)) {
    return { error: "format" };
  }
  const value = Number(`${groups.join("")}.${fraction || "0"}`);
  if (!Number.isFinite(value)) return { error: "format" };
  if (value <= 0) return { error: "zero" };
  if (value > EXACT_DISTRIBUTION_MAX) return { error: "too_large" };
  return { value: Math.round(value * 100) / 100 };
}
