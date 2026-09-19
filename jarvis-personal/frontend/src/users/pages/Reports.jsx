import { useEffect,useMemo,useState } from "react";
import { deviceLanguage, localeTag } from "../../lib/locale";
import { getBasicReport } from "../services/jarvisApi";
const language=deviceLanguage();
const tx=(es,en)=>language==="es"?es:en;
const money=v=>new Intl.NumberFormat(localeTag(language),{style:"currency",currency:"CRC",maximumFractionDigits:0}).format(Number(v)||0);
const now=()=>new Date().toISOString().slice(0,7);
const shift=(period,delta)=>{const [y,m]=period.split("-").map(Number);const d=new Date(y,m-1+delta,1);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`};

export default function Reports(){
  const [period,setPeriod]=useState(now()),[range,setRange]=useState(1),[rows,setRows]=useState([]),[error,setError]=useState("");
  useEffect(()=>{
    setRows([]);setError("");
    Promise.all(Array.from({length:range},(_,index)=>getBasicReport(shift(period,-index))))
      .then(result=>setRows(result.reverse())).catch(e=>setError(e.message));
  },[period,range]);
  const data=rows[rows.length-1];
  const max=Math.max(...rows.flatMap(row=>[Number(row.income),Number(row.expenses)]),1);
  const categoryRows=useMemo(()=>data?.categories||[],[data]);

  return <section className="finva-basic-reports">
    <div className="hero"><span>BASIC</span><h1>{tx("Reportes","Reports")}</h1><p>{tx("Compará resultados, tendencias y categorías con datos reales registrados.","Compare results, trends, and categories using your recorded data.")}</p></div>
    <div className="basic-report-tabs"><button className={range===1?"active":""} onClick={()=>setRange(1)}>{tx("Mes","Month")}</button><button className={range===3?"active":""} onClick={()=>setRange(3)}>3 {tx("meses","months")}</button><button className={range===6?"active":""} onClick={()=>setRange(6)}>6 {tx("meses","months")}</button></div>
    <input className="month-picker" type="month" value={period} onChange={e=>setPeriod(e.target.value)}/>
    {error&&<div className="panel error">{error}</div>}
    {data&&<>
      <article className="basic-report-chart">
        <header><strong>{tx("Ingresos vs gastos","Income vs expenses")}</strong><span>{range===1?tx("Este mes","This month"):`${range} ${tx("meses","months")}`}</span></header>
        <div className="basic-report-bars">{rows.map(row=><div key={row.period}><small>{row.period.slice(5)}</small><i><b className="income" style={{width:`${Number(row.income)/max*100}%`}}/></i><i><b className="expense" style={{width:`${Number(row.expenses)/max*100}%`}}/></i></div>)}</div>
        <footer><span>{tx("Ingresos","Income")} {money(data.income)}</span><span>{tx("Gastos","Expenses")} {money(data.expenses)}</span></footer>
      </article>
      <article className="basic-report-categories"><h3>{tx("Tendencia por categoría","Category trend")}</h3>{categoryRows.slice(0,4).map(item=><div key={item.category}><span>{item.category}</span><strong>{money(item.amount)}</strong></div>)}</article>
      <article className="basic-report-balance"><h3>{tx("Balance comparado","Balance comparison")}</h3>{rows.slice(-2).map(row=><div key={row.period}><span>{new Date(`${row.period}-01T12:00:00`).toLocaleDateString(localeTag(language),{month:"long"})}</span><strong>{money(row.balance)}</strong></div>)}{data.comparison&&<b className={Number(data.comparison.expenses)<=0?"positive":"negative"}>{tx("Variación de gastos","Expense change")}: {money(data.comparison.expenses)}</b>}</article>
    </>}
  </section>;
}
