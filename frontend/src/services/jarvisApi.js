const API_URL = "http://127.0.0.1:8000";

export const getStatus = async () => {
  const response = await fetch(`${API_URL}/status`);

  if (!response.ok) {
    throw new Error("No se pudo obtener el estado de Jarvis");
  }

  return response.json();
};

export const askJarvis = async (text) => {
  const response = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text }),
  });

  if (!response.ok) {
    throw new Error("No se pudo comunicar con Jarvis");
  }

  return response.json();
};