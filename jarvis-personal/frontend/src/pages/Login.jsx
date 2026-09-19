import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { startGoogleLogin } from "../lib/nativeAuth";
import { tx } from "../lib/locale";

function GoogleIcon() {
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

        <button
          className="login-google-btn auth-google-btn"
          onClick={loginWithGoogle}
          disabled={loading}
          type="button"
        >
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
  );}
