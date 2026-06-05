import { useEffect, useState } from "react";
import { Calendar, RefreshCw, Target } from "lucide-react";
import { getGoals } from "../services/jarvisApi";

const formatCRC = (value = 0) =>
  new Intl.NumberFormat("es-CR", {
    style: "currency",
    currency: "CRC",
    maximumFractionDigits: 0,
  }).format(Number(value) || 0);

export default function Goals() {
  const [goals, setGoals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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

    return Math.min(
      100,
      Math.round((Number(goal.current_amount || 0) / Number(goal.target_amount)) * 100)
    );
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
          <p>
            Cuando agreguemos metas desde la interfaz o por chat, se mostrarán
            aquí con progreso, fecha objetivo y prioridad.
          </p>
        </div>
      ) : (
        <div className="goals-grid">
          {goals.map((goal) => {
            const progress = calculateProgress(goal);
            const remaining = Math.max(
              Number(goal.target_amount || 0) - Number(goal.current_amount || 0),
              0
            );

            return (
              <div key={goal.id} className="goal-card">
                <div className="goal-header">
                  <Target size={20} />
                  <span>{goal.priority?.toUpperCase() || "MEDIA"}</span>
                </div>

                <h3>{goal.name}</h3>

                <div className="goal-progress">
                  <div
                    className="goal-progress-fill"
                    style={{
                      width: `${progress}%`,
                    }}
                  />
                </div>

                <div className="goal-percent">{progress}%</div>

                <div className="goal-money">
                  {formatCRC(goal.current_amount)}
                  {" / "}
                  {formatCRC(goal.target_amount)}
                </div>

                <div className="goal-remaining">
                  Faltan {formatCRC(remaining)}
                </div>

                <div className="goal-date">
                  <Calendar size={14} />
                  {goal.target_date || "Sin fecha"}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
