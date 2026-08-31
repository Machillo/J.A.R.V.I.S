import { useEffect, useState } from "react";
import Login from "./pages/Login";
import UnifiedOnboarding from "./pages/UnifiedOnboarding";
import PersonalApp from "./personal/PersonalApp";
import UsersApp from "./users/UsersApp";
import { getMe, getOwnerBridgeToken, setOwnerBridgeToken } from "./services/jarvisApi";
import { supabase } from "./lib/supabase";

function BootScreen({ message = "Preparando tu espacio..." }) {
  return (
    <main className="unified-router-boot">
      <strong>FINVA</strong>
      <span>{message}</span>
    </main>
  );
}

export default function App() {
  const [session, setSession] = useState(null);
  const [sessionLoaded, setSessionLoaded] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  const [identityError, setIdentityError] = useState("");
  const [ownerBridgeMode, setOwnerBridgeMode] = useState(false);

  useEffect(() => {
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const incomingBridgeToken = hash.get("jarvis_owner_bridge");

    if (incomingBridgeToken) {
      setOwnerBridgeToken(incomingBridgeToken);
      setOwnerBridgeMode(true);
      setSessionLoaded(true);
      return;
    }

    if (getOwnerBridgeToken()) {
      setOwnerBridgeMode(true);
      setSessionLoaded(true);
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setSessionLoaded(true);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setCurrentUser(null);
      setIdentityError("");
      setSessionLoaded(true);
    });

    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    const isPersonal = ownerBridgeMode || currentUser?.role === "owner" || currentUser?.role === "admin";
    document.title = isPersonal ? "J.A.R.V.I.S." : "Finva";
  }, [ownerBridgeMode, currentUser]);

  useEffect(() => {
    if (ownerBridgeMode || !session) return;

    let cancelled = false;
    getMe()
      .then((profile) => {
        if (!cancelled) setCurrentUser(profile);
      })
      .catch((error) => {
        if (!cancelled) setIdentityError(error?.message || "No pudimos resolver tu cuenta.");
      });

    return () => { cancelled = true; };
  }, [session, ownerBridgeMode]);

  if (ownerBridgeMode) {
    return <PersonalApp />;
  }

  if (!sessionLoaded) {
    return <BootScreen message="Inicializando sesión..." />;
  }

  if (!session) {
    return <Login />;
  }

  if (identityError) {
    return (
      <main className="unified-router-boot">
        <strong>No pudimos cargar tu cuenta.</strong>
        <span>{identityError}</span>
        <button type="button" onClick={() => supabase.auth.signOut()}>Cerrar sesión</button>
      </main>
    );
  }

  if (!currentUser) {
    return <BootScreen />;
  }

  if (currentUser.role === "owner" || currentUser.role === "admin") {
    return <PersonalApp />;
  }

  if (!currentUser.plan_selected || !currentUser.onboarding_completed) {
    return (
      <UnifiedOnboarding
        user={currentUser}
        onComplete={(profile) => setCurrentUser(profile)}
      />
    );
  }

  return <UsersApp user={currentUser} onUserChange={setCurrentUser} />;
}
