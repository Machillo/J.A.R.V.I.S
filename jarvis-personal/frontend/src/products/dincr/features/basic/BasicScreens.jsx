import { ChevronRight } from "lucide-react";
import { deviceLanguage } from "../../../../lib/locale";
import AccountActions from "../../components/AccountActions";

const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const planning = [
  ["budget", tx("Presupuesto", "Budget"), tx("Controlá cuánto asignás y cuánto queda.", "Control how much you assign and how much remains.")],
  ["calendar", tx("Calendario financiero", "Financial calendar"), tx("Visualizá pagos, ingresos y fechas.", "See payments, income, and important dates.")],
  ["recurring", tx("Recurrentes", "Recurring"), tx("Automatizá tus compromisos habituales.", "Automate your regular commitments.")],
  ["reports", tx("Reportes", "Reports"), tx("Compará tendencias y períodos.", "Compare trends and periods.")],
  ["strategy", tx("Estrategia", "Strategy"), tx("Organizá el dinero disponible del mes.", "Organize the money available this month.")],
];

export default function BasicMore({ onNavigate, onLogout }) {
  return <section className="dincr-basic-more">
    <article className="basic-more-intro">{tx("PLANIFICACIÓN BASIC", "BASIC PLANNING")}</article>
    <div className="basic-more-list">
      {planning.map(([key, title, subtitle]) => <button type="button" key={key} onClick={() => onNavigate(key)}>
        <span><strong>{title}</strong><small>{subtitle}</small></span>
        <ChevronRight size={16}/>
      </button>)}
    </div>
    <button className="basic-more-money" type="button" onClick={() => onNavigate("situation")}>
      <small>{tx("Mi dinero", "My money")}</small>
      <span>{tx("Situación financiera · Historial · Resumen mensual", "Financial situation · History · Monthly summary")}</span>
    </button>
    <div className="basic-more-list">
      <button type="button" onClick={() => onNavigate("settings")}>
        <span><strong>{tx("Ajustes de cuenta y plan", "Account and plan settings")}</strong><small>{tx("Perfil, apariencia, seguridad y cambio de plan.", "Profile, appearance, security, and plan changes.")}</small></span>
        <ChevronRight size={16}/>
      </button>
      <button type="button" onClick={() => onNavigate("feedback")}>
        <span><strong>{tx("Ayuda y soporte", "Help & support")}</strong><small>{tx("Reportá un problema o compartí una sugerencia.", "Report a problem or share feedback.")}</small></span>
        <ChevronRight size={16}/>
      </button>
    </div>
    <AccountActions onLogout={onLogout} variant="basic"/>
  </section>;
}
