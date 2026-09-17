import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Bug, Lightbulb, LifeBuoy, Send } from "lucide-react";
import { SUPPORT_CONTEXT_KEY } from "../../lib/apiErrors";
import { createFeedback, getFeedback } from "../services/jarvisApi";

const EMPTY = { category: "", subject: "", screen: "", happened: "", expected: "", benefit: "", reproducible: "" };

export default function Feedback() {
  const [reports, setReports] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const load = () => getFeedback().then(setReports).catch(() => setReports([]));

  useEffect(() => {
    load();
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(SUPPORT_CONTEXT_KEY) || "null");
      if (saved) {
        setForm((current) => ({ ...current, category: saved.kind === "improvement" ? "improvement" : "error", screen: saved.screen || "", happened: saved.summary || "", errorReference: saved.errorReference || "" }));
        window.sessionStorage.removeItem(SUPPORT_CONTEXT_KEY);
      }
    } catch { /* Ignore an invalid local draft. */ }
  }, []);

  const ready = useMemo(() => {
    if (!form.category || form.subject.trim().length < 3) return false;
    if (form.category === "error") return form.screen.trim() && form.happened.trim().length >= 5;
    return form.happened.trim().length >= 5 && form.benefit.trim().length >= 3;
  }, [form]);
  const change = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    if (!ready) return;
    setBusy(true); setError(""); setNotice("");
    const lines = form.category === "error"
      ? [`Pantalla o sección: ${form.screen}`, `Qué ocurrió: ${form.happened}`, `Qué esperaba: ${form.expected || "No indicado"}`, `¿Se puede repetir?: ${form.reproducible || "No indicado"}`]
      : [`Mejora propuesta: ${form.happened}`, `Cómo ayudaría: ${form.benefit}`, `Pantalla o sección: ${form.screen || "General"}`];
    try {
      const saved = await createFeedback({ category: form.category, subject: form.subject, message: lines.join("\n"), app_version: import.meta.env.VITE_APP_VERSION || "1.8.5", screen: form.screen || undefined, error_reference: form.errorReference || undefined });
      setNotice(`Listo. Tu reporte es ${saved.public_id}. Soporte ya puede revisarlo.`);
      setForm(EMPTY);
      load();
    } catch (cause) {
      setError(cause.message || "No pudimos enviar el reporte. Intentá nuevamente.");
    } finally { setBusy(false); }
  };

  return <section className="mobile-page feedback-page">
    <div className="mobile-page-heading"><p className="eyebrow">Soporte FINVA</p><h1>¿Cómo te ayudamos?</h1><span>Te hacemos unas preguntas cortas para entender y resolverlo mejor.</span></div>
    {!form.category ? <div className="support-choice-grid">
      <button type="button" className="mobile-panel support-choice" onClick={() => setForm({ ...form, category: "error" })}><Bug size={28}/><strong>Tengo un problema</strong><span>Algo falló, no carga o no funciona como esperaba.</span></button>
      <button type="button" className="mobile-panel support-choice" onClick={() => setForm({ ...form, category: "improvement" })}><Lightbulb size={28}/><strong>Quiero proponer una mejora</strong><span>Hay algo que podría ser más claro, fácil o útil.</span></button>
    </div> : <form className="mobile-panel feedback-form support-chat" onSubmit={submit}>
      <button type="button" className="support-back" onClick={() => setForm(EMPTY)}><ArrowLeft size={17}/> Cambiar tipo</button>
      <div className="support-chat-title"><LifeBuoy size={24}/><strong>{form.category === "error" ? "Contanos qué pasó" : "Contanos tu idea"}</strong></div>
      <label>¿Cómo resumirías {form.category === "error" ? "el problema" : "la mejora"}?<input required minLength="3" maxLength="140" value={form.subject} onChange={change("subject")} placeholder="Ejemplo: No puedo guardar una meta"/></label>
      {form.category === "error" ? <>
        <label>¿En cuál pantalla o sección ocurrió?<input required value={form.screen} onChange={change("screen")} placeholder="Ejemplo: Metas"/></label>
        <label>¿Qué ocurrió?<textarea required minLength="5" rows="4" value={form.happened} onChange={change("happened")} placeholder="Contanos qué hiciste y qué viste."/></label>
        <label>¿Qué esperabas que pasara?<textarea rows="3" value={form.expected} onChange={change("expected")}/></label>
        <label>¿Pasa siempre o solo algunas veces?<select value={form.reproducible} onChange={change("reproducible")}><option value="">Elegí una opción</option><option>Siempre</option><option>Algunas veces</option><option>Solo ocurrió una vez</option></select></label>
      </> : <>
        <label>¿Qué te gustaría mejorar?<textarea required minLength="5" rows="4" value={form.happened} onChange={change("happened")}/></label>
        <label>¿Cómo te ayudaría ese cambio?<textarea required minLength="3" rows="3" value={form.benefit} onChange={change("benefit")}/></label>
        <label>¿En cuál pantalla lo pondrías? (opcional)<input value={form.screen} onChange={change("screen")}/></label>
      </>}
      <p className="support-privacy">No incluyás contraseñas, códigos ni números completos de cuentas o tarjetas.</p>
      <button className="primary-button finva-button finva-button-primary" disabled={busy || !ready}><Send size={17}/> {busy ? "Enviando..." : "Enviar a soporte"}</button>
      {notice && <p className="success-banner">{notice}</p>}{error && <p className="onboarding-error">{error}</p>}
    </form>}
    {reports.length > 0 && <div className="mobile-panel"><h2>Mis reportes</h2>{reports.map((report)=><div className="feedback-row" key={report.id}><strong>{report.public_id} · {report.subject}</strong><span>{report.status}</span></div>)}</div>}
  </section>;
}
