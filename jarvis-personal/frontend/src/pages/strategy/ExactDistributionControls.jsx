// Owner only: choose where the money to split comes from. The MODE says the source (DINCR's
// estimate, or the amount the Owner has left after paying everything, split whole); the STRATEGY
// (the backend's Director engine) decides how it is split, the same in both. Calculating records
// nothing; CONFIRMAR is the Owner declaring he carried it out, and the backend records it once.
// Android: OwnerExactDistribution.kt · iOS: OwnerExactDistributionView.swift.
import { useState } from "react";

import "./ExactDistributionControls.css";

function stepLines(step, tx) {
  switch (step.action) {
    case "debt_extra_payment":
      return (step.targets || []).map((target) => [tx(`Abono a ${target.name || ""}`, `Payment to ${target.name || ""}`), target.amount]);
    case "salvavidas_deposit":
      return [[tx("Depósito al Salvavidas", "Deposit to the Salvavidas"), step.amount]];
    case "goal_contribution":
      return [[tx(`Aporte a ${step.goal_name || ""}`, `Contribution to ${step.goal_name || ""}`), step.amount]];
    case "investment_reserve":
      return [[tx("Reservado para invertir", "Reserved to invest"), step.amount]];
    default:
      return [[tx("Para vivir (no se registra: tus gastos se registran cuando ocurren)", "To live on (not recorded: spending is recorded when it happens)"), step.amount]];
  }
}

export default function ExactDistributionControls({
  mode, onMode, amount, onAmount, onCalculate, loading, error, result, tx,
  plan, canConfirm, confirming, confirmed, onConfirm, money,
}) {
  const [asking, setAsking] = useState(false);
  const warnings = Array.isArray(result?.distribution_warnings) ? result.distribution_warnings : [];
  const lines = (plan?.steps || []).flatMap((step) => stepLines(step, tx));
  return (
    <div className="exact-distribution" data-testid="exact-distribution">
      <div className="exact-distribution-modes" role="group" aria-label={tx("Tipo de distribución", "Distribution type")}>
        <button type="button" aria-pressed={mode === "estimate"} className={mode === "estimate" ? "active" : ""} onClick={() => onMode("estimate")}>
          {tx("Aproximada", "Estimated")}
        </button>
        <button type="button" aria-pressed={mode === "exact"} className={mode === "exact" ? "active" : ""} onClick={() => onMode("exact")}>
          {tx("Monto exacto", "Exact amount")}
        </button>
      </div>
      {mode === "estimate" ? (
        <p className="exact-distribution-note">
          {tx("Distribución aproximada: calculada con tus registros en DINCR. Puede diferir del dinero que realmente tenés.",
            "Estimated distribution: calculated from your records in DINCR. It may differ from the money you really have.")}
        </p>
      ) : (
        <form className="exact-distribution-form" onSubmit={(event) => { event.preventDefault(); onCalculate(); }}>
          <p className="exact-distribution-note">
            {tx("Indicá cuánto dinero te sobra después de pagar tus gastos, tarjetas y cuotas. DINCR reparte ese monto completo con tu estrategia actual, sin volver a descontar esos pagos. Calcular no registra nada: solo CONFIRMAR registra los movimientos.",
              "Enter how much money you have left after paying your expenses, cards and instalments. DINCR splits that whole amount with your current strategy, without deducting those payments again. Calculating records nothing: only CONFIRM records the movements.")}
          </p>
          <label>
            <span>{tx("Monto que te sobra, en colones (₡)", "Amount you have left, in colones (₡)")}</span>
            <input inputMode="decimal" autoComplete="off" value={amount} onChange={(event) => onAmount(event.target.value)}
              aria-invalid={Boolean(error)} data-testid="exact-distribution-amount" />
          </label>
          {error && <p className="exact-distribution-error" role="alert">{error}</p>}
          <button type="submit" disabled={loading || confirming} data-testid="exact-distribution-calculate">
            {loading ? tx("Calculando…", "Calculating…") : result ? tx("Actualizar distribución", "Update distribution") : tx("Calcular distribución", "Calculate distribution")}
          </button>
          {result && (
            <p className="exact-distribution-note" role="status" data-testid="exact-distribution-status">
              {confirmed
                ? tx("Distribución confirmada: se registraron los abonos, el ahorro y los demás destinos. Tus deudas, tu Salvavidas y tu estrategia ya lo reflejan.",
                  "Distribution confirmed: the payments, the savings and the other destinations were recorded. Your debts, Salvavidas and strategy already show it.")
                : tx("Calculado con el monto que indicaste. Todavía no se registró nada. Si ya moviste el dinero así, presioná CONFIRMAR.",
                  "Calculated from the amount you entered. Nothing has been recorded yet. If you already moved the money this way, press CONFIRM.")}
            </p>
          )}
          {warnings.map((warning) => (
            <p className="exact-distribution-error" role="alert" key={warning.code || warning.message}>{warning.message}</p>
          ))}
          {result && lines.length > 0 && (
            <div className="exact-distribution-plan" data-testid="exact-distribution-plan">
              <strong>{confirmed ? tx("Lo que se registró", "What was recorded") : tx("Lo que se registrará al confirmar", "What CONFIRM will record")}</strong>
              <ul>
                {lines.map(([label, value], index) => (
                  <li key={`${label}-${index}`}><span>{label}</span><span>{money(value)}</span></li>
                ))}
              </ul>
            </div>
          )}
          {result && (plan?.blocking_reasons || []).map((reason) => (
            <p className="exact-distribution-error" role="alert" key={reason}>{reason}</p>
          ))}
          {canConfirm && !asking && (
            <button type="button" className="exact-distribution-confirm" onClick={() => setAsking(true)} data-testid="exact-distribution-confirm">
              {tx("CONFIRMAR", "CONFIRM")}
            </button>
          )}
          {canConfirm && asking && (
            <div className="exact-distribution-ask" role="alertdialog" aria-label={tx("¿Ya hiciste estos movimientos?", "Did you already make these movements?")}>
              <p>
                <strong>{tx("¿Ya hiciste estos movimientos?", "Did you already make these movements?")}</strong>{" "}
                {tx("Al confirmar, DINCR registra los abonos, el ahorro y los demás destinos de esta distribución, y tus saldos cambian. Confirmá solo si ya moviste el dinero así.",
                  "When you confirm, DINCR records the payments, the savings and the other destinations of this distribution, and your balances change. Confirm only if you already moved the money this way.")}
              </p>
              <button type="button" disabled={confirming} onClick={() => { setAsking(false); onConfirm(); }} data-testid="exact-distribution-confirm-yes">
                {confirming ? tx("Confirmando…", "Confirming…") : tx("Sí, confirmar", "Yes, confirm")}
              </button>
              <button type="button" disabled={confirming} onClick={() => setAsking(false)}>{tx("Cancelar", "Cancel")}</button>
            </div>
          )}
        </form>
      )}
    </div>
  );
}
