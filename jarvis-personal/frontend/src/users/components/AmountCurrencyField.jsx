import { baseCurrency, currencySymbol, entryCurrencies, formatMoney, toBaseAmount } from "../../lib/currency";
import { tx } from "../../lib/locale";

// [ amount ] [ CRC | USD ]. An amount in the other currency needs the user's own
// exchange rate (CRC per 1 USD): DINCR shows the base amount it will record and
// never guesses a rate. `suggestedRate` is the user's last rate, if any.
export default function AmountCurrencyField({ form, setForm, suggestedRate = "", allowCurrency = true }) {
  const base = baseCurrency();
  const options = allowCurrency ? entryCurrencies() : [base];
  const currency = options.includes(form.currency) ? form.currency : base;
  const foreign = currency !== base;
  const preview = foreign ? toBaseAmount(form.amount, currency, form.exchange_rate) : null;
  const choose = (code) => setForm({
    ...form, currency: code,
    exchange_rate: code === base ? "" : (form.exchange_rate || suggestedRate),
  });

  return <>
    <div className="entry-amount-row">
      <label className="entry-amount-field"><span>{tx("Monto", "Amount")}</span><div><b>{currencySymbol(currency)}</b><input required inputMode="decimal" type="number" min="0.01" step="0.01" placeholder="0" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })}/></div></label>
      {options.length > 1 && <div className="entry-currency-toggle" role="radiogroup" aria-label={tx("Moneda", "Currency")}>
        {options.map((code) => <button type="button" role="radio" aria-checked={code === currency} className={code === currency ? "active" : ""} key={code} onClick={() => choose(code)}>{code}</button>)}
      </div>}
    </div>
    {foreign && <label className="entry-rate-field"><span>{tx("Tipo de cambio (₡ por $1)", "Exchange rate (₡ per $1)")}</span>
      <input required inputMode="decimal" type="number" min="0.0001" step="0.0001" placeholder="0" value={form.exchange_rate} onChange={(e) => setForm({ ...form, exchange_rate: e.target.value })}/>
      <small className="finva-form-hint">{preview == null
        ? tx("Ingresá el tipo de cambio que usaste. DINCR no lo adivina.", "Enter the exchange rate you used. DINCR doesn’t guess it.")
        : tx(`Se registrará como ${formatMoney(preview)} en tu moneda principal.`, `It will be recorded as ${formatMoney(preview)} in your main currency.`)}</small>
    </label>}
  </>;
}

// "$100 · TC 505" under a stored amount that was typed in another currency.
export function OriginalAmount({ row }) {
  if (!row?.original_currency) return null;
  return <small className="entry-original-amount">{formatMoney(row.original_amount, row.original_currency)} · {tx("TC", "Rate")} {Number(row.exchange_rate)}</small>;
}
