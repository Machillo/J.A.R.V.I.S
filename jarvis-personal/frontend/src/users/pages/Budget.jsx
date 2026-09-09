import { useEffect, useState } from "react";
import { getBudget, saveBudget } from "../services/jarvisApi";
const money=(v)=>new Intl.NumberFormat("es-CR",{style:"currency",currency:"CRC",maximumFractionDigits:0}).format(Number(v)||0);
export default function Budget(){
 const [data,setData]=useState(null),[error,setError]=useState(""),[saving,setSaving]=useState(false);
 const load=()=>getBudget().then(setData).catch(e=>setError(e.message)); useEffect(load,[]);
 const change=(i,value)=>setData({...data,items:data.items.map((x,n)=>n===i?{...x,monthly_limit:value}:x)});
 const save=async()=>{setSaving(true);setError("");try{setData(await saveBudget({items:data.items.map(x=>({category:x.category,monthly_limit:Number(x.monthly_limit)||0}))}))}catch(e){setError(e.message)}finally{setSaving(false)}};
 if(!data)return <div className={`panel ${error?"error":""}`}>{error||"Preparando presupuesto..."}</div>;
 return <section><div className="hero"><span>BASIC 02</span><h1>Presupuesto guiado</h1><p>Finva propone una base; vos podés ajustarla.</p></div>{error&&<div className="panel error">{error}</div>}
 <div className="kpis"><div className="card"><small>Ingreso estimado</small><strong>{money(data.income)}</strong></div><div className="card"><small>Cuotas de deuda</small><strong>{money(data.debt_minimums)}</strong></div><div className="card"><small>Recurrentes</small><strong>{money(data.recurring_expenses)}</strong></div><div className="card"><small>Para categorías</small><strong>{money(data.available_for_categories)}</strong></div></div>
 <div className="panel budget-list"><h3>{data.is_proposal?"Propuesta inicial":"Tu presupuesto"}</h3>{data.items.map((x,i)=><label key={x.category}><span><b>{x.category}</b><small>Gastado {money(x.spent)} · disponible {money(x.remaining)}</small></span><input type="number" min="0" value={x.monthly_limit} onChange={e=>change(i,e.target.value)}/></label>)}<button onClick={save} disabled={saving}>{saving?"Guardando...":"Guardar presupuesto"}</button></div></section>;
}
