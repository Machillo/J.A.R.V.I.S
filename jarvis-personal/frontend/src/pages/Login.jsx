import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { startGoogleLogin } from "../lib/nativeAuth";
import { tx } from "../lib/locale";

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

export default function Login({ nativeError = "" }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loginWithGoogle = async () => {
    setLoading(true);
    setError("");
    const { error: authError } = await startGoogleLogin();
    if (authError) {
      setError(authError.message);
      setLoading(false);
      return;
    }
    setLoading(false);
  };

  return (
    <main className="login-page auth-shell">
      <section className="login-card auth-card">
        <div className="finva-login-top">
          <strong>FINVA</strong>
          <small>JARVIS Financial Intelligence</small>
        </div>

        <div className="finva-login-hero">
          <span className="finva-login-mark" aria-hidden="true">F</span>
          <h1 className="auth-title">FINVA</h1>
          <h2>{tx("Tu vida financiera, en equilibrio", "Your financial life, in balance")}</h2>
          <p className="finva-login-pillars">
            {tx("Organizá · Planificá · Avanzá · Lográ más", "Organize · Plan · Move forward · Achieve more")}
          </p>
        </div>

        <h3 className="finva-login-account-title">
          {tx("Una cuenta, tus espacios financieros", "One account, your financial spaces")}
        </h3>

        <button className="login-google-btn auth-google-btn" onClick={loginWithGoogle} disabled={loading} type="button">
          <GoogleIcon />
          {loading ? tx("Conectando con Google...", "Connecting to Google...") : tx("Continuar con Google", "Continue with Google")}
        </button>

        {(error || nativeError) && <p className="auth-message auth-error">{error || nativeError}</p>}

        <p className="login-warning auth-secure-note">
          <ShieldCheck size={15} />
          {tx(
            "Google es actualmente nuestro único método de acceso seguro. Se abrirá el navegador para continuar.",
            "Google is currently our only secure sign-in method. Your browser will open to continue."
          )}
        </p>
      </section>
    </main>
  );
}
