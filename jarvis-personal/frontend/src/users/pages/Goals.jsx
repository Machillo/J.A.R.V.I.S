import { useEffect, useState } from "react";
import { CalendarClock, Plus, Target } from "lucide-react";
import { contributeGoal, contributeSavingsPlan, createGoal, createSavingsPlan, deleteGoal, deleteSavingsPlan, getGoals, getSavingsPlans, updateGoal, updateSavingsPlan } from "../services/jarvisApi";
import { AmountDialog, ConfirmDialog } from "../components/FinvaDialog";
import FinvaFormSheet from "../components/FinvaFormSheet";

const money = (value) => new Intl.NumberFormat("es-CR", { style:"currency", currency:"CRC", maximumFractionDigits:2 }).format(Number(value) || 0);
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
    <label><span>Nombre de la meta</span><input required placeholder="Ej. Viaje familiar" value={value.name} onChange={(e) => setValue({...value,name:e.target.value})}/></label>
    <label><span>Monto objetivo</span><input required type="number" inputMode="decimal" min="0.01" step="0.01" placeholder="₡0" value={value.target_amount} onChange={(e) => setValue({...value,target_amount:e.target.value})}/></label>
    {advanced && <>
      <label><span>Ya ahorrado</span><input type="number" inputMode="decimal" min="0" step="0.01" placeholder="₡0" value={value.current_amount} onChange={(e) => setValue({...value,current_amount:e.target.value})}/></label>
      <label><span>Fecha objetivo</span><input type="date" value={value.target_date || ""} onChange={(e) => setValue({...value,target_date:e.target.value})}/></label>
      <label><span>Prioridad</span><select value={value.priority} onChange={(e) => setValue({...value,priority:e.target.value})}><option value="low">Baja</option><option value="medium">Media</option><option value="high">Alta</option><option value="critical">Prioritaria</option></select></label>
    </>}
  </div>;
}

function SavingsFields({ value, setValue }) {
  return <div className="finva-compact-fields">
    <label><span>Nombre del ahorro</span><input required placeholder="Ej. Marchamo" value={value.name} onChange={(e) => setValue({...value,name:e.target.value})}/></label>
    <label><span>Monto por mes</span><input required type="number" inputMode="decimal" min="0.01" step="0.01" placeholder="₡0" value={value.monthly_amount} onChange={(e) => setValue({...value,monthly_amount:e.target.value})}/></label>
    <label><span>Ya tenés ahorrado</span><input type="number" inputMode="decimal" min="0" step="0.01" placeholder="₡0" value={value.saved_amount} onChange={(e) => setValue({...value,saved_amount:e.target.value})}/></label>
    <label><span>Empezar</span><input required type="date" value={value.start_date} onChange={(e) => setValue({...value,start_date:e.target.value})}/></label>
    <label><span>Ahorrar hasta</span><input required type="date" min={value.start_date || undefined} value={value.end_date} onChange={(e) => setValue({...value,end_date:e.target.value})}/></label>
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
    <div className="hero"><span>{advanced ? "BASIC 04" : "FREE 05"}</span><h1>Metas y ahorros</h1><p>Separá lo que querés alcanzar de lo que planeás guardar cada mes.</p></div>
    <div className="finva-segmented goals-segmented" role="tablist"><button type="button" className={view === "goals" ? "active" : ""} onClick={() => setView("goals")}><Target size={17}/>Metas</button><button type="button" className={view === "savings" ? "active" : ""} onClick={() => setView("savings")}><CalendarClock size={17}/>Ahorros programados</button></div>
    {error && <div className="panel error">{error}</div>}
    {view === "goals" ? <GoalsList rows={rows} advanced={advanced} onCreate={() => setCreating(true)} onContribute={(goal) => { setContribution({...goal,kind:"goal"}); setContributionAmount(""); }} onEdit={setEdit} onDelete={(goal) => setDeleting({...goal,kind:"goal"})}/> : <SavingsList rows={savings} onCreate={() => setCreatingSavings(true)} onContribute={(item) => { setContribution({...item,kind:"savings"}); setContributionAmount(""); }} onEdit={setEditSavings} onDelete={(item) => setDeleting({...item,kind:"savings"})}/>}
    <FinvaFormSheet open={creating} eyebrow="Nueva meta" title="Agregar meta" onClose={() => setCreating(false)}><form className="form finva-sheet-form" onSubmit={submitGoal}><GoalFields value={form} setValue={setForm} advanced={advanced}/><button className="finva-button finva-button-success">Guardar meta</button></form></FinvaFormSheet>
    <FinvaFormSheet open={Boolean(edit)} eyebrow="Meta" title="Editar meta" onClose={() => setEdit(null)}>{edit && <form className="form finva-sheet-form" onSubmit={saveGoal}><GoalFields value={edit} setValue={setEdit} advanced={advanced}/><label><span>Estado</span><select value={edit.status} onChange={(e) => setEdit({...edit,status:e.target.value})}><option value="active">Activa</option><option value="paused">Pausada</option><option value="completed">Completada</option></select></label><button className="finva-button finva-button-primary">Guardar cambios</button></form>}</FinvaFormSheet>
    <FinvaFormSheet open={creatingSavings} eyebrow="Ahorro mensual" title="Programar ahorro" onClose={() => setCreatingSavings(false)}><form className="form finva-sheet-form" onSubmit={submitSavings}><SavingsFields value={savingsForm} setValue={setSavingsForm}/><button className="finva-button finva-button-success">Guardar programación</button></form></FinvaFormSheet>
    <FinvaFormSheet open={Boolean(editSavings)} eyebrow="Ahorro mensual" title="Editar programación" onClose={() => setEditSavings(null)}>{editSavings && <form className="form finva-sheet-form" onSubmit={saveSavings}><SavingsFields value={editSavings} setValue={setEditSavings}/><label><span>Estado</span><select value={editSavings.status} onChange={(e) => setEditSavings({...editSavings,status:e.target.value})}><option value="active">Activo</option><option value="paused">Pausado</option><option value="completed">Completado</option></select></label><button className="finva-button finva-button-primary">Guardar cambios</button></form>}</FinvaFormSheet>
    <AmountDialog open={Boolean(contribution)} title={contribution?.kind === "savings" ? "Registrar ahorro" : "Registrar aporte"} description={contribution ? `Sumar dinero a ${contribution.name}.` : ""} value={contributionAmount} onValueChange={setContributionAmount} confirmLabel="Registrar" onConfirm={registerContribution} onClose={() => { if (!busyDialog) setContribution(null); }} busy={busyDialog} tone="success"/>
    <ConfirmDialog open={Boolean(deleting)} title={deleting?.kind === "savings" ? "Eliminar ahorro programado" : "Eliminar meta"} description={deleting ? `Se eliminará ${deleting.name}. Esta acción no se puede deshacer.` : ""} onConfirm={remove} onClose={() => { if (!busyDialog) setDeleting(null); }} busy={busyDialog}/>
  </section>;
}

function GoalsList({ rows, advanced, onCreate, onContribute, onEdit, onDelete }) {
  return <><button className="finva-add-strip goal" type="button" onClick={onCreate}><span><Target size={20}/></span><div><strong>Agregar meta</strong><small>Definí un objetivo y medí su progreso</small></div><Plus size={19}/></button><div className="goal-grid content-first-grid">{rows.length ? rows.map((goal) => {
    const target = Math.max(Number(goal.target_amount) || 1,1), current = Number(goal.current_amount) || 0, progress = Math.min(current/target*100,100), needed = monthly(goal);
    return <article className="panel goal-card-basic compact-record-card" key={goal.id}><header><b>{goal.name}</b>{advanced && <small>{goal.priority}</small>}</header><progress max="100" value={progress}/><p>{progress.toFixed(1)}% · {money(current)} de {money(target)}</p><div className="record-meta"><span>Faltan {money(Math.max(target-current,0))}</span>{advanced && <span>{needed == null ? "Agregá fecha para calcular aporte" : `${money(needed)}/mes`}</span>}</div><div className="actions"><button className="finva-button finva-button-success" type="button" onClick={() => onContribute(goal)}>Registrar aporte</button>{advanced && <button className="finva-button finva-button-secondary" type="button" onClick={() => onEdit({...goal})}>Editar</button>}<button className="finva-button finva-button-danger" type="button" onClick={() => onDelete(goal)}>Eliminar</button></div></article>;
  }) : <div className="panel finva-empty-state">Todavía no creaste metas.</div>}</div></>;
}

function SavingsList({ rows, onCreate, onContribute, onEdit, onDelete }) {
  return <><button className="finva-add-strip savings" type="button" onClick={onCreate}><span><CalendarClock size={20}/></span><div><strong>Programar ahorro</strong><small>Elegí cuánto guardar por mes y hasta cuándo</small></div><Plus size={19}/></button><div className="goal-grid content-first-grid">{rows.length ? rows.map((item) => {
    const months = monthsInclusive(item.start_date,item.end_date), planned = Number(item.monthly_amount)*months, saved = Number(item.saved_amount) || 0, progress = planned ? Math.min(saved/planned*100,100) : 0;
    return <article className="panel goal-card-basic compact-record-card savings-plan-card" key={item.id}><header><b>{item.name}</b><small>{item.status === "active" ? "Activo" : item.status === "paused" ? "Pausado" : "Completado"}</small></header><progress max="100" value={progress}/><p>{money(item.monthly_amount)}/mes · {months} {months === 1 ? "mes" : "meses"}</p><div className="record-meta"><span>{money(saved)} ahorrado</span><span>Plan: {money(planned)} hasta {item.end_date}</span></div><div className="actions"><button className="finva-button finva-button-success" type="button" onClick={() => onContribute(item)}>Registrar ahorro</button><button className="finva-button finva-button-secondary" type="button" onClick={() => onEdit({...item})}>Editar</button><button className="finva-button finva-button-danger" type="button" onClick={() => onDelete(item)}>Eliminar</button></div></article>;
  }) : <div className="panel finva-empty-state">Todavía no programaste ahorros mensuales.</div>}</div></>;
}
