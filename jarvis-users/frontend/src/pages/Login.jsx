import { Apple, BrainCircuit, Fingerprint, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { supabase } from "../lib/supabase";

function GoogleIcon() {
  return (
    <svg className="google-icon" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.4-.4-3.5Z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 16.2 4 9.5 8.5 6.3 14.7Z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.3 0-9.7-3.3-11.3-7.9l-6.5 5C9.4 39.6 16.1 44 24 44Z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.3 4.2-4.1 5.6l6.2 5.2C36.9 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5Z" />
    </svg>
  );
}

export default function Login() {
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  const oauth = async (provider) => {
    setLoading(provider);
    setError("");
    const { error: authError } = await supabase.auth.signInWithOAuth({
      provider,
      options: provider === "google" ? { queryParams: { prompt: "select_account" } } : undefined,
    });
    if (authError) {
      setError(authError.message);
      setLoading("");
    }
  };

  const loginWithPasskey = async () => {
    setLoading("passkey");
    setError("");
    const { error: authError } = await supabase.auth.signInWithPasskey();
    if (authError) {
      setError(authError.message);
      setLoading("");
    }
  };

  return (
    <main className="login-page auth-shell">
      <div className="auth-grid-lines" aria-hidden="true"></div>
      <div className="auth-aura auth-aura-one" aria-hidden="true"></div>
      <div className="auth-aura auth-aura-two" aria-hidden="true"></div>
      <section className="login-card auth-card">
        <div className="auth-orb-wrap"><div className="auth-orb-glow"></div><div className="auth-orb"><BrainCircuit size={58} /></div></div>
        <p className="login-kicker">JARVIS</p>
        <h1 className="auth-title">J.A.R.V.I.S.</h1>
        <p className="login-subtitle">Una cuenta JARVIS. Elegí cómo demostrar que sos vos.</p>

        <div className="auth-methods">
          <button className="login-google-btn auth-google-btn" onClick={() => oauth("google")} disabled={Boolean(loading)} type="button">
            <GoogleIcon /> {loading === "google" ? "Conectando..." : "Continuar con Google"}
          </button>
          <button className="auth-provider-btn" onClick={() => oauth("apple")} disabled={Boolean(loading)} type="button">
            <Apple size={20} /> {loading === "apple" ? "Conectando..." : "Continuar con Apple"}
          </button>
          <button className="auth-provider-btn auth-passkey-btn" onClick={loginWithPasskey} disabled={Boolean(loading)} type="button">
            <Fingerprint size={21} /> {loading === "passkey" ? "Verificando..." : "Entrar con Passkey / Face ID"}
          </button>
        </div>

        {error && <p className="onboarding-error">{error}</p>}
        <p className="auth-security"><ShieldCheck size={16} /> Face ID nunca sale de tu dispositivo. Desbloquea localmente tu passkey.</p>
      </section>
    </main>
  );
}
