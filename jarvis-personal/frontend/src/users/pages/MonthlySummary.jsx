import { useEffect, useState } from "react";
import { getFreeMonthlySummary } from "../services/jarvisApi";

const money=(value)=>new Intl.NumberFormat("es-CR",{style:"currency",currency:"CRC",maximumFractionDigits:0}).format(Number(value)||0);
const currentMonth=()=>new Date().toISOString().slice(0,7);

export default function MonthlySummary(){
  const[period,setPeriod]=useState(currentMonth()),[data,setData]=useState(null),[error,setError]=useState("");
  useEffect(()=>{setError("");getFreeMonthlySummary(period).then(setData).catch((err)=>setError(err.message));},[period]);
  const max=Math.max(...(data?.categories||[]).map((item)=>Number(item.amount)),1);
  return <section><div className="hero"><span>FREE 07</span><h1>Resumen mensual</h1><p>Lo que ocurrió durante el mes, sin recomendaciones.</p></div><input className="month-picker" type="month" value={period} onChange={(e)=>setPeriod(e.target.value)}/>{error&&<div className="panel error">{error}</div>}{!data&&!error?<div className="panel">Cargando resumen...</div>:data&&<><div className="kpis"><div className="card"><small>Total ingresado</small><strong>{money(data.income)}</strong></div><div className="card"><small>Total gastado</small><strong>{money(data.expenses)}</strong></div><div className="card"><small>Balance</small><strong className={data.balance<0?"negative":""}>{money(data.balance)}</strong></div><div className="card"><small>Deuda pagada</small><strong>{money(data.debt_paid)}</strong></div><div className="card"><small>Ahorro registrado</small><strong>{money(data.savings)}</strong></div><div className="card"><small>Progreso de metas</small><strong>{data.goals.progress}%</strong></div></div><div className="panel monthly-highlight"><small>Categoría con mayor gasto</small><strong>{data.top_category?.category||"Sin gastos"}</strong><span>{money(data.top_category?.amount)}</span></div><div className="panel free-categories"><h3>Distribución de gastos</h3>{data.categories.map((item)=><div key={item.category}><span>{item.category}</span><i><b style={{width:`${Number(item.amount)/max*100}%`}}/></i><strong>{money(item.amount)}</strong></div>)}</div></>}</section>;
}
