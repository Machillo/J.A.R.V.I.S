import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, AlertCircle, Bot, Bug, CheckCircle2, Lightbulb, MessageCircle, RefreshCw, RotateCcw, Send, UserRound, X } from "lucide-react";
import { SUPPORT_CONTEXT_KEY } from "../../lib/apiErrors";
import { createFeedback, getFeedback, getPlatformHealth, updateFeedbackResolution } from "../services/jarvisApi";
import { tx } from "../../lib/locale";

const EMPTY = { category: "", subject: "", screen: "", happened: "", expected: "", benefit: "", reproducible: "", errorReference: "" };
const ERROR_STEPS = ["subject", "screen", "happened", "expected", "reproducible", "review"];
const IDEA_STEPS = ["subject", "happened", "benefit", "screen", "review"];

const prompts = {
  subject: tx("Contame el problema en una frase corta.", "Describe the issue in one short sentence."),
  screen: tx("¿En cuál pantalla o sección ocurrió?", "Which screen or section did it happen on?"),
  happened: tx("¿Qué hiciste y qué ocurrió después?", "What did you do, and what happened next?"),
  expected: tx("¿Qué esperabas que pasara? Si no aplica, podés omitirlo.", "What did you expect to happen? You can skip this if it doesn't apply."),
  benefit: tx("¿Cómo te ayudaría ese cambio?", "How would that change help you?"),
  reproducible: tx("¿Con qué frecuencia sucede?", "How often does it happen?"),
  review: tx("Perfecto. Ya tengo el contexto necesario. ¿Lo envío a soporte?", "Perfect. I have the context I need. Should I send it to support?"),
};

const statusLabel = (report) => {
  if (report.user_resolution === "resolved") return tx("Resuelto", "Resolved");
  if (report.user_resolution === "still_happening") return tx("Sigue ocurriendo", "Still happening");
  if (report.status === "reviewing") return tx("En revisión", "Under review");
  if (report.status === "resolved") return tx("Resuelto por soporte", "Resolved by support");
  return tx("Recibido", "Received");
};

function Bubble({ role, children }) {
  return <div className={`support-bubble support-bubble--${role}`}>
    <span>{role === "bot" ? <Bot size={17}/> : <UserRound size={17}/>}</span><p>{children}</p>
  </div>;
}

export default function Feedback() {
  const [reports, setReports] = useState([]);
  const [health, setHealth] = useState(null);
  const [healthBusy, setHealthBusy] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [step, setStep] = useState("category");
  const [draft, setDraft] = useState("");
  const [chatOpen, setChatOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [resolving, setResolving] = useState(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const load = () => getFeedback().then(setReports).catch(() => setReports([]));
  const loadHealth = useCallback(async () => {
    setHealthBusy(true);
    try { setHealth(await getPlatformHealth()); }
    catch { setHealth({ status: navigator.onLine ? "degraded" : "offline" }); }
    finally { setHealthBusy(false); }
  }, []);

  useEffect(() => {
    load();
    loadHealth();
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(SUPPORT_CONTEXT_KEY) || "null");
      if (saved) {
        setForm({ ...EMPTY, category: "error", screen: saved.screen || "", happened: saved.summary || "", errorReference: saved.errorReference || "" });
        setStep("subject");
        setChatOpen(true);
        window.sessionStorage.removeItem(SUPPORT_CONTEXT_KEY);
      }
    } catch { /* Ignore an invalid local draft. */ }
  }, [loadHealth]);

  const steps = form.category === "improvement" ? IDEA_STEPS : ERROR_STEPS;
  const transcript = useMemo(() => {
    const rows = [{ role:"bot", text:tx("Hola, soy el asistente de soporte de FINVA. Te haré unas preguntas cortas para entenderlo bien.", "Hi, I'm FINVA's support assistant. I'll ask a few short questions so I can understand it correctly.") }];
    if (!form.category) return rows;
    rows.push({ role:"user", text:form.category === "error" ? tx("Tengo un problema", "I have a problem") : tx("Quiero proponer una mejora", "I want to suggest an improvement") });
    for (const key of steps) {
      rows.push({ role:"bot", text:key === "happened" && form.category === "improvement" ? tx("Contame qué te gustaría mejorar.", "Tell me what you'd like to improve.") : prompts[key] });
      if (key === "review") break;
      if (form[key]) rows.push({ role:"user", text:form[key] });
      else if (key === "expected" && steps.indexOf(step) > steps.indexOf(key)) rows.push({ role:"user", text:tx("Omitir", "Skip") });
      else break;
    }
    return rows;
  }, [form, step, steps]);

  const chooseCategory = (category) => {
    setForm({ ...EMPTY, category }); setStep("subject"); setDraft(""); setError("");
  };
  const answer = (value = draft) => {
    const clean = value.trim();
    if (!clean && step !== "expected" && !(step === "screen" && form.category === "improvement")) return;
    setForm({ ...form, [step]: clean });
    setStep(steps[steps.indexOf(step) + 1] || "review");
    setDraft("");
  };
  const restart = () => { setForm(EMPTY); setStep("category"); setDraft(""); setError(""); };
  const closeChat = () => { restart(); setChatOpen(false); };
  const openChat = () => { restart(); setNotice(""); setChatOpen(true); };

  const submit = async () => {
    setBusy(true); setError("");
    const lines = form.category === "error"
      ? [tx(`Pantalla o sección: ${form.screen}`, `Screen or section: ${form.screen}`), tx(`Qué ocurrió: ${form.happened}`, `What happened: ${form.happened}`), tx(`Qué esperaba: ${form.expected || "No indicado"}`, `Expected: ${form.expected || "Not provided"}`), tx(`¿Se puede repetir?: ${form.reproducible}`, `Reproducible?: ${form.reproducible}`)]
      : [tx(`Mejora propuesta: ${form.happened}`, `Suggested improvement: ${form.happened}`), tx(`Cómo ayudaría: ${form.benefit}`, `How it would help: ${form.benefit}`), tx(`Pantalla o sección: ${form.screen || "General"}`, `Screen or section: ${form.screen || "General"}`)];
    try {
      const saved = await createFeedback({ category: form.category, subject: form.subject, message: lines.join("\n"), app_version: import.meta.env.VITE_APP_VERSION, screen: form.screen || undefined, error_reference: form.errorReference || undefined });
      setNotice(saved.email_sent
        ? tx(`Listo. Enviamos ${saved.public_id} al correo de soporte.`, `Done. We emailed ${saved.public_id} to support.`)
        : tx(`Guardamos ${saved.public_id}. Soporte ya puede revisarlo.`, `We saved ${saved.public_id}. Support can now review it.`));
      restart(); setChatOpen(false); load();
    } catch (cause) {
      setError(cause.message || tx("No pudimos enviar el reporte. Intentá nuevamente.", "We couldn't send the report. Please try again."));
    } finally { setBusy(false); }
  };

  const resolveReport = async (report, resolution) => {
    setResolving(report.id); setError("");
    try {
      await updateFeedbackResolution(report.id, resolution);
      setNotice(resolution === "resolved"
        ? tx(`${report.public_id} quedó marcado como resuelto.`, `${report.public_id} was marked as resolved.`)
        : tx(`Avisamos a soporte que ${report.public_id} sigue ocurriendo.`, `We told support that ${report.public_id} is still happening.`));
      await load();
    } catch (cause) {
      setError(cause.message || tx("No pudimos actualizar el reporte.", "We couldn't update the report."));
    } finally { setResolving(null); }
  };

  const needsText = !["category", "reproducible", "review"].includes(step);
  const canSendText = draft.trim().length >= (step === "subject" ? 3 : 1)
    || step === "expected" || (step === "screen" && form.category === "improvement");
  const healthStatus = health?.status || "checking";
  const healthCopy = healthStatus === "operational"
    ? tx("Todos los servicios responden con normalidad.", "All services are responding normally.")
    : healthStatus === "offline"
      ? tx("Este dispositivo no tiene conexión.", "This device is offline.")
      : healthStatus === "major_outage"
        ? tx("Detectamos una interrupción amplia y ya estamos recibiendo diagnósticos.", "We detected a widespread outage and are receiving diagnostics.")
        : tx("Detectamos fallos recientes y FINVA está operando de forma limitada.", "We detected recent failures and FINVA is operating with limitations.");

  return <section className="mobile-page feedback-page support-conversation-page">
    <div className="mobile-page-heading"><p className="eyebrow">{tx("Soporte FINVA", "FINVA support")}</p><h1>{tx("¿En qué te ayudamos?", "How can we help?")}</h1><span>{tx("Conversá con el asistente o revisá el estado de tus reportes.", "Chat with the assistant or review your reports.")}</span></div>
    <section className={`mobile-panel support-health support-health--${healthStatus}`}><span><Activity size={22}/></span><div><small>{tx("Estado de FINVA", "FINVA status")}</small><strong>{healthStatus === "operational" ? tx("Operando normalmente", "Operational") : healthStatus === "offline" ? tx("Sin conexión", "Offline") : healthStatus === "major_outage" ? tx("Interrupción temporal", "Temporary outage") : healthStatus === "checking" ? tx("Comprobando…", "Checking…") : tx("Servicio degradado", "Degraded service")}</strong><p>{healthCopy}</p></div><button type="button" disabled={healthBusy} onClick={loadHealth} aria-label={tx("Actualizar estado", "Refresh status")}><RefreshCw size={18}/></button></section>
    <button type="button" className="mobile-panel support-chat-launch" onClick={openChat}><span><MessageCircle size={22}/></span><div><strong>{tx("Nueva conversación", "New conversation")}</strong><small>{tx("Reportar un problema o proponer una mejora", "Report a problem or suggest an improvement")}</small></div></button>
    {notice && <p className="success-banner">{notice}</p>}{error && !chatOpen && <p className="onboarding-error">{error}</p>}

    <section className="mobile-panel support-report-history">
      <h2>{tx("Mis reportes", "My reports")}</h2>
      {reports.length === 0 && <p className="support-empty">{tx("Todavía no tenés reportes.", "You don't have any reports yet.")}</p>}
      {reports.map((report) => <article className="support-report-card" key={report.id}>
        <div className="support-report-heading"><div><small>{report.public_id}</small><strong>{report.subject}</strong></div><span className={`support-status support-status--${report.user_resolution || report.status}`}>{statusLabel(report)}</span></div>
        {report.user_resolution !== "resolved" && <div className="support-resolution"><p>{tx("¿Esto ya quedó resuelto?", "Has this been resolved?")}</p><div><button type="button" disabled={resolving === report.id} onClick={() => resolveReport(report, "resolved")}><CheckCircle2 size={16}/>{tx("Sí, se resolvió", "Yes, resolved")}</button><button type="button" disabled={resolving === report.id} onClick={() => resolveReport(report, "still_happening")}><AlertCircle size={16}/>{tx("No, sigue igual", "No, still happening")}</button></div></div>}
      </article>)}
    </section>

    {chatOpen && <div className="support-chat-overlay" role="dialog" aria-modal="true" aria-label={tx("Chat de soporte", "Support chat")}>
      <div className="support-chat-shell">
        <header><div><p className="eyebrow">{tx("Soporte FINVA", "FINVA support")}</p><h2>{tx("Nueva conversación", "New conversation")}</h2></div><button type="button" onClick={closeChat} aria-label={tx("Cerrar chat", "Close chat")}><X size={22}/></button></header>
        <section className="support-conversation" aria-live="polite">
          <div className="support-transcript">{transcript.map((item, index) => <Bubble role={item.role} key={`${item.role}-${index}`}>{item.text}</Bubble>)}</div>
          {step === "category" && <div className="support-quick-actions"><button type="button" onClick={() => chooseCategory("error")}><Bug size={18}/>{tx("Tengo un problema", "I have a problem")}</button><button type="button" onClick={() => chooseCategory("improvement")}><Lightbulb size={18}/>{tx("Quiero proponer una mejora", "I want to suggest an improvement")}</button></div>}
          {needsText && <div className="support-composer"><textarea rows="2" autoFocus value={draft} maxLength={step === "subject" ? 140 : 1000} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && canSendText) { event.preventDefault(); answer(); } }} placeholder={tx("Escribí tu respuesta…", "Type your answer…")}/><button type="button" disabled={!canSendText} onClick={() => answer()} aria-label={tx("Enviar respuesta", "Send answer")}><Send size={19}/></button>{(step === "expected" || (step === "screen" && form.category === "improvement")) && <button className="support-skip" type="button" onClick={() => answer("")}>{tx("Omitir", "Skip")}</button>}</div>}
          {step === "reproducible" && <div className="support-quick-actions">{[tx("Siempre", "Always"), tx("Algunas veces", "Sometimes"), tx("Solo ocurrió una vez", "It only happened once")].map((option) => <button type="button" key={option} onClick={() => answer(option)}>{option}</button>)}</div>}
          {step === "review" && <div className="support-review-actions"><button type="button" className="primary-button finva-button finva-button-primary" disabled={busy} onClick={submit}><Send size={17}/>{busy ? tx("Enviando…", "Sending…") : tx("Sí, enviar a soporte", "Yes, send to support")}</button><button type="button" onClick={restart}><RotateCcw size={16}/>{tx("Empezar de nuevo", "Start over")}</button></div>}
          {form.category && step !== "review" && <button className="support-restart" type="button" onClick={restart}><RotateCcw size={14}/>{tx("Reiniciar conversación", "Restart conversation")}</button>}
          <p className="support-privacy">{tx("No incluyás contraseñas, códigos ni números completos de cuentas o tarjetas.", "Do not include passwords, codes, or full account or card numbers.")}</p>
          {error && <p className="onboarding-error">{error}</p>}
        </section>
      </div>
    </div>}
  </section>;
}
