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
    accounts: {
      eyebrow: "BANCA POR CORREO", title: "Cuentas", intro: "JARVIS reconoce la institución desde los correos que ya procesa. Revisá cada movimiento antes de incorporarlo a finanzas.", add: "Agregar cuenta", detected: "Bancos detectados", version: "BAC y MultiMoney · versión 1", recognizing: "Reconociendo bancos en tus correos...", noneDetected: "Todavía no encontré correos de BAC o MultiMoney.", detectedByEmail: "Cuenta detectada por correo", movements: "movimientos detectados", review: "por revisar", movement: "Movimiento bancario", pending: "Por revisar", rejected: "Rechazado", duplicate: "Duplicado", inFinance: "En finanzas", approve: "Aprobar movimiento", reject: "Rechazar movimiento", realBalance: "Saldo real registrado", reconcileDifference: "Diferencia por conciliar", manual: "Cuentas manuales", manualHelp: "Saldos que alimentan patrimonio y conciliación", loading: "Cargando cuentas...", noManual: "Todavía no hay saldos manuales. Los bancos detectados arriba no inventan balances.", hideConfirm: "¿Ocultar esta cuenta financiera?", loadError: "No pude cargar las cuentas.", emailError: "No pude leer los movimientos bancarios."
    },
    common: { close: "Cerrar", retry: "Reintentar", month: "mes", months: "meses", currentYear: "Año actual" },
    finance: { loading: "Cargando núcleo financiero...", syncing: "Estoy sincronizando los datos reales de Supabase.", loadError: "No pude cargar el panel financiero", retryHelp: "Revisá los registros de Render o volvé a intentar.", noMovements: "Sin movimientos", chartWhenTransactions: "Cuando haya transacciones, el gráfico se activará.", income: "Ingresos", expensesDebt: "Gastos/deuda", addFinance: "AÑADIR FINANZAS", preview: "VISTA PREVIA", write: "Escribir", speak: "Hablar", baseMonth: "Mes base", dollar: "Dólar", analyze: "Analizar", save: "Guardar", expenses: "Gastos", debts: "Deudas", loans: "Préstamos", noCategories: "Sin categorías todavía", chartWhenExpenses: "Cuando haya gastos registrados, el gráfico se activará.", totalYtd: "TOTAL AÑO", showTotal: "Mostrar total", voiceUnsupported: "Este navegador no soporta reconocimiento de voz.", voiceError: "No pude escucharte bien." },
    strategy: { loading: "Cargando estrategia...", loadError: "No pude cargar la estrategia.", noDate: "Sin fecha estimada", reviewPayment: "Revisar cuota", lifebuoy: "Salvavidas", investments: "Inversiones", debtAdvice: "Asesoría de deudas", distribution: "Distribución de dinero", bonus: "Aguinaldo" },
    wealth: { eyebrow: "CENTRO PATRIMONIAL", title: "Patrimonio", intro: "Una vista ordenada de lo que tenés, lo que debés y lo que está construyendo valor.", control: "Control", netWorthHelp: "Activos, inversiones y deudas consolidados", investmentsHelp: "Aportes, rendimiento, dividendos y costos", businessesHelp: "Proyectos, sociedades e ingresos extra", timelineHelp: "Ingresos, cuotas y compromisos próximos", reconciliationHelp: "Diferencias, gastos olvidados y duplicados", deteriorationHelp: "Alertas tempranas y cambios negativos" },
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
    accounts: {
      eyebrow: "EMAIL BANKING", title: "Accounts", intro: "JARVIS recognizes the institution from the emails it already processes. Review each transaction before adding it to finance.", add: "Add account", detected: "Detected banks", version: "BAC and MultiMoney · version 1", recognizing: "Recognizing banks in your emails...", noneDetected: "I haven’t found BAC or MultiMoney emails yet.", detectedByEmail: "Account detected by email", movements: "detected transactions", review: "to review", movement: "Bank transaction", pending: "To review", rejected: "Rejected", duplicate: "Duplicate", inFinance: "In finance", approve: "Approve transaction", reject: "Reject transaction", realBalance: "Recorded real balance", reconcileDifference: "Reconciliation difference", manual: "Manual accounts", manualHelp: "Balances used for net worth and reconciliation", loading: "Loading accounts...", noManual: "There are no manual balances yet. Detected banks above do not invent balances.", hideConfirm: "Hide this financial account?", loadError: "I couldn’t load the accounts.", emailError: "I couldn’t read the bank transactions."
    },
    common: { close: "Close", retry: "Retry", month: "month", months: "months", currentYear: "Current year" },
    finance: { loading: "Loading financial core...", syncing: "I’m syncing your real Supabase data.", loadError: "I couldn’t load the financial dashboard", retryHelp: "Check Render logs or try again.", noMovements: "No transactions", chartWhenTransactions: "The chart will activate when transactions are recorded.", income: "Income", expensesDebt: "Expenses/debt", addFinance: "ADD FINANCE", preview: "PREVIEW", write: "Write", speak: "Speak", baseMonth: "Base month", dollar: "Dollar", analyze: "Analyze", save: "Save", expenses: "Expenses", debts: "Debts", loans: "Loans", noCategories: "No categories yet", chartWhenExpenses: "The chart will activate when expenses are recorded.", totalYtd: "TOTAL YTD", showTotal: "Show total", voiceUnsupported: "This browser doesn’t support speech recognition.", voiceError: "I couldn’t hear you clearly." },
    strategy: { loading: "Loading strategy...", loadError: "I couldn’t load the strategy.", noDate: "No estimated date", reviewPayment: "Review payment", lifebuoy: "Emergency fund", investments: "Investments", debtAdvice: "Debt advisory", distribution: "Money distribution", bonus: "Annual bonus" },
    wealth: { eyebrow: "WEALTH CENTER", title: "Wealth", intro: "An organized view of what you own, what you owe, and what is building value.", control: "Control", netWorthHelp: "Consolidated assets, investments, and debts", investmentsHelp: "Contributions, performance, dividends, and costs", businessesHelp: "Projects, companies, and extra income", timelineHelp: "Upcoming income, payments, and commitments", reconciliationHelp: "Differences, forgotten expenses, and duplicates", deteriorationHelp: "Early warnings and negative changes" },
  },
};

export const deviceLanguage = () => {
  if (typeof navigator === "undefined") return "es";
  const primary = (navigator.languages?.[0] || navigator.language || "es").toLowerCase();
  return primary.startsWith("es") ? "es" : "en";
};

export const localeTag = (language = deviceLanguage()) => language === "es" ? "es-CR" : "en-US";

// Shared copy helper so JARVIS and FINVA always follow the same device-language rule.
export const tx = (spanish, english, language = deviceLanguage()) =>
  language === "es" ? spanish : english;

export const t = (key, language = deviceLanguage()) => {
  const value = key.split(".").reduce((node, part) => node?.[part], dictionaries[language]);
  return value ?? key;
};

export const applyDocumentLanguage = (language = deviceLanguage()) => {
  if (typeof document !== "undefined") document.documentElement.lang = language;
  return language;
};
