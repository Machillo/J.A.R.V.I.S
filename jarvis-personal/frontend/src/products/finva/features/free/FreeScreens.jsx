import { useEffect, useMemo, useState } from "react";
import { ChevronRight, CircleHelp, Clock3, History, Landmark, LogOut, PiggyBank, ReceiptText, ShieldCheck, WalletCards } from "lucide-react";
import AppearanceSelector from "../../../../components/AppearanceSelector";
import { deviceLanguage, localeTag } from "../../../../lib/locale";
import { getSavingsPlans } from "../../../../users/services/jarvisApi";

const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;
const money = (value) => new Intl.NumberFormat(localeTag(language), { style:"currency", currency:"CRC", maximumFractionDigits:0 }).format(Number(value) || 0);

function MenuRow({ icon: Icon, title, subtitle, onClick, danger = false }) {
  return <button className={`free-menu-row ${danger ? "danger" : ""}`} type="button" onClick={onClick}>
    <span className="free-menu-icon"><Icon size={19}/></span>
    <span><strong>{title}</strong>{subtitle ? <small>{subtitle}</small> : null}</span>
    <ChevronRight size={18}/>
  </button>;
}

export function FreeMore({ onNavigate, onLogout }) {
  const [savings, setSavings] = useState([]);
  useEffect(() => { getSavingsPlans().then(setSavings).catch(() => setSavings([])); }, []);
  const total = useMemo(() => savings.reduce((sum, item) => sum + Number(item.saved_amount || 0), 0), [savings]);
  const monthly = useMemo(() => savings.reduce((sum, item) => sum + Number(item.monthly_amount || 0), 0), [savings]);
  const first = savings[0];

  return <section className="free-screen free-more-screen">
    <small className="free-plan-label">{tx("Gratis", "Free")}</small>
    <article className="free-summary-card free-summary-card--green">
      <small>{tx("AHORRO PROGRAMADO", "SCHEDULED SAVINGS")}</small>
      <strong>{money(total)}</strong>
      <span>{money(monthly)}/{tx("mes", "month")} · {savings.length} {tx("planes activos", "active plans")}</span>
    </article>
    <article className="free-section-card">
      <header><strong>{tx("Próximo ahorro", "Next saving")}</strong><button type="button" onClick={() => onNavigate("savings")}>{tx("Administrar", "Manage")}</button></header>
      {first ? <div className="free-saving-row"><span className="free-row-icon"><PiggyBank size={20}/></span><span><strong>{first.name}</strong><small>{first.end_date ? `${tx("Hasta", "Until")} ${first.end_date}` : tx("Sin fecha final", "No end date")}</small></span><b>{money(first.monthly_amount)}</b></div> : <p className="free-empty">{tx("Todavía no programaste ahorros.", "You haven't scheduled savings yet.")}</p>}
    </article>
    <div className="free-menu-card">
      <MenuRow icon={Landmark} title={tx("Situación financiera", "Financial situation")} subtitle={tx("Ingresos, compromisos y moneda", "Income, commitments and currency")} onClick={() => onNavigate("situation")}/>
      <MenuRow icon={History} title={tx("Historial completo", "Full history")} subtitle={tx("Todos tus movimientos", "All your transactions")} onClick={() => onNavigate("transactions")}/>
      <MenuRow icon={ReceiptText} title={tx("Resumen mensual", "Monthly summary")} subtitle={tx("Así cerró tu mes", "How your month ended")} onClick={() => onNavigate("monthly")}/>
      <MenuRow icon={CircleHelp} title={tx("Ayuda y soporte", "Help & support")} subtitle={tx("Contanos un problema o mejora", "Tell us about an issue or idea")} onClick={() => onNavigate("feedback")}/>
    </div>
    <button className="free-text-action" type="button" onClick={onLogout}><LogOut size={17}/>{tx("Cerrar sesión", "Log out")}</button>
  </section>;
}

export function FreeSettings({ user, onNavigate, onLogout }) {
  const initial = (user?.display_name || user?.email || "U").slice(0,1).toUpperCase();
  return <section className="free-screen free-settings-screen">
    <article className="free-profile-card"><span>{initial}</span><div><strong>{user?.display_name || tx("Usuario", "User")}</strong><small>{user?.email}</small></div><ChevronRight size={18}/></article>
    <div className="free-settings-group">
      <small>{tx("APARIENCIA", "APPEARANCE")}</small>
      <AppearanceSelector/>
    </div>
    <div className="free-menu-card">
      <MenuRow icon={WalletCards} title={tx("Moneda y formato", "Currency & format")} subtitle={tx("Colón costarricense · CRC", "Costa Rican colón · CRC")} onClick={() => onNavigate("situation")}/>
      <MenuRow icon={ShieldCheck} title={tx("Privacidad y seguridad", "Privacy & security")} subtitle={tx("Cuenta y permisos", "Account and permissions")} onClick={() => onNavigate("plan-settings")}/>
      <MenuRow icon={Clock3} title={tx("Plan", "Plan")} subtitle={tx("FINVA Gratis", "FINVA Free")} onClick={() => onNavigate("plan-settings")}/>
      <MenuRow icon={CircleHelp} title={tx("Ayuda", "Help")} subtitle={tx("Soporte FINVA", "FINVA support")} onClick={() => onNavigate("feedback")}/>
    </div>
    <button className="free-logout-button" type="button" onClick={onLogout}><LogOut size={18}/>{tx("Cerrar sesión", "Log out")}</button>
  </section>;
}
