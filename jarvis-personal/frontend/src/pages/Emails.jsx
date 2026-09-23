import { useEffect, useState } from "react";
import { ArrowLeft, BrainCircuit, Check, MailSearch, RefreshCw, ShieldCheck, X } from "lucide-react";
import {
  classifyEmailCandidate,
  decideEmailCandidate,
  getEmailMonitorCandidates,
  getEmailMonitorStatus,
  syncEmailMonitorGmail,
} from "../services/jarvisApi";
import { JarvisGlassCard, JarvisScreen, JarvisStatusPill } from "../products/jarvis/components/JarvisScreen";

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
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [message, setMessage] = useState("");
  const [lastScan, setLastScan] = useState(null);
  const [classifying, setClassifying] = useState(null);
  const [classification, setClassification] = useState({ description: "", transaction_type: "expense", category: "Compras", remember_rule: true });

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

  const handleScan = async () => {
    setScanning(true);
    setMessage("Escaneando Gmail. Las reglas personales conocidas se procesan automáticamente; lo desconocido queda pendiente...");
    try {
      const result = await syncEmailMonitorGmail({
        max_results: 250,
        auto_commit: true,
        current_month_only: true,
      });
      setLastScan(result);
      const summary = result?.summary || {};
      setMessage(
        result?.message ||
          `Encontrados: ${result?.found || 0} · Pendientes: ${summary.pending || 0} · Duplicados: ${summary.duplicates || 0}`
      );
      setFilter("pending");
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
      await load(filter);
      if (decision === "confirm") await onFinanceChanged?.();
    } catch (error) {
      setMessage(error.message || "No pude aplicar la decisión.");
    }
  };

  const openClassification = (item) => {
    setClassifying(item.id);
    setClassification({
      description: item.description || "",
      transaction_type: item.transaction_type === "income" ? "income" : item.transaction_type === "debt_payment" ? "debt_payment" : "expense",
      category: item.category || "Compras",
      remember_rule: true,
    });
  };

  const handleClassification = async (item) => {
    setMessage("DINCR está guardando y aprendiendo esta clasificación...");
    try {
      const result = await classifyEmailCandidate({ candidate_id: item.id, ...classification, auto_commit_future: classification.remember_rule });
      setMessage(result?.message || "Movimiento clasificado.");
      setClassifying(null);
      await load(filter);
      await onFinanceChanged?.();
    } catch (error) {
      setMessage(error.message || "No pude guardar la clasificación.");
    }
  };

  const handleFilter = async (nextFilter) => {
    setFilter(nextFilter);
    await load(nextFilter);
  };

  const selectedCandidate = candidates.find((item) => item.id === classifying);

  if (selectedCandidate) {
    return (
      <JarvisScreen
        eyebrow="Email Monitor"
        title="Revisar movimiento"
        subtitle="Confirmá antes de enviarlo a Finanzas"
        className="email-review-screen"
        actions={<button type="button" className="jarvis-circle-button" onClick={() => setClassifying(null)} aria-label="Volver"><ArrowLeft size={20} /></button>}
      >
        <JarvisGlassCard className="email-review-source">
          <span>{selectedCandidate.bank_name || selectedCandidate.sender || "Correo bancario"}{selectedCandidate.card_last4 ? ` · **** ${selectedCandidate.card_last4}` : ""}</span>
          <strong>{selectedCandidate.email_subject || selectedCandidate.description || "Movimiento detectado"}</strong>
          <small>{dateText(selectedCandidate.transaction_date)}</small>
        </JarvisGlassCard>

        <JarvisGlassCard className="email-review-amount">
          <span>Monto detectado</span>
          <strong>{money(selectedCandidate.amount)}</strong>
          <JarvisStatusPill tone="success">Movimiento detectado</JarvisStatusPill>
        </JarvisGlassCard>

        <div className="email-review-fields">
          <label className="email-review-field">
            <span>Descripción</span>
            <input value={classification.description} onChange={(event) => setClassification((current) => ({ ...current, description: event.target.value }))} />
          </label>
          <label className="email-review-field">
            <span>Tipo</span>
            <select value={classification.transaction_type} onChange={(event) => setClassification((current) => ({ ...current, transaction_type: event.target.value }))}>
              <option value="expense">Gasto</option>
              <option value="income">Ingreso</option>
              <option value="debt_payment">Pago de deuda</option>
            </select>
          </label>
          <label className="email-review-field">
            <span>Categoría</span>
            <input value={classification.category} onChange={(event) => setClassification((current) => ({ ...current, category: event.target.value }))} />
          </label>
          <div className="email-review-field is-readonly">
            <span>Cuenta</span>
            <strong>{selectedCandidate.account || selectedCandidate.bank_name || "Sin asociar"}{selectedCandidate.card_last4 ? ` · ${selectedCandidate.card_last4}` : ""}</strong>
          </div>
        </div>

        <label className="email-review-remember">
          <input type="checkbox" checked={classification.remember_rule} onChange={(event) => setClassification((current) => ({ ...current, remember_rule: event.target.checked }))} />
          <span>Recordar esta clasificación para movimientos futuros.</span>
        </label>

        {message && <div className="jarvis-inline-message">{message}</div>}
        <div className="email-review-actions">
          <button type="button" className="jarvis-primary-button" onClick={() => handleClassification(selectedCandidate)}><Check size={17} /> Aprobar y guardar</button>
          <button type="button" className="jarvis-danger-button" onClick={() => handleSingleDecision(selectedCandidate, "reject")}><X size={17} /> Rechazar</button>
        </div>
      </JarvisScreen>
    );
  }

  return (
    <JarvisScreen eyebrow="Email Monitor" title="Correos financieros" subtitle="Gmail → revisión → Finanzas" className="emails-page email-monitor-screen">
      <JarvisGlassCard className="email-sync-card">
        <div>
          <JarvisStatusPill tone={monitor?.gmail_ready ? "success" : "warning"}>{monitor?.gmail_ready ? "● Gmail conectado" : "Gmail sin configurar"}</JarvisStatusPill>
          <strong>Último escaneo</strong>
          <small>{lastScan ? "Actualizado ahora" : "Listo para consultar"}</small>
        </div>
        <button className="jarvis-primary-button" type="button" onClick={handleScan} disabled={scanning || !monitor?.gmail_ready}>
          {scanning ? <RefreshCw size={17} /> : <MailSearch size={17} />}
          {scanning ? "Escaneando…" : "Escanear"}
        </button>
      </JarvisGlassCard>

      {!monitor?.gmail_ready && (
        <div className="jarvis-inline-message is-warning">Email Monitor necesita la configuración de Gmail para sincronizar.</div>
      )}

      {message && <div className="jarvis-inline-message">{message}</div>}

      <div className="email-monitor-kpis">
        <JarvisGlassCard className="is-warning"><strong>{Number(totals?.pending || 0).toLocaleString("es-CR")}</strong><span>Pendientes</span></JarvisGlassCard>
        <JarvisGlassCard className="is-success"><strong>{Number((totals?.confirmed || 0) + (totals?.auto_saved || 0)).toLocaleString("es-CR")}</strong><span>En finanzas</span></JarvisGlassCard>
        <JarvisGlassCard><strong>{Number(totals?.duplicate || 0).toLocaleString("es-CR")}</strong><span>Duplicados</span></JarvisGlassCard>
      </div>

      {lastScan?.processed?.length > 0 && (
        <JarvisGlassCard className="email-scan-panel">
          <h3><ShieldCheck size={18} /> Último escaneo</h3>
          <p>Gmail encontró {lastScan.found} correos. Los repetidos se omitieron por ID/fingerprint y no se crean movimientos duplicados.</p>
        </JarvisGlassCard>
      )}

      <div className="email-toolbar">
        <div className="email-filter-tabs">
          {["pending", "confirmed", "duplicate", "rejected"].map((item) => (
            <button key={item} className={filter === item ? "active" : ""} type="button" onClick={() => handleFilter(item)}>
              {statusLabel[item] || item}
            </button>
          ))}
        </div>
      </div>

      <div className="jarvis-section-heading"><h3>{filter === "pending" ? "Revisión pendiente" : statusLabel[filter]}</h3><span><BrainCircuit size={15} /> {candidates.length}</span></div>

      {loading ? (
        <JarvisGlassCard className="jarvis-empty-state">Cargando correos…</JarvisGlassCard>
      ) : candidates.length === 0 ? (
        <JarvisGlassCard className="jarvis-empty-state">No hay movimientos para este filtro.</JarvisGlassCard>
      ) : (
        <div className="email-candidate-list">
          {candidates.map((item) => {
            const isPending = item.status === "pending" && !item.transaction_id;
            return (
              <button type="button" className={`email-candidate-card ${item.status}`} key={item.id} onClick={() => isPending && openClassification(item)}>
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
                  {item.transaction_id ? (
                    <small>Movimiento #{item.transaction_id}</small>
                  ) : item.status === "duplicate" ? (
                    <small>Canónico #{item.canonical_transaction_id || item.duplicate_of}</small>
                  ) : null}
                </div>

              </button>
            );
          })}
        </div>
      )}
    </JarvisScreen>
  );
}
