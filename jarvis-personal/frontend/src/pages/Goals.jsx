import { useEffect, useState } from "react";
import { Calendar, Edit3, RefreshCw, Save, Target, X } from "lucide-react";
import { getGoals, updateGoal } from "../services/jarvisApi";

const formatCRC = (value = 0) =>
  new Intl.NumberFormat("es-CR", {
    style: "currency",
    currency: "CRC",
    maximumFractionDigits: 0,
  }).format(Number(value) || 0);

const priorityLabels = {
  low: "BAJA",
  medium: "MEDIA",
  high: "ALTA",
  critical: "PRIORITARIA",
};

export default function Goals() {
  const [goals, setGoals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({});

  const loadGoals = async () => {
    try {
      setLoading(true);
      setError("");
      const data = await getGoals();
      setGoals(Array.isArray(data) ? data : []);
    } catch (loadError) {
      console.error(loadError);
      setError(loadError.message || "No pude cargar las metas.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGoals();
  }, []);

  const calculateProgress = (goal) => {
    if (!goal.target_amount) return 0;
    return Math.min(100, Math.round((Number(goal.current_amount || 0) / Number(goal.target_amount)) * 100));
  };

  const startEdit = (goal) => {
    setEditingId(goal.id);
    setForm({
      name: goal.name || "",
      target_amount: goal.target_amount || 0,
      current_amount: goal.current_amount || 0,
      target_date: goal.target_date || "",
      priority: goal.priority || "medium",
      status: goal.status || "active",
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setForm({});
  };

  const saveGoal = async (goalId) => {
    setSaving(true);
    setError("");
    try {
      await updateGoal(goalId, {
        ...form,
        target_amount: Number(form.target_amount) || 0,
        current_amount: Number(form.current_amount) || 0,
        target_date: form.target_date || null,
      });
      cancelEdit();
      await loadGoals();
    } catch (saveError) {
      console.error(saveError);
      setError(saveError.message || "No pude guardar la meta.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <section className="data-page">
        <div className="empty-state full-width">
          <div className="jarvis-loader"></div>
          <h3>Cargando metas...</h3>
          <p>Estoy consultando tus metas financieras reales.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="data-page">
      <div className="page-section-header">
        <div>
          <h2>Metas Estratégicas</h2>
          <p>Viajes, ahorro, deuda y objetivos personales.</p>
        </div>

        <button className="hud-action-button" onClick={loadGoals}>
          <RefreshCw size={16} />
          Actualizar
        </button>
      </div>

      {error && <div className="inline-error">{error}</div>}

      {goals.length === 0 ? (
        <div className="empty-state full-width">
          <Target size={36} />
          <h3>No hay metas activas todavía</h3>
          <p>Cuando agreguemos metas desde la interfaz o por chat, se mostrarán aquí con progreso, fecha objetivo y prioridad.</p>
        </div>
      ) : (
        <div className="goals-grid">
          {goals.map((goal) => {
            const progress = calculateProgress(goal);
            const remaining = Math.max(Number(goal.target_amount || 0) - Number(goal.current_amount || 0), 0);
            const isEditing = editingId === goal.id;

            return (
              <div key={goal.id} className={`goal-card ${goal.priority || "medium"}`}>
                <div className="goal-header">
                  <Target size={20} />
                  <span>{priorityLabels[goal.priority] || "MEDIA"}</span>
                </div>

                {isEditing ? (
                  <div className="goal-edit-form">
                    <label>Nombre<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
                    <label>Monto objetivo<input type="number" value={form.target_amount} onChange={(event) => setForm({ ...form, target_amount: event.target.value })} /></label>
                    <label>Monto actual<input type="number" value={form.current_amount} onChange={(event) => setForm({ ...form, current_amount: event.target.value })} /></label>
                    <label>Fecha objetivo<input type="date" value={form.target_date || ""} onChange={(event) => setForm({ ...form, target_date: event.target.value })} /></label>
                    <label>Importancia
                      <select value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value })}>
                        <option value="low">Baja</option>
                        <option value="medium">Media</option>
                        <option value="high">Alta</option>
                        <option value="critical">Prioritaria</option>
                      </select>
                    </label>
                    <label>Estado
                      <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
                        <option value="active">Activa</option>
                        <option value="paused">Pausada</option>
                        <option value="completed">Completada</option>
                      </select>
                    </label>
                    <div className="goal-edit-actions">
                      <button className="hud-action-button success" onClick={() => saveGoal(goal.id)} disabled={saving}><Save size={15} /> Guardar</button>
                      <button className="ghost-button" onClick={cancelEdit} disabled={saving}><X size={15} /> Cancelar</button>
                    </div>
                  </div>
                ) : (
                  <>
                    <h3>{goal.name}</h3>
                    <div className="goal-progress"><div className="goal-progress-fill" style={{ width: `${progress}%` }} /></div>
                    <div className="goal-percent">{progress}%</div>
                    <div className="goal-money">{formatCRC(goal.current_amount)} / {formatCRC(goal.target_amount)}</div>
                    <div className="goal-remaining">Faltan {formatCRC(remaining)}</div>
                    <div className="goal-date"><Calendar size={14} />{goal.target_date || "Sin fecha"}</div>
                    <button className="goal-edit-button" onClick={() => startEdit(goal)}><Edit3 size={15} /> Editar</button>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
