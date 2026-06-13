import { useEffect, useMemo, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  CircleDollarSign,
  Database,
  RefreshCw,
  Search,
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
import {
  getDebts,
  getFinanceCycleReport,
  getFixedExpenseStatus,
  getTransactionAnalysis,
  getTransactions,
} from "../services/jarvisApi";

const formatCRC = (value = 0) =>
  new Intl.NumberFormat("es-CR", {
    style: "currency",
    currency: "CRC",
    maximumFractionDigits: 0,
  }).format(Number(value) || 0);

const formatDate = (value) => {
  if (!value) return "Sin fecha";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat("es-CR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
};

const typeLabel = {
  income: "Ingreso",
  expense: "Gasto",
  debt_payment: "Pago deuda",
  transfer: "Transferencia",
  investment: "Inversión",
  investment_withdrawal: "Retiro inversión",
  loan_disbursement: "Desembolso",
};

function LoadingState() {
  return (
    <section className="data-page">
      <div className="empty-state full-width">
        <div className="jarvis-loader"></div>
        <h3>Cargando transacciones...</h3>
        <p>Consultando los movimientos registrados en Supabase.</p>
      </div>
    </section>
  );
}

function EmptyState() {
  return (
    <div className="empty-state full-width">
      <Database size={34} />
      <h3>No hay transacciones todavía</h3>
      <p>
        Cuando importemos enero a mayo o agregues movimientos manuales, esta
        pantalla mostrará tabla, totales y categorías.
      </p>
    </div>
  );
}

export default function Transactions() {
  const [transactions, setTransactions] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [cycleReport, setCycleReport] = useState(null);
  const [fixedStatus, setFixedStatus] = useState(null);
  const [debts, setDebts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  const loadTransactions = async () => {
    try {
      setLoading(true);
      setError("");

      const [transactionData, analysisData, cycleData, fixedData, debtData] = await Promise.all([
        getTransactions(),
        getTransactionAnalysis(),
        getFinanceCycleReport().catch(() => null),
        getFixedExpenseStatus().catch(() => null),
        getDebts().catch(() => []),
      ]);

      setTransactions(Array.isArray(transactionData) ? transactionData : []);
      setAnalysis(analysisData || null);
      setCycleReport(cycleData || null);
      setFixedStatus(fixedData || null);
      setDebts(Array.isArray(debtData) ? debtData : []);
    } catch (loadError) {
      console.error(loadError);
      setError(loadError.message || "No pude cargar transacciones.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTransactions();
  }, []);

  const filteredTransactions = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return transactions;

    return transactions.filter((transaction) => {
      const text = [
        transaction.description,
        transaction.category,
        transaction.account,
        transaction.transaction_type,
        transaction.source,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return text.includes(term);
    });
  }, [transactions, search]);

  const monthlyChartData = (analysis?.expenses_by_month || []).map((item) => ({
    month: item.month,
    gastos: Number(item.total) || 0,
  }));

  const summary = analysis?.summary || {};
  const estimatedNetIncome =
    Number(cycleReport?.income?.fixed_expected) ||
    Number(cycleReport?.payroll_projection?.net_income) ||
    Number(summary.income) ||
    0;
  const estimatedFixedExpenses = Number(fixedStatus?.summary?.expected) || 0;
  const estimatedDebtPayments = debts.reduce(
    (total, debt) => total + (Number(debt.monthly_payment) || 0),
    0
  );
  const estimatedNetExpenses = estimatedFixedExpenses + estimatedDebtPayments;

  if (loading) return <LoadingState />;

  return (
    <section className="data-page">
      <div className="page-section-header">
        <div>
          <h2>Transacciones</h2>
          <p>Movimientos reales registrados por usuario.</p>
        </div>

        <button className="hud-action-button" onClick={loadTransactions}>
          <RefreshCw size={16} />
          Actualizar
        </button>
      </div>

      {error && (
        <div className="inline-error">
          {error}
        </div>
      )}

      <div className="data-kpi-grid">
        <article className="hud-card compact glow-green">
          <div className="card-header">
            <span>Ingreso neto estimado</span>
            <ArrowUpRight size={18} />
          </div>
          <h2>{formatCRC(estimatedNetIncome)}</h2>
        </article>

        <article className="hud-card compact glow-red">
          <div className="card-header">
            <span>Gasto neto estimado</span>
            <ArrowDownRight size={18} />
          </div>
          <h2>{formatCRC(estimatedNetExpenses)}</h2>
        </article>

        <article className="hud-card compact glow-green">
          <div className="card-header">
            <span>Ingresos reales</span>
            <ArrowUpRight size={18} />
          </div>
          <h2>{formatCRC(summary.income)}</h2>
        </article>

        <article className="hud-card compact glow-red">
          <div className="card-header">
            <span>Gastos reales</span>
            <ArrowDownRight size={18} />
          </div>
          <h2>{formatCRC(summary.expenses)}</h2>
        </article>

        <article className="hud-card compact">
          <div className="card-header">
            <span>Pagos deuda</span>
            <CircleDollarSign size={18} />
          </div>
          <h2>{formatCRC(summary.debt_payments)}</h2>
          <p>Aplicados desde movimientos</p>
        </article>

        <article className="hud-card compact">
          <div className="card-header">
            <span>Neto</span>
            <CircleDollarSign size={18} />
          </div>
          <h2>{formatCRC(summary.net_from_transactions)}</h2>
          <p>Ingreso - gastos - deuda</p>
        </article>
      </div>

      <div className="dashboard-grid">
        <article className="hud-panel large">
          <div className="panel-title">
            <div>
              <h3>GASTOS POR MES</h3>
              <p>Basado en transacciones guardadas.</p>
            </div>
          </div>

          {monthlyChartData.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="chart-shell transaction-chart-shell">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={monthlyChartData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="month" />
                  <YAxis tickFormatter={(value) => `₡${Math.round(value / 1000)}k`} />
                  <Tooltip formatter={(value) => formatCRC(value)} />
                  <Bar dataKey="gastos" name="Gastos" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </article>

        <article className="hud-panel">
          <div className="panel-title">
            <div>
              <h3>TOP CATEGORÍAS</h3>
              <p>Principales gastos</p>
            </div>
          </div>

          <div className="metric-list">
            {(analysis?.top_expense_categories || []).length === 0 ? (
              <EmptyState />
            ) : (
              analysis.top_expense_categories.map((item) => (
                <div key={item.category || "Sin categoría"}>
                  <span>{item.category || "Sin categoría"}</span>
                  <strong>{formatCRC(item.total)}</strong>
                </div>
              ))
            )}
          </div>
        </article>
      </div>

      <article className="hud-panel data-table-panel">
        <div className="panel-title">
          <div>
            <h3>HISTORIAL</h3>
            <p>{filteredTransactions.length} movimientos visibles</p>
          </div>

          <label className="search-box">
            <Search size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar por descripción, categoría o cuenta"
            />
          </label>
        </div>

        {transactions.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="responsive-table transaction-history-scroll">
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Descripción</th>
                  <th>Tipo</th>
                  <th>Categoría</th>
                  <th>Cuenta</th>
                  <th>Monto</th>
                </tr>
              </thead>

              <tbody>
                {filteredTransactions.map((transaction) => (
                  <tr key={transaction.id}>
                    <td>{formatDate(transaction.transaction_date)}</td>
                    <td>{transaction.description}</td>
                    <td>
                      <span className={`type-pill ${transaction.transaction_type}`}>
                        {typeLabel[transaction.transaction_type] || transaction.transaction_type}
                      </span>
                    </td>
                    <td>{transaction.category || "Sin categoría"}</td>
                    <td>{transaction.account || "Sin cuenta"}</td>
                    <td className={transaction.transaction_type === "income" ? "good-text" : "danger-text"}>
                      {formatCRC(transaction.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </section>
  );
}
