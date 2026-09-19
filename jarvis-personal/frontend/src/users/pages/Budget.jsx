import { useEffect, useState } from "react";
import { getBudget, saveBudget } from "../services/jarvisApi";
import { deviceLanguage, localeTag, tx } from "../../lib/locale";
const language=deviceLanguage();
const copy=(es,en)=>tx(es,en,language);
const money=(v)=>new Intl.NumberFormat(localeTag(language),{style:"currency",currency:"CRC",maximumFractionDigits:0}).format(Number(v)||0);
export default function Budget(){
 const [data,setData]=useState(null),[error,setError]=useState(""),[saving,setSaving]=useState(false);
 const load=()=>getBudget().then(setData).catch(e=>setError(e.message)); useEffect(load,[]);
 const change=(i,value)=>setData({...data,items:data.items.map((x,n)=>n===i?{...x,monthly_limit:value}:x)});
 const save=async()=>{setSaving(true);setError("");try{setData(await saveBudget({items:data.items.map(x=>({category:x.category,monthly_limit:Number(x.monthly_limit)||0}))}))}catch(e){setError(e.message)}finally{setSaving(false)}};
 if(!data)return <div className={`panel ${error?"error":""}`}>{error||copy("Preparando presupuesto...","Preparing budget...")}</div>;
 return <section><div className="hero"><span>BASIC 02</span><h1>{copy("Presupuesto guiado","Guided budget")}</h1><p>{copy("Finva propone una base; vos podés ajustarla.","Finva suggests a starting point; you can adjust it.")}</p></div>{error&&<div className="panel error">{error}</div>}
 <div className="kpis"><div className="card"><small>{copy("Ingreso estimado","Estimated income")}</small><strong>{money(data.income)}</strong></div><div className="card"><small>{copy("Cuotas de deuda","Debt payments")}</small><strong>{money(data.debt_minimums)}</strong></div><div className="card"><small>{copy("Recurrentes","Recurring")}</small><strong>{money(data.recurring_expenses)}</strong></div><div className="card"><small>{copy("Para categorías","For categories")}</small><strong>{money(data.available_for_categories)}</strong></div></div>
 <div className="panel budget-list"><h3>{data.is_proposal?copy("Propuesta inicial","Initial proposal"):copy("Tu presupuesto","Your budget")}</h3>{data.items.map((x,i)=><label key={x.category}><span><b>{x.category}</b><small>{copy("Gastado","Spent")} {money(x.spent)} · {copy("disponible","available")} {money(x.remaining)}</small></span><input type="number" min="0" step="0.01" value={x.monthly_limit} onChange={e=>change(i,e.target.value)}/></label>)}<button className="finva-button finva-button-primary" onClick={save} disabled={saving}>{saving?copy("Guardando...","Saving..."):copy("Guardar presupuesto","Save budget")}</button></div></section>;
}
