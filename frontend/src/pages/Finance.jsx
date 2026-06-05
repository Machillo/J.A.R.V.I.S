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
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getTransactionAnalysis } from "../services/jarvisApi";

const CRC = new Intl.NumberFormat("es-CR", {
  style: "currency",
  currency: "CRC",
  maximumFractionDigits: 0,
});

const formatCRC = (value = 0) => CRC.format(Number(value) || 0);

const shortCRC = (value = 0) => {
  const number = Number(value) || 0;

  if (Math.abs(number) >= 1_000_000) return `₡${(number / 1_000_000).toFixed(1)}M`;
  if (Math.abs(number) >= 1_000) return `₡${Math.round(number / 1_000)}k`;

  return formatCRC(number);
};

const monthLabel = (month = "") => {
  const labels = {
    "01": "ENE",
    "02": "FEB",
    "03": "MAR",
    "04": "ABR",
    "05": "MAY",
    "06": "JUN",
    "07": "JUL",
    "08": "AGO",
    "09": "SET",
    "10": "OCT",
    "11": "NOV",
    "12": "DIC",
  };

  return labels[month.slice(5, 7)] || month;
};

const clampPercent = (value) => Math.min(Math.max(Math.round(Number(value) || 0), 0), 100);

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
    <section className="dashboard-page finance-page">
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
    <section className="dashboard-page finance-page">
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

export default function Finance({ dashboard, loading = false, error = "", onRefresh }) {
  const [transactionAnalysis, setTransactionAnalysis] = useState(null);
  const [analysisError, setAnalysisError] = useState("");

  useEffect(() => {
    let active = true;

    getTransactionAnalysis()
      .then((data) => {
        if (!active) return;
        setTransactionAnalysis(data);
        setAnalysisError("");
      })
      .catch((analysisError) => {
        console.error(analysisError);
        if (!active) return;
        setTransactionAnalysis(null);
        setAnalysisError(analysisError.message || "No pude leer las transacciones.");
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
  const currentMonth = transactionAnalysis?.current_month_summary || {};

  const projectedIncome = Number(summary?.income?.monthly_net_income) || 0;
  const realCurrentIncome = Number(currentMonth?.income) || 0;
  const realCurrentLoans = Number(currentMonth?.loan_received) || 0;
  const realCurrentExpenses = Number(currentMonth?.expenses) || 0;
  const realCurrentDebtPayments = Number(currentMonth?.debt_payments) || 0;
  const realCurrentAvailable = Number(currentMonth?.available) || 0;

  const totalImportedExpenses = Number(txSummary?.expenses) || 0;
  const totalImportedDebtPayments = Number(txSummary?.debt_payments) || 0;
  const debtTotal = Number(summary?.debts?.total) || 0;
  const monthlyDebtPayments = Number(summary?.debts?.monthly_payments) || 0;
  const netWorth = Number(summary?.assets?.net_worth) || 0;
  const assetsTotal = Number(summary?.assets?.assets_total) || 0;
  const fixedExpenses = Number(summary?.expenses?.fixed_expenses) || 0;

  const goalProgress = goal?.target_amount
    ? clampPercent((Number(goal.current_amount) / Number(goal.target_amount)) * 100)
    : 0;

  const debtProgress =
    realCurrentIncome > 0
      ? clampPercent((realCurrentDebtPayments / realCurrentIncome) * 100)
      : debtTotal > 0
        ? 100
        : 0;

  const monthlyChartData = useMemo(() => {
    const rows = transactionAnalysis?.monthly_flow || [];

    return rows.slice(-6).map((item) => ({
      month: monthLabel(item.month),
      ingresos: Number(item.income) || 0,
      prestamos: Number(item.loan_received) || 0,
      gastos: Number(item.expenses) || 0,
      deudas: Number(item.debt_payments) || 0,
    }));
  }, [transactionAnalysis]);

  const categoryChartData = useMemo(() => {
    return (transactionAnalysis?.top_expense_categories || []).map((item) => ({
      category: item.category || "Sin categoría",
      total: Number(item.total) || 0,
    }));
  }, [transactionAnalysis]);

  const visibleDebts = topDebts.slice(0, 8);

  return (
    <section className="dashboard-page finance-page">
      <div className="cards-grid finance-kpis">
        <article className="hud-card glow-green">
          <div className="card-header">
            <span>INGRESO NETO</span>
            <ArrowUpRight size={18} />
          </div>
          <MiniLine type="up" />
          <h2>{formatCRC(projectedIncome)}</h2>
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
              <p>{goal ? `${formatCRC(goal.current_amount)} de ${formatCRC(goal.target_amount)}` : "Sin meta activa"}</p>
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
              <h2>{formatCRC(realCurrentDebtPayments || monthlyDebtPayments)}</h2>
              <p>{currentMonth?.month ? `Pagado en ${monthLabel(currentMonth.month)}` : "Pago mensual configurado"}</p>
            </div>
          </div>
        </article>

        <article className="hud-card wide-balance">
          <div className="card-header">
            <span>SALDO REAL</span>
            <Wallet size={18} />
          </div>
          <h2 className={realCurrentAvailable < 0 ? "danger-text" : "good-text"}>{formatCRC(realCurrentAvailable)}</h2>
          <p>{currentMonth?.month ? `Flujo importado de ${monthLabel(currentMonth.month)}` : "Disponible estimado"}</p>
        </article>
      </div>

      <div className="finance-summary-strip">
        <div>
          <span>Ingreso del mes</span>
          <strong>{formatCRC(realCurrentIncome)}</strong>
        </div>
        <div>
          <span>Préstamos recibidos</span>
          <strong>{formatCRC(realCurrentLoans)}</strong>
        </div>
        <div>
          <span>Gastos del mes</span>
          <strong>{formatCRC(realCurrentExpenses)}</strong>
        </div>
        <div>
          <span>Histórico importado</span>
          <strong>{formatCRC(totalImportedExpenses + totalImportedDebtPayments)}</strong>
        </div>
      </div>

      <div className="dashboard-grid finance-dashboard-grid">
        <article className="hud-panel large finance-chart-panel">
          <div className="panel-title">
            <div>
              <h3>FLUJO MENSUAL</h3>
              <p>Ingresos, préstamos, gastos y pagos de deuda importados</p>
            </div>
            <span>REAL</span>
          </div>

          {monthlyChartData.length === 0 ? (
            <EmptyPanel title="Sin movimientos" description="Cuando haya transacciones, el gráfico se activará." />
          ) : (
            <div className="chart-shell finance-chart-shell">
              <ResponsiveContainer width="100%" height={310}>
                <BarChart data={monthlyChartData} margin={{ top: 16, right: 8, left: -16, bottom: 2 }} barCategoryGap="18%">
                  <defs>
                    <linearGradient id="jarvisIncome" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#29e6ff" stopOpacity="1" />
                      <stop offset="100%" stopColor="#29e6ff" stopOpacity="0.25" />
                    </linearGradient>
                    <linearGradient id="jarvisExpense" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#ff3d6e" stopOpacity="1" />
                      <stop offset="100%" stopColor="#ff3d6e" stopOpacity="0.22" />
                    </linearGradient>
                    <linearGradient id="jarvisLoan" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#b85cff" stopOpacity="1" />
                      <stop offset="100%" stopColor="#b85cff" stopOpacity="0.2" />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="4 8" vertical={false} />
                  <XAxis dataKey="month" axisLine={false} tickLine={false} />
                  <YAxis tickFormatter={shortCRC} width={60} axisLine={false} tickLine={false} />
                  <Tooltip formatter={(value) => formatCRC(value)} cursor={{ fill: "rgba(41,230,255,.06)" }} />
                  <Bar dataKey="ingresos" name="Ingresos" fill="url(#jarvisIncome)" radius={[10, 10, 2, 2]} />
                  <Bar dataKey="prestamos" name="Préstamos" fill="url(#jarvisLoan)" radius={[10, 10, 2, 2]} />
                  <Bar dataKey="gastos" name="Gastos" fill="url(#jarvisExpense)" radius={[10, 10, 2, 2]} />
                  <Bar dataKey="deudas" name="Pagos deuda" fill="#ff6b82" radius={[10, 10, 2, 2]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="legend finance-legend">
            <span className="cyan"></span> Ingresos
            <span className="purple"></span> Préstamos
            <span className="red"></span> Gastos / deuda
          </div>
        </article>

        <article className="hud-panel large finance-chart-panel">
          <div className="panel-title">
            <div>
              <h3>GASTOS POR CATEGORÍA</h3>
              <p>Top categorías del histórico importado</p>
            </div>
            <span>REAL</span>
          </div>

          {analysisError ? (
            <div className="inline-error">{analysisError}</div>
          ) : categoryChartData.length === 0 ? (
            <EmptyPanel title="Sin categorías todavía" description="No encontré gastos tipo expense en transacciones." />
          ) : (
            <div className="category-rank-list">
              {categoryChartData.map((item, index) => {
                const max = categoryChartData[0]?.total || 1;
                const width = Math.max((item.total / max) * 100, 8);
                return (
                  <div className="category-rank-item" key={item.category}>
                    <div>
                      <span>{index + 1}</span>
                      <strong>{item.category}</strong>
                      <em>{formatCRC(item.total)}</em>
                    </div>
                    <div className="category-rank-bar">
                      <span style={{ width: `${width}%` }}></span>
                    </div>
                  </div>
                );
              })}
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
              <EmptyPanel title="Sin alertas críticas" description="Cuando haya riesgo de flujo, deuda o metas, aparecerá aquí." />
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
              <p>Deudas activas registradas</p>
            </div>
          </div>
          <div className="debt-list">
            {visibleDebts.length === 0 ? (
              <EmptyPanel title="Sin deudas registradas" description="Las deudas que agregues desde Finanzas o chat aparecerán aquí." />
            ) : (
              visibleDebts.map((debt) => (
                <div className="debt-item" key={debt.id}>
                  <div>
                    <strong>{debt.name}</strong>
                    <span>{formatCRC(debt.remaining_amount)}</span>
                  </div>
                  <div className="debt-meta-line">
                    <small>Pago: {formatCRC(debt.monthly_payment || 0)}</small>
                    {debt.interest_rate ? <small>Interés: {debt.interest_rate}%</small> : null}
                  </div>
                  <div className="debt-bar">
                    <span style={{ width: `${debtTotal > 0 ? Math.min((debt.remaining_amount / debtTotal) * 100, 100) : 0}%` }}></span>
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
          <h2 className={netWorth < 0 ? "danger-text" : "good-text"}>{formatCRC(netWorth)}</h2>
          <p className="muted">Activos registrados menos deudas registradas.</p>
        </article>

        <article className="hud-panel large">
          <div className="panel-title">
            <div>
              <h3>RECOMENDACIONES</h3>
              <p>Acciones sugeridas por estado actual</p>
            </div>
          </div>
          {recommendations.length === 0 ? (
            <EmptyPanel title="Sin recomendaciones todavía" description="Cuando registremos ingresos, gastos, deudas y metas, Jarvis tendrá más contexto." />
          ) : (
            <div className="recommendation-list">
              {recommendations.map((item, index) => (
                <div className="recommendation-item" key={index}>{item}</div>
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
