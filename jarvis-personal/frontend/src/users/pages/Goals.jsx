import { useEffect, useState } from "react";
import { Plus, Target } from "lucide-react";
import { contributeGoal, createGoal, deleteGoal, getGoals, updateGoal } from "../services/jarvisApi";
import { AmountDialog, ConfirmDialog } from "../components/FinvaDialog";
import FinvaFormSheet from "../components/FinvaFormSheet";

const money = (value) => new Intl.NumberFormat("es-CR", { style:"currency", currency:"CRC", maximumFractionDigits:0 }).format(Number(value) || 0);
const empty = { name:"", target_amount:"", current_amount:0, target_date:"", priority:"medium", status:"active" };
const monthly = (goal) => {
  if (!goal.target_date) return null;
  const now = new Date();
  const end = new Date(`${goal.target_date}T12:00:00`);
  const months = Math.max((end.getFullYear()-now.getFullYear())*12+end.getMonth()-now.getMonth(),1);
  return Math.max((Number(goal.target_amount)-Number(goal.current_amount))/months,0);
};

function GoalFields({ value, setValue, advanced }) {
  return <div className="finva-compact-fields">
    <label><span>Nombre de la meta</span><input required placeholder="Ej. Fondo de emergencia" value={value.name} onChange={(e) => setValue({...value,name:e.target.value})}/></label>
    <label><span>Monto objetivo</span><input required type="number" inputMode="decimal" min="0.01" placeholder="₡0" value={value.target_amount} onChange={(e) => setValue({...value,target_amount:e.target.value})}/></label>
    {advanced && <>
      <label><span>Ya ahorrado</span><input type="number" inputMode="decimal" min="0" placeholder="₡0" value={value.current_amount} onChange={(e) => setValue({...value,current_amount:e.target.value})}/></label>
      <label><span>Fecha objetivo</span><input type="date" value={value.target_date || ""} onChange={(e) => setValue({...value,target_date:e.target.value})}/></label>
      <label><span>Prioridad</span><select value={value.priority} onChange={(e) => setValue({...value,priority:e.target.value})}><option value="low">Baja</option><option value="medium">Media</option><option value="high">Alta</option><option value="critical">Prioritaria</option></select></label>
    </>}
  </div>;
}

export default function Goals({ plan = "free" }) {
  const advanced = plan !== "free";
  const [rows,setRows] = useState([]);
  const [form,setForm] = useState(empty);
  const [creating,setCreating] = useState(false);
  const [edit,setEdit] = useState(null);
  const [contribution,setContribution] = useState(null);
  const [contributionAmount,setContributionAmount] = useState("");
  const [deleting,setDeleting] = useState(null);
  const [busyDialog,setBusyDialog] = useState(false);
  const [error,setError] = useState("");

  const run = async (fn) => {
    setError("");
    try { return await fn(); }
    catch (err) { setError(err.message); return null; }
  };
  const load = () => run(async () => setRows(await getGoals()));
  useEffect(() => { load(); }, []);
  const payload = (value) => ({...value,target_amount:Number(value.target_amount),current_amount:Number(value.current_amount || 0),target_date:value.target_date || null});
  const submit = async (event) => {
    event.preventDefault();
    if (await run(() => createGoal(payload(form)))) { setForm(empty); setCreating(false); load(); }
  };
  const save = async (event) => {
    event.preventDefault();
    if (await run(() => updateGoal(edit.id,payload(edit)))) { setEdit(null); load(); }
  };
  const registerContribution = async () => {
    setBusyDialog(true);
    const saved = await run(() => contributeGoal(contribution.id,{amount:Number(contributionAmount)}));
    setBusyDialog(false);
    if (saved) { setContribution(null); setContributionAmount(""); load(); }
  };
  const removeGoal = async () => {
    setBusyDialog(true);
    const removed = await run(() => deleteGoal(deleting.id));
    setBusyDialog(false);
    if (removed) { setDeleting(null); load(); }
  };

  return <section className="content-first-page">
    <div className="hero"><span>{advanced ? "BASIC 04" : "FREE 05"}</span><h1>Metas de ahorro</h1><p>{advanced ? "Aportes y ritmo necesario para llegar a tiempo." : "Objetivo, aportes manuales y progreso, sin estrategia."}</p></div>
    {error && <div className="panel error">{error}</div>}
    <button className="finva-add-strip goal" type="button" onClick={() => setCreating(true)}><span><Target size={20}/></span><div><strong>Agregar meta</strong><small>Creá un nuevo objetivo de ahorro</small></div><Plus size={19}/></button>

    <div className="goal-grid content-first-grid">{rows.length ? rows.map((goal) => {
      const target = Math.max(Number(goal.target_amount) || 1,1);
      const current = Number(goal.current_amount) || 0;
      const progress = Math.min(current/target*100,100);
      const needed = monthly(goal);
      return <article className="panel goal-card-basic compact-record-card" key={goal.id}>
        <header><b>{goal.name}</b>{advanced && <small>{goal.priority}</small>}</header>
        <progress max="100" value={progress}/>
        <p>{progress.toFixed(1)}% · {money(current)} de {money(target)}</p>
        <div className="record-meta"><span>Faltan {money(Math.max(target-current,0))}</span>{advanced && <span>{needed == null ? "Agregá fecha para calcular aporte" : `${money(needed)}/mes`}</span>}</div>
        <div className="actions">
          <button className="finva-button finva-button-success" type="button" onClick={() => { setContribution(goal); setContributionAmount(""); }}>Registrar aporte</button>
          {advanced && <button className="finva-button finva-button-secondary" type="button" onClick={() => setEdit({...goal})}>Editar</button>}
          <button className="finva-button finva-button-danger" type="button" onClick={() => setDeleting(goal)}>Eliminar</button>
        </div>
      </article>;
    }) : <div className="panel finva-empty-state">Todavía no creaste metas de ahorro.</div>}</div>

    <FinvaFormSheet open={creating} eyebrow="Nueva meta" title="Agregar meta" onClose={() => setCreating(false)}>
      <form className="form finva-sheet-form" onSubmit={submit}><GoalFields value={form} setValue={setForm} advanced={advanced}/><button className="finva-button finva-button-success">Guardar meta</button></form>
    </FinvaFormSheet>
    <FinvaFormSheet open={Boolean(edit)} eyebrow="Meta" title="Editar meta" onClose={() => setEdit(null)}>
      {edit && <form className="form finva-sheet-form" onSubmit={save}><GoalFields value={edit} setValue={setEdit} advanced={advanced}/><label><span>Estado</span><select value={edit.status} onChange={(e) => setEdit({...edit,status:e.target.value})}><option value="active">Activa</option><option value="paused">Pausada</option><option value="completed">Completada</option></select></label><button className="finva-button finva-button-primary">Guardar cambios</button></form>}
    </FinvaFormSheet>
    <AmountDialog open={Boolean(contribution)} title="Registrar aporte" description={contribution ? `Sumar dinero a ${contribution.name}.` : ""} value={contributionAmount} onValueChange={setContributionAmount} confirmLabel="Registrar aporte" onConfirm={registerContribution} onClose={() => { if (!busyDialog) setContribution(null); }} busy={busyDialog} tone="success"/>
    <ConfirmDialog open={Boolean(deleting)} title="Eliminar meta" description={deleting ? `Se eliminará ${deleting.name}. Esta acción no se puede deshacer.` : ""} onConfirm={removeGoal} onClose={() => { if (!busyDialog) setDeleting(null); }} busy={busyDialog}/>
  </section>;
}
