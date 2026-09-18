import { AlertTriangle, BriefcaseBusiness, CalendarDays, CheckCircle2, ChevronRight, Gem, Landmark, TrendingUp } from "lucide-react";
import JarvisDisclosure from "../products/jarvis/components/JarvisDisclosure";
import { deviceLanguage, t } from "../lib/locale";

export default function Wealth({ navigatePage }) {
  const language = deviceLanguage();
  const tr = (key) => t(key, language);
  const wealthGroups = [
    {
      title: tr("nav.wealth"),
      items: [
        ["netWorth", Gem, tr("nav.netWorth"), tr("wealth.netWorthHelp")],
        ["financialAccounts", Landmark, tr("nav.accounts"), language === "es" ? "Saldos reales, efectivo y cuentas financieras" : "Real balances, cash, and financial accounts"],
        ["investments", TrendingUp, tr("nav.investments"), tr("wealth.investmentsHelp")],
        ["businesses", BriefcaseBusiness, tr("nav.businesses"), tr("wealth.businessesHelp")],
      ],
    },
    {
      title: tr("wealth.control"),
      items: [
        ["financialTimeline", CalendarDays, tr("nav.financialTimeline"), tr("wealth.timelineHelp")],
        ["reconciliation", CheckCircle2, tr("nav.reconciliation"), tr("wealth.reconciliationHelp")],
        ["deterioration", AlertTriangle, tr("nav.deterioration"), tr("wealth.deteriorationHelp")],
      ],
    },
  ];

  return (
    <section className="jarvis-v2-screen wealth-v2">
      <header className="wealth-v2-intro">
        <span>{tr("wealth.eyebrow")}</span>
        <h2>{tr("wealth.title")}</h2>
        <p>{tr("wealth.intro")}</p>
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
