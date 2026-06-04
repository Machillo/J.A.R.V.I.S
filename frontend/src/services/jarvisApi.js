import { supabase } from "../lib/supabase";

const API_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const getAuthHeaders = async () => {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;

  return token
    ? { Authorization: `Bearer ${token}` }
    : {};
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

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Error en ${endpoint}: ${response.status} ${errorText}`);
  }

  return response.json();
};

export const getStatus = () => request("/status");

export const getMe = () => request("/auth/me");

export const getFinanceDashboard = () => request("/finance/dashboard");

export const askJarvis = async (message) => {
  return request("/jarvis/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message }),
  });
};

export const getGoals = () => request("/goals");

export const createSalary = (payload) =>
  request("/finance/salaries", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const createDebt = (payload) =>
  request("/finance/debts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const createSaving = (payload) =>
  request("/finance/savings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const createInvestment = (payload) =>
  request("/finance/investments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const createExpense = (payload) =>
  request("/finance/expenses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const createEmploymentProfile = (payload) =>
  request("/finance/employment-profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
