import {
  Brain,
  CircleDollarSign,
  LayoutDashboard,
  Settings,
  Target,
  WalletCards,
} from "lucide-react";

const menuItems = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "finance", label: "Finanzas", icon: CircleDollarSign },
  { id: "goals", label: "Metas", icon: Target },
  { id: "memory", label: "Memory Core", icon: Brain },
  { id: "settings", label: "Config", icon: Settings },
];

export default function Sidebar({
  activePage,
  setActivePage,
  sidebarOpen,
  setSidebarOpen,
}) {
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