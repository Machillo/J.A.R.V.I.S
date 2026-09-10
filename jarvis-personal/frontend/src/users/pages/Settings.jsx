import { Check, ChevronRight, Crown, Sparkles, WalletCards } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getPlans, selectPlan } from "../services/jarvisApi";
import AccountSecurity from "../components/AccountSecurity";

const icons = { free: WalletCards, basic: Sparkles, vip: Crown };

export default function Settings({ user, onUserChange }) {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [changing, setChanging] = useState("");
  const [confirming, setConfirming] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [betaAccepted, setBetaAccepted] = useState(false);

  const currentPlan = user?.subscription?.plan || "free";
  const currentPlanInfo = useMemo(
    () => plans.find((plan) => plan.code === currentPlan),
    [plans, currentPlan],
  );

  useEffect(() => {
    getPlans()
      .then(setPlans)
      .catch((err) => setError(err.message || "No se pudieron cargar los planes."))
      .finally(() => setLoading(false));
  }, []);

  const changePlan = async (planCode) => {
    if (planCode === currentPlan) return;
    if (confirming !== planCode) {
      setConfirming(planCode);
      setMessage("");
      setError("");
      return;
    }

    setChanging(planCode);
    setError("");
    setMessage("");
    try {
      const response = await selectPlan(planCode, planCode === "free" ? false : betaAccepted);
      if (response.status === "payment_pending") {
        setConfirming("");
        setMessage(`Solicitud ${planCode.toUpperCase()} creada. Se activará únicamente cuando se confirme el pago.`);
        return;
      }
      onUserChange?.(response.profile);
      setConfirming("");
      setMessage(`Plan cambiado a ${response.profile?.subscription?.plan?.toUpperCase() || planCode.toUpperCase()}.`);
    } catch (err) {
      setError(err.message || "No se pudo cambiar el plan.");
    } finally {
      setChanging("");
    }
  };

  return (
    <section className="mobile-page settings-page">
      <div className="mobile-page-heading">
        <p className="eyebrow">Cuenta</p>
        <h1>Mi Finva</h1>
        <span>Administrá tu perfil y el plan que querés probar.</span>
      </div>

      <div className="account-card">
        <div>
          <strong>{user?.display_name || "Usuario"}</strong>
          <small>{user?.email}</small>
        </div>
        <span className="role-pill">{user?.role}</span>
      </div>

      <AccountSecurity user={user} />

      <div className="section-heading compact">
        <div>
          <p className="eyebrow">Suscripción</p>
          <h2>Tu plan actual</h2>
        </div>
      </div>

      <article className={`current-plan-card plan-${currentPlan}`}>
        <div className="current-plan-icon">
          {currentPlan === "vip" ? <Crown size={24} /> : currentPlan === "basic" ? <Sparkles size={24} /> : <WalletCards size={24} />}
        </div>
        <div className="current-plan-copy">
          <strong>{currentPlanInfo?.name || currentPlan.toUpperCase()}</strong>
          <span>{currentPlanInfo?.tagline || "Plan personal Finva"}</span>
        </div>
        <span className="plan-status-pill">Actual</span>
      </article>

      <div className="section-heading compact plan-change-heading">
        <div>
          <p className="eyebrow">Desarrollo</p>
          <h2>Cambiar de plan</h2>
          <span>Basic y VIP requieren pago confirmado. El precio beta dura 3 meses.</span>
        </div>
      </div>

      {loading ? (
        <div className="mobile-panel"><p>Cargando planes...</p></div>
      ) : (
        <div className="settings-plan-list">
          {plans.map((plan) => {
            const Icon = icons[plan.code] || WalletCards;
            const isCurrent = plan.code === currentPlan;
            const isConfirming = confirming === plan.code;
            return (
              <article className={`settings-plan-row ${isCurrent ? "is-current" : ""}`} key={plan.code}>
                <div className="settings-plan-main">
                  <div className={`plan-mini-icon plan-${plan.code}`}><Icon size={20} /></div>
                  <div>
                    <strong>{plan.name}</strong>
                    <small>{plan.tagline}</small>
                  </div>
                </div>

                {isCurrent ? (
                  <span className="selected-plan-label"><Check size={16} /> Seleccionado</span>
                ) : (
                  <button
                    type="button"
                    className={isConfirming ? "confirm-plan-button" : "change-plan-button"}
                    disabled={Boolean(changing)}
                    onClick={() => changePlan(plan.code)}
                  >
                    {changing === plan.code ? "Cambiando..." : isConfirming ? `Confirmar ${plan.name}` : <>Elegir <ChevronRight size={17} /></>}
                  </button>
                )}
              </article>
            );
          })}
        </div>
      )}

      {confirming && confirming !== currentPlan && (
        <p className="plan-change-note">Tocá de nuevo “Confirmar” para aplicar el cambio. Más adelante esta pantalla gestionará upgrades, downgrades, renovación y cancelación real.</p>
      )}
      <label className="beta-consent"><input type="checkbox" checked={betaAccepted} onChange={(e)=>setBetaAccepted(e.target.checked)}/><span>Acepto el precio beta: Basic ₡1.990 o VIP ₡3.990 al mes por 3 meses; luego ₡2.990 o ₡5.990 respectivamente.</span></label>
      {message && <p className="success-banner">{message}</p>}
      {error && <p className="onboarding-error">{error}</p>}
    </section>
  );
}
