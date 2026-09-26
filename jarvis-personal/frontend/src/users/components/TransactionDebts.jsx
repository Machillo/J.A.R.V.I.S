import { useEffect, useState } from "react";
import { ChevronRight, CreditCard } from "lucide-react";
import { getDebts } from "../services/jarvisApi";
import { deviceLanguage } from "../../lib/locale";
import { formatMoney } from "../../lib/currency";

const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;
// Amounts are in the account's base currency (CRC or USD).
const money = (value) => formatMoney(value);

// Read-only view of the user's debts inside Movimientos. It reads the same endpoint
// and service as the Debts screen (getDebts -> GET /user-product/finance/debts), keeps
// nothing of its own and never writes: every change happens in the Debts screen,
// which `onManage` opens. scripts/test-debts-in-transactions.mjs keeps it that way.
export default function TransactionDebts({ onManage }) {
  const [debts, setDebts] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getDebts()
      .then((rows) => { if (active) setDebts(Array.isArray(rows) ? rows : []); })
      .catch((err) => { if (active) setError(err?.message || tx("No pudimos cargar tus deudas.", "We couldn’t load your debts.")); });
    return () => { active = false; };
  }, []);

  if (error) return <div className="free-error" role="alert">{error}</div>;
  if (!debts) return <p className="free-empty" role="status">{tx("Cargando deudas…", "Loading debts…")}</p>;

  const open = debts.filter((debt) => Number(debt.remaining_amount) > 0);
  const total = open.reduce((sum, debt) => sum + Number(debt.remaining_amount || 0), 0);

  return <section className="transaction-debts" aria-labelledby="transaction-debts-title">
    <header>
      <span><small id="transaction-debts-title">{tx("Tus deudas", "Your debts")}</small><strong>{money(total)}</strong><em>{open.length} {open.length === 1 ? tx("activa", "active") : tx("activas", "active")}</em></span>
      {onManage && <button type="button" onClick={onManage}>{tx("Gestionar", "Manage")}<ChevronRight size={15}/></button>}
    </header>
    {debts.length ? <div className="free-transaction-list">
      {debts.map((debt) => {
        const paid = Number(debt.remaining_amount) <= 0;
        return <button className="free-transaction-row" type="button" key={debt.id} onClick={onManage}>
          <span><strong>{debt.name}</strong><small>{paid ? tx("Pagada", "Paid off") : `${money(debt.monthly_payment)}/${tx("mes", "month")}`}{debt.progress_percent != null && ` · ${Math.round(Number(debt.progress_percent))}% ${tx("pagado", "paid")}`}</small></span>
          <b className="debt">{money(debt.remaining_amount)}</b>
        </button>;
      })}
    </div> : <p className="free-empty"><CreditCard size={16}/> {tx("No tenés deudas registradas.", "You have no recorded debts.")}</p>}
  </section>;
}
