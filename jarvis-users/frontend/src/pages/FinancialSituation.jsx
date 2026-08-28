import { useEffect, useMemo, useState } from "react";
import {
  BriefcaseBusiness,
  ChevronRight,
  CircleDollarSign,
  CreditCard,
  Flag,
  PiggyBank,
  Save,
  ShieldCheck,
  Sparkles,
  WalletCards,
} from "lucide-react";
import { getFinancialSituation, updateFinancialSituation } from "../services/jarvisApi";

const money = (value) => new Intl.NumberFormat("es-CR", { style: "currency", currency: "CRC", maximumFractionDigits: 0 }).format(Number(value) || 0);
const empty = {
  income_type: "fixed",
  fixed_monthly_salary: "",
  hourly_rate: "",
  work_days_per_week: 5,
  hours_per_day: "",
  pay_frequency: "biweekly",
  payday_note: "",
  essential_monthly_expenses: "",
  liquid_savings: "",
  emergency_fund_target: "",
  strategy_preference: "balanced",
  discretionary_monthly_minimum: "",
};

const labels = {
  free: { name: "Gratis", hint: "Organización financiera" },
  basic: { name: "Basic", hint: "Organización + estrategia" },
  vip: { name: "VIP", hint: "Dirección financiera" },
};

const numOrNull = (value) => value === "" || value === null || value === undefined ? null : Number(value);

export default function FinancialSituation({ plan = "free", onNavigate }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = () => getFinancialSituation().then((response) => {
    setData(response);
    const fp = response.financial_profile || {};
    setForm({
      income_type: fp.income_type || "fixed",
      fixed_monthly_salary: fp.fixed_monthly_salary ?? "",
      hourly_rate: fp.hourly_rate ?? "",
      work_days_per_week: fp.work_days_per_week ?? 5,
      hours_per_day: fp.hours_per_day ?? "",
      pay_frequency: fp.pay_frequency || "biweekly",
      payday_note: fp.payday_note || "",
      essential_monthly_expenses: fp.essential_monthly_expenses ?? "",
      liquid_savings: fp.liquid_savings ?? "",
      emergency_fund_target: fp.emergency_fund_target ?? "",
      strategy_preference: fp.strategy_preference || "balanced",
      discretionary_monthly_minimum: fp.discretionary_monthly_minimum ?? "",
    });
  });

  useEffect(() => { load().catch((e) => setError(e.message)); }, []);

  const completeness = useMemo(() => {
    if (!data) return 0;
    const checks = [
      Boolean(form.income_type),
      form.income_type === "fixed" ? Number(form.fixed_monthly_salary) > 0 : Number(form.hourly_rate) > 0,
      Number(form.work_days_per_week) > 0,
      Boolean(form.pay_frequency),
    ];
    if (plan !== "free") checks.push(
      form.essential_monthly_expenses !== "",
      form.liquid_savings !== "",
      form.emergency_fund_target !== "",
      Number(data.debts?.missing_interest || 0) === 0,
    );
    if (plan === "vip") checks.push(
      Boolean(form.strategy_preference),
      form.discretionary_monthly_minimum !== "",
      Number(data.goals?.count || 0) > 0,
    );
    return Math.round((checks.filter(Boolean).length / checks.length) * 100);
  }, [data, form, plan]);

  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const save = async () => {
    setSaving(true); setError(""); setMessage("");
    try {
      const payload = {
        ...form,
        fixed_monthly_salary: form.income_type === "fixed" ? numOrNull(form.fixed_monthly_salary) : null,
        hourly_rate: form.income_type === "hourly" ? numOrNull(form.hourly_rate) : null,
        hours_per_day: form.income_type === "hourly" ? numOrNull(form.hours_per_day) : null,
        work_days_per_week: Number(form.work_days_per_week),
        essential_monthly_expenses: numOrNull(form.essential_monthly_expenses),
        liquid_savings: numOrNull(form.liquid_savings),
        emergency_fund_target: numOrNull(form.emergency_fund_target),
        discretionary_monthly_minimum: numOrNull(form.discretionary_monthly_minimum),
      };
      const response = await updateFinancialSituation(payload);
      setData(response);
      setEditing("");
      setMessage("Tu situación financiera quedó actualizada.");
    } catch (e) {
      setError(e.message || "No pudimos guardar los cambios.");
    } finally { setSaving(false); }
  };

  if (!data && !error) return <div className="mobile-panel">Cargando tu situación financiera...</div>;

  const planName = labels[plan]?.name || plan.toUpperCase();
  return (
    <section className={`mobile-page financial-situation plan-view-${plan}`}>
      <div className="mobile-page-heading">
        <p className="eyebrow">Perfil financiero · {planName}</p>
        <h1>Mi situación financiera</h1>
        <span>Actualizá lo que JARVIS sabe de vos. Cada plan usa un nivel distinto de información.</span>
      </div>

      <article className="profile-completeness-card">
        <div className="profile-completeness-top"><div><strong>{completeness}% completo</strong><small>{labels[plan]?.hint}</small></div><span>{planName}</span></div>
        <div className="profile-completeness-track"><i style={{ width: `${completeness}%` }} /></div>
        {plan !== "free" && Number(data.debts?.missing_interest || 0) > 0 && <p>Podés mejorar la precisión agregando la tasa de interés de {data.debts.missing_interest} deuda(s).</p>}
      </article>

      <div className="situation-card-list">
        <SituationCard icon={CircleDollarSign} title="Ingresos" summary={form.income_type === "fixed" ? `${money(form.fixed_monthly_salary)} / mes` : `${money(form.hourly_rate)} / hora`} editing={editing === "income"} onEdit={() => setEditing(editing === "income" ? "" : "income")}>
          <div className="situation-form-grid">
            <label><span>Tipo de ingreso</span><select value={form.income_type} onChange={(e) => update("income_type", e.target.value)}><option value="fixed">Salario fijo</option><option value="hourly">Pago por hora</option></select></label>
            {form.income_type === "fixed" ? <label><span>Salario mensual</span><input type="number" min="0" value={form.fixed_monthly_salary} onChange={(e) => update("fixed_monthly_salary", e.target.value)} /></label> : <label><span>Pago por hora</span><input type="number" min="0" value={form.hourly_rate} onChange={(e) => update("hourly_rate", e.target.value)} /></label>}
          </div>
        </SituationCard>

        <SituationCard icon={BriefcaseBusiness} title="Trabajo y pagos" summary={`${form.work_days_per_week} días/semana · ${form.pay_frequency === "weekly" ? "semanal" : form.pay_frequency === "monthly" ? "mensual" : "quincenal"}`} editing={editing === "work"} onEdit={() => setEditing(editing === "work" ? "" : "work")}>
          <div className="situation-form-grid">
            <label><span>Días por semana</span><input type="number" min="1" max="7" value={form.work_days_per_week} onChange={(e) => update("work_days_per_week", e.target.value)} /></label>
            {form.income_type === "hourly" && <label><span>Horas por día</span><input type="number" min="0.1" max="24" step="0.1" value={form.hours_per_day} onChange={(e) => update("hours_per_day", e.target.value)} /></label>}
            <label><span>Frecuencia de pago</span><select value={form.pay_frequency} onChange={(e) => update("pay_frequency", e.target.value)}><option value="weekly">Semanal</option><option value="biweekly">Quincenal</option><option value="monthly">Mensual</option></select></label>
            <label><span>Día(s) aproximado(s)</span><input value={form.payday_note} onChange={(e) => update("payday_note", e.target.value)} placeholder="Ej. 15 y 30" /></label>
          </div>
        </SituationCard>

        {plan !== "free" && <SituationCard icon={WalletCards} title="Gastos esenciales" summary={`${money(form.essential_monthly_expenses)} / mes`} editing={editing === "expenses"} onEdit={() => setEditing(editing === "expenses" ? "" : "expenses")} badge="Basic+">
          <label className="situation-single-field"><span>Estimado mensual</span><input type="number" min="0" value={form.essential_monthly_expenses} onChange={(e) => update("essential_monthly_expenses", e.target.value)} /></label>
          <p className="situation-help">JARVIS usa este dato para no recomendar comprometer dinero que necesitás para vivir.</p>
        </SituationCard>}

        {plan !== "free" && <SituationCard icon={CreditCard} title="Deudas" summary={`${data.debts?.count || 0} deuda(s) · ${money(data.debts?.balance)}`} actionLabel="Administrar" onAction={() => onNavigate?.("debts")} badge="Basic+" />}

        {plan !== "free" && <SituationCard icon={PiggyBank} title="Ahorro y emergencia" summary={`${money(form.liquid_savings)} disponibles`} editing={editing === "savings"} onEdit={() => setEditing(editing === "savings" ? "" : "savings")} badge="Basic+">
          <div className="situation-form-grid">
            <label><span>Ahorro líquido</span><input type="number" min="0" value={form.liquid_savings} onChange={(e) => update("liquid_savings", e.target.value)} /></label>
            <label><span>Meta de emergencia</span><input type="number" min="0" value={form.emergency_fund_target} onChange={(e) => update("emergency_fund_target", e.target.value)} /></label>
          </div>
        </SituationCard>}

        {plan === "vip" && <SituationCard icon={Flag} title="Metas financieras" summary={`${data.goals?.count || 0} activa(s) · ${money(data.goals?.current)} ahorrado`} actionLabel="Administrar" onAction={() => onNavigate?.("goals")} badge="VIP" />}

        {plan === "vip" && <SituationCard icon={Sparkles} title="Preferencias del Director" summary={form.strategy_preference === "debt" ? "Priorizar deudas" : form.strategy_preference === "emergency" ? "Priorizar seguridad" : form.strategy_preference === "goals" ? "Priorizar metas" : "Estrategia equilibrada"} editing={editing === "vip"} onEdit={() => setEditing(editing === "vip" ? "" : "vip")} badge="VIP">
          <div className="situation-form-grid">
            <label><span>Prioridad principal</span><select value={form.strategy_preference} onChange={(e) => update("strategy_preference", e.target.value)}><option value="debt">Salir de deudas</option><option value="emergency">Seguridad</option><option value="goals">Metas</option><option value="balanced">Equilibrado</option></select></label>
            <label><span>Mínimo mensual para vos</span><input type="number" min="0" value={form.discretionary_monthly_minimum} onChange={(e) => update("discretionary_monthly_minimum", e.target.value)} /></label>
          </div>
        </SituationCard>}
      </div>

      {plan === "free" && <article className="tier-explanation-card"><ShieldCheck size={20}/><div><strong>Vista Gratis</strong><p>Mostramos solamente los datos que este plan necesita. Si subís a Basic, aparecerán gastos esenciales, deudas y ahorro sin mezclar funciones VIP.</p></div></article>}
      {plan === "basic" && <article className="tier-explanation-card"><Sparkles size={20}/><div><strong>Vista Basic</strong><p>JARVIS usa ingresos, gastos esenciales, deudas y ahorro para construir recomendaciones determinísticas. Las preferencias avanzadas del Director quedan reservadas para VIP.</p></div></article>}
      {plan === "vip" && <article className="tier-explanation-card vip"><ShieldCheck size={20}/><div><strong>Vista VIP</strong><p>Además de la base Basic, el perfil incorpora metas y preferencias que alimentarán la dirección financiera dinámica y sus futuros escenarios.</p></div></article>}

      {editing && <button type="button" className="situation-save-button" disabled={saving} onClick={save}><Save size={18}/>{saving ? "Guardando..." : "Guardar cambios"}</button>}
      {message && <p className="success-banner">{message}</p>}
      {error && <p className="onboarding-error">{error}</p>}
    </section>
  );
}

function SituationCard({ icon: Icon, title, summary, editing, onEdit, children, badge, actionLabel, onAction }) {
  return <article className={`situation-card ${editing ? "is-editing" : ""}`}>
    <div className="situation-card-head">
      <div className="situation-card-icon"><Icon size={20}/></div>
      <div className="situation-card-copy"><div><strong>{title}</strong>{badge && <em>{badge}</em>}</div><small>{summary}</small></div>
      {actionLabel ? <button type="button" className="situation-edit" onClick={onAction}>{actionLabel}<ChevronRight size={16}/></button> : <button type="button" className="situation-edit" onClick={onEdit}>{editing ? "Cerrar" : "Editar"}</button>}
    </div>
    {editing && children && <div className="situation-card-body">{children}</div>}
  </article>;
}
