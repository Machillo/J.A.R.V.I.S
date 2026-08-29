import { useState } from "react";
import { Gift, Search, ShieldCheck, UserRoundCheck, XCircle } from "lucide-react";
import { getManagedUsers, grantCourtesySubscription, revokeCourtesySubscription } from "../services/jarvisApi";

const fmtDate = (value) => {
  if (!value) return "Sin vencimiento";
  try {
    return new Intl.DateTimeFormat("es-CR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  } catch {
    return value;
  }
};

export default function UserManagement() {
  const [search, setSearch] = useState("");
  const [users, setUsers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [plan, setPlan] = useState("vip");
  const [days, setDays] = useState(30);
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const runSearch = async (event) => {
    event?.preventDefault();
    const q = search.trim();
    if (!q) {
      setUsers([]);
      setSelected(null);
      setMessage("Escribí un correo o nombre.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const result = await getManagedUsers(q);
      setUsers(Array.isArray(result) ? result : []);
      if (Array.isArray(result) && result.length === 1) setSelected(result[0]);
      if (!result?.length) setMessage("No encontré usuarios con ese correo.");
    } catch (error) {
      setMessage(error.message || "No pude consultar JARVIS Users.");
    } finally {
      setLoading(false);
    }
  };

  const grant = async () => {
    if (!selected) return;
    setLoading(true);
    setMessage("");
    try {
      const updated = await grantCourtesySubscription(selected.id, {
        plan,
        days: Number(days),
        note: note.trim() || null,
      });
      setSelected(updated);
      setUsers((current) => current.map((u) => u.id === updated.id ? updated : u));
      setMessage(`Cortesía ${plan.toUpperCase()} activada por ${days} días.`);
    } catch (error) {
      setMessage(error.message || "No pude asignar la cortesía.");
    } finally {
      setLoading(false);
    }
  };

  const revoke = async () => {
    if (!selected) return;
    if (!window.confirm(`¿Quitar la cortesía de ${selected.email}? Volverá al plan Free.`)) return;
    setLoading(true);
    setMessage("");
    try {
      const updated = await revokeCourtesySubscription(selected.id);
      setSelected(updated);
      setUsers((current) => current.map((u) => u.id === updated.id ? updated : u));
      setMessage("Cortesía retirada. El usuario volvió a Free.");
    } catch (error) {
      setMessage(error.message || "No pude retirar la cortesía.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="user-admin-page">
      <div className="app-section-card user-admin-intro">
        <div className="user-admin-title">
          <ShieldCheck size={24} />
          <div>
            <strong>Control de cuentas</strong>
            <small>Solo owner. Buscá por correo y administrá cortesías temporales.</small>
          </div>
        </div>

        <form className="user-admin-search" onSubmit={runSearch}>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="correo@ejemplo.com"
            autoComplete="off"
          />
          <button type="submit" disabled={loading}>
            <Search size={18} /> Buscar
          </button>
        </form>
      </div>

      {!!users.length && (
        <div className="app-section-card user-admin-results">
          {users.map((user) => (
            <button
              type="button"
              key={user.id}
              className={`user-admin-result ${selected?.id === user.id ? "active" : ""}`}
              onClick={() => setSelected(user)}
            >
              <UserRoundCheck size={20} />
              <span>
                <strong>{user.email}</strong>
                <small>{user.display_name || "Sin nombre"} · {(user.plan || "sin plan").toUpperCase()}</small>
              </span>
            </button>
          ))}
        </div>
      )}

      {selected && (
        <div className="app-section-card user-admin-editor">
          <div className="user-admin-account">
            <div>
              <span>Cuenta seleccionada</span>
              <strong>{selected.email}</strong>
            </div>
            <span className={`user-admin-badge ${selected.subscription_status || "none"}`}>
              {(selected.plan || "sin plan").toUpperCase()}
            </span>
          </div>

          <div className="user-admin-meta">
            <span>Origen: <strong>{selected.access_source === "courtesy" ? "Cortesía" : "Normal"}</strong></span>
            <span>Vence: <strong>{fmtDate(selected.expires_at)}</strong></span>
          </div>

          <div className="user-admin-fields">
            <label>
              Plan de cortesía
              <select value={plan} onChange={(event) => setPlan(event.target.value)}>
                <option value="basic">Basic</option>
                <option value="vip">VIP</option>
              </select>
            </label>
            <label>
              Duración
              <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
                <option value={7}>7 días</option>
                <option value={14}>14 días</option>
                <option value={30}>30 días</option>
                <option value={60}>60 días</option>
                <option value={90}>90 días</option>
                <option value={180}>180 días</option>
                <option value={365}>1 año</option>
              </select>
            </label>
            <label className="wide">
              Nota interna opcional
              <input value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} placeholder="Ej: familiar, beta tester, promoción..." />
            </label>
          </div>

          <div className="user-admin-actions">
            <button className="user-admin-primary" type="button" onClick={grant} disabled={loading}>
              <Gift size={18} /> Dar cortesía
            </button>
            {selected.access_source === "courtesy" && (
              <button className="user-admin-danger" type="button" onClick={revoke} disabled={loading}>
                <XCircle size={18} /> Quitar cortesía
              </button>
            )}
          </div>
        </div>
      )}

      {message && <p className="user-admin-message">{message}</p>}
    </section>
  );
}
