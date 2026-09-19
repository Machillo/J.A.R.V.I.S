import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Bug, Lightbulb, LifeBuoy, Send } from "lucide-react";
import { SUPPORT_CONTEXT_KEY } from "../../lib/apiErrors";
import { createFeedback, getFeedback } from "../services/jarvisApi";
import { tx } from "../../lib/locale";

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
      ? [tx(`Pantalla o sección: ${form.screen}`, `Screen or section: ${form.screen}`), tx(`Qué ocurrió: ${form.happened}`, `What happened: ${form.happened}`), tx(`Qué esperaba: ${form.expected || "No indicado"}`, `Expected: ${form.expected || "Not provided"}`), tx(`¿Se puede repetir?: ${form.reproducible || "No indicado"}`, `Reproducible?: ${form.reproducible || "Not provided"}`)]
      : [tx(`Mejora propuesta: ${form.happened}`, `Suggested improvement: ${form.happened}`), tx(`Cómo ayudaría: ${form.benefit}`, `How it would help: ${form.benefit}`), tx(`Pantalla o sección: ${form.screen || "General"}`, `Screen or section: ${form.screen || "General"}`)];
    try {
      const saved = await createFeedback({ category: form.category, subject: form.subject, message: lines.join("\n"), app_version: import.meta.env.VITE_APP_VERSION || "1.8.5", screen: form.screen || undefined, error_reference: form.errorReference || undefined });
      setNotice(saved.email_sent
        ? tx(`Listo. Enviamos ${saved.public_id} al correo de soporte.`, `Done. We emailed ${saved.public_id} to support.`)
        : tx(`Guardamos ${saved.public_id}, pero el correo no pudo enviarse. Soporte puede revisarlo desde el panel.`, `We saved ${saved.public_id}, but the email could not be sent. Support can review it from the dashboard.`));
      setForm(EMPTY);
      load();
    } catch (cause) {
      setError(cause.message || tx("No pudimos enviar el reporte. Intentá nuevamente.", "We couldn’t send the report. Please try again."));
    } finally { setBusy(false); }
  };

  return <section className="mobile-page feedback-page">
    <div className="mobile-page-heading"><p className="eyebrow">{tx("Soporte FINVA","FINVA support")}</p><h1>{tx("¿Cómo te ayudamos?","How can we help?")}</h1><span>{tx("Te hacemos unas preguntas cortas para entender y resolverlo mejor.","We’ll ask a few short questions so we can understand and resolve it better.")}</span></div>
    {!form.category ? <div className="support-choice-grid">
      <button type="button" className="mobile-panel support-choice" onClick={() => setForm({ ...form, category: "error" })}><Bug size={28}/><strong>{tx("Tengo un problema","I have a problem")}</strong><span>{tx("Algo falló, no carga o no funciona como esperaba.","Something failed, won’t load, or doesn’t work as expected.")}</span></button>
      <button type="button" className="mobile-panel support-choice" onClick={() => setForm({ ...form, category: "improvement" })}><Lightbulb size={28}/><strong>{tx("Quiero proponer una mejora","I want to suggest an improvement")}</strong><span>{tx("Hay algo que podría ser más claro, fácil o útil.","Something could be clearer, easier, or more useful.")}</span></button>
    </div> : <form className="mobile-panel feedback-form support-chat" onSubmit={submit}>
      <button type="button" className="support-back" onClick={() => setForm(EMPTY)}><ArrowLeft size={17}/> {tx("Cambiar tipo","Change type")}</button>
      <div className="support-chat-title"><LifeBuoy size={24}/><strong>{form.category === "error" ? tx("Contanos qué pasó","Tell us what happened") : tx("Contanos tu idea","Tell us your idea")}</strong></div>
      <label>{tx("¿Cómo resumirías", "How would you summarize")} {form.category === "error" ? tx("el problema","the problem") : tx("la mejora","the improvement")}?<input required minLength="3" maxLength="140" value={form.subject} onChange={change("subject")} placeholder={tx("Ejemplo: No puedo guardar una meta","Example: I can’t save a goal")}/></label>
      {form.category === "error" ? <>
        <label>{tx("¿En cuál pantalla o sección ocurrió?","Which screen or section was it on?")}<input required value={form.screen} onChange={change("screen")} placeholder={tx("Ejemplo: Metas","Example: Goals")}/></label>
        <label>{tx("¿Qué ocurrió?","What happened?")}<textarea required minLength="5" rows="4" value={form.happened} onChange={change("happened")} placeholder={tx("Contanos qué hiciste y qué viste.","Tell us what you did and what you saw.")}/></label>
        <label>{tx("¿Qué esperabas que pasara?","What did you expect to happen?")}<textarea rows="3" value={form.expected} onChange={change("expected")}/></label>
        <label>{tx("¿Pasa siempre o solo algunas veces?","Does it happen every time or only sometimes?")}<select value={form.reproducible} onChange={change("reproducible")}><option value="">{tx("Elegí una opción","Choose an option")}</option><option>{tx("Siempre","Always")}</option><option>{tx("Algunas veces","Sometimes")}</option><option>{tx("Solo ocurrió una vez","It only happened once")}</option></select></label>
      </> : <>
        <label>{tx("¿Qué te gustaría mejorar?","What would you like to improve?")}<textarea required minLength="5" rows="4" value={form.happened} onChange={change("happened")}/></label>
        <label>{tx("¿Cómo te ayudaría ese cambio?","How would that change help you?")}<textarea required minLength="3" rows="3" value={form.benefit} onChange={change("benefit")}/></label>
        <label>{tx("¿En cuál pantalla lo pondrías? (opcional)","Which screen would you put it on? (optional)")}<input value={form.screen} onChange={change("screen")}/></label>
      </>}
      <p className="support-privacy">{tx("No incluyás contraseñas, códigos ni números completos de cuentas o tarjetas.","Do not include passwords, codes, or full account or card numbers.")}</p>
      <button className="primary-button finva-button finva-button-primary" disabled={busy || !ready}><Send size={17}/> {busy ? tx("Enviando...","Sending...") : tx("Enviar a soporte","Send to support")}</button>
      {notice && <p className="success-banner">{notice}</p>}{error && <p className="onboarding-error">{error}</p>}
    </form>}
    {reports.length > 0 && <div className="mobile-panel"><h2>{tx("Mis reportes","My reports")}</h2>{reports.map((report)=><div className="feedback-row" key={report.id}><strong>{report.public_id} · {report.subject}</strong><span>{report.status}</span></div>)}</div>}
  </section>;
}
