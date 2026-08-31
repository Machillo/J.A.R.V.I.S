import { Apple, CheckCircle2, Fingerprint, Link2, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { supabase } from "../../lib/supabase";

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
    if (!supabase.auth.registerPasskey) { setError("Passkeys todavía no están disponibles en este cliente."); setBusy(""); return; }
    const { data, error: passkeyError } = await supabase.auth.registerPasskey();
    if (passkeyError) setError(passkeyError.message);
    else {
      setMessage(`Passkey registrada${data?.friendly_name ? `: ${data.friendly_name}` : ""}.`);
      await reload();
    }
    setBusy("");
  };

  return (
    <>
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">Seguridad</p>
          <h2>Formas de entrar</h2>
          <span>Todas apuntan a la misma identidad JARVIS; no crean otra cuenta cuando se vinculan desde aquí.</span>
        </div>
      </div>

      <div className="security-method-list">
        <article className="security-method-row">
          <div><Link2 size={20} /><span><strong>Google</strong><small>{hasProvider("google") ? "Vinculado" : "No vinculado"}</small></span></div>
          {hasProvider("google") && <CheckCircle2 size={18} />}
        </article>

        <article className="security-method-row">
          <div><Apple size={20} /><span><strong>Apple</strong><small>{hasProvider("apple") ? "Vinculado a esta misma cuenta" : "Podés agregar Sign in with Apple"}</small></span></div>
          {hasProvider("apple") ? <CheckCircle2 size={18} /> : <button type="button" onClick={linkApple} disabled={Boolean(busy)}>{busy === "apple" ? "Abriendo..." : "Vincular"}</button>}
        </article>

        <article className="security-method-row">
          <div><Fingerprint size={21} /><span><strong>Passkey / Face ID</strong><small>{passkeys.length ? `${passkeys.length} registrada${passkeys.length === 1 ? "" : "s"}` : "Usá biometría/PIN del dispositivo"}</small></span></div>
          <button type="button" onClick={registerPasskey} disabled={Boolean(busy)}>{busy === "passkey" ? "Registrando..." : passkeys.length ? "Agregar otra" : "Registrar"}</button>
        </article>
      </div>

      {user?.role === "owner" && (
        <div className={`owner-bridge-card ${user?.personal_bridge?.linked ? "is-linked" : ""}`}>
          <div><strong>JARVIS Personal</strong><small>{user?.personal_bridge?.linked ? "Identidad privada conectada" : "Pendiente de vincular con tu identidad Personal"}</small></div>
          <span>{user?.personal_bridge?.linked ? "Conectado" : "Pendiente"}</span>
        </div>
      )}

      <button className="security-refresh" type="button" onClick={reload}><RefreshCw size={15} /> Actualizar métodos</button>
      {message && <p className="success-banner">{message}</p>}
      {error && <p className="onboarding-error">{error}</p>}
    </>
  );
}
