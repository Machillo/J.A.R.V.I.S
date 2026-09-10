import { AlertTriangle, Check, ChevronRight, Crown, Sparkles, WalletCards, X } from "lucide-react";
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

  const openPlanDialog = (planCode) => {
    if (planCode === currentPlan) return;
    setConfirming(planCode);
    setMessage("");
    setError("");
    setBetaAccepted(false);
  };

  const changePlan = async () => {
    const planCode = confirming;
    if (!planCode || planCode === currentPlan) return;
    if (planCode !== "free" && !betaAccepted) {
      setError("Debés aceptar las condiciones del precio beta para continuar.");
      return;
    }
    setChanging(planCode);
    setError("");
    setMessage("");
    try {
      const response = await selectPlan(planCode, planCode === "free" ? false : betaAccepted);
      if (response.status === "payment_pending") {
        setConfirming("");
        setMessage(`Solicitud ${planCode.toUpperCase()} creada. Se activará cuando confirmemos el pago.`);
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
                    className="change-plan-button"
                    disabled={Boolean(changing)}
                    onClick={() => openPlanDialog(plan.code)}
                  >
                    <>Elegir <ChevronRight size={17} /></>
                  </button>
                )}
              </article>
            );
          })}
        </div>
      )}

      {message && <p className="success-banner">{message}</p>}
      {!confirming && error && <p className="onboarding-error">{error}</p>}

      {confirming && confirming !== currentPlan && (() => {
        const selected = plans.find((plan) => plan.code === confirming);
        const SelectedIcon = icons[confirming] || WalletCards;
        return <div className="plan-dialog-backdrop" role="presentation" onMouseDown={(event)=>{if(event.target===event.currentTarget&&!changing)setConfirming("");}}>
          <section className={`plan-dialog plan-${confirming}`} role="dialog" aria-modal="true" aria-labelledby="plan-dialog-title">
            <button className="plan-dialog-close" type="button" aria-label="Cerrar" disabled={Boolean(changing)} onClick={()=>setConfirming("")}><X size={20}/></button>
            <div className="plan-dialog-icon"><SelectedIcon size={28}/></div>
            <p className="eyebrow">Confirmar cambio</p>
            <h2 id="plan-dialog-title">Cambiar a {selected?.name || confirming.toUpperCase()}</h2>
            <p>{selected?.tagline || "Tu nuevo plan FINVA"}</p>
            {confirming !== "free" && <label className="beta-consent dialog-consent"><input type="checkbox" checked={betaAccepted} onChange={(e)=>{setBetaAccepted(e.target.checked);setError("");}}/><span>Acepto el precio beta de {confirming === "basic" ? "₡1.990" : "₡3.990"} al mes por 3 meses; luego {confirming === "basic" ? "₡2.990" : "₡5.990"}.</span></label>}
            {error && <div className="plan-dialog-error"><AlertTriangle size={18}/><span>{error}</span></div>}
            <div className="plan-dialog-actions"><button type="button" className="plan-dialog-cancel" disabled={Boolean(changing)} onClick={()=>setConfirming("")}>Cancelar</button><button type="button" className="plan-dialog-confirm" disabled={Boolean(changing)} onClick={changePlan}>{changing ? "Procesando..." : `Confirmar ${selected?.name || confirming.toUpperCase()}`}</button></div>
          </section>
        </div>;
      })()}
    </section>
  );
}
