import { AlertTriangle, BriefcaseBusiness, CalendarDays, CheckCircle2, ChevronRight, Gem, Landmark, TrendingUp } from "lucide-react";
import JarvisDisclosure from "../products/jarvis/components/JarvisDisclosure";

const wealthGroups = [
  {
    title: "Patrimonio",
    items: [
      ["netWorth", Gem, "Patrimonio neto", "Activos, inversiones y deudas consolidados"],
      ["financialAccounts", Landmark, "Cuentas", "Saldos reales, efectivo y cuentas financieras"],
      ["investments", TrendingUp, "Inversiones", "Aportes, rendimiento, dividendos y costos"],
      ["businesses", BriefcaseBusiness, "Negocios", "Proyectos, sociedades e ingresos extra"],
    ],
  },
  {
    title: "Control",
    items: [
      ["financialTimeline", CalendarDays, "Timeline financiero", "Ingresos, cuotas y compromisos próximos"],
      ["reconciliation", CheckCircle2, "Conciliación", "Diferencias, gastos olvidados y duplicados"],
      ["deterioration", AlertTriangle, "Deterioro financiero", "Alertas tempranas y cambios negativos"],
    ],
  },
];

export default function Wealth({ navigatePage }) {
  return (
    <section className="jarvis-v2-screen wealth-v2">
      <header className="wealth-v2-intro">
        <span>WEALTH CENTER</span>
        <h2>Patrimonio</h2>
        <p>Una vista ordenada de lo que tenés, lo que debés y lo que está construyendo valor.</p>
      </header>

      {wealthGroups.map((group) => (
        <JarvisDisclosure title={group.title} key={group.title} className="wealth-v2-group">
          <div className="jarvis-v2-group">
            {group.items.map(([page, Icon, title, subtitle]) => (
              <button className="jarvis-v2-row" type="button" key={page} onClick={() => navigatePage(page)}>
                <span className="jarvis-v2-row-icon"><Icon size={18} /></span>
                <span className="jarvis-v2-row-copy"><strong>{title}</strong><small>{subtitle}</small></span>
                <ChevronRight size={17} className="wealth-v2-chevron" />
              </button>
            ))}
          </div>
        </JarvisDisclosure>
      ))}
    </section>
  );
}
