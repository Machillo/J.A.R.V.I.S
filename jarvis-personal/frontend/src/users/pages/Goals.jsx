import { useEffect, useState } from "react";
import { CalendarClock, Plus, Target } from "lucide-react";
import { contributeGoal, contributeSavingsPlan, createGoal, createSavingsPlan, deleteGoal, deleteSavingsPlan, getGoals, getSavingsPlans, updateGoal, updateSavingsPlan } from "../services/jarvisApi";
import { AmountDialog, ConfirmDialog } from "../components/FinvaDialog";
import FinvaFormSheet from "../components/FinvaFormSheet";
import { deviceLanguage, localeTag } from "../../lib/locale";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const money = (value) => new Intl.NumberFormat(localeTag(language), { style:"currency", currency:"CRC", maximumFractionDigits:2 }).format(Number(value) || 0);
const today = () => new Date().toISOString().slice(0,10);
const goalEmpty = { name:"", target_amount:"", current_amount:0, target_date:"", priority:"medium", status:"active" };
const savingsEmpty = { name:"", monthly_amount:"", saved_amount:0, start_date:today(), end_date:"", status:"active" };
const monthsInclusive = (startValue, endValue) => {
  if (!startValue || !endValue) return 0;
  const start = new Date(`${startValue}T12:00:00`), end = new Date(`${endValue}T12:00:00`);
  return Math.max((end.getFullYear()-start.getFullYear())*12+end.getMonth()-start.getMonth()+1,1);
};
const monthly = (goal) => {
  if (!goal.target_date) return null;
  const now = new Date(), end = new Date(`${goal.target_date}T12:00:00`);
  const months = Math.max((end.getFullYear()-now.getFullYear())*12+end.getMonth()-now.getMonth(),1);
  return Math.max((Number(goal.target_amount)-Number(goal.current_amount))/months,0);
};

function GoalFields({ value, setValue, advanced }) {
  return <div className="finva-compact-fields">
    <label><span>{tx("Nombre de la meta", "Goal name")}</span><input required placeholder={tx("Ej. Viaje familiar", "E.g. Family trip")} value={value.name} onChange={(e) => setValue({...value,name:e.target.value})}/></label>
    <label><span>{tx("Monto objetivo", "Target amount")}</span><input required type="number" inputMode="decimal" min="0.01" step="0.01" placeholder="₡0" value={value.target_amount} onChange={(e) => setValue({...value,target_amount:e.target.value})}/></label>
    {advanced && <>
      <label><span>{tx("Ya ahorrado", "Already saved")}</span><input type="number" inputMode="decimal" min="0" step="0.01" placeholder="₡0" value={value.current_amount} onChange={(e) => setValue({...value,current_amount:e.target.value})}/></label>
      <label><span>{tx("Fecha objetivo", "Target date")}</span><input type="date" value={value.target_date || ""} onChange={(e) => setValue({...value,target_date:e.target.value})}/></label>
      <label><span>{tx("Prioridad", "Priority")}</span><select value={value.priority} onChange={(e) => setValue({...value,priority:e.target.value})}><option value="low">{tx("Baja", "Low")}</option><option value="medium">{tx("Media", "Medium")}</option><option value="high">{tx("Alta", "High")}</option><option value="critical">{tx("Prioritaria", "Critical")}</option></select></label>
    </>}
  </div>;
}

function SavingsFields({ value, setValue }) {
  return <div className="finva-compact-fields">
    <label><span>{tx("Nombre del ahorro", "Savings name")}</span><input required placeholder={tx("Ej. Marchamo", "E.g. Annual vehicle fee")} value={value.name} onChange={(e) => setValue({...value,name:e.target.value})}/></label>
    <label><span>{tx("Monto por mes", "Amount per month")}</span><input required type="number" inputMode="decimal" min="0.01" step="0.01" placeholder="₡0" value={value.monthly_amount} onChange={(e) => setValue({...value,monthly_amount:e.target.value})}/></label>
    <label><span>{tx("Ya tenés ahorrado", "Already saved")}</span><input type="number" inputMode="decimal" min="0" step="0.01" placeholder="₡0" value={value.saved_amount} onChange={(e) => setValue({...value,saved_amount:e.target.value})}/></label>
    <label><span>{tx("Empezar", "Start")}</span><input required type="date" value={value.start_date} onChange={(e) => setValue({...value,start_date:e.target.value})}/></label>
    <label><span>{tx("Ahorrar hasta", "Save until")}</span><input required type="date" min={value.start_date || undefined} value={value.end_date} onChange={(e) => setValue({...value,end_date:e.target.value})}/></label>
  </div>;
}

export default function Goals({ plan = "free" }) {
  const advanced = plan !== "free";
  const [view,setView] = useState("goals"), [rows,setRows] = useState([]), [savings,setSavings] = useState([]);
  const [form,setForm] = useState(goalEmpty), [savingsForm,setSavingsForm] = useState(savingsEmpty);
  const [creating,setCreating] = useState(false), [creatingSavings,setCreatingSavings] = useState(false);
  const [edit,setEdit] = useState(null), [editSavings,setEditSavings] = useState(null);
  const [contribution,setContribution] = useState(null), [contributionAmount,setContributionAmount] = useState("");
  const [deleting,setDeleting] = useState(null), [busyDialog,setBusyDialog] = useState(false), [error,setError] = useState("");
  const run = async (fn) => { setError(""); try { return await fn(); } catch (err) { setError(err.message); return null; } };
  const load = () => run(async () => { const [goalsData,savingsData] = await Promise.all([getGoals(),getSavingsPlans()]); setRows(goalsData); setSavings(savingsData); });
  useEffect(() => { load(); }, []);
  const goalPayload = (value) => ({...value,target_amount:Number(value.target_amount),current_amount:Number(value.current_amount || 0),target_date:value.target_date || null});
  const savingsPayload = (value) => ({...value,monthly_amount:Number(value.monthly_amount),saved_amount:Number(value.saved_amount || 0)});
  const submitGoal = async (event) => { event.preventDefault(); if (await run(() => createGoal(goalPayload(form)))) { setForm(goalEmpty); setCreating(false); load(); } };
  const saveGoal = async (event) => { event.preventDefault(); if (await run(() => updateGoal(edit.id,goalPayload(edit)))) { setEdit(null); load(); } };
  const submitSavings = async (event) => { event.preventDefault(); if (await run(() => createSavingsPlan(savingsPayload(savingsForm)))) { setSavingsForm({...savingsEmpty,start_date:today()}); setCreatingSavings(false); load(); } };
  const saveSavings = async (event) => { event.preventDefault(); if (await run(() => updateSavingsPlan(editSavings.id,savingsPayload(editSavings)))) { setEditSavings(null); load(); } };
  const registerContribution = async () => {
    setBusyDialog(true);
    const saved = contribution?.kind === "savings" ? await run(() => contributeSavingsPlan(contribution.id,{amount:Number(contributionAmount)})) : await run(() => contributeGoal(contribution.id,{amount:Number(contributionAmount)}));
    setBusyDialog(false); if (saved) { setContribution(null); setContributionAmount(""); load(); }
  };
  const remove = async () => {
    setBusyDialog(true);
    const removed = deleting?.kind === "savings" ? await run(() => deleteSavingsPlan(deleting.id)) : await run(() => deleteGoal(deleting.id));
    setBusyDialog(false); if (removed) { setDeleting(null); load(); }
  };

  return <section className="content-first-page">
    <div className="hero"><span>{advanced ? "BASIC 04" : "FREE 05"}</span><h1>{tx("Metas y ahorros", "Goals and savings")}</h1><p>{tx("Separá lo que querés alcanzar de lo que planeás guardar cada mes.", "Keep your goals separate from what you plan to save each month.")}</p></div>
    <div className="finva-segmented goals-segmented" role="tablist"><button type="button" className={view === "goals" ? "active" : ""} onClick={() => setView("goals")}><Target size={17}/>{tx("Metas", "Goals")}</button><button type="button" className={view === "savings" ? "active" : ""} onClick={() => setView("savings")}><CalendarClock size={17}/>{tx("Ahorros programados", "Scheduled savings")}</button></div>
    {error && <div className="panel error">{error}</div>}
    {view === "goals" ? <GoalsList rows={rows} advanced={advanced} onCreate={() => setCreating(true)} onContribute={(goal) => { setContribution({...goal,kind:"goal"}); setContributionAmount(""); }} onEdit={setEdit} onDelete={(goal) => setDeleting({...goal,kind:"goal"})}/> : <SavingsList rows={savings} onCreate={() => setCreatingSavings(true)} onContribute={(item) => { setContribution({...item,kind:"savings"}); setContributionAmount(""); }} onEdit={setEditSavings} onDelete={(item) => setDeleting({...item,kind:"savings"})}/>}
    <FinvaFormSheet open={creating} eyebrow={tx("Nueva meta", "New goal")} title={tx("Agregar meta", "Add goal")} onClose={() => setCreating(false)}><form className="form finva-sheet-form" onSubmit={submitGoal}><GoalFields value={form} setValue={setForm} advanced={advanced}/><button className="finva-button finva-button-success">{tx("Guardar meta", "Save goal")}</button></form></FinvaFormSheet>
    <FinvaFormSheet open={Boolean(edit)} eyebrow={tx("Meta", "Goal")} title={tx("Editar meta", "Edit goal")} onClose={() => setEdit(null)}>{edit && <form className="form finva-sheet-form" onSubmit={saveGoal}><GoalFields value={edit} setValue={setEdit} advanced={advanced}/><label><span>{tx("Estado", "Status")}</span><select value={edit.status} onChange={(e) => setEdit({...edit,status:e.target.value})}><option value="active">{tx("Activa", "Active")}</option><option value="paused">{tx("Pausada", "Paused")}</option><option value="completed">{tx("Completada", "Completed")}</option></select></label><button className="finva-button finva-button-primary">{tx("Guardar cambios", "Save changes")}</button></form>}</FinvaFormSheet>
    <FinvaFormSheet open={creatingSavings} eyebrow={tx("Ahorro mensual", "Monthly savings")} title={tx("Programar ahorro", "Schedule savings")} onClose={() => setCreatingSavings(false)}><form className="form finva-sheet-form" onSubmit={submitSavings}><SavingsFields value={savingsForm} setValue={setSavingsForm}/><button className="finva-button finva-button-success">{tx("Guardar programación", "Save schedule")}</button></form></FinvaFormSheet>
    <FinvaFormSheet open={Boolean(editSavings)} eyebrow={tx("Ahorro mensual", "Monthly savings")} title={tx("Editar programación", "Edit schedule")} onClose={() => setEditSavings(null)}>{editSavings && <form className="form finva-sheet-form" onSubmit={saveSavings}><SavingsFields value={editSavings} setValue={setEditSavings}/><label><span>{tx("Estado", "Status")}</span><select value={editSavings.status} onChange={(e) => setEditSavings({...editSavings,status:e.target.value})}><option value="active">{tx("Activo", "Active")}</option><option value="paused">{tx("Pausado", "Paused")}</option><option value="completed">{tx("Completado", "Completed")}</option></select></label><button className="finva-button finva-button-primary">{tx("Guardar cambios", "Save changes")}</button></form>}</FinvaFormSheet>
    <AmountDialog open={Boolean(contribution)} title={contribution?.kind === "savings" ? tx("Registrar ahorro", "Record savings") : tx("Registrar aporte", "Record contribution")} description={contribution ? tx(`Sumar dinero a ${contribution.name}.`, `Add money to ${contribution.name}.`) : ""} value={contributionAmount} onValueChange={setContributionAmount} confirmLabel={tx("Registrar", "Record")} onConfirm={registerContribution} onClose={() => { if (!busyDialog) setContribution(null); }} busy={busyDialog} tone="success"/>
    <ConfirmDialog open={Boolean(deleting)} title={deleting?.kind === "savings" ? tx("Eliminar ahorro programado", "Delete scheduled savings") : tx("Eliminar meta", "Delete goal")} description={deleting ? tx(`Se eliminará ${deleting.name}. Esta acción no se puede deshacer.`, `${deleting.name} will be deleted. This action cannot be undone.`) : ""} onConfirm={remove} onClose={() => { if (!busyDialog) setDeleting(null); }} busy={busyDialog}/>
  </section>;
}

function GoalsList({ rows, advanced, onCreate, onContribute, onEdit, onDelete }) {
  return <><button className="finva-add-strip goal" type="button" onClick={onCreate}><span><Target size={20}/></span><div><strong>{tx("Agregar meta", "Add goal")}</strong><small>{tx("Definí un objetivo y medí su progreso", "Set a target and track its progress")}</small></div><Plus size={19}/></button><div className="goal-grid content-first-grid">{rows.length ? rows.map((goal) => {
    const target = Math.max(Number(goal.target_amount) || 1,1), current = Number(goal.current_amount) || 0, progress = Math.min(current/target*100,100), needed = monthly(goal);
    return <article className="panel goal-card-basic compact-record-card" key={goal.id}><header><b>{goal.name}</b>{advanced && <small>{goal.priority}</small>}</header><progress max="100" value={progress}/><p>{progress.toFixed(1)}% · {money(current)} {tx("de", "of")} {money(target)}</p><div className="record-meta"><span>{tx("Faltan", "Remaining")} {money(Math.max(target-current,0))}</span>{advanced && <span>{needed == null ? tx("Agregá fecha para calcular aporte", "Add a date to calculate the contribution") : `${money(needed)}/${tx("mes", "month")}`}</span>}</div><div className="actions"><button className="finva-button finva-button-success" type="button" onClick={() => onContribute(goal)}>{tx("Registrar aporte", "Record contribution")}</button>{advanced && <button className="finva-button finva-button-secondary" type="button" onClick={() => onEdit({...goal})}>{tx("Editar", "Edit")}</button>}<button className="finva-button finva-button-danger" type="button" onClick={() => onDelete(goal)}>{tx("Eliminar", "Delete")}</button></div></article>;
  }) : <div className="panel finva-empty-state">{tx("Todavía no creaste metas.", "You haven't created any goals yet.")}</div>}</div></>;
}

function SavingsList({ rows, onCreate, onContribute, onEdit, onDelete }) {
  return <><button className="finva-add-strip savings" type="button" onClick={onCreate}><span><CalendarClock size={20}/></span><div><strong>{tx("Programar ahorro", "Schedule savings")}</strong><small>{tx("Elegí cuánto guardar por mes y hasta cuándo", "Choose how much to save each month and until when")}</small></div><Plus size={19}/></button><div className="goal-grid content-first-grid">{rows.length ? rows.map((item) => {
    const months = monthsInclusive(item.start_date,item.end_date), planned = Number(item.monthly_amount)*months, saved = Number(item.saved_amount) || 0, progress = planned ? Math.min(saved/planned*100,100) : 0;
    return <article className="panel goal-card-basic compact-record-card savings-plan-card" key={item.id}><header><b>{item.name}</b><small>{item.status === "active" ? tx("Activo", "Active") : item.status === "paused" ? tx("Pausado", "Paused") : tx("Completado", "Completed")}</small></header><progress max="100" value={progress}/><p>{money(item.monthly_amount)}/{tx("mes", "month")} · {months} {months === 1 ? tx("mes", "month") : tx("meses", "months")}</p><div className="record-meta"><span>{money(saved)} {tx("ahorrado", "saved")}</span><span>{tx("Plan", "Plan")}: {money(planned)} {tx("hasta", "until")} {item.end_date}</span></div><div className="actions"><button className="finva-button finva-button-success" type="button" onClick={() => onContribute(item)}>{tx("Registrar ahorro", "Record savings")}</button><button className="finva-button finva-button-secondary" type="button" onClick={() => onEdit({...item})}>{tx("Editar", "Edit")}</button><button className="finva-button finva-button-danger" type="button" onClick={() => onDelete(item)}>{tx("Eliminar", "Delete")}</button></div></article>;
  }) : <div className="panel finva-empty-state">{tx("Todavía no programaste ahorros mensuales.", "You haven't scheduled monthly savings yet.")}</div>}</div></>;
}
