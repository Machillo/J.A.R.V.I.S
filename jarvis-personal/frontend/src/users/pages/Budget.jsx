import { useEffect, useMemo, useState } from "react";
import { getBudget, saveBudget } from "../services/jarvisApi";
import { deviceLanguage, localeTag, tx } from "../../lib/locale";
import { formatMoney } from "../../lib/currency";
import { categoryLabel } from "../../lib/categories";
const language=deviceLanguage();
const copy=(es,en)=>tx(es,en,language);
// Amounts are in the account's base currency (CRC or USD).
const money = (value) => formatMoney(value);

export default function Budget({ plan = "basic" }){
  const [data,setData]=useState(null),[error,setError]=useState(""),[saving,setSaving]=useState(false),[editing,setEditing]=useState(false);
  const load=()=>getBudget().then(setData).catch(e=>setError(e.message));
  useEffect(() => { load(); }, []);
  const totals=useMemo(()=>{
    const items=data?.items||[];
    const spent=items.reduce((sum,item)=>sum+Number(item.spent||0),0);
    const budgeted=items.reduce((sum,item)=>sum+Number(item.monthly_limit||0),0);
    return {spent,budgeted,available:Math.max(budgeted-spent,0)};
  },[data]);
  const change=(i,value)=>setData({...data,items:data.items.map((x,n)=>n===i?{...x,monthly_limit:value}:x)});
  const save=async()=>{setSaving(true);setError("");try{setData(await saveBudget({items:data.items.map(x=>({category:x.category,monthly_limit:Number(x.monthly_limit)||0}))}));setEditing(false)}catch(e){setError(e.message)}finally{setSaving(false)}};
  if(!data)return <div className={`panel ${error?"error":""}`}>{error||copy("Preparando presupuesto...","Preparing budget...")}</div>;

  return <section className="finva-basic-budget">
    {plan !== "basic" && <div className="hero"><span>DINCR · {plan === "vip" ? "VIP" : "BASIC"}</span><h1>{copy("Presupuesto guiado","Guided budget")}</h1><p>{copy("Organizá cuánto querés usar por categoría y comparalo con lo que ya gastaste.","Organize how much you want to use by category and compare it with what you've already spent.")}</p></div>}
    {error&&<div className="panel error">{error}</div>}
    <article className="basic-budget-summary">
      <small>{new Date().toLocaleDateString(localeTag(language),{month:"long"}).toUpperCase()}</small>
      <strong>{money(totals.spent)} <span>/ {money(totals.budgeted)}</span></strong>
      <b>{copy("Disponible","Available")} {money(totals.available)}</b>
    </article>
    <div className="basic-budget-list">
      {data.items.map((item,index)=>{
        const limit=Number(item.monthly_limit)||0, spent=Number(item.spent)||0;
        const pct=limit?Math.min(spent/limit*100,100):0;
        const over=limit>0&&spent>limit;
        return <article className={`basic-budget-category${over?" is-over":""}`} key={item.category}>
          <header><strong>{categoryLabel(item.category)}</strong><span>{over?`${money(spent-limit)} ${copy("excedido","over")}`:`${money(Math.max(limit-spent,0))} ${copy("libre","left")}`}</span></header>
          {editing
            ? <label><span>{copy("Límite mensual","Monthly limit")}</span><input type="number" min="0" step="0.01" value={item.monthly_limit} onChange={e=>change(index,e.target.value)}/></label>
            : <><p>{money(spent)} / {money(limit)}</p><progress max="100" value={pct}/></>}
        </article>;
      })}
    </div>
    {editing
      ? <div className="basic-budget-actions"><button className="finva-button finva-button-secondary" type="button" onClick={()=>{load();setEditing(false)}}>{copy("Cancelar","Cancel")}</button><button className="finva-button finva-button-primary" type="button" onClick={save} disabled={saving}>{saving?copy("Guardando...","Saving..."):copy("Guardar presupuesto","Save budget")}</button></div>
      : <button className="finva-button finva-button-primary basic-wide-action" type="button" onClick={()=>setEditing(true)}>{copy("Editar presupuesto","Edit budget")}</button>}
  </section>;
}
