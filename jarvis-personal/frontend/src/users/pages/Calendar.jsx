import { useEffect,useState } from "react";
import { deviceLanguage, localeTag } from "../../lib/locale";
import { getFinancialCalendar } from "../services/jarvisApi";
const language=deviceLanguage();
const tx=(es,en)=>language==="es"?es:en;
const money=v=>new Intl.NumberFormat(localeTag(language),{style:"currency",currency:"CRC",maximumFractionDigits:0}).format(Number(v)||0);
const now=()=>new Date().toISOString().slice(0,7);

export default function FinancialCalendar({ plan = "basic" }){
  const [period,setPeriod]=useState(now()),[data,setData]=useState(null),[error,setError]=useState("");
  useEffect(()=>{setData(null);getFinancialCalendar(period).then(setData).catch(e=>setError(e.message))},[period]);
  const grouped=(data?.events||[]).reduce((acc,event)=>{(acc[event.date] ||= []).push(event);return acc},{});
  return <section className="finva-basic-calendar">
    {plan === "free" && <div className="hero"><span>BASIC</span><h1>{tx("Calendario financiero","Financial calendar")}</h1><p>{tx("Pagos, ingresos, deudas y fechas importantes del mes.","Payments, income, debt, and important dates for the month.")}</p></div>}
    <div className="basic-calendar-picker"><input className="month-picker" type="month" value={period} onChange={e=>setPeriod(e.target.value)}/></div>
    {error&&<div className="panel error">{error}</div>}
    {!data?<div className="panel">{tx("Cargando...","Loading...")}</div>:<>
      <article className="basic-calendar-summary"><span><small>{tx("COMPROMISOS","COMMITMENTS")}</small><strong>{data.summary.commitments}</strong></span><span><small>{tx("PAGOS CONOCIDOS","KNOWN PAYMENTS")}</small><strong>{money(data.summary.payments)}</strong></span></article>
      <div className="basic-calendar-days">
        {Object.keys(grouped).length ? Object.entries(grouped).map(([date,events])=><article className="basic-calendar-day" key={date}>
          <header><strong>{new Date(`${date}T12:00:00`).toLocaleDateString(localeTag(language),{day:"2-digit",month:"long"})}</strong><span>{events.length} {events.length===1?tx("evento","event"):tx("eventos","events")}</span></header>
          {events.map((event,index)=><div className={`basic-calendar-event ${event.kind}`} key={`${date}-${event.name}-${index}`}>
            <span><b>{event.name}</b><small>{event.kind}</small></span><strong>{event.amount?money(event.amount):"—"}</strong>
          </div>)}
        </article>):<div className="panel finva-empty-state">{tx("No hay eventos configurados para este mes.","No events configured for this month.")}</div>}
      </div>
    </>}
  </section>;
}
