import { useEffect, useState } from "react";
import {
  BarChart3, Building2, CalendarDays, ChevronRight, CircleUserRound, CreditCard, Landmark,
  LifeBuoy, LogOut, Mail, ReceiptText, Repeat2, Settings, ShieldCheck,
  SlidersHorizontal, Sparkles, Target, TrendingUp, WalletCards,
} from "lucide-react";
import { tx } from "../../../../lib/locale";
import { getVipGmailStatus } from "../../../../users/services/jarvisApi";

function Hub({ eyebrow, title, description, groups }) {
  return <section className="mobile-page finva-hub-page">
    <div className="mobile-page-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><span>{description}</span></div>
    {groups.filter((group) => group.items.length).map((group) => <section className="finva-hub-group" key={group.title}>
      <h2>{group.title}</h2>
      <div>{group.items.map(({ key, label, detail, icon: Icon, action }) => <button type="button" key={key} onClick={action}>
        <span className="finva-hub-icon"><Icon size={20}/></span><span><strong>{label}</strong><small>{detail}</small></span><ChevronRight size={18}/>
      </button>)}</div>
    </section>)}
  </section>;
}

const item = (navigate, key, label, detail, icon) => ({ key, label, detail, icon, action: () => navigate(key) });

export function PlanHub({ plan, navigate }) {
  const planning = [
    item(navigate, "debts", tx("Deudas", "Debts"), tx("Pagos, saldos y estrategia", "Payments, balances and strategy"), CreditCard),
    item(navigate, "goals", tx("Metas y ahorros", "Goals and savings"), tx("Objetivos que estás construyendo", "Goals you are building"), Target),
  ];
  if (plan !== "free") planning.unshift(item(navigate, "budget", tx("Presupuesto", "Budget"), tx("Decidí cómo usar tu dinero", "Decide how to use your money"), WalletCards));
  const organization = plan === "free" ? [] : [
    item(navigate, "calendar", tx("Calendario financiero", "Financial calendar"), tx("Fechas y compromisos próximos", "Upcoming dates and commitments"), CalendarDays),
    item(navigate, "recurring", tx("Pagos recurrentes", "Recurring payments"), tx("Ingresos y gastos que se repiten", "Recurring income and expenses"), Repeat2),
  ];
  if (plan === "vip") organization.push(
    item(navigate, "vip-emergency", tx("Fondo de emergencia", "Emergency fund"), tx("Tu Salvavidas financiero", "Your financial safety net"), ShieldCheck),
  );
  return <Hub eyebrow="DINCR" title={tx("Tu plan", "Your plan")} description={tx("Todo lo que estás organizando, en un solo lugar.", "Everything you are organizing, in one place.")} groups={[{ title: tx("Construí tu plan", "Build your plan"), items: planning }, { title: tx("Organización", "Organization"), items: organization }]}/>;
}

export function AdvisorHub({ plan, navigate }) {
  const intelligence = plan === "vip" ? [
    item(navigate, "vip-today", tx("DINCR Today", "DINCR Today"), tx("Qué requiere tu atención hoy", "What needs your attention today"), Sparkles),
    item(navigate, "strategy", tx("Dirección VIP", "VIP direction"), tx("Tu prioridad financiera actual", "Your current financial priority"), Landmark),
    item(navigate, "vip-reality", tx("Plan vs realidad", "Plan vs reality"), tx("Compará lo planeado con lo ocurrido", "Compare plan with reality"), BarChart3),
    item(navigate, "vip-monthly-review", tx("Revisión mensual", "Monthly review"), tx("Qué cambió y qué sigue", "What changed and what comes next"), ReceiptText),
    item(navigate, "vip-projections", tx("Proyecciones", "Projections"), tx("Cómo puede evolucionar tu dinero", "How your money may evolve"), TrendingUp),
    item(navigate, "vip-scenarios", tx("Escenarios", "Scenarios"), tx("Probá decisiones antes de tomarlas", "Test decisions before making them"), SlidersHorizontal),
  ] : plan === "basic" ? [item(navigate, "strategy", tx("Mi estrategia", "My strategy"), tx("Una ruta clara para avanzar", "A clear path forward"), Sparkles)] : [item(navigate, "monthly", tx("Resumen mensual", "Monthly summary"), tx("Entendé cómo cerró tu mes", "Understand how your month ended"), BarChart3)];
  return <Hub eyebrow={tx("Tu asesor", "Your advisor")} title="DINCR" description={plan === "vip" ? tx("DINCR aprende de tu historia y reajusta tu estrategia.", "DINCR learns from your history and adjusts your strategy.") : tx("Entendé tu situación y descubrí tu siguiente paso.", "Understand your situation and discover your next step.")} groups={[{ title: tx("Dirección financiera", "Financial direction"), items: intelligence }]}/>;
}

export function ProfileHub({ plan, navigate, onLogout }) {
  // L-2: mail is paused outside the Owner. Only a mailbox or notices from before the pause still show it,
  // so they can be reviewed and the mailbox disconnected.
  const [mailLeftovers, setMailLeftovers] = useState(false);
  useEffect(() => {
    if (plan !== "vip") return undefined;
    let active = true;
    getVipGmailStatus().then((status) => {
      if (active) setMailLeftovers(Boolean(status?.pending) || (status?.connections || []).some((c) => c.status !== "disabled"));
    }).catch(() => {});
    return () => { active = false; };
  }, [plan]);
  const account = [
    item(navigate, "situation", tx("Mi situación financiera", "My financial situation"), tx("Ingresos, gastos y datos personales", "Income, expenses and personal data"), CircleUserRound),
    item(navigate, "settings", tx("Cuenta y plan", "Account and plan"), tx("Perfil, suscripción y preferencias", "Profile, subscription and preferences"), Settings),
  ];
  if (plan === "vip") account.splice(1, 0,
    item(navigate, "accounts", tx("Cuentas", "Accounts"), tx("Tus cuentas propias y días de corte", "Your own accounts and cut days"), Building2),
    ...(mailLeftovers ? [item(navigate, "gmail", tx("Correo conectado anteriormente", "Previously connected mail"), tx("Revisá lo importado o desconectalo", "Review what was imported or disconnect it"), Mail)] : []));
  const support = [item(navigate, "feedback", tx("Ayuda y sugerencias", "Help and feedback"), tx("Soporte y estado del servicio", "Support and service status"), LifeBuoy), { key: "logout", label: tx("Cerrar sesión", "Log out"), detail: tx("Salir de DINCR en este dispositivo", "Sign out of DINCR on this device"), icon: LogOut, action: onLogout }];
  return <Hub eyebrow={tx("Tu cuenta", "Your account")} title={tx("Perfil", "Profile")} description={tx("Configuración, conexiones y soporte.", "Settings, connections and support.")} groups={[{ title: tx("Cuenta", "Account"), items: account }, { title: tx("Soporte", "Support"), items: support }]}/>;
}
