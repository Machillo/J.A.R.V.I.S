const API_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const request = async (endpoint, options = {}) => {
  const response = await fetch(`${API_URL}${endpoint}`, options);

  if (!response.ok) {
    throw new Error(`Error en ${endpoint}`);
  }

  return response.json();
};

export const getStatus = () => request("/status");

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