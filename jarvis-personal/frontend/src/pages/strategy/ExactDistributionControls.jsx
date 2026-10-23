// Owner only (phase 1): choose where the money to split comes from. The MODE says the source
// (DINCR's estimate, or the amount the Owner has left after paying everything, split whole); the STRATEGY (the backend's Director engine)
// decides how it is split, the same in both. A plan: nothing is recorded or changed.
// Android: OwnerExactDistribution.kt · iOS: OwnerExactDistributionView.swift.
import "./ExactDistributionControls.css";

export default function ExactDistributionControls({ mode, onMode, amount, onAmount, onCalculate, loading, error, result, tx }) {
  const warnings = Array.isArray(result?.distribution_warnings) ? result.distribution_warnings : [];
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
            {tx("Indicá cuánto dinero te sobra después de pagar tus gastos, tarjetas y cuotas. DINCR reparte ese monto completo con tu estrategia actual, sin volver a descontar esos pagos. No registra movimientos ni cambia tus saldos.",
              "Enter how much money you have left after paying your expenses, cards and instalments. DINCR splits that whole amount with your current strategy, without deducting those payments again. It records no movement and changes no balance.")}
          </p>
          <label>
            <span>{tx("Monto que te sobra, en colones (₡)", "Amount you have left, in colones (₡)")}</span>
            <input inputMode="decimal" autoComplete="off" value={amount} onChange={(event) => onAmount(event.target.value)}
              aria-invalid={Boolean(error)} data-testid="exact-distribution-amount" />
          </label>
          {error && <p className="exact-distribution-error" role="alert">{error}</p>}
          <button type="submit" disabled={loading} data-testid="exact-distribution-calculate">
            {loading ? tx("Calculando…", "Calculating…") : result ? tx("Actualizar distribución", "Update distribution") : tx("Calcular distribución", "Calculate distribution")}
          </button>
          {result && (
            <p className="exact-distribution-note" role="status">
              {tx("Calculado con el monto que indicaste. Es un plan: no se registró ningún movimiento ni cambió ningún saldo.",
                "Calculated from the amount you entered. It’s a plan: no movement was recorded and no balance changed.")}
            </p>
          )}
          {warnings.map((warning) => (
            <p className="exact-distribution-error" role="alert" key={warning.code || warning.message}>{warning.message}</p>
          ))}
        </form>
      )}
    </div>
  );
}
