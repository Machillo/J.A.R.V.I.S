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

export const getJarvisPremiumStatus = () => request("/jarvis/premium/status");
export const getJarvisPremiumGuides = () => request("/jarvis/premium/guides");
export const getJarvisPremiumStrategySummary = () => request("/jarvis/premium/strategy-summary");
export const createJarvisPremiumInitialStrategy = () => request("/jarvis/premium/initial-strategy", { method: "POST" });


export const getSportsPreferences = () => request("/jarvis/preferences/sports");
export const updateSportsPreferences = (payload) => jsonRequest("/jarvis/preferences/sports", "POST", payload);
export const saveBrowserNotificationSubscription = (payload) => jsonRequest("/jarvis/notifications/browser", "POST", payload);

export const getNotificationStatus = () => request("/notifications/status");
export const getVapidPublicKey = () => request("/notifications/vapid-public-key");
export const savePushSubscription = (payload) => jsonRequest("/notifications/subscribe", "POST", payload);
export const sendTestNotification = () => request("/notifications/test", { method: "POST" });
export const getUpcomingCalendarEvents = (days = 30) => request(`/jarvis/calendar/upcoming?days=${days}`);

export const getMemorySummary = () => request("/jarvis/memory/summary");
export const getMemoryItems = (category = "") => request(`/jarvis/memory${category ? `?category=${encodeURIComponent(category)}` : ""}`);
export const searchMemoryItems = (query) => request(`/jarvis/memory/search?q=${encodeURIComponent(query || "")}`);
export const createMemoryItem = (payload) => jsonRequest("/jarvis/memory", "POST", payload);
export const deleteMemoryItem = (id) => request(`/jarvis/memory/${id}`, { method: "DELETE" });
export const getProfilePreferences = () => request("/jarvis/preferences/profile");
export const updateProfilePreferences = (payload) => jsonRequest("/jarvis/preferences/profile", "POST", payload);


export const previewFinanceInput = (payload) => jsonRequest("/transactions/finance-input/preview", "POST", payload);
export const commitFinanceInput = (payload) => jsonRequest("/transactions/finance-input/commit", "POST", payload);
export const previewFinancePdf = async ({ file, default_year_month = "", exchange_rate = 495 }) => {
  const authHeaders = await getAuthHeaders();
  const formData = new FormData();
  formData.append("file", file);
  if (default_year_month) formData.append("default_year_month", default_year_month);
  formData.append("exchange_rate", String(exchange_rate));

  const response = await fetch(`${API_URL}/transactions/finance-input/pdf-preview`, {
    method: "POST",
    headers: { ...authHeaders },
    body: formData,
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.error || "No pude leer el PDF.");
  }
  return payload;
};

export const getFixedExpenses = () => request("/finance/fixed-expenses");
export const getFixedExpenseStatus = (month = "") => request(`/finance/fixed-expenses/status${month ? `?month=${encodeURIComponent(month)}` : ""}`);
export const createFixedExpense = (payload) => jsonRequest("/finance/fixed-expenses", "POST", payload);
export const updateFixedExpense = (id, payload) => jsonRequest(`/finance/fixed-expenses/${id}`, "PUT", payload);
export const deleteFixedExpense = (id) => request(`/finance/fixed-expenses/${id}`, { method: "DELETE" });
export const seedOwnerFixedExpenses = () => request("/finance/fixed-expenses/seed-owner-defaults", { method: "POST" });


export const getEmailMonitorStatus = () => request("/email-monitor/status");
export const syncEmailMonitorGmail = (payload = {}) => {
  const params = new URLSearchParams();
  if (payload.max_results) params.set("max_results", payload.max_results);
  if (payload.auto_commit !== undefined) params.set("auto_commit", payload.auto_commit ? "true" : "false");
  if (payload.current_month_only !== undefined) params.set("current_month_only", payload.current_month_only ? "true" : "false");
  if (payload.query) params.set("query", payload.query);
  return request(`/email-monitor/sync-gmail${params.toString() ? `?${params.toString()}` : ""}`, { method: "POST" });
};
export const getEmailMonitorCandidates = (status = "", limit = 50) => {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", limit);
  return request(`/email-monitor/candidates?${params.toString()}`);
};
export const decideEmailCandidate = (payload) => jsonRequest("/email-monitor/candidates/decision", "POST", payload);
export const scanEmailText = (payload) => jsonRequest("/email-monitor/scan-text", "POST", payload);
