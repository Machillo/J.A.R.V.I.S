import { useCallback, useEffect, useRef, useState } from "react";
import { App as CapacitorApp } from "@capacitor/app";
import { flushPendingOperations } from "./lib/operationRecovery";
import Login from "./pages/Login";
import FinvaOnboarding from "./pages/FinvaOnboarding";
import ProfileSetup from "./pages/ProfileSetup";
import LegalConsent from "./pages/LegalConsent";
import PersonalApp from "./personal/PersonalApp";
import UsersApp from "./users/UsersApp";
import { getMe, getOwnerBridgeToken, setOwnerBridgeToken } from "./services/jarvisApi";
import { supabase } from "./lib/supabase";
import { registerNativeAuthListener } from "./lib/nativeAuth";
import { identifyTelemetryUser, trackEvent } from "./lib/telemetry";
import { openSupport } from "./lib/apiErrors";
import { tx } from "./lib/locale";
import ReleaseUpdateNotice from "./components/ReleaseUpdateNotice";
import { getReleasePolicy } from "./lib/releasePolicy";
import { detectNativePlatform } from "./ui/native/platform";

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
  const [nativeAuthError, setNativeAuthError] = useState("");
  const [releasePolicy, setReleasePolicy] = useState(null);
  const currentUserRef = useRef(null);

  const refreshReleasePolicy = useCallback(async () => {
    try {
      setReleasePolicy(await getReleasePolicy(detectNativePlatform()));
    } catch {
      // Compatibility checks are fail-open: a network or backend outage must
      // never strand a user outside FINVA.
      setReleasePolicy(null);
    }
  }, []);

  useEffect(() => { refreshReleasePolicy(); }, [refreshReleasePolicy]);

  useEffect(() => {
    currentUserRef.current = currentUser;
    identifyTelemetryUser(currentUser);
  }, [currentUser]);

  useEffect(() => {
    let cleanup = () => {};
    registerNativeAuthListener(setNativeAuthError).then((remove) => { cleanup = remove; });
    return () => cleanup();
  }, []);

  useEffect(() => {
    let activeUserId = null;
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
      activeUserId = data.session?.user?.id || null;
      setSession(data.session);
      setSessionLoaded(true);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, nextSession) => {
      const nextUserId = nextSession?.user?.id || null;
      const identityChanged = event === "SIGNED_OUT" || (activeUserId !== null && activeUserId !== nextUserId);
      activeUserId = nextUserId;
      setSession(nextSession);
      // Returning from Android's file picker can refresh the Supabase token.
      // Keep the mounted screen during TOKEN_REFRESHED so transient state
      // such as the selected receipt is not lost.
      if (identityChanged) setCurrentUser(null);
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

  useEffect(() => {
    if (ownerBridgeMode || !session) return;

    let cancelled = false;
    let nativeListener;
    let refreshing = false;
    let lastRefreshAt = 0;

    const profileChanged = (previous, next) => {
      if (!previous) return true;
      const fields = ["id", "role", "plan", "plan_selected", "profile_setup_completed", "display_name", "base_currency", "onboarding_completed", "subscription_status"];
      return fields.some((field) => previous?.[field] !== next?.[field])
        || previous?.subscription?.plan !== next?.subscription?.plan
        || previous?.subscription?.status !== next?.subscription?.status;
    };

    const refreshProfile = async () => {
      const now = Date.now();
      if (refreshing || now - lastRefreshAt < 15_000) return;
      refreshing = true;
      lastRefreshAt = now;
      try {
        const profile = await getMe();
        if (!cancelled) {
          if (profileChanged(currentUserRef.current, profile)) setCurrentUser(profile);
          setIdentityError("");
        }
      } catch {
        // Keep the current screen usable on a temporary network failure.
      } finally {
        refreshing = false;
      }
    };

    CapacitorApp.addListener("appStateChange", ({ isActive }) => {
      if (isActive) {
        trackEvent("app_resumed");
        flushPendingOperations();
        refreshProfile();
        refreshReleasePolicy();
      }
    }).then((listener) => {
      nativeListener = listener;
    });

    return () => {
      cancelled = true;
      nativeListener?.remove();
    };
  }, [session, ownerBridgeMode, refreshReleasePolicy]);

  if (ownerBridgeMode) {
    return <PersonalApp />;
  }

  if (!sessionLoaded) {
    return <BootScreen message={tx("Inicializando sesión...", "Initializing session...")} />;
  }

  if (!session) {
    return <Login nativeError={nativeAuthError} />;
  }

  if (identityError) {
    return (
      <main className="unified-router-boot">
        <strong>{tx("No pudimos cargar tu cuenta.", "We couldn’t load your account.")}</strong>
        <span>{identityError || tx("Intentá nuevamente o escribinos desde soporte.", "Try again or contact support.")}</span>
        <div className="boot-actions">
          <button type="button" onClick={() => window.location.reload()}>{tx("Intentar de nuevo", "Try again")}</button>
          <button type="button" onClick={() => { openSupport({ kind: "problem", screen: "inicio", summary: tx("No se pudo cargar la cuenta.", "The account could not be loaded.") }); window.location.reload(); }}>{tx("Abrir soporte", "Open support")}</button>
          <button type="button" onClick={() => supabase.auth.signOut()}>{tx("Cerrar sesión", "Log out")}</button>
        </div>
      </main>
    );
  }

  if (!currentUser) {
    return <BootScreen />;
  }

  if (currentUser.role !== "owner" && currentUser.role !== "admin" && releasePolicy?.required) {
    return <ReleaseUpdateNotice policy={releasePolicy} required onRefresh={refreshReleasePolicy} />;
  }

  if (currentUser.role !== "owner" && currentUser.role !== "admin" && currentUser.legal?.required) {
    return <LegalConsent user={currentUser} onAccepted={setCurrentUser} />;
  }

  if (!currentUser.profile_setup_completed) {
    return <ProfileSetup user={currentUser} onComplete={setCurrentUser} />;
  }

  if (currentUser.role === "owner" || currentUser.role === "admin") {
    return <PersonalApp />;
  }

  if (!currentUser.plan_selected) {
    return (
      <FinvaOnboarding
        user={currentUser}
        onComplete={(profile) => setCurrentUser(profile)}
      />
    );
  }

  return <UsersApp user={currentUser} onUserChange={setCurrentUser} releasePolicy={releasePolicy} />;
}
