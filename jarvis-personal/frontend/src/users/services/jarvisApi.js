import { supabase } from "../../lib/supabase";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

async function authHeaders() {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  if (!token) throw new Error("No hay sesión activa.");
  return { Authorization: `Bearer ${token}` };
}

async function request(path, options = {}) {
  const headers = { ...(await authHeaders()), ...(options.headers || {}) };
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`Error ${response.status} en ${path}: ${payload?.detail || payload?.error || "Error de API"}`);
  return payload;
}

function json(path, method, body) {
  return request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const getMe = () => request("/auth/me");
export const getPlans = () => request("/auth/plans");
export const selectPlan = (plan) => json("/auth/plan", "POST", { plan });

export const getFinancialSituation = () => request("/user-product/financial-situation");
export const updateFinancialSituation = (payload) => json("/user-product/financial-situation", "PUT", payload);

export const getFinanceSummary = () => request("/user-product/finance/summary");
export const getIncome = () => request("/user-product/finance/income");
export const createIncome = (payload) => json("/user-product/finance/income", "POST", payload);
export const updateIncome = (id, payload) => json(`/user-product/finance/income/${id}`, "PUT", payload);
export const deleteIncome = (id) => request(`/user-product/finance/income/${id}`, { method: "DELETE" });
export const getExpenses = () => request("/user-product/finance/expenses");
export const createExpense = (payload) => json("/user-product/finance/expenses", "POST", payload);
export const updateExpense = (id, payload) => json(`/user-product/finance/expenses/${id}`, "PUT", payload);
export const deleteExpense = (id) => request(`/user-product/finance/expenses/${id}`, { method: "DELETE" });
export const getOvertime = () => request("/user-product/finance/overtime");
export const createOvertime = (payload) => json("/user-product/finance/overtime", "POST", payload);

export const getDebts = () => request("/user-product/finance/debts");
export const createDebt = (payload) => json("/user-product/finance/debts", "POST", payload);
export const updateDebt = (id, payload) => json(`/user-product/finance/debts/${id}`, "PUT", payload);
export const deleteDebt = (id) => request(`/user-product/finance/debts/${id}`, { method: "DELETE" });
export const payDebt = (id, payload) => json(`/user-product/finance/debts/${id}/payments`, "POST", payload);

export const getStrategyBasic = () => request("/user-product/finance/strategy-basic");
export const simulateStrategyBasic = (extra_monthly) => json("/user-product/finance/strategy-basic/simulate", "POST", { extra_monthly });
export const getStrategyVip = () => request("/user-product/finance/strategy-vip");
export const simulateStrategyVip = (payload) => json("/user-product/finance/strategy-vip/simulate", "POST", payload);
export const getVipCommandCenter = () => request("/user-product/vip/command-center");

export const getGoals = () => request("/user-product/goals");
export const createGoal = (payload) => json("/user-product/goals", "POST", payload);
export const updateGoal = (id, payload) => json(`/user-product/goals/${id}`, "PUT", payload);
export const contributeGoal = (id, payload) => json(`/user-product/goals/${id}/contributions`, "POST", payload);
export const deleteGoal = (id) => request(`/user-product/goals/${id}`, { method: "DELETE" });

export const getTransactions = () => request("/user-product/transactions");
export const createTransaction = (payload) => json("/user-product/transactions", "POST", payload);
export const deleteTransaction = (id) => request(`/user-product/transactions/${id}`, { method: "DELETE" });

export const getBasicDashboard = () => request("/user-product/basic/dashboard");
export const getBudget = () => request("/user-product/basic/budget");
export const saveBudget = (payload) => json("/user-product/basic/budget", "PUT", payload);
export const getFinancialCalendar = (period) => request(`/user-product/basic/calendar${period ? `?period=${period}` : ""}`);
export const getRecurring = () => request("/user-product/basic/recurring");
export const createRecurring = (payload) => json("/user-product/basic/recurring", "POST", payload);
export const updateRecurring = (id, payload) => json(`/user-product/basic/recurring/${id}`, "PUT", payload);
export const deleteRecurring = (id) => request(`/user-product/basic/recurring/${id}`, { method: "DELETE" });
export const getBasicReport = (period) => request(`/user-product/basic/reports${period ? `?period=${period}` : ""}`);
export const getFreeDashboard = () => request("/user-product/free/dashboard");
export const getFreeMonthlySummary = (period) => request(`/user-product/free/monthly-summary${period ? `?period=${period}` : ""}`);
export const getFreeMovements = () => request("/user-product/free/movements");
export const updateFreeMovement = (id, payload) => json(`/user-product/free/movements/${encodeURIComponent(id)}`, "PUT", payload);
export const deleteFreeMovement = (id) => request(`/user-product/free/movements/${encodeURIComponent(id)}`, { method: "DELETE" });
