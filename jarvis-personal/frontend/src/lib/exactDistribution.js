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
