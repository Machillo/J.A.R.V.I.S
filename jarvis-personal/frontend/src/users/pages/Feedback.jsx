import { useEffect, useState } from "react";
import { LifeBuoy, Send } from "lucide-react";
import { createFeedback, getFeedback } from "../services/jarvisApi";

export default function Feedback() {
  const [reports, setReports] = useState([]);
  const [form, setForm] = useState({ category: "improvement", subject: "", message: "" });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const load = () => getFeedback().then(setReports).catch((e) => setError(e.message));
  useEffect(load, []);
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const saved = await createFeedback(form);
      setNotice(`Recibido como ${saved.public_id}.`);
      setForm({ category: "improvement", subject: "", message: "" });
      load();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  return <section className="mobile-page feedback-page">
    <div className="mobile-page-heading"><p className="eyebrow">Ayuda</p><h1>Reportes y sugerencias</h1><span>Contanos qué falló o qué mejoraría FINVA. No incluyás claves ni datos bancarios sensibles.</span></div>
    <form className="mobile-panel feedback-form" onSubmit={submit}>
      <LifeBuoy size={24}/>
      <label>Tipo<select value={form.category} onChange={(e)=>setForm({...form,category:e.target.value})}><option value="improvement">Mejora</option><option value="error">Error</option><option value="payment">Pago</option><option value="support">Soporte</option><option value="security">Seguridad</option></select></label>
      <label>Asunto<input required minLength="3" maxLength="140" value={form.subject} onChange={(e)=>setForm({...form,subject:e.target.value})}/></label>
      <label>Detalle<textarea required minLength="5" maxLength="4000" rows="6" value={form.message} onChange={(e)=>setForm({...form,message:e.target.value})}/></label>
      <button className="primary-button" disabled={busy}><Send size={17}/> {busy ? "Enviando..." : "Enviar"}</button>
      {notice && <p className="success-banner">{notice}</p>}{error && <p className="onboarding-error">{error}</p>}
    </form>
    {reports.length > 0 && <div className="mobile-panel"><h2>Mis reportes</h2>{reports.map(r=><div className="feedback-row" key={r.id}><strong>{r.public_id} · {r.subject}</strong><span>{r.status}</span></div>)}</div>}
  </section>;
}
