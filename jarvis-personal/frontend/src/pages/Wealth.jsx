import { AlertTriangle, BriefcaseBusiness, CalendarDays, CheckCircle2, ChevronRight, Gem, Landmark, TrendingUp } from "lucide-react";

export default function Wealth({ navigatePage }) {
  return <section className="app-hub-page wealth-hub-page">
    <div className="wealth-hub-intro">
      <span className="strategy-eyebrow">WEALTH CENTER</span>
      <h2>Patrimonio</h2>
      <p>Inversiones, negocios e ingresos que construyen patrimonio fuera de tu salario.</p>
    </div>
    <div className="app-list-group wealth-options-group">
      <button className="app-list-item" onClick={() => navigatePage("deterioration")}>
        <span className="app-list-icon"><AlertTriangle size={24}/></span>
        <span className="app-list-copy"><strong>Deterioro financiero</strong><small>Alertas tempranas y causas de cambios negativos</small></span>
        <ChevronRight size={22} className="app-list-chevron" />
      </button>
      <button className="app-list-item" onClick={() => navigatePage("reconciliation")}>
        <span className="app-list-icon"><CheckCircle2 size={24}/></span>
        <span className="app-list-copy"><strong>Conciliación financiera</strong><small>Detectar diferencias, gastos olvidados y posibles duplicados</small></span>
        <ChevronRight size={22} className="app-list-chevron" />
      </button>
      <button className="app-list-item" onClick={() => navigatePage("financialTimeline")}>
        <span className="app-list-icon"><CalendarDays size={24}/></span>
        <span className="app-list-copy"><strong>Timeline financiero</strong><small>Liquidez móvil, ingresos, cuotas y compromisos próximos</small></span>
        <ChevronRight size={22} className="app-list-chevron" />
      </button>
      <button className="app-list-item" onClick={() => navigatePage("netWorth")}>
        <span className="app-list-icon"><Gem size={24}/></span>
        <span className="app-list-copy"><strong>Patrimonio neto en vivo</strong><small>Activos, inversiones, deudas e historial consolidado</small></span>
        <ChevronRight size={22} className="app-list-chevron" />
      </button>
      <button className="app-list-item" onClick={() => navigatePage("financialAccounts")}>
        <span className="app-list-icon"><Landmark size={24}/></span>
        <span className="app-list-copy"><strong>Cuentas financieras</strong><small>BAC, MultiMoney, efectivo, Salvavidas y saldos reales</small></span>
        <ChevronRight size={22} className="app-list-chevron" />
      </button>
      <button className="app-list-item" onClick={() => navigatePage("investments")}>
        <span className="app-list-icon"><TrendingUp size={24}/></span>
        <span className="app-list-copy"><strong>Inversiones</strong><small>IBKR, aportes, rendimiento, dividendos y costos</small></span>
        <ChevronRight size={22} className="app-list-chevron" />
      </button>
      <button className="app-list-item" onClick={() => navigatePage("businesses")}>
        <span className="app-list-icon"><BriefcaseBusiness size={24}/></span>
        <span className="app-list-copy"><strong>Negocios</strong><small>JARVIS, bot, sociedades e ingresos extra</small></span>
        <ChevronRight size={22} className="app-list-chevron" />
      </button>
    </div>
  </section>;
}
