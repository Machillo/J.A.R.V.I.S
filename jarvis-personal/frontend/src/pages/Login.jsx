import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { startOAuthLogin } from "../lib/nativeAuth";
import { tx } from "../lib/locale";
import { detectNativePlatform } from "../ui/native/platform";

// Sign in with Apple is required on iOS (App Store guideline 4.8) and needs the Apple
// provider enabled in Supabase Auth. Android users sign in with Google.
const offersApple = detectNativePlatform() !== "android";

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

function AppleIcon() {
  return (
    <svg className="apple-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M16.37 12.6c-.02-2.1 1.72-3.12 1.8-3.17-.98-1.43-2.5-1.63-3.05-1.65-1.3-.13-2.54.76-3.2.76-.66 0-1.68-.74-2.76-.72-1.42.02-2.73.83-3.46 2.1-1.48 2.56-.38 6.35 1.06 8.43.7 1.02 1.54 2.16 2.63 2.12 1.06-.04 1.46-.68 2.73-.68 1.28 0 1.63.68 2.75.66 1.14-.02 1.86-1.04 2.55-2.06.8-1.18 1.13-2.32 1.15-2.38-.03-.01-2.2-.85-2.2-3.4ZM14.27 6.4c.58-.7.97-1.68.86-2.65-.83.03-1.84.55-2.44 1.25-.54.62-1.01 1.61-.88 2.56.93.07 1.88-.47 2.46-1.16Z" />
    </svg>
  );
}

export default function Login({ nativeError = "" }) {
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  const login = async (provider) => {
    setLoading(provider);
    setError("");
    const { error: authError } = await startOAuthLogin(provider);
    if (authError) setError(tx("No pudimos completar el acceso. Intentá nuevamente.", "We couldn’t sign you in. Please try again."));
    setLoading("");
  };

  return (
    <main className="login-page auth-shell">
      <section className="login-card auth-card">
        <div className="finva-login-top">
          <strong>DINCR</strong>
          <small>{tx("Finanzas personales · Costa Rica", "Personal finance · Costa Rica")}</small>
        </div>

        <div className="finva-login-hero">
          <span className="finva-login-mark" aria-hidden="true">D</span>
          <h1 className="auth-title">DINCR</h1>
          <h2>{tx("Tu dinero, con propósito", "Your money, with purpose")}</h2>
          <p className="finva-login-pillars">
            {tx("Organizá · Planificá · Avanzá · Lográ más", "Organize · Plan · Move forward · Achieve more")}
          </p>
        </div>

        <h3 className="finva-login-account-title">
          {tx("Una cuenta, tus espacios financieros", "One account, your financial spaces")}
        </h3>

        <button className="login-google-btn auth-google-btn" onClick={() => login("google")} disabled={Boolean(loading)} type="button">
          <GoogleIcon />
          {loading === "google" ? tx("Conectando con Google...", "Connecting to Google...") : tx("Continuar con Google", "Continue with Google")}
        </button>
        {offersApple && <button className="login-google-btn auth-google-btn login-apple-btn" onClick={() => login("apple")} disabled={Boolean(loading)} type="button">
          <AppleIcon />
          {loading === "apple" ? tx("Conectando con Apple...", "Connecting to Apple...") : tx("Continuar con Apple", "Continue with Apple")}
        </button>}

        {(error || nativeError) && <p className="auth-message auth-error">{error || nativeError}</p>}

        <p className="login-warning auth-secure-note">
          <ShieldCheck size={15} />
          {offersApple ? tx(
            "Accedé con tu cuenta de Google o Apple. Se abrirá el navegador para continuar.",
            "Sign in with your Google or Apple account. Your browser will open to continue."
          ) : tx(
            "Accedé con tu cuenta de Google. Se abrirá el navegador para continuar.",
            "Sign in with your Google account. Your browser will open to continue."
          )}
        </p>
      </section>
    </main>
  );
}
