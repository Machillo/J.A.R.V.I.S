import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CircleDollarSign,
  Target,
  Wallet,
} from "lucide-react";

const formatCRC = (value = 0) =>
  new Intl.NumberFormat("es-CR", {
    style: "currency",
    currency: "CRC",
    maximumFractionDigits: 0,
  }).format(value);

function MiniLine({ type = "up" }) {
  const points =
    type === "up"
      ? "0,35 18,28 33,32 50,20 70,24 90,10"
      : "0,18 18,12 33,20 50,17 70,28 90,35";

  return (
    <svg className={`mini-line ${type}`} viewBox="0 0 90 45">
      <polyline points={points} fill="none" strokeWidth="2" />
    </svg>
  );
}

function ProgressRing({ value = 0, color = "cyan" }) {
  const safeValue = Math.min(Math.max(value, 0), 100);

  return (
    <div className={`progress-ring ${color}`}>
      <div
        className="progress-ring-inner"
        style={{
          background: `conic-gradient(var(--ring-color) ${safeValue}%, rgba(255,255,255,.08) 0)`,
        }}
      >
        <div className="progress-ring-center">{safeValue}%</div>
      </div>
    </div>
  );
}

export default function Dashboard({ dashboard }) {
  const summary = dashboard?.summary;
  const cards = dashboard?.cards || [];
  const alerts = dashboard?.alerts || [];
  const topDebts = dashboard?.top_debts || [];
  const goal = summary?.goals?.most_urgent_goal;

  const income = summary?.income?.monthly_net_income || 0;
  const available = summary?.cashflow?.available_cash || 0;
  const debtTotal = summary?.debts?.total || 0;
  const netWorth = summary?.assets?.net_worth || 0;

  const goalProgress = goal
    ? Math.round((goal.current_amount / goal.target_amount) * 100)
    : 0;

  const debtProgress = debtTotal > 0 ? 71 : 0;

  return (
    <section className="dashboard-page">
      <div className="cards-grid">
        <article className="hud-card glow-green">
          <div className="card-header">
            <span>INGRESO NETO</span>
            <ArrowUpRight size={18} />
          </div>

          <MiniLine type="up" />

          <h2>{formatCRC(income)}</h2>
          <p>Sueldo neto proyectado</p>
        </article>

        <article className="hud-card glow-red">
          <div className="card-header">
            <span>DEUDA TOTAL</span>
            <ArrowDownRight size={18} />
          </div>

          <MiniLine type="down" />

          <h2>{formatCRC(debtTotal)}</h2>
          <p>Pasivos registrados</p>
        </article>

        <article className="hud-card">
          <div className="card-header">
            <span>META PRINCIPAL</span>
            <Target size={18} />
          </div>

          <div className="ring-row">
            <ProgressRing value={goalProgress} />
            <div>
              <h2>{goal?.name || "Sin meta"}</h2>
              <p>
                {goal
                  ? `${formatCRC(goal.current_amount)} de ${formatCRC(goal.target_amount)}`
                  : "Sin meta activa"}
              </p>
            </div>
          </div>
        </article>

        <article className="hud-card glow-red">
          <div className="card-header">
            <span>DEUDAS</span>
            <AlertTriangle size={18} />
          </div>

          <div className="ring-row">
            <ProgressRing value={debtProgress} color="red" />
            <div>
              <h2>{formatCRC(debtTotal)}</h2>
              <p>Pago mensual: {formatCRC(summary?.debts?.monthly_payments || 0)}</p>
            </div>
          </div>
        </article>

        <article className="hud-card wide-balance">
          <div className="card-header">
            <span>SALDO DISPONIBLE</span>
            <Wallet size={18} />
          </div>

          <h2>{formatCRC(available)}</h2>
          <p>Disponible estimado después de gastos y deudas</p>
        </article>
      </div>

      <div className="dashboard-grid">
        <article className="hud-panel large">
          <div className="panel-title">
            <div>
              <h3>INGRESOS VS GASTOS</h3>
              <p>Últimos meses</p>
            </div>
            <span>6 MESES</span>
          </div>

          <div className="bar-chart">
            {["ENE", "FEB", "MAR", "ABR", "MAY"].map((month, index) => (
              <div className="bar-group" key={month}>
                <div className="bars">
                  <span style={{ height: `${50 + index * 8}%` }}></span>
                  <span style={{ height: `${35 + index * 10}%` }}></span>
                </div>
                <small>{month}</small>
              </div>
            ))}
          </div>

          <div className="legend">
            <span className="cyan"></span> Ingresos
            <span className="red"></span> Gastos
          </div>
        </article>

        <article className="hud-panel">
          <div className="panel-title">
            <div>
              <h3>ALERTAS</h3>
              <p>Prioridad actual</p>
            </div>
          </div>

          <div className="alert-list">
            {alerts.map((alert, index) => (
              <div className={`alert-item ${alert.level}`} key={index}>
                <AlertTriangle size={18} />
                <span>{alert.message}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="hud-panel">
          <div className="panel-title">
            <div>
              <h3>RESUMEN DE DEUDAS</h3>
              <p>Top deudas</p>
            </div>
          </div>

          <div className="debt-list">
            {topDebts.map((debt) => (
              <div className="debt-item" key={debt.id}>
                <div>
                  <strong>{debt.name}</strong>
                  <span>{formatCRC(debt.remaining_amount)}</span>
                </div>

                <div className="debt-bar">
                  <span
                    style={{
                      width: `${Math.min(
                        (debt.remaining_amount / debtTotal) * 100,
                        100
                      )}%`,
                    }}
                  ></span>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="hud-panel">
          <div className="panel-title">
            <div>
              <h3>NET WORTH</h3>
              <p>Patrimonio neto</p>
            </div>
            <CircleDollarSign size={20} />
          </div>

          <h2 className={netWorth < 0 ? "danger-text" : "good-text"}>
            {formatCRC(netWorth)}
          </h2>

          <p className="muted">
            Activos registrados menos deudas registradas.
          </p>
        </article>

        
      </div>
    </section>
  );
}