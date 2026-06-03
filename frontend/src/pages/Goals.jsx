import { useEffect, useState } from "react";
import { Target, Calendar } from "lucide-react";
import { getGoals } from "../services/jarvisApi";

export default function Goals() {
  const [goals, setGoals] = useState([]);

  useEffect(() => {
  const loadGoals = async () => {
    try {
      const data = await getGoals();
      setGoals(data);
    } catch (error) {
      console.error(error);
    }
  };

  loadGoals();
}, []);

  const calculateProgress = (goal) => {
    if (!goal.target_amount) return 0;

    return Math.min(
      100,
      Math.round(
        (goal.current_amount / goal.target_amount) * 100
      )
    );
  };

  return (
    <>
      <h2>Metas Estratégicas</h2>
      <p className="muted">
        Viajes, ahorro, deuda y objetivos personales.
      </p>

      <div className="goals-grid">
        {goals.map((goal) => {
          const progress = calculateProgress(goal);

          return (
            <div
              key={goal.id}
              className="goal-card"
            >
              <div className="goal-header">
                <Target size={20} />

                <span>
                  {goal.priority?.toUpperCase()}
                </span>
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

              <div className="goal-percent">
                {progress}%
              </div>

              <div className="goal-money">
                ₡{goal.current_amount?.toLocaleString()}
                {" / "}
                ₡{goal.target_amount?.toLocaleString()}
              </div>

              <div className="goal-remaining">
                Faltan ₡
                {(
                  goal.target_amount -
                  goal.current_amount
                ).toLocaleString()}
              </div>

              <div className="goal-date">
                <Calendar size={14} />
                {goal.target_date}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}