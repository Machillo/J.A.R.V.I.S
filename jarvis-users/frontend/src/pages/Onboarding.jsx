import { useEffect, useMemo, useState } from "react";
import {
  BriefcaseBusiness,
  ChevronLeft,
  ChevronRight,
  Crosshair,
  Flag,
  LogOut,
  PiggyBank,
  Plus,
  ShieldCheck,
  Trash2,
  WalletCards,
} from "lucide-react";
import { completeOnboarding, getOnboarding } from "../services/jarvisApi";
import { supabase } from "../lib/supabase";

const PLAN_STEPS = { free: 2, basic: 5, vip: 7 };
const LEVEL_STEP = { none: 1, free: 3, basic: 6, vip: 8 };

const emptyDebt = () => ({
  name: "",
  remaining_amount: "",
  total_amount: "",
  monthly_payment: "",
  interest_rate: "",
  payment_day: "",
});

const emptyGoal = () => ({
  name: "",
  target_amount: "",
  current_amount: "",
  target_date: "",
  priority: "medium",
});

const numberOrNull = (value) => (value === "" || value === null || value === undefined ? null : Number(value));
const planLabel = (plan) => (plan === "free" ? "Gratis" : plan === "basic" ? "Basic" : "VIP");

export default function Onboarding({ user, onComplete }) {
  const plan = user?.subscription?.plan || "free";
  const totalSteps = PLAN_STEPS[plan] || 2;
  const previousLevel = user?.onboarding_level || "none";
  const initialStep = Math.min(LEVEL_STEP[previousLevel] || 1, totalSteps);

  const [step, setStep] = useState(initialStep);
  const [loading, setLoading] = useState(true);
  const [existingDebts, setExistingDebts] = useState([]);
  const [existingGoals, setExistingGoals] = useState([]);
  const [form, setForm] = useState({
    income_type: "fixed",
    fixed_monthly_salary: "",
    hourly_rate: "",
    work_days_per_week: 5,
    hours_per_day: 8,
    pay_frequency: "biweekly",
    payday_note: "",
    essential_monthly_expenses: "",
    liquid_savings: "",
    emergency_fund_target: "",
    has_debts: null,
    debts: [],
    has_goals: null,
    goals: [],
    strategy_preference: "balanced",
    discretionary_monthly_minimum: "",
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getOnboarding()
      .then((data) => {
        const fp = data?.financial_profile || {};
        const debts = data?.debts || [];
        const goals = data?.goals || [];
        setExistingDebts(debts);
        setExistingGoals(goals);
        setForm((current) => ({
          ...current,
          income_type: fp.income_type || current.income_type,
          fixed_monthly_salary: fp.fixed_monthly_salary ?? current.fixed_monthly_salary,
          hourly_rate: fp.hourly_rate ?? current.hourly_rate,
          work_days_per_week: fp.work_days_per_week ?? current.work_days_per_week,
          hours_per_day: fp.hours_per_day ?? current.hours_per_day,
          pay_frequency: fp.pay_frequency || current.pay_frequency,
          payday_note: fp.payday_note || "",
          essential_monthly_expenses: fp.essential_monthly_expenses ?? "",
          liquid_savings: fp.liquid_savings ?? "",
          emergency_fund_target: fp.emergency_fund_target ?? "",
          strategy_preference: fp.strategy_preference || "balanced",
          discretionary_monthly_minimum: fp.discretionary_monthly_minimum ?? "",
          has_debts: debts.length ? true : current.has_debts,
          has_goals: goals.length ? true : current.has_goals,
        }));
      })
      .catch((err) => setError(err.message || "No pudimos cargar tu información actual."))
      .finally(() => setLoading(false));
  }, []);

  const content = useMemo(() => {
    const copy = {
      1: ["¿Cómo recibís tus ingresos?", "Esto nos da la base para entender cuánto dinero entra normalmente."],
      2: ["¿Cuándo y cuánto trabajás?", "Solo necesitamos tu rutina de pago; luego podrás corregirla desde tu perfil."],
      3: ["Tu costo de vida actual", "Una aproximación es suficiente. JARVIS la irá refinando con tus movimientos."],
      4: ["Hablemos de tus deudas", "Si no conocés interés, cuota o monto original, podés dejarlos vacíos."],
      5: ["Tu colchón de seguridad", "Esto evita que una estrategia de deuda te deje sin dinero para imprevistos."],
      6: ["¿Qué querés conseguir?", "Agregá solo las metas que hoy sean importantes. Podrás crear más después."],
      7: ["¿Cómo querés que JARVIS priorice?", "No es una decisión permanente; servirá como punto de partida para tu estrategia VIP."],
    };
    return copy[step] || copy[1];
  }, [step]);

  const update = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
    setError("");
  };

  const updateDebt = (index, field, value) => {
    setForm((current) => ({
      ...current,
      debts: current.debts.map((debt, i) => (i === index ? { ...debt, [field]: value } : debt)),
    }));
    setError("");
  };

  const updateGoal = (index, field, value) => {
    setForm((current) => ({
      ...current,
      goals: current.goals.map((goal, i) => (i === index ? { ...goal, [field]: value } : goal)),
    }));
    setError("");
  };

  const validateStep = () => {
    if (step === 1) {
      if (form.income_type === "fixed" && Number(form.fixed_monthly_salary) <= 0) return "Necesitamos tu salario mensual para trabajar con tus números.";
      if (form.income_type === "hourly" && Number(form.hourly_rate) <= 0) return "Necesitamos saber cuánto ganás por hora.";
    }
    if (step === 2) {
      if (Number(form.work_days_per_week) < 1 || Number(form.work_days_per_week) > 7) return "Indicá cuántos días trabajás por semana.";
      if (form.income_type === "hourly" && Number(form.hours_per_day) <= 0) return "Indicá cuántas horas trabajás por día.";
    }
    if (step === 3 && (form.essential_monthly_expenses === "" || Number(form.essential_monthly_expenses) < 0)) {
      return "Indicá aproximadamente cuánto necesitás al mes para tus gastos esenciales. Puede ser 0 si corresponde.";
    }
    if (step === 4) {
      if (form.has_debts === null) return "Decinos si actualmente tenés deudas.";
      if (form.has_debts && existingDebts.length === 0 && form.debts.length === 0) return "Agregá al menos una deuda.";
      for (const debt of form.debts) {
        if (!debt.name.trim() || Number(debt.remaining_amount) <= 0) return "En cada deuda solo son obligatorios el nombre y el saldo pendiente.";
        if (debt.total_amount && Number(debt.remaining_amount) > Number(debt.total_amount)) return "El saldo pendiente no puede superar el monto original.";
      }
    }
    if (step === 5) {
      if (form.liquid_savings === "" || Number(form.liquid_savings) < 0) return "Indicá cuánto ahorro líquido tenés actualmente. Puede ser 0.";
      if (form.emergency_fund_target === "" || Number(form.emergency_fund_target) < 0) return "Indicá cuánto te gustaría tener como fondo de emergencia. Puede ser 0 por ahora.";
    }
    if (step === 6) {
      if (form.has_goals === null) return "Decinos si tenés alguna meta financiera activa.";
      if (form.has_goals && existingGoals.length === 0 && form.goals.length === 0) return "Agregá al menos una meta.";
      for (const goal of form.goals) {
        if (!goal.name.trim() || Number(goal.target_amount) <= 0) return "Cada meta necesita un nombre y un monto objetivo.";
      }
    }
    if (step === 7 && form.discretionary_monthly_minimum === "") return "Indicá cuánto querés reservar como mínimo para tus gastos personales. Puede ser 0.";
    return "";
  };

  const next = () => {
    const problem = validateStep();
    if (problem) return setError(problem);
    setStep((current) => Math.min(totalSteps, current + 1));
  };

  const submit = async () => {
    const problem = validateStep();
    if (problem) return setError(problem);

    setSaving(true);
    setError("");
    try {
      const payload = {
        income_type: form.income_type,
        fixed_monthly_salary: form.income_type === "fixed" ? Number(form.fixed_monthly_salary) : null,
        hourly_rate: form.income_type === "hourly" ? Number(form.hourly_rate) : null,
        work_days_per_week: Number(form.work_days_per_week),
        hours_per_day: form.income_type === "hourly" ? Number(form.hours_per_day) : null,
        pay_frequency: form.pay_frequency,
        payday_note: form.payday_note.trim() || null,
        essential_monthly_expenses: plan === "free" ? null : numberOrNull(form.essential_monthly_expenses),
        liquid_savings: plan === "free" ? null : numberOrNull(form.liquid_savings),
        emergency_fund_target: plan === "free" ? null : numberOrNull(form.emergency_fund_target),
        has_debts: plan === "free" ? false : Boolean(form.has_debts),
        debts: plan !== "free" && form.has_debts
          ? form.debts.map((debt) => ({
              name: debt.name.trim(),
              remaining_amount: Number(debt.remaining_amount),
              total_amount: numberOrNull(debt.total_amount),
              monthly_payment: numberOrNull(debt.monthly_payment),
              interest_rate: numberOrNull(debt.interest_rate),
              payment_day: numberOrNull(debt.payment_day),
            }))
          : [],
        has_goals: plan === "vip" ? Boolean(form.has_goals) : false,
        goals: plan === "vip" && form.has_goals
          ? form.goals.map((goal) => ({
              name: goal.name.trim(),
              target_amount: Number(goal.target_amount),
              current_amount: Number(goal.current_amount || 0),
              target_date: goal.target_date || null,
              priority: goal.priority,
            }))
          : [],
        strategy_preference: plan === "vip" ? form.strategy_preference : null,
        discretionary_monthly_minimum: plan === "vip" ? numberOrNull(form.discretionary_monthly_minimum) : null,
      };
      const response = await completeOnboarding(payload);
      onComplete(response.profile);
    } catch (err) {
      setError(err.message || "No se pudo guardar la configuración.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <main className="onboarding-shell"><section className="onboarding-card onboarding-loading"><strong>J.A.R.V.I.S.</strong><span>Preparando tu configuración...</span></section></main>;
  }

  return (
    <main className="onboarding-shell">
      <section className="onboarding-card">
        <header className="onboarding-topbar">
          <div><strong>J.A.R.V.I.S.</strong><small>{planLabel(plan)} · configuración</small></div>
          <button className="onboarding-logout" onClick={() => supabase.auth.signOut()} type="button"><LogOut size={17} /> Salir</button>
        </header>

        <div className="onboarding-progress-copy"><strong>{step}/{totalSteps}</strong><span>{Math.round((step / totalSteps) * 100)}%</span></div>
        <div className="onboarding-progress" aria-label={`Paso ${step} de ${totalSteps}`}>
          {Array.from({ length: totalSteps }, (_, index) => index + 1).map((item) => <span key={item} className={item <= step ? "active" : ""}></span>)}
        </div>

        <div className="onboarding-heading">
          <p>Paso {step} de {totalSteps}</p>
          <h1>{content[0]}</h1>
          <span>{content[1]}</span>
        </div>

        {step === 1 && (
          <div className="onboarding-section">
            <div className="choice-grid">
              <button type="button" className={form.income_type === "fixed" ? "choice active" : "choice"} onClick={() => update("income_type", "fixed")}><BriefcaseBusiness /><strong>Salario fijo</strong><small>Recibís un salario mensual definido.</small></button>
              <button type="button" className={form.income_type === "hourly" ? "choice active" : "choice"} onClick={() => update("income_type", "hourly")}><WalletCards /><strong>Pago por hora</strong><small>Tu ingreso depende de las horas trabajadas.</small></button>
            </div>
            {form.income_type === "fixed" ? <label className="onboarding-field"><span>Salario mensual</span><input type="number" min="0" step="0.01" placeholder="₡ Monto mensual" value={form.fixed_monthly_salary} onChange={(e) => update("fixed_monthly_salary", e.target.value)} /></label> : <label className="onboarding-field"><span>Pago por hora</span><input type="number" min="0" step="0.01" placeholder="₡ Tarifa por hora" value={form.hourly_rate} onChange={(e) => update("hourly_rate", e.target.value)} /></label>}
          </div>
        )}

        {step === 2 && (
          <div className="onboarding-section onboarding-fields-grid">
            <label className="onboarding-field"><span>Días que trabajás por semana</span><input type="number" min="1" max="7" value={form.work_days_per_week} onChange={(e) => update("work_days_per_week", e.target.value)} /></label>
            {form.income_type === "hourly" && <label className="onboarding-field"><span>Horas aproximadas por día</span><input type="number" min="0.5" max="24" step="0.5" value={form.hours_per_day} onChange={(e) => update("hours_per_day", e.target.value)} /></label>}
            <label className="onboarding-field"><span>Frecuencia de pago</span><select value={form.pay_frequency} onChange={(e) => update("pay_frequency", e.target.value)}><option value="weekly">Semanal</option><option value="biweekly">Quincenal</option><option value="monthly">Mensual</option></select></label>
            <label className="onboarding-field"><span>Día(s) aproximado(s) de pago · opcional</span><input placeholder="Ej. 15 y 30, cada viernes..." value={form.payday_note} onChange={(e) => update("payday_note", e.target.value)} /></label>
          </div>
        )}

        {step === 3 && (
          <div className="onboarding-section">
            <div className="onboarding-icon-copy"><WalletCards /><div><strong>Gastos esenciales mensuales</strong><small>Casa, servicios, alimentación, transporte y obligaciones necesarias.</small></div></div>
            <label className="onboarding-field"><span>Monto aproximado</span><input type="number" min="0" step="0.01" placeholder="₡ 0" value={form.essential_monthly_expenses} onChange={(e) => update("essential_monthly_expenses", e.target.value)} /></label>
            <p className="onboarding-help">No tiene que ser perfecto. Más adelante JARVIS podrá calcularlo mejor usando tu historial real.</p>
          </div>
        )}

        {step === 4 && (
          <div className="onboarding-section">
            <p className="onboarding-question">¿Tenés deudas actualmente?</p>
            <div className="yes-no"><button type="button" className={form.has_debts === true ? "active" : ""} onClick={() => setForm((current) => ({ ...current, has_debts: true, debts: current.debts.length || existingDebts.length ? current.debts : [emptyDebt()] }))}>Sí</button><button type="button" className={form.has_debts === false ? "active" : ""} disabled={existingDebts.length > 0} onClick={() => setForm((current) => ({ ...current, has_debts: false, debts: [] }))}>No</button></div>
            {existingDebts.length > 0 && <div className="existing-items"><strong>Ya guardadas</strong>{existingDebts.map((debt) => <div key={debt.id}><span>{debt.name}</span><b>₡{Number(debt.remaining_amount).toLocaleString("es-CR")}</b></div>)}</div>}
            {form.has_debts && <div className="onboarding-debts"><p className="onboarding-help"><strong>Solo nombre y saldo pendiente son obligatorios.</strong> Lo que no sepás puede quedar vacío.</p>{form.debts.map((debt, index) => <div className="onboarding-debt" key={index}><div className="debt-title"><strong>Nueva deuda {index + 1}</strong><button type="button" onClick={() => setForm((current) => ({ ...current, debts: current.debts.filter((_, i) => i !== index) }))}><Trash2 size={17}/></button></div><div className="onboarding-fields-grid debt-fields"><label className="onboarding-field"><span>Nombre *</span><input placeholder="Ej. BAC" value={debt.name} onChange={(e) => updateDebt(index, "name", e.target.value)} /></label><label className="onboarding-field"><span>Saldo pendiente *</span><input type="number" min="0" step="0.01" placeholder="₡" value={debt.remaining_amount} onChange={(e) => updateDebt(index, "remaining_amount", e.target.value)} /></label><label className="onboarding-field"><span>Monto original · opcional</span><input type="number" min="0" step="0.01" placeholder="No sé" value={debt.total_amount} onChange={(e) => updateDebt(index, "total_amount", e.target.value)} /></label><label className="onboarding-field"><span>Cuota mensual · opcional</span><input type="number" min="0" step="0.01" placeholder="No sé" value={debt.monthly_payment} onChange={(e) => updateDebt(index, "monthly_payment", e.target.value)} /></label><label className="onboarding-field"><span>Interés anual % · opcional</span><input type="number" min="0" step="0.01" placeholder="No sé" value={debt.interest_rate} onChange={(e) => updateDebt(index, "interest_rate", e.target.value)} /></label><label className="onboarding-field"><span>Día de pago · opcional</span><input type="number" min="1" max="31" placeholder="1-31" value={debt.payment_day} onChange={(e) => updateDebt(index, "payment_day", e.target.value)} /></label></div></div>)}<button className="add-another-debt" type="button" onClick={() => setForm((current) => ({ ...current, debts: [...current.debts, emptyDebt()] }))}><Plus size={17}/> Agregar deuda</button></div>}
          </div>
        )}

        {step === 5 && (
          <div className="onboarding-section onboarding-fields-grid">
            <div className="onboarding-icon-copy full"><PiggyBank /><div><strong>Ahorro disponible hoy</strong><small>Dinero líquido que podrías usar ante una emergencia. No inversiones.</small></div></div>
            <label className="onboarding-field"><span>Ahorro líquido actual</span><input type="number" min="0" step="0.01" placeholder="₡ 0" value={form.liquid_savings} onChange={(e) => update("liquid_savings", e.target.value)} /></label>
            <label className="onboarding-field"><span>Meta de fondo de emergencia</span><input type="number" min="0" step="0.01" placeholder="₡ 0" value={form.emergency_fund_target} onChange={(e) => update("emergency_fund_target", e.target.value)} /></label>
            <p className="onboarding-help full">Si todavía no sabés cuánto debería ser tu fondo, poné 0. Más adelante JARVIS podrá proponerte uno.</p>
          </div>
        )}

        {step === 6 && (
          <div className="onboarding-section">
            <p className="onboarding-question">¿Tenés metas financieras activas?</p>
            <div className="yes-no"><button type="button" className={form.has_goals === true ? "active" : ""} onClick={() => setForm((current) => ({ ...current, has_goals: true, goals: current.goals.length || existingGoals.length ? current.goals : [emptyGoal()] }))}>Sí</button><button type="button" className={form.has_goals === false ? "active" : ""} disabled={existingGoals.length > 0} onClick={() => setForm((current) => ({ ...current, has_goals: false, goals: [] }))}>No</button></div>
            {existingGoals.length > 0 && <div className="existing-items"><strong>Ya guardadas</strong>{existingGoals.map((goal) => <div key={goal.id}><span>{goal.name}</span><b>₡{Number(goal.target_amount).toLocaleString("es-CR")}</b></div>)}</div>}
            {form.has_goals && <div className="onboarding-debts">{form.goals.map((goal, index) => <div className="onboarding-debt" key={index}><div className="debt-title"><strong>Nueva meta {index + 1}</strong><button type="button" onClick={() => setForm((current) => ({ ...current, goals: current.goals.filter((_, i) => i !== index) }))}><Trash2 size={17}/></button></div><div className="onboarding-fields-grid debt-fields"><label className="onboarding-field"><span>Meta *</span><input placeholder="Ej. Viaje" value={goal.name} onChange={(e) => updateGoal(index, "name", e.target.value)} /></label><label className="onboarding-field"><span>Monto objetivo *</span><input type="number" min="0" step="0.01" placeholder="₡" value={goal.target_amount} onChange={(e) => updateGoal(index, "target_amount", e.target.value)} /></label><label className="onboarding-field"><span>Ya ahorrado · opcional</span><input type="number" min="0" step="0.01" placeholder="₡ 0" value={goal.current_amount} onChange={(e) => updateGoal(index, "current_amount", e.target.value)} /></label><label className="onboarding-field"><span>Fecha objetivo · opcional</span><input type="date" value={goal.target_date} onChange={(e) => updateGoal(index, "target_date", e.target.value)} /></label><label className="onboarding-field full"><span>Prioridad</span><select value={goal.priority} onChange={(e) => updateGoal(index, "priority", e.target.value)}><option value="low">Baja</option><option value="medium">Media</option><option value="high">Alta</option><option value="critical">Crítica</option></select></label></div></div>)}<button className="add-another-debt" type="button" onClick={() => setForm((current) => ({ ...current, goals: [...current.goals, emptyGoal()] }))}><Plus size={17}/> Agregar meta</button></div>}
          </div>
        )}

        {step === 7 && (
          <div className="onboarding-section">
            <p className="onboarding-question">¿Qué querés que JARVIS cuide primero?</p>
            <div className="priority-grid">
              {[{ code: "debt", icon: Crosshair, title: "Salir de deudas", text: "Priorizar deuda sin descuidar lo esencial." }, { code: "emergency", icon: ShieldCheck, title: "Seguridad", text: "Fortalecer primero tu colchón de emergencia." }, { code: "goals", icon: Flag, title: "Metas", text: "Dar más peso a tus objetivos financieros." }, { code: "balanced", icon: WalletCards, title: "Equilibrado", text: "Distribuir el progreso entre varias prioridades." }].map(({ code, icon: Icon, title, text }) => <button key={code} type="button" className={form.strategy_preference === code ? "choice active" : "choice"} onClick={() => update("strategy_preference", code)}><Icon /><strong>{title}</strong><small>{text}</small></button>)}
            </div>
            <label className="onboarding-field"><span>Mínimo mensual que querés reservar para vos</span><input type="number" min="0" step="0.01" placeholder="₡ 0" value={form.discretionary_monthly_minimum} onChange={(e) => update("discretionary_monthly_minimum", e.target.value)} /></label>
            <p className="onboarding-help">No es un presupuesto definitivo. Le dice a JARVIS cuánto no debería comprometer automáticamente en estrategias.</p>
          </div>
        )}

        {error && <p className="onboarding-error">{error}</p>}

        <footer className="onboarding-actions">
          {step > initialStep ? <button className="secondary" type="button" onClick={() => { setError(""); setStep((current) => current - 1); }}><ChevronLeft size={18}/> Atrás</button> : <span></span>}
          {step < totalSteps ? <button className="primary" type="button" onClick={next}>Continuar <ChevronRight size={18}/></button> : <button className="primary" type="button" onClick={submit} disabled={saving}>{saving ? "Guardando..." : `Activar ${planLabel(plan)}`}</button>}
        </footer>

        {initialStep > 1 && <p className="onboarding-required-note">Ya conservamos lo que completaste en {previousLevel === "free" ? "Gratis" : "Basic"}. Solo te estamos pidiendo la información nueva que necesita {planLabel(plan)}.</p>}
      </section>
    </main>
  );
}
