import { useEffect, useMemo, useState } from "react";
import {
  BriefcaseBusiness,
  ChevronRight,
  CircleDollarSign,
  CreditCard,
  Flag,
  HelpCircle,
  PiggyBank,
  Save,
  ShieldCheck,
  Sparkles,
  WalletCards,
} from "lucide-react";
import { getFinancialSituation, updateFinancialSituation } from "../services/jarvisApi";
import { deviceLanguage, localeTag, tx as translate } from "../../lib/locale";

const language = deviceLanguage();
const tx = (es, en) => translate(es, en, language);
const money = (value) => new Intl.NumberFormat(localeTag(language), { style: "currency", currency: "CRC", currencyDisplay: "narrowSymbol", maximumFractionDigits: 0 }).format(Number(value) || 0);
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
  free: { name: tx("Gratis", "Free"), hint: tx("Organización financiera", "Financial organization") },
  basic: { name: "Basic", hint: tx("Organización + estrategia", "Organization + strategy") },
  vip: { name: "VIP", hint: tx("Dirección financiera", "Financial direction") },
};

const numOrNull = (value) => value === "" || value === null || value === undefined ? null : Number(value);

function FieldHelp({ label, children }) {
  const [open, setOpen] = useState(false);
  return <span className="situation-field-label">
    <span>{label}</span>
    <button type="button" aria-label={`${tx("Ayuda sobre", "Help with")} ${label}`} aria-expanded={open} onClick={(event) => { event.preventDefault(); event.stopPropagation(); setOpen((current) => !current); }}><HelpCircle size={15}/></button>
    {open && <span className="situation-field-help" role="status">{children}</span>}
  </span>;
}

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
      fixed_monthly_salary: fp.fixed_monthly_salary ?? (response.observed?.income_count > 0 ? response.observed.monthly_income_average : ""),
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
      setMessage(tx("Tu situación financiera quedó actualizada.", "Your financial situation was updated."));
    } catch (e) {
      setError(e.message || tx("No pudimos guardar los cambios.", "We couldn’t save the changes."));
    } finally { setSaving(false); }
  };

  if (!data && !error) return <div className="mobile-panel">{tx("Cargando tu situación financiera...", "Loading your financial situation...")}</div>;
  if (!data) return <div className="panel error" role="alert">{error}</div>;

  const planName = labels[plan]?.name || plan.toUpperCase();
  return (
    <section className={`mobile-page financial-situation plan-view-${plan}`}>
      <div className="mobile-page-heading">
        <p className="eyebrow">{tx("Perfil financiero", "Financial profile")} · {planName}</p>
        <h1>{tx("Mi situación financiera", "My financial situation")}</h1>
        <span>{tx("Actualizá lo que DINCR sabe de vos. Cada plan usa un nivel distinto de información.", "Update what DINCR knows about you. Each plan uses a different level of information.")}</span>
      </div>

      <article className="profile-completeness-card">
        <div className="profile-completeness-top"><div><strong>{completeness}% {tx("completo", "complete")}</strong><small>{labels[plan]?.hint}</small></div><span>{planName}</span></div>
        <div className="profile-completeness-track"><i style={{ width: `${completeness}%` }} /></div>
        {plan !== "free" && Number(data.debts?.missing_interest || 0) > 0 && <p>{tx(`Podés mejorar la precisión agregando la tasa de interés de ${data.debts.missing_interest} deuda(s).`, `Improve accuracy by adding the interest rate for ${data.debts.missing_interest} debt(s).`)}</p>}
      </article>

      {!data.financial_profile && Number(data.observed?.income_count || 0) > 0 && <article className="situation-observed-note"><Sparkles size={18}/><div><strong>{tx("Referencia tomada de tus movimientos", "Reference based on your transactions")}</strong><p>{tx(`Calculamos ${money(data.observed.monthly_income_average)} al mes con ${data.observed.income_count} ingreso(s) de los últimos 90 días. Revisalo antes de guardar.`, `We calculated ${money(data.observed.monthly_income_average)} per month from ${data.observed.income_count} income transaction(s) in the last 90 days. Review it before saving.`)}</p></div></article>}

      <div className="situation-card-list">
        <SituationCard icon={CircleDollarSign} title={tx("Referencia de ingresos", "Income reference")} summary={tx("DINCR usa tus movimientos reales, no un salario proyectado", "DINCR uses your actual transactions, not projected income")} editing={editing === "income"} onEdit={() => setEditing(editing === "income" ? "" : "income")}>
          <div className="situation-form-grid">
            <label><FieldHelp label={tx("¿Cómo te pagan?", "How are you paid?")}>{tx("Salario mensual es para un monto fijo o parecido cada mes. Pago por hora es cuando el ingreso depende de las horas trabajadas.", "Monthly salary is for a fixed or similar amount each month. Hourly pay is for income based on hours worked.")}</FieldHelp><select value={form.income_type} onChange={(e) => update("income_type", e.target.value)}><option value="fixed">{tx("Recibo un salario mensual", "I receive a monthly salary")}</option><option value="hourly">{tx("Me pagan por hora trabajada", "I am paid by the hour")}</option></select></label>
            {form.income_type === "fixed" ? <label><FieldHelp label={tx("Salario mensual de referencia", "Reference monthly salary")}>{tx("Este dato queda como referencia para estrategia. Tu dinero día a día se toma de los ingresos reales que registrás.", "This is used as a strategy reference. Your daily finances use the actual income you record.")}</FieldHelp><input type="number" min="0" step="0.01" inputMode="decimal" value={form.fixed_monthly_salary} onChange={(e) => update("fixed_monthly_salary", e.target.value)} /></label> : <label><FieldHelp label={tx("Cuánto te pagan por hora", "Hourly rate")}>{tx("Es el pago de una hora normal, sin multiplicarlo por el día o el mes.", "Enter the pay for one regular hour, without multiplying it by the day or month.")}</FieldHelp><input type="number" min="0" step="0.01" inputMode="decimal" value={form.hourly_rate} onChange={(e) => update("hourly_rate", e.target.value)} /></label>}
          </div>
        </SituationCard>

        <SituationCard icon={BriefcaseBusiness} title={tx("Trabajo y pagos", "Work and pay")} summary={`${form.work_days_per_week} ${tx("días/semana", "days/week")} · ${form.pay_frequency === "weekly" ? tx("semanal", "weekly") : form.pay_frequency === "monthly" ? tx("mensual", "monthly") : tx("quincenal", "twice monthly")}`} editing={editing === "work"} onEdit={() => setEditing(editing === "work" ? "" : "work")}>
          <div className="situation-form-grid">
            <label><FieldHelp label={tx("Días que trabajás por semana", "Workdays per week")}>{tx("Escribí cuántos días trabajás normalmente en una semana.", "Enter how many days you usually work each week.")}</FieldHelp><input type="number" min="1" max="7" step="1" inputMode="numeric" value={form.work_days_per_week} onChange={(e) => update("work_days_per_week", e.target.value)} /></label>
            {form.income_type === "hourly" && <label><FieldHelp label={tx("Horas que trabajás por día", "Hours worked per day")}>{tx("Podés escribir un número entero como 8 o un decimal como 7.5.", "You can enter a whole number such as 8 or a decimal such as 7.5.")}</FieldHelp><input type="number" min="0.25" max="24" step="0.25" inputMode="decimal" value={form.hours_per_day} onChange={(e) => update("hours_per_day", e.target.value)} /></label>}
            <label><FieldHelp label={tx("Cada cuánto te pagan", "Pay frequency")}>{tx("Elegí si recibís dinero semanalmente, dos veces al mes o una vez al mes.", "Choose whether you are paid weekly, twice a month, or monthly.")}</FieldHelp><select value={form.pay_frequency} onChange={(e) => update("pay_frequency", e.target.value)}><option value="weekly">{tx("Cada semana", "Every week")}</option><option value="biweekly">{tx("Dos veces al mes", "Twice a month")}</option><option value="monthly">{tx("Una vez al mes", "Once a month")}</option></select></label>
            <label><FieldHelp label={tx("¿Qué día te pagan?", "What day are you paid?")}>{tx("Escribí una fecha o descripción aproximada para organizar el calendario.", "Enter an approximate date or description to organize your calendar.")}</FieldHelp><input value={form.payday_note} onChange={(e) => update("payday_note", e.target.value)} placeholder={tx("Ej. 15 y 30", "E.g. 15th and 30th")} /></label>
          </div>
        </SituationCard>

        {plan !== "free" && <SituationCard icon={WalletCards} title={tx("Gastos esenciales", "Essential expenses")} summary={`${money(form.essential_monthly_expenses)} / ${tx("mes", "month")}`} editing={editing === "expenses"} onEdit={() => setEditing(editing === "expenses" ? "" : "expenses")} badge="Basic+">
          <label className="situation-single-field"><FieldHelp label={tx("Gastos necesarios del mes", "Required monthly expenses")}>{tx("Incluí vivienda, comida, servicios, transporte, medicinas y otros pagos indispensables.", "Include housing, food, utilities, transportation, medicine, and other essential payments.")}</FieldHelp><input type="number" min="0" step="0.01" value={form.essential_monthly_expenses} onChange={(e) => update("essential_monthly_expenses", e.target.value)} /></label>
          <p className="situation-help">{tx("DINCR usa este dato para no recomendar comprometer dinero que necesitás para vivir.", "DINCR uses this amount to avoid recommending money that you need for living expenses.")}</p>
        </SituationCard>}

        {plan !== "free" && <SituationCard icon={CreditCard} title={tx("Deudas", "Debts")} summary={`${data.debts?.count || 0} ${tx("deuda(s)", "debt(s)")} · ${money(data.debts?.balance)}`} actionLabel={tx("Administrar", "Manage")} onAction={() => onNavigate?.("debts")} badge="Basic+" />}

        {plan !== "free" && <SituationCard icon={PiggyBank} title={tx("Ahorro y emergencia", "Savings and emergency fund")} summary={`${money(form.liquid_savings)} ${tx("disponibles", "available")}`} editing={editing === "savings"} onEdit={() => setEditing(editing === "savings" ? "" : "savings")} badge="Basic+">
          <div className="situation-form-grid">
            <label><FieldHelp label={tx("Ahorro disponible ahora", "Savings available now")}>{tx("Dinero guardado que podés usar inmediatamente, como efectivo o saldo disponible en una cuenta.", "Saved money you can use immediately, such as cash or an available account balance.")}</FieldHelp><input type="number" min="0" step="0.01" value={form.liquid_savings} onChange={(e) => update("liquid_savings", e.target.value)} /></label>
            <label><FieldHelp label={tx("Meta para emergencias", "Emergency fund target")}>{tx("Monto que querés reservar para imprevistos.", "The amount you want to reserve for unexpected expenses.")}</FieldHelp><input type="number" min="0" step="0.01" value={form.emergency_fund_target} onChange={(e) => update("emergency_fund_target", e.target.value)} /></label>
          </div>
        </SituationCard>}

        {plan === "vip" && <SituationCard icon={Flag} title={tx("Metas financieras", "Financial goals")} summary={`${data.goals?.count || 0} ${tx("activa(s)", "active")} · ${money(data.goals?.current)} ${tx("ahorrado", "saved")}`} actionLabel={tx("Administrar", "Manage")} onAction={() => onNavigate?.("goals")} badge="VIP" />}

        {plan === "vip" && <SituationCard icon={Sparkles} title={tx("Preferencias del Director", "Director preferences")} summary={form.strategy_preference === "debt" ? tx("Priorizar deudas", "Prioritize debt") : form.strategy_preference === "emergency" ? tx("Priorizar seguridad", "Prioritize security") : form.strategy_preference === "goals" ? tx("Priorizar metas", "Prioritize goals") : tx("Estrategia equilibrada", "Balanced strategy")} editing={editing === "vip"} onEdit={() => setEditing(editing === "vip" ? "" : "vip")} badge="VIP">
          <div className="situation-form-grid">
            <label><FieldHelp label={tx("¿Qué querés priorizar?", "What do you want to prioritize?")}>{tx("DINCR usa esta respuesta para ordenar sus recomendaciones.", "DINCR uses this answer to rank its recommendations.")}</FieldHelp><select value={form.strategy_preference} onChange={(e) => update("strategy_preference", e.target.value)}><option value="debt">{tx("Salir de deudas", "Pay off debt")}</option><option value="emergency">{tx("Crear ahorro de emergencia", "Build an emergency fund")}</option><option value="goals">{tx("Cumplir mis metas", "Reach my goals")}</option><option value="balanced">{tx("Un poco de todo", "A little of everything")}</option></select></label>
            <label><FieldHelp label={tx("Dinero mínimo para tus gustos", "Minimum personal spending")}>{tx("Monto que querés conservar mensualmente para entretenimiento, salidas o compras personales.", "The amount you want to keep each month for entertainment, outings, or personal purchases.")}</FieldHelp><input type="number" min="0" step="0.01" value={form.discretionary_monthly_minimum} onChange={(e) => update("discretionary_monthly_minimum", e.target.value)} /></label>
          </div>
        </SituationCard>}
      </div>

      {plan === "free" && <article className="tier-explanation-card"><ShieldCheck size={20}/><div><strong>{tx("Vista Gratis", "Free view")}</strong><p>{tx("Mostramos solamente los datos que este plan necesita. Si subís a Basic, aparecerán gastos esenciales, deudas y ahorro sin mezclar funciones VIP.", "We show only the data this plan needs. Upgrading to Basic adds essential expenses, debt, and savings without mixing in VIP features.")}</p></div></article>}
      {plan === "basic" && <article className="tier-explanation-card"><Sparkles size={20}/><div><strong>{tx("Vista Basic", "Basic view")}</strong><p>{tx("DINCR usa ingresos, gastos esenciales, deudas y ahorro para construir recomendaciones determinísticas. Las preferencias avanzadas del Director quedan reservadas para VIP.", "DINCR uses income, essential expenses, debt, and savings to build deterministic recommendations. Advanced Director preferences remain exclusive to VIP.")}</p></div></article>}
      {plan === "vip" && <article className="tier-explanation-card vip"><ShieldCheck size={20}/><div><strong>{tx("Vista VIP", "VIP view")}</strong><p>{tx("Además de la base Basic, el perfil incorpora metas y preferencias que alimentarán la dirección financiera dinámica y sus futuros escenarios.", "In addition to the Basic profile, this includes goals and preferences that power dynamic financial direction and future scenarios.")}</p></div></article>}

      {editing && <button type="button" className="situation-save-button" disabled={saving} onClick={save}><Save size={18}/>{saving ? tx("Guardando...", "Saving...") : tx("Guardar cambios", "Save changes")}</button>}
      {message && <p className="success-banner">{message}</p>}
      {message && plan === "vip" && <button type="button" className="situation-save-button" onClick={() => onNavigate?.("overview")}>{tx("Continuar con mi estrategia VIP", "Continue to my VIP strategy")}</button>}
      {error && <p className="onboarding-error">{error}</p>}
    </section>
  );
}

function SituationCard({ icon: Icon, title, summary, editing, onEdit, children, badge, actionLabel, onAction }) {
  return <article className={`situation-card ${editing ? "is-editing" : ""}`}>
    <div className="situation-card-head">
      <div className="situation-card-icon"><Icon size={20}/></div>
      <div className="situation-card-copy"><div><strong>{title}</strong>{badge && <em>{badge}</em>}</div><small>{summary}</small></div>
      {actionLabel ? <button type="button" className="situation-edit" onClick={onAction}>{actionLabel}<ChevronRight size={16}/></button> : <button type="button" className="situation-edit" onClick={onEdit}>{editing ? tx("Cerrar", "Close") : tx("Editar", "Edit")}</button>}
    </div>
    {editing && children && <div className="situation-card-body">{children}</div>}
  </article>;
}
