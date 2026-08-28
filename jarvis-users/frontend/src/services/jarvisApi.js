import { supabase } from "../lib/supabase";

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
  if (!response.ok) throw new Error(payload?.detail || payload?.error || "Error de API");
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
export const getOnboarding = () => request("/auth/onboarding");
export const completeOnboarding = (payload) => json("/auth/onboarding", "POST", payload);
export const getFinancialSituation = () => request("/auth/financial-situation");
export const updateFinancialSituation = (payload) => json("/auth/financial-situation", "PUT", payload);
export const getFinanceSummary = () => request("/finance/summary");
export const getIncome = () => request("/finance/income");
export const createIncome = (payload) => json("/finance/income", "POST", payload);
export const getExpenses = () => request("/finance/expenses");
export const createExpense = (payload) => json("/finance/expenses", "POST", payload);
export const getOvertime = () => request("/finance/overtime");
export const createOvertime = (payload) => json("/finance/overtime", "POST", payload);
export const getDebts = () => request("/finance/debts");
export const createDebt = (payload) => json("/finance/debts", "POST", payload);
export const updateDebt = (id, payload) => json(`/finance/debts/${id}`, "PUT", payload);
export const deleteDebt = (id) => request(`/finance/debts/${id}`, { method: "DELETE" });
export const payDebt = (id, payload) => json(`/finance/debts/${id}/payments`, "POST", payload);
export const getStrategyBasic = () => request("/finance/strategy-basic");
export const getGoals = () => request("/goals");
export const createGoal = (payload) => json("/goals", "POST", payload);
export const updateGoal = (id, payload) => json(`/goals/${id}`, "PUT", payload);
export const deleteGoal = (id) => request(`/goals/${id}`, { method: "DELETE" });
export const getTransactions = () => request("/transactions");
export const createTransaction = (payload) => json("/transactions", "POST", payload);
export const updateTransaction = (id, payload) => json(`/transactions/${id}`, "PUT", payload);
export const deleteTransaction = (id) => request(`/transactions/${id}`, { method: "DELETE" });
