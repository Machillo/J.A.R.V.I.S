import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, CheckCircle2, ChevronDown, ChevronUp, Copy, Crown, LogOut, Smartphone, Sparkles, Upload, WalletCards } from "lucide-react";
import { getBillingCatalog, getMe, getOnboarding, getPlans, selectPlan, uploadPaymentReceipt } from "../services/jarvisApi";
import { supabase } from "../lib/supabase";
import { hasNativeReceiptPicker, pickNativeReceipt, receiptFromWebInput } from "../lib/receiptPicker";
import { markFinvaWelcomeSeen, shouldShowFinvaWelcome } from "../lib/firstRunExperience";
import FinvaWelcomeStory from "./FinvaWelcomeStory";

const iconMap = { free: WalletCards, basic: Sparkles, vip: Crown };

export default function FinvaOnboarding({ user, onComplete }) {
  const completedRef = useRef(false);
  const [profile, setProfile] = useState(user);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [betaAccepted, setBetaAccepted] = useState(false);
  const [expandedPlan, setExpandedPlan] = useState("");
  const [billing, setBilling] = useState(null);
  const [paymentFlow, setPaymentFlow] = useState(null);
  const [receipt, setReceipt] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [copied, setCopied] = useState("");
  const [showWelcome, setShowWelcome] = useState(() => shouldShowFinvaWelcome(user?.id));

  const hydrate = (data) => {
    const p = data?.profile;
    if (p) setProfile(p);
  };

  useEffect(() => {
    Promise.all([getPlans(), getOnboarding(), getBillingCatalog()])
      .then(([planRows, onboarding, billingCatalog]) => {
        setPlans(planRows);
        hydrate(onboarding);
        setBilling(billingCatalog);
        if (!onboarding?.profile?.plan_selected && billingCatalog?.order?.status === "payment_pending") {
          setPaymentFlow({ order: billingCatalog.order, payment: billingCatalog.payment });
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const receiptSubmittedAt = paymentFlow?.order?.receipt_submitted_at;
  const promotionActive = Boolean(billing?.promotion?.active);

  useEffect(() => {
    if (!receiptSubmittedAt) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const next = await getBillingCatalog();
        setBilling(next);
        if (next?.order?.status === "paid" || next?.subscription?.status === "active") {
          const activeProfile = await getMe();
          if (activeProfile?.plan_selected) {
            setProfile(activeProfile);
            setPaymentFlow(null);
          }
        } else if (next?.order) {
          setPaymentFlow((current) => current ? { ...current, order: next.order, payment: next.payment } : current);
        }
      } catch {
        // Keep the waiting screen and retry without interrupting the user.
      }
    }, 8000);
    return () => window.clearInterval(timer);
  }, [receiptSubmittedAt]);

  useEffect(() => {
    if (profile?.plan_selected && !completedRef.current) {
      completedRef.current = true;
      onComplete(profile);
    }
  }, [profile, onComplete]);

  const choosePlan = async (code) => {
    setSaving(true); setError("");
    try {
      const result = await selectPlan(code, code === "free" || promotionActive ? false : betaAccepted);
      if (result.status === "payment_pending") {
        setBilling((current) => ({ ...current, order: result.order, payment: result.payment }));
        setPaymentFlow({ order: result.order, payment: result.payment });
        setReceipt(null);
        return;
      }
      // The plan mutation already returns the updated identity. A second
      // request here could fail after activation and strand the onboarding UI.
      const activeProfile = result.profile?.plan_selected ? result.profile : await getMe();
      if (!activeProfile?.plan_selected) throw new Error("El plan se activó, pero no pudimos actualizar tu cuenta. Intentá de nuevo.");
      setProfile(activeProfile);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  const finishWelcome = () => {
    markFinvaWelcomeSeen(user?.id);
    setShowWelcome(false);
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
    } catch { fallbackCopy(); }
    setCopied(field);
    window.setTimeout(() => setCopied(""), 1800);
  };

  const sendReceipt = async () => {
    if (!receipt || !paymentFlow?.order?.id) {
      setError("Seleccioná la imagen o PDF del comprobante.");
      return;
    }
    setUploading(true); setError("");
    try {
      const response = await uploadPaymentReceipt(paymentFlow.order.id, receipt);
      setPaymentFlow((current) => ({ ...current, order: response.order }));
      setBilling((current) => ({ ...current, order: response.order }));
    } catch (e) { setError(e.message || "No se pudo subir el comprobante."); }
    finally { setUploading(false); }
  };

  const chooseNativeReceipt = async () => {
    setError("");
    try {
      const file = await pickNativeReceipt();
      if (file) setReceipt(file);
    } catch (e) {
      if (!String(e?.message || "").toLowerCase().includes("cancel")) {
        setError(e.message || "No pudimos abrir el comprobante.");
      }
    }
  };

  if (!profile?.plan_selected && showWelcome) {
    return <FinvaWelcomeStory onFinish={finishWelcome} />;
  }

  if (!profile?.plan_selected && paymentFlow) {
    const order = paymentFlow.order;
    const payment = paymentFlow.payment || billing?.payment || {};
    const submitted = Boolean(order?.receipt_submitted_at);
    return <main className="unified-onboarding-shell">
      <section className="unified-onboarding-card unified-payment-stage">
        <div className="unified-onboarding-top">
          <div><strong>DINCR</strong><small>Activar {order?.plan_code?.toUpperCase()}</small></div>
          {!submitted && <button type="button" onClick={() => { setPaymentFlow(null); setReceipt(null); setError(""); }} disabled={uploading}>Volver</button>}
        </div>
        <div className="unified-payment-heading"><div className="unified-plan-icon"><Smartphone size={24}/></div><div><span className="unified-eyebrow">PAGO MENSUAL POR SINPE</span><h1>{submitted ? "Comprobante recibido" : `Activar ${order?.plan_code?.toUpperCase()}`}</h1></div></div>
        {!submitted ? <>
          <p className="unified-payment-description">Hacé el SINPE con el monto exacto y pegá el código completo en el detalle. Después subí el comprobante.</p>
          <div className="unified-payment-data">
            <div><span>Monto exacto</span><strong>₡{Number(order?.amount || 0).toLocaleString("es-CR")}</strong></div>
            <div><span>Número SINPE</span><strong>{payment.phone || "Pendiente de configurar"}</strong>{payment.phone && <button type="button" onClick={() => copyValue(payment.phone, "phone")}><Copy size={16}/>{copied === "phone" ? "Copiado" : "Copiar"}</button>}</div>
            {payment.recipient && <div><span>Destinatario</span><strong>{payment.recipient}</strong></div>}
            <div className="unified-payment-code"><span>Código para el detalle</span><strong>{order?.payment_code}</strong><button type="button" onClick={() => copyValue(order?.payment_code, "code")}><Copy size={16}/>{copied === "code" ? "Copiado" : "Copiar código"}</button></div>
          </div>
          <small className="unified-payment-expiry">Código válido hasta {order?.code_expires_at ? new Date(order.code_expires_at).toLocaleTimeString("es-CR", { hour: "2-digit", minute: "2-digit" }) : "dentro de 2 horas"}.</small>
          {!payment.phone && <div className="unified-inline-error"><AlertTriangle size={18}/><span>El número SINPE todavía no está configurado. No realicés el pago hasta que aparezca.</span></div>}
          <div className="unified-receipt-upload"><Upload size={19}/><span>{receipt ? `Listo: ${receipt.name}` : "Seleccioná una imagen o PDF"}</span></div>
          {hasNativeReceiptPicker
            ? <button className="unified-native-picker-button" type="button" onClick={chooseNativeReceipt}>{receipt ? "Cambiar comprobante" : "Abrir archivos del teléfono"}</button>
            : <input className="unified-native-file-input" type="file" accept="image/*,.pdf,application/pdf" onChange={(event) => { try { setReceipt(receiptFromWebInput(event.currentTarget)); setError(""); } catch (e) { setReceipt(null); setError(e.message); } }}/>
          }
          {error && <p className="unified-onboarding-error">{error}</p>}
          <button className="unified-primary" type="button" disabled={uploading || !receipt || !payment.phone} onClick={sendReceipt}>{uploading ? "Subiendo..." : "Enviar comprobante"}</button>
        </> : <div className="unified-payment-waiting"><CheckCircle2 size={38}/><strong>Listo, ya recibimos tu comprobante</strong><p>DINCR está esperando la confirmación. Cuando coincidan el código y el monto, tu plan se activará automáticamente.</p><small>Podés cerrar la app. Al volver, continuaremos verificando el pago.</small></div>}
      </section>
    </main>;
  }

  if (!profile?.plan_selected) return <main className="unified-onboarding-shell">
    <section className="unified-onboarding-card unified-plan-stage">
      <div className="unified-onboarding-top">
        <div><strong>DINCR</strong><small>Elegí tu plan personal</small></div>
        <button type="button" onClick={() => supabase.auth.signOut()}><LogOut size={17}/> Salir</button>
      </div>
      <div className="unified-onboarding-intro">
        <span className="unified-eyebrow">BIENVENIDO</span>
        <h1>Tu espacio financiero empieza acá</h1>
        <p>Cada cuenta recibe su propio espacio aislado. Podés empezar gratis y cambiar de plan cuando corresponda.</p>
      </div>
      {loading ? <div className="unified-loading"><div className="unified-spinner"/><span>Preparando tus planes...</span></div> : <div className="unified-plan-list">{plans.map((item) => {
        const Icon = iconMap[item.code] || WalletCards;
        const expanded = expandedPlan === item.code;
        return <article key={item.code} className={`unified-plan-card ${item.code} ${expanded ? "is-expanded" : ""}`}>
          <button type="button" className="unified-plan-summary" aria-expanded={expanded} onClick={() => { setExpandedPlan(expanded ? "" : item.code); setBetaAccepted(false); setError(""); }}>
            <span className="unified-plan-icon"><Icon size={22}/></span>
            <span className="unified-plan-copy"><span>{item.code === "free" ? "EMPEZÁ HOY" : item.code === "basic" ? "MÁS CONTROL" : "EXPERIENCIA COMPLETA"}</span><strong>{item.name}</strong><small>{item.tagline}</small></span>
            <span className="unified-plan-price">{item.code === "free" || promotionActive ? "₡0" : `₡${Number(item.regular_price_crc || 0).toLocaleString("es-CR")}`}<small>{item.code === "free" ? "" : promotionActive ? " hasta 31 dic" : "/mes"}</small></span>
            {expanded ? <ChevronUp size={20}/> : <ChevronDown size={20}/>}
          </button>
          {expanded && <div className="unified-plan-details">
            <ul>{item.features.map(f => <li key={f}><Check size={16}/><span>{f}</span></li>)}</ul>
            {item.code !== "free" && (promotionActive ? <div className="unified-payment-preview"><CheckCircle2 size={18}/><span>Acceso gratuito hasta el 31 de diciembre de 2026. Después costará ₡{Number(item.regular_price_crc || 0).toLocaleString("es-CR")}/mes y no se cobrará automáticamente.</span></div> : <><small className="beta-price">Precio normal: ₡{Number(item.regular_price_crc || 0).toLocaleString("es-CR")}/mes.</small><div className="unified-payment-preview"><Smartphone size={18}/><span>Al continuar generaremos el código para el detalle del SINPE y podrás subir el comprobante aquí mismo.</span></div><label className="beta-consent"><input type="checkbox" checked={betaAccepted} onChange={(e) => { setBetaAccepted(e.target.checked); setError(""); }}/><span>Acepto el precio normal de ₡{Number(item.regular_price_crc || 0).toLocaleString("es-CR")} al mes y entiendo que el plan se activa al confirmar el pago.</span></label></>)}
            <button className="unified-plan-button" disabled={saving || (item.code !== "free" && !promotionActive && !betaAccepted)} onClick={() => choosePlan(item.code)}>{saving ? "Preparando..." : item.code === "free" ? "Empezar gratis" : promotionActive ? `Activar ${item.name} gratis` : `Continuar con ${item.name}`}</button>
          </div>}
        </article>;
      })}</div>}
      {error && <p className="unified-onboarding-error">{error}</p>}
    </section>
  </main>;

  return <main className="unified-onboarding-shell">
    <section className="unified-onboarding-card unified-loading">
      <div className="unified-spinner"/>
      <span>Abriendo DINCR…</span>
    </section>
  </main>;
}
