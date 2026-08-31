import { useEffect, useState } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Finance from "./pages/Finance";
import Debts from "./pages/Debts";
import StrategyBasic from "./pages/StrategyBasic";
import Goals from "./pages/Goals";
import Transactions from "./pages/Transactions";
import SettingsPage from "./pages/Settings";
import FinancialSituation from "./pages/FinancialSituation";
import Login from "./pages/Login";
import PlanSelection from "./pages/PlanSelection";
import Onboarding from "./pages/Onboarding";
import { getMe, getPersonalSession } from "./services/jarvisApi";
import { supabase } from "./lib/supabase";

export default function App() {
  const [session, setSession] = useState(null);
  const [authReady, setAuthReady] = useState(false);
  const [user, setUser] = useState(null);
  const [page, setPage] = useState("overview");
  const [routingOwner, setRoutingOwner] = useState(false);
  const [ownerRouteError, setOwnerRouteError] = useState("");

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [page]);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setAuthReady(true); });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, nextSession) => { setSession(nextSession); setAuthReady(true); setUser(null); });
    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!session) return;
    setOwnerRouteError("");
    getMe()
      .then(async (profile) => {
        setUser(profile);
        if (profile?.role !== "owner") return;

        if (!profile?.personal_bridge?.linked) {
          setOwnerRouteError("Tu cuenta owner fue reconocida, pero todavía no está vinculada con JARVIS Personal.");
          return;
        }

        setRoutingOwner(true);
        const personal = await getPersonalSession();
        const target = `${personal.personal_app_url}/#jarvis_owner_bridge=${encodeURIComponent(personal.bridge_token)}`;
        window.location.replace(target);
      })
      .catch((error) => {
        setRoutingOwner(false);
        setOwnerRouteError(error?.message || "No pudimos resolver tu identidad JARVIS.");
        setUser(null);
      });
  }, [session]);

  if (!authReady || (session && !user) || routingOwner) return <main className="boot-screen"><strong>J.A.R.V.I.S.</strong><span>{routingOwner ? "Abriendo tu JARVIS Personal..." : "Preparando tu espacio..."}</span></main>;
  if (!session) return <Login />;
  if (!user) return <main className="boot-screen"><strong>No pudimos cargar tu perfil.</strong>{ownerRouteError && <span>{ownerRouteError}</span>}<button onClick={() => supabase.auth.signOut()}>Cerrar sesión</button></main>;
  if (user.role === "owner" && ownerRouteError) return <main className="boot-screen"><strong>Cuenta owner reconocida.</strong><span>{ownerRouteError}</span><button onClick={() => supabase.auth.signOut()}>Cerrar sesión</button></main>;
  if (!user.plan_selected) return <PlanSelection onSelected={setUser} />;
  if (!user.onboarding_completed) return <Onboarding user={user} onComplete={setUser} />;

  const plan = user.subscription?.plan || "free";
  const pages = {
    overview: <Dashboard user={user} plan={plan} onNavigate={setPage} />, finance: <Finance />, debts: <Debts />,
    strategy: <StrategyBasic plan={plan} />, goals: <Goals />, transactions: <Transactions />,
    situation: <FinancialSituation plan={plan} onNavigate={setPage} />,
    settings: <SettingsPage user={user} onUserChange={setUser} />,
  };

  return <div className="app mobile-app-shell">
    <main className="content mobile-content">
      <header className="mobile-app-header">
        <div><strong>J.A.R.V.I.S.</strong><small>{plan === "free" ? "Gratis" : plan.toUpperCase()}</small></div>
        <button className="profile-chip" type="button" onClick={() => setPage("settings")}>{(user.display_name || user.email || "U").slice(0, 1).toUpperCase()}</button>
      </header>
      {pages[page] || pages.overview}
    </main>
    <Sidebar page={page} plan={plan} onNavigate={setPage} onLogout={() => supabase.auth.signOut()} />
  </div>;
}
