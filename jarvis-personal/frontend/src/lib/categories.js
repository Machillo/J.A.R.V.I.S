import { deviceLanguage } from "./locale.js";

// Category values are stored in Spanish because the backend classifies and
// plans with these canonical names. English sessions only change the label.
const ENGLISH_CATEGORY_LABELS = {
  "Ahorro y metas": "Savings and goals",
  "Boleta de pago": "Paycheck",
  Bono: "Bonus",
  Comida: "Food",
  Compras: "Shopping",
  Deporte: "Sports",
  Entretenimiento: "Entertainment",
  Familiar: "Family",
  Gasolina: "Gas",
  "Gastos fijos": "Fixed expenses",
  general: "General",
  Ignorado: "Ignored",
  Mascotas: "Pets",
  Otros: "Other",
  "Otros ingresos": "Other income",
  Personal: "Personal",
  Reembolso: "Refund",
  Reembolsos: "Refunds",
  Restaurante: "Restaurants",
  Salario: "Salary",
  Salud: "Health",
  Seguros: "Insurance",
  Servicios: "Utilities",
  "Servicios personales": "Personal services",
  Suscripciones: "Subscriptions",
  Teléfono: "Phone",
  Transferencia: "Transfer",
  "Transferencia interna": "Internal transfer",
  Transporte: "Transportation",
  Vivienda: "Housing",
};

const CANONICAL_BY_ENGLISH = Object.fromEntries(
  Object.entries(ENGLISH_CATEGORY_LABELS).map(([canonical, english]) => [english.toLowerCase(), canonical]),
);

export function categoryLabel(value, language = deviceLanguage()) {
  if (!value || language === "es") return value;
  return ENGLISH_CATEGORY_LABELS[value] || value;
}

// Maps a label typed or picked in the form back to the stored canonical value.
export function categoryValue(label, language = deviceLanguage()) {
  if (!label || language === "es") return label;
  return CANONICAL_BY_ENGLISH[String(label).trim().toLowerCase()] || label;
}
