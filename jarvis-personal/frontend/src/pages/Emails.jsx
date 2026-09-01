import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, MailSearch, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import {
  bulkDecideEmailCandidates,
  decideEmailCandidate,
  getEmailMonitorCandidates,
  getEmailMonitorStatus,
  syncEmailMonitorGmail,
} from "../services/jarvisApi";

const money = (value) => `₡${Math.round(Number(value || 0)).toLocaleString("es-CR")}`;
const dateText = (value) => (value ? new Date(value).toLocaleDateString("es-CR") : "—");

const statusLabel = {
  pending: "Pendiente",
  duplicate: "Duplicado",
  confirmed: "En finanzas",
  auto_saved: "En finanzas",
  rejected: "Rechazado",
};

const typeLabel = {
  expense: "Gasto",
  income: "Ingreso",
  debt_payment: "Pago deuda",
  transfer: "Transferencia",
  internal_transfer: "Movimiento interno",
};

const directionText = (item) => {
  const notes = String(item.notes || "");
  const origin = notes.match(/origen:\s*([^|]+)/i)?.[1]?.trim();
  const destination = notes.match(/destino:\s*([^|]+)/i)?.[1]?.trim();
  if (origin && destination) return `De ${origin} → ${destination}`;
  if (origin) return `Origen: ${origin}`;
  if (destination) return `Destino: ${destination}`;
  return "";
};

export default function Emails({ onFinanceChanged }) {
  const [monitor, setMonitor] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [totals, setTotals] = useState({});
  const [filter, setFilter] = useState("pending");
  const [selected, setSelected] = useState({});
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [message, setMessage] = useState("");
  const [lastScan, setLastScan] = useState(null);

  const load = async (nextFilter = filter) => {
    setLoading(true);
    try {
      const [statusData, candidateData] = await Promise.all([
        getEmailMonitorStatus(),
        getEmailMonitorCandidates(nextFilter, 250),
      ]);
      setMonitor(statusData);
      setCandidates(candidateData?.items || []);
      setTotals(candidateData?.totals || statusData?.totals || {});
    } catch (error) {
      setMessage(error.message || "No pude cargar correos.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(filter);
  }, []);

  const pendingItems = useMemo(
    () => candidates.filter((item) => item.status === "pending" && !item.transaction_id),
    [candidates]
  );

  const selectedIds = useMemo(
    () => Object.entries(selected)
      .filter(([, value]) => value)
      .map(([key]) => Number(key)),
    [selected]
  );

  const toggleAllPending = () => {
    const allSelected = pendingItems.length > 0 && pendingItems.every((item) => selected[item.id]);
    if (allSelected) {
      setSelected({});
      return;
    }
    const next = {};
    pendingItems.forEach((item) => {
      next[item.id] = true;
    });
    setSelected(next);
  };

  const handleScan = async () => {
    setScanning(true);
    setMessage("Escaneando Gmail. Se ignoran correos ya ingresados y no se autoguarda nada en finanzas...");
    try {
      const result = await syncEmailMonitorGmail({
        max_results: 250,
        auto_commit: false,
        current_month_only: true,
      });
      setLastScan(result);
      const summary = result?.summary || {};
      setMessage(
        result?.message ||
          `Encontrados: ${result?.found || 0} · Pendientes: ${summary.pending || 0} · Duplicados: ${summary.duplicates || 0}`
      );
      setFilter("pending");
      setSelected({});
      await load("pending");
    } catch (error) {
      setMessage(error.message || "Falló el escaneo de Gmail.");
    } finally {
      setScanning(false);
    }
  };

  const handleSingleDecision = async (item, decision) => {
    setMessage(decision === "confirm" ? "Agregando movimiento a finanzas..." : "Rechazando movimiento...");
    try {
      const result = await decideEmailCandidate({ candidate_id: item.id, decision });
      setMessage(result?.message || "Listo.");
      setSelected((current) => ({ ...current, [item.id]: false }));
      await load(filter);
      if (decision === "confirm") await onFinanceChanged?.();
    } catch (error) {
      setMessage(error.message || "No pude aplicar la decisión.");
    }
  };

  const handleBulkConfirm = async () => {
    const ids = selectedIds.length > 0 ? selectedIds : pendingItems.map((item) => item.id);
    if (ids.length === 0) {
      setMessage("No hay movimientos pendientes para agregar.");
      return;
    }
    setMessage(`Agregando ${ids.length} movimiento(s) a finanzas...`);
    try {
      const result = await bulkDecideEmailCandidates({ candidate_ids: ids, decision: "confirm" });
      setMessage(result?.message || "Movimientos agregados.");
      setSelected({});
      await load(filter);
      await onFinanceChanged?.();
    } catch (error) {
      setMessage(error.message || "No pude guardar los movimientos.");
    }
  };

  const handleFilter = async (nextFilter) => {
    setFilter(nextFilter);
    setSelected({});
    await load(nextFilter);
  };

  return (
    <section className="page emails-page">
      <div className="page-section-header">
        <div>
          <span className="eyebrow">Gmail → Finanzas</span>
          <h2>Correos financieros</h2>
          <p>Primero escaneás, revisás los movimientos y después los agregás a finanzas. Nada se guarda solo.</p>
        </div>
        <button className="primary-action-button" type="button" onClick={handleScan} disabled={scanning || !monitor?.gmail_ready}>
          {scanning ? <RefreshCw size={18} /> : <MailSearch size={18} />}
          {scanning ? "Escaneando..." : "Escanear nuevos correos"}
        </button>
      </div>

      {!monitor?.gmail_ready && (
        <div className="alert-card">Faltan llaves Gmail: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET y GMAIL_REFRESH_TOKEN.</div>
      )}

      {message && <div className="alert-card">{message}</div>}

      <div className="email-kpi-grid">
        <article className="hud-card"><span>Pendientes</span><strong>{Number(totals?.pending || 0).toLocaleString("es-CR")}</strong></article>
        <article className="hud-card"><span>En finanzas</span><strong>{Number((totals?.confirmed || 0) + (totals?.auto_saved || 0)).toLocaleString("es-CR")}</strong></article>
        <article className="hud-card"><span>Duplicados</span><strong>{Number(totals?.duplicate || 0).toLocaleString("es-CR")}</strong></article>
        <article className="hud-card"><span>Mostrando</span><strong>{candidates.length.toLocaleString("es-CR")}</strong></article>
      </div>

      {lastScan?.processed?.length > 0 && (
        <div className="hud-panel email-scan-panel">
          <h3><ShieldCheck size={18} /> Último escaneo</h3>
          <p>Gmail encontró {lastScan.found} correos. Los repetidos se omitieron por ID/fingerprint y no se crean movimientos duplicados.</p>
          <div className="email-scan-list">
            {lastScan.processed.slice(0, 250).map((item) => (
              <div key={item.gmail_id}>
                <span>{item.subject || "Sin asunto"}</span>
                <small>
                  {item.status} {item.candidate_status ? `· ${item.candidate_status}` : ""}
                  {item.message ? ` · ${item.message}` : ""}
                </small>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="email-toolbar">
        <div className="email-filter-tabs">
          {["pending", "confirmed", "duplicate", "rejected"].map((item) => (
            <button key={item} className={filter === item ? "active" : ""} type="button" onClick={() => handleFilter(item)}>
              {statusLabel[item] || item}
            </button>
          ))}
        </div>
        <div className="email-toolbar-actions">
          <button className="jarvis-action-button secondary" type="button" onClick={toggleAllPending} disabled={pendingItems.length === 0}>
            {selectedIds.length ? "Quitar selección" : "Seleccionar pendientes"}
          </button>
          <button className="jarvis-action-button" type="button" onClick={handleBulkConfirm} disabled={pendingItems.length === 0}>
            <CheckCircle2 size={18} /> Agregar a finanzas
          </button>
        </div>
      </div>

      {loading ? (
        <div className="hud-card">Cargando correos...</div>
      ) : candidates.length === 0 ? (
        <div className="hud-card">No hay movimientos para este filtro.</div>
      ) : (
        <div className="email-candidate-list">
          {candidates.map((item) => {
            const isPending = item.status === "pending" && !item.transaction_id;
            return (
              <article className={`email-candidate-card ${item.status}`} key={item.id}>
                <label className="email-select-box">
                  <input
                    type="checkbox"
                    checked={Boolean(selected[item.id])}
                    disabled={!isPending}
                    onChange={(event) => setSelected((current) => ({ ...current, [item.id]: event.target.checked }))}
                  />
                </label>

                <div className="email-candidate-main">
                  <div className="email-candidate-title">
                    <strong>{item.description}</strong>
                    <span className={`email-status-pill ${item.status}`}>{statusLabel[item.status] || item.status}</span>
                  </div>
                  <p>{item.email_subject || item.review_reason || "Movimiento detectado por correo"}</p>
                  {directionText(item) && <p className="email-candidate-detail">{directionText(item)}</p>}
                  <small>
                    {dateText(item.transaction_date)} · {item.category} · {typeLabel[item.transaction_type] || item.transaction_type}
                    {item.card_owner ? ` · ${item.card_owner}` : ""}
                    {item.card_last4 ? ` · ****${item.card_last4}` : ""}
                  </small>
                </div>

                <div className="email-candidate-side">
                  <strong>{money(item.amount)}</strong>
                  {isPending ? (
                    <div className="email-candidate-actions">
                      <button type="button" onClick={() => handleSingleDecision(item, "confirm")}>Aceptar</button>
                      <button type="button" className="danger" onClick={() => handleSingleDecision(item, "reject")}><Trash2 size={14} /> Rechazar</button>
                    </div>
                  ) : item.transaction_id ? (
                    <small>Movimiento #{item.transaction_id}</small>
                  ) : item.status === "duplicate" ? (
                    <small>Canónico #{item.canonical_transaction_id || item.duplicate_of}</small>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
