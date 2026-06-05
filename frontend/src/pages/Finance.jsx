import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CircleDollarSign,
  Target,
  Wallet,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getTransactionAnalysis } from "../services/jarvisApi";

const formatCRC = (value = 0) =>
  new Intl.NumberFormat("es-CR", {
    style: "currency",
    currency: "CRC",
    maximumFractionDigits: 0,
  }).format(Number(value) || 0);

const shortCRC = (value = 0) => {
  const number = Number(value) || 0;

  if (Math.abs(number) >= 1_000_000) {
    return `₡${(number / 1_000_000).toFixed(1)}M`;
  }

  if (Math.abs(number) >= 1_000) {
    return `₡${Math.round(number / 1_000)}k`;
  }

  return formatCRC(number);
};

const clampPercent = (value) =>
  Math.min(Math.max(Math.round(Number(value) || 0), 0), 100);

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
  const safeValue = clampPercent(value);

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

function LoadingPanel({ message = "Cargando núcleo financiero..." }) {
  return (
    <section className="dashboard-page">
      <div className="empty-state full-width">
        <div className="jarvis-loader"></div>
        <h3>{message}</h3>
        <p>Estoy sincronizando los datos reales de Supabase.</p>
      </div>
    </section>
  );
}

function ErrorPanel({ error, onRetry }) {
  return (
    <section className="dashboard-page">
      <div className="empty-state full-width danger">
        <AlertTriangle size={32} />
        <h3>No pude cargar el dashboard financiero</h3>
        <p>{error || "Revisa Render logs o vuelve a intentar."}</p>
        {onRetry && (
          <button className="hud-action-button" onClick={onRetry}>
            Reintentar
          </button>
        )}
      </div>
    </section>
  );
}

function EmptyPanel({ title, description }) {
  return (
    <div className="empty-state">
      <CircleDollarSign size={28} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

export default function Finance({
  dashboard,
  loading = false,
  error = "",
  onRefresh,
}) {
  const [transactionAnalysis, setTransactionAnalysis] = useState(null);
  const [transactionAnalysisError, setTransactionAnalysisError] = useState("");

  useEffect(() => {
    let active = true;

    getTransactionAnalysis()
      .then((data) => {
        if (active) {
          setTransactionAnalysis(data);
          setTransactionAnalysisError("");
        }
      })
      .catch((analysisError) => {
        console.error(analysisError);
        if (active) {
          setTransactionAnalysis(null);
          setTransactionAnalysisError("No pude leer el análisis de transacciones.");
        }
      });

    return () => {
      active = false;
    };
  }, [dashboard]);

  if (loading) return <LoadingPanel />;
  if (error) return <ErrorPanel error={error} onRetry={onRefresh} />;

  const summary = dashboard?.summary || {};
  const alerts = dashboard?.alerts || [];
  const topDebts = dashboard?.top_debts || [];
  const recommendations = dashboard?.quick_recommendations || [];
  const goal = summary?.goals?.most_urgent_goal;

  const txSummary = transactionAnalysis?.summary || {};
  const latestMonth = transactionAnalysis?.latest_month || {};
  const monthlyFlow = transactionAnalysis?.monthly_flow || [];

  const income = Number(summary?.income?.monthly_net_income) || 0;
  const latestIncome = Number(latestMonth?.income) || 0;
  const latestLoans = Number(latestMonth?.loans_received) || 0;
  const latestExpenses = Number(latestMonth?.expenses) || 0;
  const latestDebtPayments = Number(latestMonth?.debt_payments) || 0;

  const totalIncome = latestIncome || Number(summary?.income?.total_income) || income;
  const expensesTotal = latestExpenses || Number(summary?.expenses?.total_expenses) || 0;
  const fixedExpenses = Number(summary?.expenses?.fixed_expenses) || 0;
  const importedCashflow = totalIncome + latestLoans - expensesTotal - latestDebtPayments;
  const available = monthlyFlow.length > 0
    ? importedCashflow
    : Number(summary?.cashflow?.available_cash) || 0;
  const debtTotal = Number(summary?.debts?.total) || 0;
  const monthlyDebtPayments = latestDebtPayments || 0;
  const netWorth = Number(summary?.assets?.net_worth) || 0;
  const assetsTotal = Number(summary?.assets?.assets_total) || 0;
  const historicalImported = Number(txSummary?.net_cashflow) || 0;

  const goalProgress = goal?.target_amount
    ? clampPercent((Number(goal.current_amount) / Number(goal.target_amount)) * 100)
    : 0;

  const debtProgress =
    totalIncome + latestLoans > 0
      ? clampPercent((monthlyDebtPayments / (totalIncome + latestLoans)) * 100)
      : 0;

  const monthlyChartData = monthlyFlow.map((item) => ({
    name: String(item.month || "").replace("2026-", ""),
    ingresos: Number(item.income) || 0,
    prestamos: Number(item.loans_received) || 0,
    gastos: (Number(item.expenses) || 0) + (Number(item.debt_payments) || 0),
  }));

  const categoryChartData = useMemo(() => {
    return (transactionAnalysis?.top_expense_categories || []).map((item) => ({
      category: item.category || "Sin categoría",
      total: Number(item.total) || 0,
    }));
  }, [transactionAnalysis]);

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
            <span>PAGOS DE DEUDA</span>
            <AlertTriangle size={18} />
          </div>

          <div className="ring-row">
            <ProgressRing value={debtProgress} color="red" />
            <div>
              <h2>{formatCRC(monthlyDebtPayments)}</h2>
              <p>Pagos registrados en el último mes importado</p>
            </div>
          </div>
        </article>

        <article className="hud-card wide-balance">
          <div className="card-header">
            <span>SALDO REAL</span>
            <Wallet size={18} />
          </div>

          <h2 className={available < 0 ? "danger-text" : ""}>{formatCRC(available)}</h2>
          <p>Ingreso + préstamos - gastos - pagos del último mes</p>
        </article>
      </div>

      <div className="finance-detail-grid">
        <article className="hud-card compact metric-card">
          <span>Ingreso del último mes</span>
          <strong>{formatCRC(totalIncome)}</strong>
        </article>
        <article className="hud-card compact metric-card">
          <span>Préstamos recibidos</span>
          <strong>{formatCRC(latestLoans)}</strong>
        </article>
        <article className="hud-card compact metric-card">
          <span>Gastos del último mes</span>
          <strong>{formatCRC(expensesTotal)}</strong>
        </article>
        <article className="hud-card compact metric-card">
          <span>Histórico importado</span>
          <strong>{formatCRC(historicalImported)}</strong>
        </article>
      </div>

      <div className="dashboard-grid">
        <article className="hud-panel large">
          <div className="panel-title">
            <div>
              <h3>FLUJO MENSUAL</h3>
              <p>Ingresos, préstamos, gastos y pagos de deuda importados</p>
            </div>
            <span>REAL</span>
          </div>

          {monthlyChartData.length === 0 ? (
            <EmptyPanel
              title="Sin movimientos"
              description="Cuando haya transacciones importadas, el gráfico se activará."
            />
          ) : (
            <>
              <div className="chart-shell finance-chart">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={monthlyChartData} margin={{ top: 16, right: 8, left: -12, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" />
                    <YAxis tickFormatter={shortCRC} width={58} />
                    <Tooltip formatter={(value) => formatCRC(value)} />
                    <Bar dataKey="ingresos" name="Ingresos" fill="var(--cyan)" radius={[8, 8, 0, 0]} />
                    <Bar dataKey="prestamos" name="Préstamos" fill="#b65cff" radius={[8, 8, 0, 0]} />
                    <Bar dataKey="gastos" name="Gastos / deuda" fill="var(--red)" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="legend finance-legend">
                <span className="cyan"></span> Ingresos
                <span className="purple"></span> Préstamos
                <span className="red"></span> Gastos / deuda
              </div>
            </>
          )}
        </article>

        <article className="hud-panel large">
          <div className="panel-title">
            <div>
              <h3>GASTOS POR CATEGORÍA</h3>
              <p>Top categorías del histórico importado</p>
            </div>
            <span>REAL</span>
          </div>

          {categoryChartData.length === 0 ? (
            <EmptyPanel
              title="Sin categorías todavía"
              description="Cuando existan gastos importados, aparecerán aquí."
            />
          ) : (
            <div className="chart-shell">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={categoryChartData} layout="vertical" margin={{ left: 0, right: 12, top: 8, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={shortCRC} />
                  <YAxis type="category" dataKey="category" width={110} />
                  <Tooltip formatter={(value) => formatCRC(value)} />
                  <Bar dataKey="total" name="Gasto" fill="var(--red)" radius={[0, 8, 8, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </article>

        <article className="hud-panel">
          <div className="panel-title">
            <div>
              <h3>ALERTAS</h3>
              <p>Prioridad actual</p>
            </div>
          </div>

          <div className="alert-list">
            {alerts.length === 0 ? (
              <EmptyPanel
                title="Sin alertas críticas"
                description="Cuando haya riesgo de flujo, deuda o metas, aparecerá aquí."
              />
            ) : (
              alerts.map((alert, index) => (
                <div className={`alert-item ${alert.level}`} key={index}>
                  <AlertTriangle size={18} />
                  <span>{alert.message}</span>
                </div>
              ))
            )}
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
            {topDebts.length === 0 ? (
              <EmptyPanel
                title="Sin deudas registradas"
                description="Las deudas que agregues desde Finanzas o chat aparecerán aquí."
              />
            ) : (
              topDebts.map((debt) => (
                <div className="debt-item" key={debt.id}>
                  <div>
                    <strong>{debt.name}</strong>
                    <span>{formatCRC(debt.remaining_amount)}</span>
                  </div>
                  <small>Pago: {formatCRC(debt.monthly_payment)} · Interés: {Number(debt.interest_rate) || 0}%</small>

                  <div className="debt-bar">
                    <span
                      style={{
                        width: `${debtTotal > 0 ? Math.min((debt.remaining_amount / debtTotal) * 100, 100) : 0}%`,
                      }}
                    ></span>
                  </div>
                </div>
              ))
            )}
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

        <article className="hud-panel large">
          <div className="panel-title">
            <div>
              <h3>RECOMENDACIONES</h3>
              <p>Acciones sugeridas por estado actual</p>
            </div>
          </div>

          {recommendations.length === 0 ? (
            <EmptyPanel
              title="Sin recomendaciones todavía"
              description="Cuando registremos ingresos, gastos, deudas y metas, Jarvis tendrá más contexto."
            />
          ) : (
            <div className="recommendation-list">
              {recommendations.map((item, index) => (
                <div className="recommendation-item" key={index}>
                  {item}
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="hud-panel">
          <div className="panel-title">
            <div>
              <h3>DATOS BASE</h3>
              <p>Estado del perfil financiero</p>
            </div>
          </div>

          <div className="metric-list">
            <div>
              <span>Gastos fijos</span>
              <strong>{formatCRC(fixedExpenses)}</strong>
            </div>
            <div>
              <span>Activos</span>
              <strong>{formatCRC(assetsTotal)}</strong>
            </div>
            <div>
              <span>Metas activas</span>
              <strong>{summary?.goals?.active_goals_count || 0}</strong>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}
