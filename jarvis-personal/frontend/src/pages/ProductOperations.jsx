import { useEffect, useState } from "react";
import { Activity, CheckCircle2, CreditCard, FileCheck2, MessageSquareWarning, RefreshCw } from "lucide-react";
import { getProductOperations, openTestPaymentReceipt, resolveTestPayment, updateProductFeedback } from "../services/jarvisApi";

export default function ProductOperations() {
  const [data,setData]=useState(null), [error,setError]=useState(""), [busy,setBusy]=useState("");
  const load=()=>{setError("");return getProductOperations().then(setData).catch(e=>setError(e.message));};
  useEffect(()=>{
    getProductOperations().then(setData).catch(e=>setError(e.message));
  },[]);
  const payment=async(id,action)=>{setBusy(`order-${id}`);try{await resolveTestPayment(id,action);await load();}catch(e){setError(e.message);}finally{setBusy("");}};
  const receipt=async(id)=>{setBusy(`receipt-${id}`);try{await openTestPaymentReceipt(id);}catch(e){setError(e.message);}finally{setBusy("");}};
  const ticket=async(id,status)=>{setBusy(`ticket-${id}`);try{await updateProductFeedback(id,{status,owner_notes:null});await load();}catch(e){setError(e.message);}finally{setBusy("");}};
  return <section className="product-ops-page">
    <article className="app-section-card product-ops-head"><div><small>FINVA BETA</small><h2>Operaciones del producto</h2><p>Cobros de prueba, uso anónimo de funciones y reportes.</p></div><button onClick={load}><RefreshCw size={18}/> Actualizar</button></article>
    {error&&<p className="user-admin-message">{error}</p>}
    <div className="product-ops-grid">{["basic","vip"].map(code=><article className="app-section-card product-kpi" key={code}><CreditCard/><small>{code.toUpperCase()} BETA</small><strong>{data?.beta?.[code]?.used||0} / {data?.beta?.[code]?.total||15}</strong><span>{data?.beta?.[code]?.remaining??15} cupos disponibles</span></article>)}</div>
    <article className="app-section-card product-ops-section"><h3><CreditCard size={19}/> Pagos pendientes</h3>{!data?.pending_orders?.length?<p>Sin solicitudes pendientes.</p>:data.pending_orders.map(o=><div className="product-ops-row" key={o.id}><div><strong>{o.display_name||o.email}</strong><small>{o.plan_code.toUpperCase()} · ₡{Number(o.amount).toLocaleString("es-CR")} · {o.payment_code}</small><small>{o.receipt_submitted_at?"Comprobante recibido":"Esperando comprobante"}</small></div><div>{o.receipt_submitted_at&&<button disabled={busy} onClick={()=>receipt(o.id)}><FileCheck2 size={16}/> Ver comprobante</button>}<button disabled={busy} onClick={()=>payment(o.id,"confirm")}><CheckCircle2 size={16}/> Confirmar</button><button disabled={busy} className="danger" onClick={()=>payment(o.id,"reject")}>Rechazar</button></div></div>)}</article>
    <article className="app-section-card product-ops-section"><h3><Activity size={19}/> Funciones usadas · 30 días</h3>{!data?.feature_usage_30d?.length?<p>Sin eventos todavía.</p>:data.feature_usage_30d.map(e=><div className="product-ops-row" key={e.event_name}><strong>{e.event_name.replaceAll("_"," ")}</strong><span>{e.uses} usos · {e.users} usuarios</span></div>)}</article>
    <article className="app-section-card product-ops-section"><h3><MessageSquareWarning size={19}/> Reportes</h3>{!data?.tickets?.length?<p>Sin reportes.</p>:data.tickets.map(t=><div className="product-ticket" key={t.id}><div><strong>{t.public_id} · {t.subject}</strong><small>{t.category} · {t.email} · {t.status}</small><p>{t.message}</p></div><select disabled={busy} value={t.status} onChange={e=>ticket(t.id,e.target.value)}><option value="new">Nuevo</option><option value="reviewing">Revisando</option><option value="resolved">Resuelto</option><option value="dismissed">Descartado</option></select></div>)}</article>
  </section>;
}
