import { useEffect, useState } from "react";
import { getFreeMonthlySummary } from "../services/jarvisApi";
import { deviceLanguage, localeTag, tx } from "../../lib/locale";

const language=deviceLanguage();
const copy=(es,en)=>tx(es,en,language);
const money=(value)=>new Intl.NumberFormat(localeTag(language),{style:"currency",currency:"CRC",maximumFractionDigits:0}).format(Number(value)||0);
const currentMonth=()=>new Date().toISOString().slice(0,7);

export default function MonthlySummary(){
  const[period,setPeriod]=useState(currentMonth()),[data,setData]=useState(null),[error,setError]=useState("");
  useEffect(()=>{setError("");getFreeMonthlySummary(period).then(setData).catch((err)=>setError(err.message));},[period]);
  const max=Math.max(...(data?.categories||[]).map((item)=>Number(item.amount)),1);
  return <section><div className="hero"><span>DINCR · FREE</span><h1>{copy("Resumen mensual","Monthly summary")}</h1><p>{copy("Lo que ocurrió durante el mes, sin recomendaciones.","What happened during the month, without recommendations.")}</p></div><input className="month-picker" type="month" value={period} onChange={(e)=>setPeriod(e.target.value)}/>{error&&<div className="panel error">{error}</div>}{!data&&!error?<div className="panel">{copy("Cargando resumen...","Loading summary...")}</div>:data&&<><div className="kpis"><div className="card"><small>{copy("Total ingresado","Total income")}</small><strong>{money(data.income)}</strong></div><div className="card"><small>{copy("Total gastado","Total spent")}</small><strong>{money(data.expenses)}</strong></div><div className="card"><small>{copy("Balance","Balance")}</small><strong className={data.balance<0?"negative":""}>{money(data.balance)}</strong></div><div className="card"><small>{copy("Deuda pagada","Debt paid")}</small><strong>{money(data.debt_paid)}</strong></div><div className="card"><small>{copy("Ahorro registrado","Recorded savings")}</small><strong>{money(data.savings)}</strong></div><div className="card"><small>{copy("Progreso de metas","Goal progress")}</small><strong>{data.goals.progress}%</strong></div></div><div className="panel monthly-highlight"><small>{copy("Categoría con mayor gasto","Top spending category")}</small><strong>{data.top_category?.category||copy("Sin gastos","No expenses")}</strong><span>{money(data.top_category?.amount)}</span></div><div className="panel free-categories"><h3>{copy("Distribución de gastos","Expense distribution")}</h3>{data.categories.map((item)=><div key={item.category}><span>{item.category}</span><i><b style={{width:`${Number(item.amount)/max*100}%`}}/></i><strong>{money(item.amount)}</strong></div>)}</div></>}</section>;
}
