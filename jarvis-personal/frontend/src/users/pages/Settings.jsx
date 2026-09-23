import { AlertTriangle, Check, CheckCircle2, ChevronRight, Clock3, Copy, Crown, Smartphone, Sparkles, Upload, WalletCards, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getBillingCatalog, getMe, getPlans, selectPlan, uploadPaymentReceipt } from "../services/jarvisApi";
import AccountSecurity from "../components/AccountSecurity";
import { hasNativeReceiptPicker, pickNativeReceipt, receiptFromWebInput } from "../../lib/receiptPicker";
import AppearanceSelector from "../../components/AppearanceSelector";
import AppLockSettings from "../components/AppLockSettings";
import { deviceLanguage, localeTag } from "../../lib/locale";
import { useFinvaBackHandler } from "../../products/finva/navigation/useFinvaNavigation";
import AccountActions from "../../products/finva/components/AccountActions";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const icons = { free: WalletCards, basic: Sparkles, vip: Crown };

export default function Settings({ user, onUserChange, onLogout }) {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [changing, setChanging] = useState("");
  const [confirming, setConfirming] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [betaAccepted, setBetaAccepted] = useState(false);
  const [billing, setBilling] = useState(null);
  const [paymentFlow, setPaymentFlow] = useState(null);
  const [receipt, setReceipt] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [copied, setCopied] = useState("");
  useFinvaBackHandler(() => {
    if (changing || uploading) return;
    if (paymentFlow) setPaymentFlow(null);
    else setConfirming("");
  }, Boolean(confirming || paymentFlow));

  const currentPlan = user?.subscription?.plan || "free";
  const currentPlanInfo = useMemo(
    () => plans.find((plan) => plan.code === currentPlan),
    [plans, currentPlan],
  );
  const receiptSubmittedAt = paymentFlow?.order?.receipt_submitted_at || billing?.order?.receipt_submitted_at;
  const promotionActive = Boolean(billing?.promotion?.active);

  useEffect(() => {
    Promise.all([getPlans(), getBillingCatalog()])
      .then(([availablePlans, billingCatalog]) => {
        setPlans(availablePlans);
        setBilling(billingCatalog);
      })
      .catch((err) => setError(err.message || "No se pudieron cargar los planes."))
      .finally(() => setLoading(false));
  }, []);


  useEffect(() => {
    if (!receiptSubmittedAt) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const next = await getBillingCatalog();
        setBilling(next);
        if (next?.order?.status === "paid" || next?.subscription?.status === "active") {
          const profile = await getMe();
          onUserChange?.(profile);
          setPaymentFlow(null);
          setMessage(`Pago confirmado. Tu plan ${profile?.subscription?.plan?.toUpperCase() || "DINCR"} ya está activo.`);
        } else if (next?.order) {
          setPaymentFlow((current) => current ? { ...current, order: next.order, payment: next.payment } : current);
        }
      } catch {
        // La pantalla conserva el estado y vuelve a intentar sin interrumpir al usuario.
      }
    }, 8000);
    return () => window.clearInterval(timer);
  }, [receiptSubmittedAt, onUserChange]);

  const openPlanDialog = (planCode) => {
    if (planCode === currentPlan) return;
    setConfirming(planCode);
    setMessage("");
    setError("");
    setBetaAccepted(false);
  };

  const copyValue = async (value, field) => {
    if (!value) return;
    const fallbackCopy = () => {
      const input = document.createElement("textarea");
      input.value = value;
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.appendChild(input);
      input.select();
      document.execCommand("copy");
      input.remove();
    };
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(value);
      else fallbackCopy();
    } catch {
      fallbackCopy();
    }
    setCopied(field);
    window.setTimeout(() => setCopied(""), 1800);
  };

  const changePlan = async () => {
    const planCode = confirming;
    if (!planCode || planCode === currentPlan) return;
    if (planCode !== "free" && !promotionActive && !betaAccepted) {
      setError("Debés aceptar el precio mensual normal para continuar.");
      return;
    }
    setChanging(planCode);
    setError("");
    setMessage("");
    try {
      const response = await selectPlan(planCode, planCode === "free" || promotionActive ? false : betaAccepted);
      if (response.status === "payment_pending") {
        setConfirming("");
        setBilling((current) => ({ ...current, order: response.order, payment: response.payment }));
        setPaymentFlow({ order: response.order, payment: response.payment });
        setReceipt(null);
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

  const sendReceipt = async () => {
    if (!receipt || !paymentFlow?.order?.id) {
      setError("Seleccioná la imagen o PDF del comprobante.");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const response = await uploadPaymentReceipt(paymentFlow.order.id, receipt);
      const nextFlow = { ...paymentFlow, order: response.order };
      setPaymentFlow(nextFlow);
      setBilling((current) => ({ ...current, order: response.order }));
      setMessage("");
    } catch (err) {
      setError(err.message || "No se pudo subir el comprobante.");
    } finally {
      setUploading(false);
    }
  };

  const chooseNativeReceipt = async () => {
    setError("");
    try {
      const file = await pickNativeReceipt();
      if (file) setReceipt(file);
    } catch (err) {
      if (!String(err?.message || "").toLowerCase().includes("cancel")) {
        setError(err.message || "No pudimos abrir el comprobante.");
      }
    }
  };

  const pendingOrder = billing?.order?.status === "payment_pending" ? billing.order : null;

  return (
    <section className="mobile-page settings-page">
      <div className="mobile-page-heading">
        <p className="eyebrow">{tx("Cuenta","Account")}</p>
        <h1>{tx("Mi DINCR","My DINCR")}</h1>
        <span>{tx("Administrá tu perfil y el plan que querés probar.", "Manage your profile and the plan you want to try.")}</span>
      </div>

      <div className="account-card">
        <div>
          <strong>{user?.display_name || "Usuario"}</strong>
          <small>{user?.email}</small>
        </div>
        <span className="role-pill">{user?.role}</span>
      </div>

      <AccountSecurity user={user} />

      <AppLockSettings userId={user?.id} />

      <AppearanceSelector />

      <article className="account-card">
        <div><strong>{tx("Información legal","Legal information")}</strong><small>{tx("Consultá los documentos vigentes cuando querás.", "Review the current documents whenever you want.")}</small></div>
        <span><a href="/terms" target="_blank" rel="noreferrer">{tx("Términos","Terms")}</a> · <a href="/privacy" target="_blank" rel="noreferrer">{tx("Privacidad","Privacy")}</a></span>
      </article>

      <div className="section-heading compact">
        <div>
          <p className="eyebrow">{tx("Suscripción","Subscription")}</p>
          <h2>{tx("Tu plan actual","Your current plan")}</h2>
        </div>
      </div>

      <article className={`current-plan-card plan-${currentPlan}`}>
        <div className="current-plan-icon">
          {currentPlan === "vip" ? <Crown size={24} /> : currentPlan === "basic" ? <Sparkles size={24} /> : <WalletCards size={24} />}
        </div>
        <div className="current-plan-copy">
          <strong>{currentPlanInfo?.name || currentPlan.toUpperCase()}</strong>
          <span>{currentPlanInfo?.tagline || "Plan personal DINCR"}</span>
        </div>
        <span className="plan-status-pill">{tx("Actual","Current")}</span>
      </article>

      <div className="section-heading compact plan-change-heading">
        <div>
          <p className="eyebrow">{tx("Desarrollo", "Development")}</p>
          <h2>{tx("Cambiar de plan","Change plan")}</h2>
          <span>{promotionActive ? "Basic y VIP están gratis hasta el 31 de diciembre de 2026. No habrá cobro automático." : "Basic y VIP utilizan sus precios normales y se activan al confirmar el SINPE."}</span>
        </div>
      </div>

      {loading ? (
        <div className="mobile-panel"><p>{tx("Cargando planes...","Loading plans...")}</p></div>
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
                  <span className="selected-plan-label"><Check size={16} /> {tx("Seleccionado","Selected")}</span>
                ) : (
                  <button
                    type="button"
                    className="change-plan-button"
                    disabled={Boolean(changing)}
                    onClick={() => openPlanDialog(plan.code)}
                  >
                    <>{tx("Elegir","Choose")} <ChevronRight size={17} /></>
                  </button>
                )}
              </article>
            );
          })}
        </div>
      )}

      {pendingOrder && !paymentFlow && (
        <article className="pending-payment-card">
          <div className="pending-payment-icon"><Clock3 size={21} /></div>
          <div>
            <strong>{tx("Pago", "Payment")} {pendingOrder.plan_code.toUpperCase()} {tx("pendiente", "pending")}</strong>
            <small>{tx("Continuá el SINPE con el código", "Continue the SINPE payment with code")} {pendingOrder.payment_code}.</small>
          </div>
          <button type="button" onClick={() => setPaymentFlow({ order: pendingOrder, payment: billing?.payment })}>{tx("Continuar","Continue")}</button>
        </article>
      )}

      {message && <p className="success-banner">{message}</p>}
      {!confirming && !paymentFlow && error && <p className="onboarding-error">{error}</p>}

      {confirming && confirming !== currentPlan && (() => {
        const selected = plans.find((plan) => plan.code === confirming);
        const SelectedIcon = icons[confirming] || WalletCards;
        return <div className="plan-dialog-backdrop" role="presentation" onMouseDown={(event)=>{if(event.target===event.currentTarget&&!changing)setConfirming("");}}>
          <section className={`plan-dialog plan-${confirming}`} role="dialog" aria-modal="true" aria-labelledby="plan-dialog-title">
            <button className="plan-dialog-close" type="button" aria-label={tx("Cerrar","Close")} disabled={Boolean(changing)} onClick={()=>setConfirming("")}><X size={20}/></button>
            <div className="plan-dialog-icon"><SelectedIcon size={28}/></div>
            <p className="eyebrow">{tx("Confirmar cambio","Confirm change")}</p>
            <h2 id="plan-dialog-title">{tx("Cambiar a", "Switch to")} {selected?.name || confirming.toUpperCase()}</h2>
            <p>{selected?.tagline || "Tu nuevo plan DINCR"}</p>
            {confirming !== "free" && (promotionActive ? <div className="plan-payment-notice"><CheckCircle2 size={19}/><span>{tx(`Este plan estará gratis hasta el 31 de diciembre de 2026. Desde enero su precio normal será ${confirming === "basic" ? "₡2.990" : "₡4.990"}/mes, sin cobro automático.`, `This plan will be free until December 31, 2026. Starting in January, its regular price will be ${confirming === "basic" ? "₡2,990" : "₡4,990"}/month, with no automatic charge.`)}</span></div> : <><div className="plan-payment-notice"><Smartphone size={19}/><span>{tx("Al continuar, DINCR generará un código para el detalle del SINPE. El plan se activa cuando confirmemos el depósito.", "When you continue, DINCR will generate a code for the SINPE payment detail. The plan activates after we confirm the deposit.")}</span></div><label className="beta-consent dialog-consent"><input type="checkbox" checked={betaAccepted} onChange={(e)=>{setBetaAccepted(e.target.checked);setError("");}}/><span>{tx(`Acepto el precio normal de ${confirming === "basic" ? "₡2.990" : "₡4.990"} al mes.`, `I accept the regular price of ${confirming === "basic" ? "₡2,990" : "₡4,990"} per month.`)}</span></label></>)}
            {error && <div className="plan-dialog-error"><AlertTriangle size={18}/><span>{error}</span></div>}
            <div className="plan-dialog-actions"><button type="button" className="plan-dialog-cancel" disabled={Boolean(changing)} onClick={()=>setConfirming("")}>{tx("Cancelar","Cancel")}</button><button type="button" className="plan-dialog-confirm" disabled={Boolean(changing)} onClick={changePlan}>{changing ? tx("Procesando...","Processing...") : `${tx("Confirmar","Confirm")} ${selected?.name || confirming.toUpperCase()}`}</button></div>
          </section>
        </div>;
      })()}

      {paymentFlow && (() => {
        const order = paymentFlow.order;
        const payment = paymentFlow.payment || billing?.payment || {};
        const submitted = Boolean(order?.receipt_submitted_at);
        return <div className="plan-dialog-backdrop" role="presentation">
          <section className={`plan-dialog payment-dialog plan-${order?.plan_code || "basic"}`} role="dialog" aria-modal="true" aria-labelledby="payment-dialog-title">
            <button className="plan-dialog-close" type="button" aria-label={tx("Cerrar","Close")} disabled={uploading} onClick={()=>{setPaymentFlow(null);setReceipt(null);setError("");}}><X size={20}/></button>
            <div className="plan-dialog-icon"><Smartphone size={26}/></div>
            <p className="eyebrow">{tx("Pago mensual por SINPE","Monthly payment by SINPE")}</p>
            <h2 id="payment-dialog-title">{tx("Activar", "Activate")} {order?.plan_code?.toUpperCase()}</h2>
            {!submitted ? <>
              <p>{tx("Realizá el SINPE con estos datos. El código debe ir completo en el detalle del pago.", "Make the SINPE payment using these details. Include the full code in the payment description.")}</p>
              <div className="sinpe-payment-data">
                <div><span>{tx("Monto exacto","Exact amount")}</span><strong>₡{Number(order?.amount || 0).toLocaleString(localeTag(language))}</strong></div>
                <div><span>{tx("Número SINPE","SINPE number")}</span><strong>{payment.phone || "Pendiente de configurar"}</strong>{payment.phone&&<button type="button" onClick={()=>copyValue(payment.phone,"phone")}><Copy size={16}/>{copied==="phone"?tx("Copiado","Copied"):tx("Copiar","Copy")}</button>}</div>
                {payment.recipient&&<div><span>{tx("Destinatario","Recipient")}</span><strong>{payment.recipient}</strong></div>}
                <div className="payment-code-row"><span>{tx("Código para el detalle","Payment detail code")}</span><strong>{order?.payment_code}</strong><button type="button" onClick={()=>copyValue(order?.payment_code,"code")}><Copy size={16}/>{copied==="code"?tx("Copiado","Copied"):tx("Copiar código","Copy code")}</button></div>
              </div>
              <small className="payment-expiry-note">{tx("Código válido hasta", "Code valid until")} {order?.code_expires_at ? new Date(order.code_expires_at).toLocaleTimeString(localeTag(language), { hour: "2-digit", minute: "2-digit" }) : tx("dentro de 2 horas", "within 2 hours")}.</small>
              {!payment.phone&&<div className="plan-dialog-error"><AlertTriangle size={18}/><span>{tx("El número SINPE todavía no está configurado. No realicés el pago hasta que aparezca.", "The SINPE number has not been configured yet. Do not make the payment until it appears.")}</span></div>}
              <div className="receipt-upload-field">
                <Upload size={19}/>
                <span>{receipt ? `Listo: ${receipt.name}` : "Seleccioná una imagen o PDF"}</span>
              </div>
              {hasNativeReceiptPicker
                ? <button className="native-receipt-picker-button" type="button" onClick={chooseNativeReceipt}>{receipt ? tx("Cambiar comprobante","Change receipt") : tx("Abrir archivos del teléfono","Open phone files")}</button>
                : <input className="native-receipt-input" type="file" accept="image/*,.pdf,application/pdf" onChange={(event)=>{try{setReceipt(receiptFromWebInput(event.currentTarget));setError("");}catch(err){setReceipt(null);setError(err.message);}}}/>
              }
              {error&&<div className="plan-dialog-error"><AlertTriangle size={18}/><span>{error}</span></div>}
              <button className="payment-submit-button" type="button" disabled={uploading||!receipt||!payment.phone} onClick={sendReceipt}>{uploading?tx("Subiendo...","Uploading..."):tx("Enviar comprobante","Send receipt")}</button>
            </> : <div className="payment-waiting-state">
              <CheckCircle2 size={34}/>
              <strong>{tx("Comprobante recibido","Receipt received")}</strong>
              <p>{tx("DINCR está esperando la confirmación del BAC. Cuando coincidan el código y el monto, tu plan se activará automáticamente.", "DINCR is waiting for BAC confirmation. When the code and amount match, your plan will activate automatically.")}</p>
              <small>{tx("Podés cerrar esta pantalla; también volveremos a comprobarlo cuando abras la app.", "You can close this screen; we will check again when you open the app.")}</small>
            </div>}
          </section>
        </div>;
      })()}

      <AccountActions onLogout={onLogout} variant={currentPlan} />
    </section>
  );
}
