import { useEffect, useState } from "react";
import { Activity, CheckCircle2, CreditCard, FileCheck2, Mail, MessageSquareWarning, RefreshCw, Smartphone } from "lucide-react";
import { getProductOperations, openTestPaymentReceipt, resendProductFeedback, resolveTestPayment, updateProductFeedback, updateReleasePolicy } from "../services/jarvisApi";

const emptyRelease = { minimum_supported_version:"1.0.0", latest_version:"1.0.0", update_url:"", message_es:"Hay una nueva versión de FINVA disponible.", message_en:"A new FINVA version is available.", is_active:false };

export default function ProductOperations() {
  const [data,setData]=useState(null), [error,setError]=useState(""), [busy,setBusy]=useState("");
  const [release,setRelease]=useState(emptyRelease);
  const load=()=>{setError("");return getProductOperations().then(setData).catch(e=>setError(e.message));};
  useEffect(()=>{
    getProductOperations().then(setData).catch(e=>setError(e.message));
  },[]);
  useEffect(()=>{
    const android=data?.release_policies?.find(item=>item.platform==="android");
    if(android) setRelease({...android,update_url:android.update_url||""});
  },[data]);
  const payment=async(id,action)=>{setBusy(`order-${id}`);try{await resolveTestPayment(id,action);await load();}catch(e){setError(e.message);}finally{setBusy("");}};
  const receipt=async(id)=>{setBusy(`receipt-${id}`);try{await openTestPaymentReceipt(id);}catch(e){setError(e.message);}finally{setBusy("");}};
  const ticket=async(id,status)=>{setBusy(`ticket-${id}`);try{await updateProductFeedback(id,{status,owner_notes:null});await load();}catch(e){setError(e.message);}finally{setBusy("");}};
  const resend=async(id)=>{setBusy(`ticket-email-${id}`);try{const result=await resendProductFeedback(id);setError(`${result.public_id} enviado nuevamente al correo de soporte.`);}catch(e){setError(e.message);}finally{setBusy("");}};
  const saveRelease=async(event)=>{event.preventDefault();setBusy("release");setError("");try{await updateReleasePolicy("android",{...release,update_url:release.update_url.trim()||null});await load();setError("Política Android actualizada.");}catch(e){setError(e.message);}finally{setBusy("");}};
  return <section className="product-ops-page">
    <article className="app-section-card product-ops-head"><div><small>FINVA</small><h2>Operaciones del producto</h2><p>Promoción de lanzamiento, pagos, uso anónimo y reportes.</p></div><button onClick={load}><RefreshCw size={18}/> Actualizar</button></article>
    {error&&<p className="user-admin-message">{error}</p>}
    <div className="product-ops-grid">{["basic","vip"].map(code=><article className="app-section-card product-kpi" key={code}><CreditCard/><small>{code.toUpperCase()} PROMOCIONAL</small><strong>{data?.promotion?.plans?.[code]||0}</strong><span>usuarios · gratis hasta 31 dic 2026</span></article>)}</div>
    <article className="app-section-card product-ops-section"><h3><Smartphone size={19}/> Política de actualización · Android</h3><p>“Más reciente” muestra un aviso opcional. “Mínima” bloquea versiones anteriores y solo puede elevarse cuando hay una URL HTTPS.</p><form className="release-policy-form" onSubmit={saveRelease}><label>Versión mínima<input value={release.minimum_supported_version} onChange={e=>setRelease({...release,minimum_supported_version:e.target.value})} placeholder="1.9.6" required/></label><label>Versión más reciente<input value={release.latest_version} onChange={e=>setRelease({...release,latest_version:e.target.value})} placeholder="1.9.7" required/></label><label className="release-policy-form__wide">URL de descarga HTTPS<input type="url" value={release.update_url} onChange={e=>setRelease({...release,update_url:e.target.value})} placeholder="https://..."/></label><label className="release-policy-form__wide">Mensaje<input value={release.message_es} onChange={e=>setRelease({...release,message_es:e.target.value})} required/></label><label className="release-policy-toggle"><input type="checkbox" checked={release.is_active} onChange={e=>setRelease({...release,is_active:e.target.checked})}/> Política activa</label><button type="submit" disabled={Boolean(busy)}>{busy==="release"?"Guardando…":"Guardar política"}</button></form></article>
    <article className="app-section-card product-ops-section"><h3><CreditCard size={19}/> Pagos pendientes</h3>{!data?.pending_orders?.length?<p>Sin solicitudes pendientes.</p>:data.pending_orders.map(o=><div className="product-ops-row" key={o.id}><div><strong>{o.display_name||o.email}</strong><small>{o.plan_code.toUpperCase()} · ₡{Number(o.amount).toLocaleString("es-CR")} · {o.payment_code}</small><small>{o.receipt_submitted_at?"Comprobante recibido":"Esperando comprobante"}</small></div><div>{o.receipt_submitted_at&&<button disabled={busy} onClick={()=>receipt(o.id)}><FileCheck2 size={16}/> Ver comprobante</button>}<button disabled={busy} onClick={()=>payment(o.id,"confirm")}><CheckCircle2 size={16}/> Confirmar</button><button disabled={busy} className="danger" onClick={()=>payment(o.id,"reject")}>Rechazar</button></div></div>)}</article>
    <article className="app-section-card product-ops-section"><h3><Activity size={19}/> Funciones usadas · 30 días</h3>{!data?.feature_usage_30d?.length?<p>Sin eventos todavía.</p>:data.feature_usage_30d.map(e=><div className="product-ops-row" key={e.event_name}><strong>{e.event_name.replaceAll("_"," ")}</strong><span>{e.uses} usos · {e.users} usuarios</span></div>)}</article>
    <article className="app-section-card product-ops-section"><h3><MessageSquareWarning size={19}/> Reportes</h3>{!data?.tickets?.length?<p>Sin reportes.</p>:data.tickets.map(t=><div className="product-ticket" key={t.id}><div><strong>{t.public_id} · {t.subject}</strong><small>{t.category} · {t.email} · {t.status}</small><p>{t.message}</p></div><div><button disabled={Boolean(busy)} onClick={()=>resend(t.id)}><Mail size={16}/> {busy===`ticket-email-${t.id}`?"Enviando…":"Reenviar correo"}</button><select disabled={Boolean(busy)} value={t.status} onChange={e=>ticket(t.id,e.target.value)}><option value="new">Nuevo</option><option value="reviewing">Revisando</option><option value="resolved">Resuelto</option><option value="dismissed">Descartado</option></select></div></div>)}</article>
  </section>;
}
