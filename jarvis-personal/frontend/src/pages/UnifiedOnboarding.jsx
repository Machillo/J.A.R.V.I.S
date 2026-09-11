import { useEffect, useState } from "react";
import { AlertTriangle, Check, CheckCircle2, ChevronDown, ChevronUp, Copy, Crown, LogOut, Smartphone, Sparkles, Upload, WalletCards } from "lucide-react";
import { completeOnboarding, getBillingCatalog, getOnboarding, getPlans, selectPlan, uploadPaymentReceipt } from "../services/jarvisApi";
import { supabase } from "../lib/supabase";

const iconMap = { free: WalletCards, basic: Sparkles, vip: Crown };
const label = (p) => p === "free" ? "Gratis" : p?.toUpperCase();
const rank = { free: 1, basic: 2, vip: 3 };

const EMPTY_FORM = {
  income_type: "fixed", fixed_monthly_salary: "", hourly_rate: "", hours_per_day: "8",
  work_days_per_week: "5", pay_frequency: "monthly", payday_note: "",
  essential_monthly_expenses: "", liquid_savings: "", emergency_fund_target: "",
  strategy_preference: "balanced", discretionary_monthly_minimum: "",
};

const valueOrEmpty = (v) => v === null || v === undefined ? "" : String(v);

export default function UnifiedOnboarding({ user, onComplete }) {
  const [profile, setProfile] = useState(user);
  const [plans, setPlans] = useState([]);
  const [financialProfile, setFinancialProfile] = useState(null);
  const [completedLevel, setCompletedLevel] = useState(user?.onboarding_level || null);
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
  const [form, setForm] = useState(EMPTY_FORM);

  const hydrate = (data) => {
    const fp = data?.financial_profile;
    const p = data?.profile;
    if (p) {
      setProfile(p);
      setCompletedLevel(p.onboarding_level || null);
    }
    if (!fp) return;
    setFinancialProfile(fp);
    setForm({
      income_type: fp.income_type || "fixed",
      fixed_monthly_salary: valueOrEmpty(fp.fixed_monthly_salary),
      hourly_rate: valueOrEmpty(fp.hourly_rate),
      hours_per_day: valueOrEmpty(fp.hours_per_day ?? 8),
      work_days_per_week: valueOrEmpty(fp.work_days_per_week ?? 5),
      pay_frequency: fp.pay_frequency || "monthly",
      payday_note: fp.payday_note || "",
      essential_monthly_expenses: valueOrEmpty(fp.essential_monthly_expenses),
      liquid_savings: valueOrEmpty(fp.liquid_savings),
      emergency_fund_target: valueOrEmpty(fp.emergency_fund_target),
      strategy_preference: fp.strategy_preference || "balanced",
      discretionary_monthly_minimum: valueOrEmpty(fp.discretionary_monthly_minimum),
    });
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

  useEffect(() => {
    if (!receiptSubmittedAt) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const next = await getBillingCatalog();
        setBilling(next);
        if (next?.order?.status === "paid" || next?.subscription?.status === "active") {
          const onboarding = await getOnboarding();
          hydrate(onboarding);
          setPaymentFlow(null);
        } else if (next?.order) {
          setPaymentFlow((current) => current ? { ...current, order: next.order, payment: next.payment } : current);
        }
      } catch {
        // Keep the waiting screen and retry without interrupting the user.
      }
    }, 8000);
    return () => window.clearInterval(timer);
  }, [receiptSubmittedAt]);

  const plan = profile?.subscription?.plan || "free";
  const completedRank = rank[completedLevel] || 0;
  const numberOrNull = (v) => v === "" ? null : Number(v);
  const baseAlreadyKnown = completedRank >= rank.free && !!financialProfile;
  const basicAlreadyKnown = completedRank >= rank.basic && !!financialProfile;
  const vipAlreadyKnown = completedRank >= rank.vip && !!financialProfile;

  const choosePlan = async (code) => {
    setSaving(true); setError("");
    try {
      const result = await selectPlan(code, code === "free" ? false : betaAccepted);
      if (result.status === "payment_pending") {
        setBilling((current) => ({ ...current, order: result.order, payment: result.payment }));
        setPaymentFlow({ order: result.order, payment: result.payment });
        setReceipt(null);
        return;
      }
      setProfile(result.profile);
      const onboarding = await getOnboarding();
      hydrate(onboarding);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
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

  const submit = async (e) => {
    e.preventDefault(); setSaving(true); setError("");
    try {
      const result = await completeOnboarding({
        income_type: form.income_type,
        fixed_monthly_salary: form.income_type === "fixed" ? numberOrNull(form.fixed_monthly_salary) : null,
        hourly_rate: form.income_type === "hourly" ? numberOrNull(form.hourly_rate) : null,
        hours_per_day: form.income_type === "hourly" ? numberOrNull(form.hours_per_day) : null,
        work_days_per_week: Number(form.work_days_per_week),
        pay_frequency: form.pay_frequency,
        payday_note: form.payday_note || null,
        essential_monthly_expenses: numberOrNull(form.essential_monthly_expenses),
        liquid_savings: numberOrNull(form.liquid_savings),
        emergency_fund_target: numberOrNull(form.emergency_fund_target),
        strategy_preference: plan === "vip" ? form.strategy_preference : (financialProfile?.strategy_preference || null),
        discretionary_monthly_minimum: numberOrNull(form.discretionary_monthly_minimum),
      });
      onComplete(result.profile);
    } catch (e2) { setError(e2.message); }
    finally { setSaving(false); }
  };

  if (!profile?.plan_selected && paymentFlow) {
    const order = paymentFlow.order;
    const payment = paymentFlow.payment || billing?.payment || {};
    const submitted = Boolean(order?.receipt_submitted_at);
    return <main className="unified-onboarding-shell">
      <section className="unified-onboarding-card unified-payment-stage">
        <div className="unified-onboarding-top">
          <div><strong>FINVA</strong><small>Activar {order?.plan_code?.toUpperCase()}</small></div>
          {!submitted && <button type="button" onClick={() => { setPaymentFlow(null); setReceipt(null); setError(""); }} disabled={uploading}>Volver</button>}
        </div>
        <div className="unified-payment-heading"><div className="unified-plan-icon"><Smartphone size={24}/></div><div><span className="unified-eyebrow">PAGO BETA POR SINPE</span><h1>{submitted ? "Comprobante recibido" : `Activar ${order?.plan_code?.toUpperCase()}`}</h1></div></div>
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
          <label className="unified-receipt-upload"><Upload size={19}/><span>{receipt?.name || "Seleccionar comprobante"}</span><input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" onChange={(event) => { setReceipt(event.target.files?.[0] || null); setError(""); }}/></label>
          {error && <p className="unified-onboarding-error">{error}</p>}
          <button className="unified-primary" type="button" disabled={uploading || !receipt || !payment.phone} onClick={sendReceipt}>{uploading ? "Subiendo..." : "Enviar comprobante"}</button>
        </> : <div className="unified-payment-waiting"><CheckCircle2 size={38}/><strong>Listo, ya recibimos tu comprobante</strong><p>FINVA está esperando la confirmación. Cuando coincidan el código y el monto, tu plan se activará automáticamente.</p><small>Podés cerrar la app. Al volver, continuaremos verificando el pago.</small></div>}
      </section>
    </main>;
  }

  if (!profile?.plan_selected) return <main className="unified-onboarding-shell">
    <section className="unified-onboarding-card unified-plan-stage">
      <div className="unified-onboarding-top">
        <div><strong>FINVA</strong><small>Elegí tu plan personal</small></div>
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
            <span className="unified-plan-price">{item.code === "free" ? "₡0" : item.code === "basic" ? "₡1.990" : "₡3.990"}<small>{item.code === "free" ? "" : "/mes"}</small></span>
            {expanded ? <ChevronUp size={20}/> : <ChevronDown size={20}/>}
          </button>
          {expanded && <div className="unified-plan-details">
            <ul>{item.features.map(f => <li key={f}><Check size={16}/><span>{f}</span></li>)}</ul>
            {item.code !== "free" && <><small className="beta-price">Precio beta por 3 meses. Luego {item.code === "basic" ? "₡2.990" : "₡5.990"}/mes.</small><div className="unified-payment-preview"><Smartphone size={18}/><span>Al continuar generaremos el código para el detalle del SINPE y podrás subir el comprobante aquí mismo.</span></div><label className="beta-consent"><input type="checkbox" checked={betaAccepted} onChange={(e) => { setBetaAccepted(e.target.checked); setError(""); }}/><span>Acepto el precio beta y entiendo que el plan se activa al confirmar el pago.</span></label></>}
            <button className="unified-plan-button" disabled={saving || (item.code !== "free" && !betaAccepted)} onClick={() => choosePlan(item.code)}>{saving ? "Preparando..." : item.code === "free" ? "Empezar gratis" : `Continuar con ${item.name}`}</button>
          </div>}
        </article>;
      })}</div>}
      {error && <p className="unified-onboarding-error">{error}</p>}
    </section>
  </main>;

  return <main className="unified-onboarding-shell">
    <form className="unified-onboarding-card unified-form-stage" onSubmit={submit}>
      <div className="unified-onboarding-top">
        <div><strong>FINVA</strong><small>Onboarding {label(plan)}</small></div>
        <button type="button" onClick={() => supabase.auth.signOut()}><LogOut size={17}/> Salir</button>
      </div>
      <div className="unified-onboarding-intro">
        <span className="unified-eyebrow">CONFIGURACIÓN INICIAL</span>
        <h1>{completedRank ? "Completemos lo nuevo de tu plan" : "Contame cómo funcionan tus finanzas"}</h1>
        <p>{completedRank ? "Finva conserva lo que ya respondiste. Solo te pedimos la información nueva de este nivel." : "Solo pedimos lo necesario para tu nivel. Después podés afinar todo dentro de Finva."}</p>
      </div>

      {baseAlreadyKnown && <div className="unified-saved-note"><Check size={17}/><span>Ingresos, jornada y frecuencia de pago ya están guardados.</span></div>}

      <div className="unified-form-grid">
        {!baseAlreadyKnown && <>
          <label>Tipo de ingreso<select value={form.income_type} onChange={e=>setForm({...form,income_type:e.target.value})}><option value="fixed">Salario fijo</option><option value="hourly">Por hora</option></select></label>
          {form.income_type === "fixed" ? <label>Salario mensual<input required type="number" min="1" value={form.fixed_monthly_salary} onChange={e=>setForm({...form,fixed_monthly_salary:e.target.value})}/></label> : <><label>Tarifa por hora<input required type="number" min="1" value={form.hourly_rate} onChange={e=>setForm({...form,hourly_rate:e.target.value})}/></label><label>Horas por día<input required type="number" min="0.1" max="24" value={form.hours_per_day} onChange={e=>setForm({...form,hours_per_day:e.target.value})}/></label></>}
          <label>Días por semana<input required type="number" min="1" max="7" value={form.work_days_per_week} onChange={e=>setForm({...form,work_days_per_week:e.target.value})}/></label>
          <label>Frecuencia de pago<select value={form.pay_frequency} onChange={e=>setForm({...form,pay_frequency:e.target.value})}><option value="weekly">Semanal</option><option value="biweekly">Quincenal</option><option value="monthly">Mensual</option></select></label>
          <label>Días de pago<input value={form.payday_note} placeholder="Ej. cada jueves" onChange={e=>setForm({...form,payday_note:e.target.value})}/></label>
        </>}

        {plan !== "free" && !basicAlreadyKnown && <>
          <label>Gastos esenciales mensuales<input required type="number" min="0" value={form.essential_monthly_expenses} onChange={e=>setForm({...form,essential_monthly_expenses:e.target.value})}/></label>
          <label>Ahorro líquido<input type="number" min="0" value={form.liquid_savings} onChange={e=>setForm({...form,liquid_savings:e.target.value})}/></label>
        </>}

        {plan === "vip" && !vipAlreadyKnown && <>
          <label>Meta fondo emergencia<input type="number" min="0" value={form.emergency_fund_target} onChange={e=>setForm({...form,emergency_fund_target:e.target.value})}/></label>
          <label>Prioridad<select value={form.strategy_preference} onChange={e=>setForm({...form,strategy_preference:e.target.value})}><option value="balanced">Equilibrado</option><option value="debt">Salir de deudas</option><option value="emergency">Seguridad</option><option value="goals">Metas</option></select></label>
          <label>Mínimo mensual para vos<input type="number" min="0" value={form.discretionary_monthly_minimum} onChange={e=>setForm({...form,discretionary_monthly_minimum:e.target.value})}/></label>
        </>}
      </div>

      <button className="unified-primary" disabled={saving}>{saving ? "Guardando..." : `Activar ${label(plan)}`}</button>
      {error && <p className="unified-onboarding-error">{error}</p>}
    </form>
  </main>;
}
