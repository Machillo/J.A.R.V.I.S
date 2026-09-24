import { Info } from "lucide-react";
import { deviceLanguage, localeTag, tx } from "../../lib/locale";

const language = deviceLanguage();
const copy = (es, en) => tx(es, en, language);
const money = (value) => new Intl.NumberFormat(localeTag(language), {
  style: "currency", currency: "CRC", currencyDisplay: "narrowSymbol", maximumFractionDigits: 0,
}).format(Number(value) || 0);

// Optional, one-time suggestions (P2: excess savings vs. very expensive debt).
// Deliberately separate from the monthly plan: not part of the allocations, not
// money already assigned, and DINCR never executes them (there is no action button).
export default function StrategyOptionalActions({ actions = [] }) {
  const visible = actions.filter((action) => action?.optional === true && action?.executes === false && action?.source === "excess_savings");
  if (!visible.length) return null;
  return (
    <section className="strategy-optional-actions" aria-labelledby="strategy-optional-actions-title">
      <header>
        <Info size={18} aria-hidden="true" />
        <div>
          <small>{copy("SUGERENCIA OPCIONAL · FUERA DEL PLAN MENSUAL", "OPTIONAL SUGGESTION · OUTSIDE THE MONTHLY PLAN")}</small>
          <h3 id="strategy-optional-actions-title">{copy("Podrías usar ahorro excedente", "You could use excess savings")}</h3>
        </div>
      </header>
      {visible.map((action) => (
        <article key={`${action.source}-${action.debt_id}`}>
          <p>
            {copy(
              `Tu ahorro supera tu fondo de emergencia objetivo en ${money(action.excess_savings)}. Si lo decidís, podrías abonar hasta ${money(action.amount)} a ${action.debt_name} (${action.interest_rate}% anual).`,
              `Your savings exceed your emergency fund target by ${money(action.excess_savings)}. If you decide to, you could pay up to ${money(action.amount)} toward ${action.debt_name} (${action.interest_rate}% annual).`,
            )}
          </p>
          <ul>
            <li>{copy(
              `Tu fondo de emergencia (${money(action.emergency_fund_target)}) y el ahorro de tus metas no se tocan.`,
              `Your emergency fund (${money(action.emergency_fund_target)}) and your goal savings stay untouched.`,
            )}</li>
            <li>{copy(
              "Antes de abonar, confirmá que no necesitás ese excedente para gastos próximos que DINCR no conoce (por ejemplo marchamo o colegio).",
              "Before paying, confirm you don't need that excess for upcoming expenses DINCR doesn't know about (for example vehicle tax or school costs).",
            )}</li>
            <li>{copy(
              "Consultá con tu entidad posibles comisiones por pago anticipado. Un abono no se puede revertir.",
              "Check with your lender for possible early-payment fees. A prepayment cannot be undone.",
            )}</li>
          </ul>
          <small>{copy(
            "Es solo una sugerencia: no forma parte de tu reparto mensual y DINCR no mueve dinero ni registra el pago.",
            "This is only a suggestion: it is not part of your monthly plan and DINCR does not move money or record the payment.",
          )}</small>
        </article>
      ))}
    </section>
  );
}
