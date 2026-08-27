import { BriefcaseBusiness, ChevronRight, TrendingUp } from "lucide-react";

export default function Wealth({ navigatePage }) {
  return <section className="app-hub-page wealth-hub-page">
    <div className="wealth-hub-intro">
      <span className="strategy-eyebrow">WEALTH CENTER</span>
      <h2>Patrimonio</h2>
      <p>Inversiones, negocios e ingresos que construyen patrimonio fuera de tu salario.</p>
    </div>
    <div className="app-list-group wealth-options-group">
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
