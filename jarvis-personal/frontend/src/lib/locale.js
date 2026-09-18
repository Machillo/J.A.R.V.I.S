const dictionaries = {
  es: {
    nav: {
      strategy: "Estrategia", finance: "Finanzas", accounts: "Cuentas", wealth: "Patrimonio", more: "Más",
      moneyControl: "Dinero y control", receivables: "Cobros y cuentas por recibir", transactions: "Transacciones",
      emailMonitor: "Monitor de correos", additionalCards: "Tarjetas adicionales", investments: "Inversiones",
      businesses: "Negocios", netWorth: "Patrimonio neto", financialTimeline: "Cronología financiera",
      reconciliation: "Conciliación", deterioration: "Deterioro financiero", personal: "JARVIS personal",
      goals: "Metas", memory: "Memoria", settings: "Configuración", profile: "Perfil y apariencia",
      administration: "Administración", manageUsers: "Administrar usuarios", finvaOperations: "Operaciones FINVA",
      logout: "Cerrar sesión", profileAlt: "Perfil",
    },
  },
  en: {
    nav: {
      strategy: "Strategy", finance: "Finance", accounts: "Accounts", wealth: "Wealth", more: "More",
      moneyControl: "Money & control", receivables: "Receivables", transactions: "Transactions",
      emailMonitor: "Email Monitor", additionalCards: "Additional cards", investments: "Investments",
      businesses: "Businesses", netWorth: "Net worth", financialTimeline: "Financial timeline",
      reconciliation: "Reconciliation", deterioration: "Financial deterioration", personal: "Personal JARVIS",
      goals: "Goals", memory: "Memory", settings: "Settings", profile: "Profile & appearance",
      administration: "Administration", manageUsers: "Manage users", finvaOperations: "FINVA operations",
      logout: "Log out", profileAlt: "Profile",
    },
  },
};

export const deviceLanguage = () => {
  if (typeof navigator === "undefined") return "es";
  const candidates = [...(navigator.languages || []), navigator.language].filter(Boolean);
  return candidates.some((value) => String(value).toLowerCase().startsWith("es")) ? "es" : "en";
};

export const localeTag = (language = deviceLanguage()) => language === "es" ? "es-CR" : "en-US";

export const t = (key, language = deviceLanguage()) => {
  const value = key.split(".").reduce((node, part) => node?.[part], dictionaries[language]);
  return value ?? key;
};

export const applyDocumentLanguage = (language = deviceLanguage()) => {
  if (typeof document !== "undefined") document.documentElement.lang = language;
  return language;
};
