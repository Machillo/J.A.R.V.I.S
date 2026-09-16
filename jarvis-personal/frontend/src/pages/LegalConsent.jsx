import { CheckCircle2, FileText, LockKeyhole, LogOut } from "lucide-react";
import { useState } from "react";
import { acceptLegal } from "../services/jarvisApi";
import { supabase } from "../lib/supabase";

export default function LegalConsent({ user, onAccepted }) {
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const legal = user?.legal || {};

  const submit = async (event) => {
    event.preventDefault();
    if (!termsAccepted || !privacyAccepted) {
      setError("Debés aceptar ambos documentos para continuar.");
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
      setError(err.message || "No pudimos registrar tu aceptación.");
    } finally {
      setSaving(false);
    }
  };

  return <main className="legal-consent-shell">
    <form className="legal-consent-card" onSubmit={submit}>
      <header className="legal-consent-top">
        <div><strong>FINVA</strong><small>JARVIS Financial Intelligence</small></div>
        <button type="button" onClick={() => supabase.auth.signOut()}><LogOut size={17}/> Salir</button>
      </header>

      <div className="legal-consent-heading">
        <span>ANTES DE CONTINUAR</span>
        <h1>Tu información, tus reglas</h1>
        <p>Leé y aceptá los documentos que explican cómo funciona el servicio y cómo protegemos tus datos.</p>
      </div>

      <a className="legal-document-link" href="/terms" target="_blank" rel="noreferrer">
        <FileText size={23}/><span><strong>Términos y Condiciones</strong><small>Uso del servicio, planes, pagos y responsabilidades.</small></span><span>Leer</span>
      </a>
      <a className="legal-document-link" href="/privacy" target="_blank" rel="noreferrer">
        <LockKeyhole size={23}/><span><strong>Política de Privacidad</strong><small>Datos recopilados, finalidad, seguridad y tus derechos.</small></span><span>Leer</span>
      </a>

      <label className="legal-check">
        <input type="checkbox" checked={termsAccepted} onChange={(event) => { setTermsAccepted(event.target.checked); setError(""); }}/>
        <span>Acepto los <a href="/terms" target="_blank" rel="noreferrer">Términos y Condiciones</a>.</span>
      </label>
      <label className="legal-check">
        <input type="checkbox" checked={privacyAccepted} onChange={(event) => { setPrivacyAccepted(event.target.checked); setError(""); }}/>
        <span>He leído y acepto la <a href="/privacy" target="_blank" rel="noreferrer">Política de Privacidad</a> y el tratamiento necesario de mis datos para prestar el servicio.</span>
      </label>

      <div className="legal-safety-note"><CheckCircle2 size={18}/><span>No vendemos tus datos ni los usamos para publicidad de terceros.</span></div>
      {error && <p className="legal-consent-error">{error}</p>}
      <button className="legal-consent-submit" disabled={saving || !termsAccepted || !privacyAccepted}>
        {saving ? "Guardando..." : "Aceptar y continuar"}
      </button>
      <small className="legal-version">Versión {legal.terms_version || "vigente"}</small>
    </form>
  </main>;
}
