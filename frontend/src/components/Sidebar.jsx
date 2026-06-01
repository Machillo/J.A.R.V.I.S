import { LayoutDashboard, Wallet, Target, Brain, Settings } from "lucide-react";

const menuItems = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "finance", label: "Finanzas", icon: Wallet },
  { id: "goals", label: "Metas", icon: Target },
  { id: "memory", label: "Memoria", icon: Brain },
  { id: "settings", label: "Config", icon: Settings },
];

export default function Sidebar({ activePage, setActivePage }) {
  return (
    <aside className="sidebar">
      <div className="logo">J.A.R.V.I.S</div>

      <nav>
        {menuItems.map((item) => {
          const Icon = item.icon;

          return (
            <button
              key={item.id}
              className={`nav-button ${activePage === item.id ? "active" : ""}`}
              onClick={() => setActivePage(item.id)}
            >
              <Icon size={20} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}