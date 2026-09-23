import { deviceLanguage } from "./locale.js";

// The plan catalog API returns Spanish copy (backend/auth/saas.py PLAN_COPY).
// English sessions show this presentation-only translation instead.
const ENGLISH_PLAN_COPY = {
  free: {
    name: "Free",
    tagline: "Organize and understand your numbers.",
    features: ["Financial summary", "Income and expenses", "Debts", "Goals", "Transactions", "Overtime"],
  },
  basic: {
    name: "Basic",
    tagline: "DINCR organizes and guides your month.",
    features: ["Everything in Free", "Full dashboard", "Guided budget", "Full debts and goals", "Calendar", "Recurring items", "Reports"],
  },
  vip: {
    name: "VIP",
    tagline: "A more complete strategy with information you authorize.",
    features: [
      "Everything in Basic",
      "Dynamic strategy, projections, and scenarios",
      "With your permission, it detects financial notices in supported emails so you can review transactions and keep your accounts and debts up to date",
      "Year-end bonus (aguinaldo) estimate if DINCR detects CCSS employer statements in a connected email",
    ],
  },
};

export function localizePlan(plan, language = deviceLanguage()) {
  if (!plan || language === "es") return plan;
  const copy = ENGLISH_PLAN_COPY[plan.code];
  return copy ? { ...plan, ...copy } : plan;
}

export function planDisplayName(code, fallback = "", language = deviceLanguage()) {
  if (language === "es") return fallback || code;
  return ENGLISH_PLAN_COPY[code]?.name || fallback || code;
}
