import {
  Brain,
  CircleDollarSign,
  Cpu,
  LayoutDashboard,
  ReceiptText,
  Settings,
  ShieldCheck,
  Target,
  WalletCards,
} from "lucide-react";

const menuItems = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "finance", label: "Finanzas", icon: CircleDollarSign },
  { id: "transactions", label: "Transacciones", icon: ReceiptText },
  { id: "goals", label: "Metas", icon: Target },
  { id: "memory", label: "Memory Core", icon: Brain },
  { id: "settings", label: "Config", icon: Settings },
];

const formatCompact = (value) => Math.round(value || 0).toLocaleString("es-CR");

export default function Sidebar({
  activePage,
  setActivePage,
  sidebarOpen,
  setSidebarOpen,
  currentUser,
  aiUsage,
  strategySummary,
}) {
  const isAdmin = currentUser?.role === "owner" || currentUser?.role === "admin";
  const usageText = aiUsage
    ? `${formatCompact(aiUsage.total_tokens)} / ${formatCompact(aiUsage.daily_limit)}`
    : "0 / --";

  return (
    <aside className={`sidebar ${sidebarOpen ? "open" : "closed"}`}>
      <div className="logo">JARVIS</div>

      <nav>
        {menuItems.map((item) => {
          const Icon = item.icon;

          return (
            <button
              key={item.id}
              className={`nav-button ${activePage === item.id ? "active" : ""}`}
              onClick={() => {
                setActivePage(item.id);

                if (window.innerWidth <= 760) {
                  setSidebarOpen(false);
                }
              }}
            >
              <span className="nav-icon">
                <Icon size={20} />
              </span>

              {sidebarOpen && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>


      {sidebarOpen && strategySummary && (
        <div className="sidebar-strategy-card">
          <span className="strategy-kicker">Estrategia actual</span>
          <strong>{strategySummary.title || "Estrategia financiera"}</strong>
          <p>{(strategySummary.summary || "Sin estrategia premium guardada.").slice(0, 140)}</p>
          {Array.isArray(strategySummary.allocations) && strategySummary.allocations.length > 0 && (
            <div className="strategy-mini-list">
              {strategySummary.allocations.slice(0, 3).map((item, index) => (
                <span key={`${item.target_name || index}-${index}`}>
                  <b>{Math.round(item.percentage || 0)}%</b> {item.target_name || "Asignación"}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="sidebar-admin-strip">
        <div className="sidebar-token-pill" title="Tokens IA usados hoy">
          <Cpu size={16} />
          {sidebarOpen && <span>IA: {usageText}</span>}
        </div>

        {isAdmin && (
          <div className="sidebar-admin-pill" title="Permisos administrativos">
            <ShieldCheck size={16} />
            {sidebarOpen && <span>Admin</span>}
          </div>
        )}
      </div>

      <div className="sidebar-core">
        <WalletCards size={28} />
        {sidebarOpen && (
          <>
            <strong>J.A.R.V.I.S.</strong>
            <small>Financial Core Online</small>
          </>
        )}
      </div>
    </aside>
  );
}
