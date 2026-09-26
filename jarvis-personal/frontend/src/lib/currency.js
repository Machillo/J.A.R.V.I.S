import { deviceLanguage, localeTag } from "./locale.js";

// Currencies a manual income or expense can be typed in.
export const ENTRY_CURRENCIES = ["CRC", "USD"];

// The account's base currency: every stored `amount` and every total is in it.
// UsersApp sets it from the signed-in account before pages render, together with
// the currencies the backend declares it converts (identity `entry_currencies`).
let base = "CRC";
let declared = [];
export const setBaseCurrency = (code, entryCodes) => {
  base = String(code || "CRC").toUpperCase();
  declared = Array.isArray(entryCodes) ? entryCodes.map((item) => String(item).toUpperCase()) : [];
};
export const baseCurrency = () => base;

// Currencies offered for a new entry. Only what the backend declared: an older
// backend ignores `currency`/`exchange_rate` and would store a USD figure as base,
// so without the declaration only the base is offered. An account whose legacy
// base currency is not CRC or USD records only in its own currency.
export const entryCurrencies = () => {
  const offered = ENTRY_CURRENCIES.filter((code) => declared.includes(code));
  return offered.length > 1 && offered.includes(base) ? offered : [base];
};

export function formatMoney(value, currency = base, { maximumFractionDigits } = {}) {
  const code = String(currency || base).toUpperCase();
  return new Intl.NumberFormat(localeTag(deviceLanguage()), {
    style: "currency", currency: code, currencyDisplay: "narrowSymbol",
    maximumFractionDigits: maximumFractionDigits ?? (code === "USD" ? 2 : 0),
  }).format(Number(value) || 0);
}

export const currencySymbol = (currency = base) => formatMoney(0, currency, { maximumFractionDigits: 0 }).replace(/[\d\s.,]/g, "");

// Base-currency amount for a typed amount, mirroring the backend: the rate is
// always CRC per 1 USD. null while the rate is missing; nothing is guessed.
export function toBaseAmount(amount, currency, rate) {
  const value = Number(amount);
  if (!Number.isFinite(value) || value <= 0) return null;
  const code = String(currency || base).toUpperCase();
  if (code === base) return value;
  const perUsd = Number(rate);
  if (!Number.isFinite(perUsd) || perUsd <= 0) return null;
  return Math.round((code === "USD" ? value * perUsd : value / perUsd) * 100) / 100;
}

// Fields sent with every create and edit. null means the base currency (and
// clears a previous foreign amount); the other currency travels with its rate.
export function entryCurrencyPayload({ currency, exchange_rate: rate }) {
  const code = String(currency || base).toUpperCase();
  return code === base ? { currency: null, exchange_rate: null } : { currency: code, exchange_rate: Number(rate) };
}

// Form state for editing a stored entry: the amount the user typed, in its currency.
// Without a declared conversion (older backend), a foreign entry is edited by its
// stored base amount, as an older app does: never its typed figure read as base.
export function entryFormAmount(row) {
  return row?.original_currency && entryCurrencies().includes(String(row.original_currency).toUpperCase())
    ? { amount: row.original_amount, currency: row.original_currency, exchange_rate: row.exchange_rate ?? "" }
    : { amount: row?.amount ?? "", currency: base, exchange_rate: "" };
}

// The user's own most recent rate, to prefill the next foreign-currency entry.
// Only manual income and expenses: bank or imported movements may carry a
// parser's or another tool's rate, which is not the user's.
export function latestUserRate(rows = []) {
  const withRate = rows.filter((row) => Number(row?.exchange_rate) > 0
    && (row.origin === undefined || row.origin === "salary" || row.origin === "expense"));
  withRate.sort((a, b) => String(b.transaction_date || b.entry_date || b.created_at || "")
    .localeCompare(String(a.transaction_date || a.entry_date || a.created_at || "")));
  return withRate.length ? String(Number(withRate[0].exchange_rate)) : "";
}
