import { supabase } from "../lib/supabase";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const getAuthHeaders = async () => {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;

  return token ? { Authorization: `Bearer ${token}` } : {};
};

const request = async (endpoint, options = {}) => {
  const authHeaders = await getAuthHeaders();

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
      ...authHeaders,
    },
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      typeof payload === "string"
        ? payload
        : payload?.detail || payload?.error || JSON.stringify(payload);

    throw new Error(`Error en ${endpoint}: ${response.status} ${message}`);
  }

  return payload;
};

const jsonRequest = (endpoint, method, payload) =>
  request(endpoint, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const getStatus = () => request("/status");
export const getMe = () => request("/auth/me");

export const getFinanceDashboard = () => request("/finance/dashboard");
export const getFinancialSummary = () => request("/finance/summary");
export const getNetWorth = () => request("/finance/net-worth");

export const getSalaries = () => request("/finance/salaries");
export const createSalary = (payload) => jsonRequest("/finance/salaries", "POST", payload);

export const getBonuses = () => request("/finance/bonuses");
export const createBonus = (payload) => jsonRequest("/finance/bonuses", "POST", payload);

export const getDebts = () => request("/finance/debts");
export const createDebt = (payload) => jsonRequest("/finance/debts", "POST", payload);

export const getSavings = () => request("/finance/savings");
export const createSaving = (payload) => jsonRequest("/finance/savings", "POST", payload);

export const getInvestments = () => request("/finance/investments");
export const createInvestment = (payload) => jsonRequest("/finance/investments", "POST", payload);

export const getExpenses = () => request("/finance/expenses");
export const createExpense = (payload) => jsonRequest("/finance/expenses", "POST", payload);

export const getEmploymentProfile = () => request("/finance/employment-profile");
export const createEmploymentProfile = (payload) =>
  jsonRequest("/finance/employment-profile", "POST", payload);

export const getPayrollDeductions = () => request("/finance/payroll-deductions");
export const getPayrollEvents = () => request("/finance/payroll-events");

export const getGoals = () => request("/goals/");
export const createGoal = (payload) => jsonRequest("/goals/", "POST", payload);

export const getTransactions = () => request("/transactions/");
export const getTransactionAnalysis = () => request("/transactions/analysis/summary");
export const createTransaction = (payload) => jsonRequest("/transactions/", "POST", payload);

export const askJarvis = async (message) => {
  return jsonRequest("/jarvis/chat", "POST", { message });
};

export const getJarvisUsageToday = () => request("/jarvis/usage/today");
export const getJarvisUsageAdmin = () => request("/jarvis/usage/admin");


export const getSportsPreferences = () => request("/jarvis/preferences/sports");
export const updateSportsPreferences = (payload) => jsonRequest("/jarvis/preferences/sports", "POST", payload);
export const saveBrowserNotificationSubscription = (payload) => jsonRequest("/jarvis/notifications/browser", "POST", payload);
export const getUpcomingCalendarEvents = (days = 30) => request(`/jarvis/calendar/upcoming?days=${days}`);
