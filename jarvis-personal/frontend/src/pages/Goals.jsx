import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Edit3, Plus, RefreshCw, Sparkles } from "lucide-react";
import { createGoal, getGoals, updateGoal } from "../services/jarvisApi";
import { deviceLanguage, localeTag } from "../lib/locale";
import { JarvisGlassCard, JarvisScreen } from "../products/jarvis/components/JarvisScreen";

const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;
const formatCRC = (value = 0) => new Intl.NumberFormat(localeTag(language), { style: "currency", currency: "CRC", maximumFractionDigits: 0 }).format(Number(value) || 0);
const emptyGoal = { name: "", target_amount: "", current_amount: "", target_date: "", priority: "medium", goal_type: "general", status: "active", funding_order: 100, is_selected: true };
const priorityLabels = { low: tx("BAJA", "LOW"), medium: tx("MEDIA", "MEDIUM"), high: tx("ALTA", "HIGH"), critical: tx("PRIORITARIA", "PRIORITY") };

const goalPayload = (form) => ({
  ...form,
  target_amount: Number(form.target_amount) || 0,
  current_amount: Number(form.current_amount) || 0,
  target_date: form.target_date || null,
  funding_order: Number(form.funding_order) || 100,
  alternative_group: form.alternative_group || null,
  depends_on_group: form.depends_on_group || null,
});

export default function Goals() {
  const [goals, setGoals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyGoal);

  const loadGoals = useCallback(async () => {
    try {
      setLoading(true); setError("");
      const data = await getGoals();
      setGoals(Array.isArray(data) ? data : []);
    } catch (loadError) {
      setError(loadError.message || tx("No pude cargar las metas.", "Goals could not be loaded."));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadGoals(); }, [loadGoals]);

  const summary = useMemo(() => {
    const target = goals.reduce((sum, goal) => sum + Number(goal.target_amount || 0), 0);
    const current = goals.reduce((sum, goal) => sum + Number(goal.current_amount || 0), 0);
    return { target, current, progress: target ? Math.min(100, Math.round(current / target * 100)) : 0 };
  }, [goals]);

  const openCreate = () => { setForm({ ...emptyGoal }); setEditingId("new"); setError(""); };
  const openEdit = (goal) => { setForm({ ...emptyGoal, ...goal, target_date: goal.target_date || "" }); setEditingId(goal.id); setError(""); };
  const closeForm = () => { setEditingId(null); setForm({ ...emptyGoal }); };

  const saveGoal = async (event) => {
    event.preventDefault(); setSaving(true); setError("");
    try {
      if (editingId === "new") await createGoal(goalPayload(form));
      else await updateGoal(editingId, goalPayload(form));
      closeForm(); await loadGoals();
    } catch (saveError) {
      setError(saveError.message || tx("No pude guardar la meta.", "The goal could not be saved."));
    } finally { setSaving(false); }
  };

  if (loading) return <section className="page"><div className="hud-card">{tx("Cargando metas...", "Loading goals...")}</div></section>;

  if (editingId !== null) {
    return (
      <JarvisScreen eyebrow={tx("Metas", "Goals")} title={editingId === "new" ? tx("Nueva meta", "New goal") : tx("Editar meta", "Edit goal")} subtitle={tx("Definí el objetivo y JARVIS arma la ruta", "Set the objective and JARVIS builds the path")} className="goals-screen goal-form-screen" actions={<button className="jarvis-circle-button" type="button" onClick={closeForm} aria-label={tx("Volver", "Back")}><ArrowLeft size={19} /></button>}>
        {error && <div className="jarvis-inline-message is-warning">{error}</div>}
        <form className="goal-form" onSubmit={saveGoal}>
          <GoalField label={tx("Nombre", "Name")}><input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={tx("Ej. Viaje Japón", "E.g. Japan trip")} /></GoalField>
          <GoalField label={tx("Monto objetivo", "Target amount")}><input required type="number" min="1" inputMode="decimal" value={form.target_amount} onChange={(e) => setForm({ ...form, target_amount: e.target.value })} placeholder="₡0" /></GoalField>
          <GoalField label={tx("Monto actual", "Current amount")}><input type="number" min="0" inputMode="decimal" value={form.current_amount} onChange={(e) => setForm({ ...form, current_amount: e.target.value })} placeholder="₡0" /></GoalField>
          <GoalField label={tx("Fecha objetivo", "Target date")}><input type="date" value={form.target_date} onChange={(e) => setForm({ ...form, target_date: e.target.value })} /></GoalField>
          <GoalField label={tx("Prioridad", "Priority")}><select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}><option value="low">{tx("Baja", "Low")}</option><option value="medium">{tx("Media", "Medium")}</option><option value="high">{tx("Alta", "High")}</option><option value="critical">{tx("Prioritaria", "Priority")}</option></select></GoalField>
          <GoalField label={tx("Tipo", "Type")}><select value={form.goal_type} onChange={(e) => setForm({ ...form, goal_type: e.target.value })}><option value="general">{tx("General", "General")}</option><option value="travel">{tx("Viaje", "Travel")}</option><option value="vehicle">{tx("Vehículo", "Vehicle")}</option><option value="purchase">{tx("Compra", "Purchase")}</option></select></GoalField>
          <JarvisGlassCard className="goal-route-note"><Sparkles size={18} /><span>{tx("JARVIS financiará esta meta según su prioridad, sin usar dinero ya comprometido.", "JARVIS will fund this goal by priority without using committed money.")}</span></JarvisGlassCard>
          <button className="jarvis-primary-button" type="submit" disabled={saving}>{saving ? tx("Guardando...", "Saving...") : tx("Guardar meta", "Save goal")}</button>
        </form>
      </JarvisScreen>
    );
  }

  return (
    <JarvisScreen eyebrow={tx("Metas", "Goals")} title={tx("Metas estratégicas", "Strategic goals")} subtitle={tx("Objetivos, prioridades y progreso", "Objectives, priorities and progress")} className="goals-screen" actions={<button className="jarvis-circle-button" type="button" onClick={loadGoals} aria-label={tx("Actualizar", "Refresh")}><RefreshCw size={18} /></button>}>
      {error && <div className="jarvis-inline-message is-warning">{error}</div>}
      <JarvisGlassCard className="goals-summary">
        <span>{tx("Progreso global", "Global progress")}</span>
        <div><strong>{summary.progress}%</strong><small>{formatCRC(summary.current)} {tx("de", "of")} {formatCRC(summary.target)}</small></div>
        <GoalProgress value={summary.progress} />
      </JarvisGlassCard>
      <div className="goals-list">
        {goals.length === 0 ? <JarvisGlassCard className="jarvis-empty-state">{tx("Todavía no creaste metas.", "You have not created any goals yet.")}</JarvisGlassCard> : goals.map((goal) => {
          const target = Number(goal.target_amount || 0); const current = Number(goal.current_amount || 0);
          const progress = target ? Math.min(100, Math.round(current / target * 100)) : 0;
          return <JarvisGlassCard as="button" type="button" className={`goal-summary-card is-${goal.priority || "medium"}`} key={goal.id} onClick={() => openEdit(goal)}>
            <span>{priorityLabels[goal.priority] || priorityLabels.medium}</span>
            <div><strong>{goal.name}</strong><b>{progress}%</b></div>
            <small>{formatCRC(current)} / {formatCRC(target)}</small>
            <GoalProgress value={progress} />
            <Edit3 className="goal-summary-card__edit" size={14} />
          </JarvisGlassCard>;
        })}
      </div>
      <button className="jarvis-primary-button goals-add-button" type="button" onClick={openCreate}><Plus size={18} />{tx("Nueva meta", "New goal")}</button>
    </JarvisScreen>
  );
}

function GoalField({ label, children }) { return <label className="goal-form-field"><span>{label}</span>{children}</label>; }
function GoalProgress({ value }) { return <div className="goal-progress-track"><span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>; }
