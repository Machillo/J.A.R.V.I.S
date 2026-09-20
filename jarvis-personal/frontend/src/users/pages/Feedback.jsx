import { useEffect, useMemo, useState } from "react";
import { Bot, Bug, Lightbulb, RotateCcw, Send, UserRound } from "lucide-react";
import { SUPPORT_CONTEXT_KEY } from "../../lib/apiErrors";
import { createFeedback, getFeedback } from "../services/jarvisApi";
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

function Bubble({ role, children }) {
  return <div className={`support-bubble support-bubble--${role}`}>
    <span>{role === "bot" ? <Bot size={17}/> : <UserRound size={17}/>}</span><p>{children}</p>
  </div>;
}

export default function Feedback() {
  const [reports, setReports] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [step, setStep] = useState("category");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const load = () => getFeedback().then(setReports).catch(() => setReports([]));

  useEffect(() => {
    load();
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(SUPPORT_CONTEXT_KEY) || "null");
      if (saved) {
        setForm({ ...EMPTY, category: "error", screen: saved.screen || "", happened: saved.summary || "", errorReference: saved.errorReference || "" });
        setStep("subject");
        window.sessionStorage.removeItem(SUPPORT_CONTEXT_KEY);
      }
    } catch { /* Ignore an invalid local draft. */ }
  }, []);

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
    setForm({ ...EMPTY, category }); setStep("subject"); setDraft(""); setNotice(""); setError("");
  };
  const answer = (value = draft) => {
    const clean = value.trim();
    if (!clean && step !== "expected" && !(step === "screen" && form.category === "improvement")) return;
    const nextForm = { ...form, [step]: clean };
    const currentIndex = steps.indexOf(step);
    setForm(nextForm); setStep(steps[currentIndex + 1] || "review"); setDraft("");
  };
  const restart = () => { setForm(EMPTY); setStep("category"); setDraft(""); setNotice(""); setError(""); };

  const submit = async () => {
    setBusy(true); setError(""); setNotice("");
    const lines = form.category === "error"
      ? [tx(`Pantalla o sección: ${form.screen}`, `Screen or section: ${form.screen}`), tx(`Qué ocurrió: ${form.happened}`, `What happened: ${form.happened}`), tx(`Qué esperaba: ${form.expected || "No indicado"}`, `Expected: ${form.expected || "Not provided"}`), tx(`¿Se puede repetir?: ${form.reproducible}`, `Reproducible?: ${form.reproducible}`)]
      : [tx(`Mejora propuesta: ${form.happened}`, `Suggested improvement: ${form.happened}`), tx(`Cómo ayudaría: ${form.benefit}`, `How it would help: ${form.benefit}`), tx(`Pantalla o sección: ${form.screen || "General"}`, `Screen or section: ${form.screen || "General"}`)];
    try {
      const saved = await createFeedback({ category: form.category, subject: form.subject, message: lines.join("\n"), app_version: import.meta.env.VITE_APP_VERSION, screen: form.screen || undefined, error_reference: form.errorReference || undefined });
      setNotice(saved.email_sent
        ? tx(`Listo. Enviamos ${saved.public_id} al correo de soporte.`, `Done. We emailed ${saved.public_id} to support.`)
        : tx(`Guardamos ${saved.public_id}. Podés seguir usando FINVA mientras soporte lo revisa.`, `We saved ${saved.public_id}. You can keep using FINVA while support reviews it.`));
      setForm(EMPTY); setStep("category"); load();
    } catch (cause) {
      setError(cause.message || tx("No pudimos enviar el reporte. Intentá nuevamente.", "We couldn't send the report. Please try again."));
    } finally { setBusy(false); }
  };

  const needsText = !["category", "reproducible", "review"].includes(step);
  const canSendText = draft.trim().length >= (step === "subject" ? 3 : 1)
    || step === "expected" || (step === "screen" && form.category === "improvement");

  return <section className="mobile-page feedback-page support-conversation-page">
    <div className="mobile-page-heading"><p className="eyebrow">{tx("Soporte FINVA", "FINVA support")}</p><h1>{tx("Hablemos", "Let's talk")}</h1><span>{tx("El asistente reúne el contexto y crea el ticket por vos.", "The assistant gathers context and creates the ticket for you.")}</span></div>
    <section className="mobile-panel support-conversation" aria-live="polite">
      <div className="support-transcript">{transcript.map((item, index) => <Bubble role={item.role} key={`${item.role}-${index}`}>{item.text}</Bubble>)}</div>
      {step === "category" && <div className="support-quick-actions">
        <button type="button" onClick={() => chooseCategory("error")}><Bug size={18}/>{tx("Tengo un problema", "I have a problem")}</button>
        <button type="button" onClick={() => chooseCategory("improvement")}><Lightbulb size={18}/>{tx("Quiero proponer una mejora", "I want to suggest an improvement")}</button>
      </div>}
      {needsText && <div className="support-composer">
        <textarea rows="2" autoFocus value={draft} maxLength={step === "subject" ? 140 : 1000} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && canSendText) { event.preventDefault(); answer(); } }} placeholder={tx("Escribí tu respuesta…", "Type your answer…")}/>
        <button type="button" disabled={!canSendText} onClick={() => answer()} aria-label={tx("Enviar respuesta", "Send answer")}><Send size={19}/></button>
        {(step === "expected" || (step === "screen" && form.category === "improvement")) && <button className="support-skip" type="button" onClick={() => answer("")}>{tx("Omitir", "Skip")}</button>}
      </div>}
      {step === "reproducible" && <div className="support-quick-actions">
        {[tx("Siempre", "Always"), tx("Algunas veces", "Sometimes"), tx("Solo ocurrió una vez", "It only happened once")].map((option) => <button type="button" key={option} onClick={() => answer(option)}>{option}</button>)}
      </div>}
      {step === "review" && <div className="support-review-actions"><button type="button" className="primary-button finva-button finva-button-primary" disabled={busy} onClick={submit}><Send size={17}/>{busy ? tx("Enviando…", "Sending…") : tx("Sí, enviar a soporte", "Yes, send to support")}</button><button type="button" onClick={restart}><RotateCcw size={16}/>{tx("Empezar de nuevo", "Start over")}</button></div>}
      {form.category && step !== "review" && <button className="support-restart" type="button" onClick={restart}><RotateCcw size={14}/>{tx("Reiniciar conversación", "Restart conversation")}</button>}
      <p className="support-privacy">{tx("No incluyás contraseñas, códigos ni números completos de cuentas o tarjetas.", "Do not include passwords, codes, or full account or card numbers.")}</p>
      {notice && <p className="success-banner">{notice}</p>}{error && <p className="onboarding-error">{error}</p>}
    </section>
    {reports.length > 0 && <div className="mobile-panel"><h2>{tx("Mis reportes", "My reports")}</h2>{reports.map((report)=><div className="feedback-row" key={report.id}><strong>{report.public_id} · {report.subject}</strong><span>{report.status}</span></div>)}</div>}
  </section>;
}
