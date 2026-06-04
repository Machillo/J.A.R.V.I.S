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