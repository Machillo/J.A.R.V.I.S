import { Apple, CheckCircle2, Fingerprint, Link2, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { supabase } from "../../lib/supabase";
import { tx } from "../../lib/locale";

export default function AccountSecurity({ user }) {
  const [identities, setIdentities] = useState([]);
  const [passkeys, setPasskeys] = useState([]);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const reload = async () => {
    setError("");
    const [{ data: identityData, error: identityError }, { data: passkeyData, error: passkeyError }] = await Promise.all([
      supabase.auth.getUserIdentities(),
      supabase.auth.passkey?.list ? supabase.auth.passkey.list() : Promise.resolve({ data: [], error: null }),
    ]);
    if (identityError) setError(identityError.message);
    else setIdentities(identityData?.identities || []);
    if (!passkeyError) setPasskeys(passkeyData || []);
  };

  useEffect(() => { reload(); }, []);

  const hasProvider = (provider) => identities.some((identity) => identity.provider === provider);

  const linkApple = async () => {
    setBusy("apple"); setError(""); setMessage("");
    const { error: linkError } = await supabase.auth.linkIdentity({ provider: "apple" });
    if (linkError) { setError(linkError.message); setBusy(""); }
  };

  const registerPasskey = async () => {
    setBusy("passkey"); setError(""); setMessage("");
    if (!supabase.auth.registerPasskey) { setError(tx("Las passkeys todavía no están disponibles en este cliente.", "Passkeys are not available in this client yet.")); setBusy(""); return; }
    const { data, error: passkeyError } = await supabase.auth.registerPasskey();
    if (passkeyError) setError(passkeyError.message);
    else {
      setMessage(tx(`Passkey registrada${data?.friendly_name ? `: ${data.friendly_name}` : ""}.`, `Passkey registered${data?.friendly_name ? `: ${data.friendly_name}` : ""}.`));
      await reload();
    }
    setBusy("");
  };

  return (
    <>
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">{tx("Seguridad", "Security")}</p>
          <h2>{tx("Formas de entrar", "Sign-in methods")}</h2>
          <span>{tx("Todas apuntan a la misma identidad DINCR; no crean otra cuenta cuando se vinculan desde aquí.", "They all point to the same DINCR identity; linking them here does not create another account.")}</span>
        </div>
      </div>

      <div className="security-method-list">
        <article className="security-method-row">
          <div><Link2 size={20} /><span><strong>Google</strong><small>{hasProvider("google") ? tx("Vinculado", "Linked") : tx("No vinculado", "Not linked")}</small></span></div>
          {hasProvider("google") && <CheckCircle2 size={18} />}
        </article>

        <article className="security-method-row">
          <div><Apple size={20} /><span><strong>Apple</strong><small>{hasProvider("apple") ? tx("Vinculado a esta misma cuenta", "Linked to this account") : tx("Podés agregar Iniciar sesión con Apple", "You can add Sign in with Apple")}</small></span></div>
          {hasProvider("apple") ? <CheckCircle2 size={18} /> : <button className="finva-button finva-button-secondary" type="button" onClick={linkApple} disabled={Boolean(busy)}>{busy === "apple" ? tx("Abriendo...", "Opening...") : tx("Vincular", "Link")}</button>}
        </article>

        <article className="security-method-row">
          <div><Fingerprint size={21} /><span><strong>Passkey / Face ID</strong><small>{passkeys.length ? tx(`${passkeys.length} registrada${passkeys.length === 1 ? "" : "s"}`, `${passkeys.length} registered`) : tx("Usá biometría/PIN del dispositivo", "Use device biometrics/PIN")}</small></span></div>
          <button className="finva-button finva-button-secondary" type="button" onClick={registerPasskey} disabled={Boolean(busy)}>{busy === "passkey" ? tx("Registrando...", "Registering...") : passkeys.length ? tx("Agregar otra", "Add another") : tx("Registrar", "Register")}</button>
        </article>
      </div>

      <button className="security-refresh finva-button finva-button-ghost" type="button" onClick={reload}><RefreshCw size={15} /> {tx("Actualizar métodos", "Refresh methods")}</button>
      {message && <p className="success-banner">{message}</p>}
      {error && <p className="onboarding-error">{error}</p>}
    </>
  );
}
