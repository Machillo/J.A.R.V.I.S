import { AlertTriangle, Check, CheckCircle2, ChevronRight, Clock3, Copy, Crown, Smartphone, Sparkles, Upload, WalletCards, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getBillingCatalog, getMe, getPlans, selectPlan, uploadPaymentReceipt } from "../services/jarvisApi";
import AccountSecurity from "../components/AccountSecurity";
import { hasNativeReceiptPicker, pickNativeReceipt, receiptFromWebInput } from "../../lib/receiptPicker";

const icons = { free: WalletCards, basic: Sparkles, vip: Crown };

export default function Settings({ user, onUserChange }) {
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

  const currentPlan = user?.subscription?.plan || "free";
  const currentPlanInfo = useMemo(
    () => plans.find((plan) => plan.code === currentPlan),
    [plans, currentPlan],
  );
  const receiptSubmittedAt = paymentFlow?.order?.receipt_submitted_at || billing?.order?.receipt_submitted_at;

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
          setMessage(`Pago confirmado. Tu plan ${profile?.subscription?.plan?.toUpperCase() || "FINVA"} ya está activo.`);
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
          <span>Durante la beta, Basic y VIP se pagan por SINPE Móvil y se activan al confirmar el depósito.</span>
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

      {pendingOrder && !paymentFlow && (
        <article className="pending-payment-card">
          <div className="pending-payment-icon"><Clock3 size={21} /></div>
          <div>
            <strong>Pago {pendingOrder.plan_code.toUpperCase()} pendiente</strong>
            <small>Continuá el SINPE con el código {pendingOrder.payment_code}.</small>
          </div>
          <button type="button" onClick={() => setPaymentFlow({ order: pendingOrder, payment: billing?.payment })}>Continuar</button>
        </article>
      )}

      {message && <p className="success-banner">{message}</p>}
      {!confirming && !paymentFlow && error && <p className="onboarding-error">{error}</p>}

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
            {confirming !== "free" && <div className="plan-payment-notice"><Smartphone size={19}/><span>Al continuar, FINVA generará un código para pegar en el detalle del SINPE. Después subís el comprobante y el plan se activa cuando confirmemos el depósito.</span></div>}
            {confirming !== "free" && <label className="beta-consent dialog-consent"><input type="checkbox" checked={betaAccepted} onChange={(e)=>{setBetaAccepted(e.target.checked);setError("");}}/><span>Acepto el precio beta de {confirming === "basic" ? "₡1.990" : "₡3.990"} al mes por 3 meses; luego {confirming === "basic" ? "₡2.990" : "₡5.990"}.</span></label>}
            {error && <div className="plan-dialog-error"><AlertTriangle size={18}/><span>{error}</span></div>}
            <div className="plan-dialog-actions"><button type="button" className="plan-dialog-cancel" disabled={Boolean(changing)} onClick={()=>setConfirming("")}>Cancelar</button><button type="button" className="plan-dialog-confirm" disabled={Boolean(changing)} onClick={changePlan}>{changing ? "Procesando..." : `Confirmar ${selected?.name || confirming.toUpperCase()}`}</button></div>
          </section>
        </div>;
      })()}

      {paymentFlow && (() => {
        const order = paymentFlow.order;
        const payment = paymentFlow.payment || billing?.payment || {};
        const submitted = Boolean(order?.receipt_submitted_at);
        return <div className="plan-dialog-backdrop" role="presentation">
          <section className={`plan-dialog payment-dialog plan-${order?.plan_code || "basic"}`} role="dialog" aria-modal="true" aria-labelledby="payment-dialog-title">
            <button className="plan-dialog-close" type="button" aria-label="Cerrar" disabled={uploading} onClick={()=>{setPaymentFlow(null);setReceipt(null);setError("");}}><X size={20}/></button>
            <div className="plan-dialog-icon"><Smartphone size={26}/></div>
            <p className="eyebrow">Pago beta por SINPE</p>
            <h2 id="payment-dialog-title">Activar {order?.plan_code?.toUpperCase()}</h2>
            {!submitted ? <>
              <p>Realizá el SINPE con estos datos. El código debe ir completo en el detalle del pago.</p>
              <div className="sinpe-payment-data">
                <div><span>Monto exacto</span><strong>₡{Number(order?.amount || 0).toLocaleString("es-CR")}</strong></div>
                <div><span>Número SINPE</span><strong>{payment.phone || "Pendiente de configurar"}</strong>{payment.phone&&<button type="button" onClick={()=>copyValue(payment.phone,"phone")}><Copy size={16}/>{copied==="phone"?"Copiado":"Copiar"}</button>}</div>
                {payment.recipient&&<div><span>Destinatario</span><strong>{payment.recipient}</strong></div>}
                <div className="payment-code-row"><span>Código para el detalle</span><strong>{order?.payment_code}</strong><button type="button" onClick={()=>copyValue(order?.payment_code,"code")}><Copy size={16}/>{copied==="code"?"Copiado":"Copiar código"}</button></div>
              </div>
              <small className="payment-expiry-note">Código válido hasta {order?.code_expires_at ? new Date(order.code_expires_at).toLocaleTimeString("es-CR", { hour: "2-digit", minute: "2-digit" }) : "dentro de 2 horas"}.</small>
              {!payment.phone&&<div className="plan-dialog-error"><AlertTriangle size={18}/><span>El número SINPE todavía no está configurado. No realicés el pago hasta que aparezca.</span></div>}
              <div className="receipt-upload-field">
                <Upload size={19}/>
                <span>{receipt ? `Listo: ${receipt.name}` : "Seleccioná una imagen o PDF"}</span>
              </div>
              {hasNativeReceiptPicker
                ? <button className="native-receipt-picker-button" type="button" onClick={chooseNativeReceipt}>{receipt ? "Cambiar comprobante" : "Abrir archivos del teléfono"}</button>
                : <input className="native-receipt-input" type="file" accept="image/*,.pdf,application/pdf" onChange={(event)=>{try{setReceipt(receiptFromWebInput(event.currentTarget));setError("");}catch(err){setReceipt(null);setError(err.message);}}}/>
              }
              {error&&<div className="plan-dialog-error"><AlertTriangle size={18}/><span>{error}</span></div>}
              <button className="payment-submit-button" type="button" disabled={uploading||!receipt||!payment.phone} onClick={sendReceipt}>{uploading?"Subiendo...":"Enviar comprobante"}</button>
            </> : <div className="payment-waiting-state">
              <CheckCircle2 size={34}/>
              <strong>Comprobante recibido</strong>
              <p>FINVA está esperando la confirmación del BAC. Cuando coincidan el código y el monto, tu plan se activará automáticamente.</p>
              <small>Podés cerrar esta pantalla; también volveremos a comprobarlo cuando abras la app.</small>
            </div>}
          </section>
        </div>;
      })()}
    </section>
  );
}
