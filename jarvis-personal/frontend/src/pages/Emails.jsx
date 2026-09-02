import { useEffect, useState } from "react";
import { BrainCircuit, MailSearch, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import {
  classifyEmailCandidate,
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
    setMessage("JARVIS está guardando y aprendiendo esta clasificación...");
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

  return (
    <section className="page emails-page">
      <div className="page-section-header">
        <div>
          <span className="eyebrow">Gmail → Finanzas</span>
          <h2>Correos financieros</h2>
          <p>JARVIS procesa las reglas que ya conoce. Si aparece un SINPE nuevo, te pregunta qué es antes de guardarlo.</p>
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
          <span className="email-learning-note"><BrainCircuit size={17} /> Los pendientes necesitan clasificación.</span>
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
                      <button type="button" onClick={() => openClassification(item)}><BrainCircuit size={14} /> Clasificar</button>
                      <button type="button" className="danger" onClick={() => handleSingleDecision(item, "reject")}><Trash2 size={14} /> Rechazar</button>
                    </div>
                  ) : item.transaction_id ? (
                    <small>Movimiento #{item.transaction_id}</small>
                  ) : item.status === "duplicate" ? (
                    <small>Canónico #{item.canonical_transaction_id || item.duplicate_of}</small>
                  ) : null}
                </div>

                {isPending && classifying === item.id && (
                  <div className="email-classification-panel">
                    <strong>JARVIS pregunta: ¿qué fue este movimiento?</strong>
                    <label>
                      Nombre claro
                      <input value={classification.description} onChange={(event) => setClassification((current) => ({ ...current, description: event.target.value }))} />
                    </label>
                    <label>
                      Tipo
                      <select value={classification.transaction_type} onChange={(event) => setClassification((current) => ({ ...current, transaction_type: event.target.value }))}>
                        <option value="expense">Gasto</option>
                        <option value="income">Ingreso</option>
                        <option value="debt_payment">Pago de deuda</option>
                      </select>
                    </label>
                    <label>
                      Categoría
                      <input value={classification.category} onChange={(event) => setClassification((current) => ({ ...current, category: event.target.value }))} />
                    </label>
                    <label className="email-remember-rule">
                      <input type="checkbox" checked={classification.remember_rule} onChange={(event) => setClassification((current) => ({ ...current, remember_rule: event.target.checked }))} />
                      Recordar esta combinación de cuentas, dirección y concepto para hacerla automática la próxima vez.
                    </label>
                    <div className="email-classification-actions">
                      <button type="button" onClick={() => handleClassification(item)}>Guardar y aprender</button>
                      <button type="button" className="secondary" onClick={() => setClassifying(null)}>Cancelar</button>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
