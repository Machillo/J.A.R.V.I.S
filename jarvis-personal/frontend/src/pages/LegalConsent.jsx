import { CheckCircle2, FileText, LockKeyhole, LogOut } from "lucide-react";
import { useState } from "react";
import { acceptLegal } from "../services/jarvisApi";
import { supabase } from "../lib/supabase";
import { tx } from "../lib/locale";

export default function LegalConsent({ user, onAccepted }) {
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const legal = user?.legal || {};

  const submit = async (event) => {
    event.preventDefault();
    if (!termsAccepted || !privacyAccepted) {
      setError(tx("Debés aceptar ambos documentos para continuar.", "You must accept both documents to continue."));
      return;
    }
    setSaving(true);
    setError("");
    try {
      const profile = await acceptLegal({
        accept_terms: true,
        accept_privacy: true,
        terms_version: legal.terms_version,
        privacy_version: legal.privacy_version,
      });
      onAccepted?.(profile);
    } catch (err) {
      setError(err.message || tx("No pudimos registrar tu aceptación.", "We couldn’t record your acceptance."));
    } finally {
      setSaving(false);
    }
  };

  return <main className="legal-consent-shell">
    <form className="legal-consent-card" onSubmit={submit}>
      <header className="legal-consent-top">
        <div><strong>DINCR</strong><small>JARVIS Financial Intelligence</small></div>
        <button type="button" onClick={() => supabase.auth.signOut()}><LogOut size={17}/> {tx("Salir", "Log out")}</button>
      </header>

      <div className="legal-consent-heading">
        <span>{tx("ANTES DE CONTINUAR", "BEFORE YOU CONTINUE")}</span>
        <h1>{tx("Tu información, tus reglas", "Your information, your rules")}</h1>
        <p>{tx("Leé y aceptá los documentos que explican cómo funciona el servicio y cómo protegemos tus datos.", "Read and accept the documents explaining how the service works and how we protect your data.")}</p>
      </div>

      <a className="legal-document-link" href="/terms" target="_blank" rel="noreferrer">
        <FileText size={23}/><span><strong>{tx("Términos y Condiciones", "Terms and Conditions")}</strong><small>{tx("Uso del servicio, planes, pagos y responsabilidades.", "Service use, plans, payments, and responsibilities.")}</small></span><span>{tx("Leer", "Read")}</span>
      </a>
      <a className="legal-document-link" href="/privacy" target="_blank" rel="noreferrer">
        <LockKeyhole size={23}/><span><strong>{tx("Política de Privacidad", "Privacy Policy")}</strong><small>{tx("Datos recopilados, finalidad, seguridad y tus derechos.", "Data collected, purpose, security, and your rights.")}</small></span><span>{tx("Leer", "Read")}</span>
      </a>

      <label className="legal-check">
        <input type="checkbox" checked={termsAccepted} onChange={(event) => { setTermsAccepted(event.target.checked); setError(""); }}/>
        <span>{tx("Acepto los", "I accept the")} <a href="/terms" target="_blank" rel="noreferrer">{tx("Términos y Condiciones", "Terms and Conditions")}</a>.</span>
      </label>
      <label className="legal-check">
        <input type="checkbox" checked={privacyAccepted} onChange={(event) => { setPrivacyAccepted(event.target.checked); setError(""); }}/>
        <span>{tx("He leído y acepto la", "I have read and accept the")} <a href="/privacy" target="_blank" rel="noreferrer">{tx("Política de Privacidad", "Privacy Policy")}</a> {tx("y el tratamiento necesario de mis datos para prestar el servicio.", "and the processing of my data required to provide the service.")}</span>
      </label>

      <div className="legal-safety-note"><CheckCircle2 size={18}/><span>{tx("No vendemos tus datos ni los usamos para publicidad de terceros.", "We do not sell your data or use it for third-party advertising.")}</span></div>
      {error && <p className="legal-consent-error">{error}</p>}
      <button className="legal-consent-submit" disabled={saving || !termsAccepted || !privacyAccepted}>
        {saving ? tx("Guardando...", "Saving...") : tx("Aceptar y continuar", "Accept and continue")}
      </button>
      <small className="legal-version">{tx("Versión", "Version")} {legal.terms_version || tx("vigente", "current")}</small>
    </form>
  </main>;
}
