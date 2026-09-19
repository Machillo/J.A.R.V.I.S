import { useEffect, useState } from "react";
import { ArrowRight, ShieldCheck, Sparkles } from "lucide-react";
import { getBudget, getFinancialSituation, getVipCommandCenter, simulateStrategyVip, updateFinancialSituation } from "../services/jarvisApi";
import { deviceLanguage, localeTag } from "../../lib/locale";

const language=deviceLanguage();
const tx=(es,en)=>language==="es"?es:en;
const money=(v)=>new Intl.NumberFormat(localeTag(language),{style:"currency",currency:"CRC",maximumFractionDigits:0}).format(Number(v)||0);
const pct=(v)=>`${Math.round(Number(v)||0)}%`;

function Loading(){return <div className="panel">{tx("Construyendo tu estrategia VIP…","Building your VIP strategy…")}</div>}
function VipHero({eyebrow,title,subtitle}){return <div className="vip-figma-heading"><span>{eyebrow||"FINVA · VIP"}</span><h1>{title}</h1>{subtitle&&<p>{subtitle}</p>}</div>}
function Row({label,value,tone=""}){return <div className="vip-figma-row"><span>{label}</span><strong className={tone}>{value}</strong></div>}

export default function VipExperience({view="dashboard",onNavigate}){
  const [data,setData]=useState(null),[profile,setProfile]=useState(null),[budget,setBudget]=useState(null),[error,setError]=useState("");
  const load=()=>{setError("");Promise.all([getVipCommandCenter(),getFinancialSituation(),getBudget()]).then(([vip,situation,budgetData])=>{setData(vip);setProfile(situation?.financial_profile || {});setBudget(budgetData)}).catch(e=>setError(e.message))};
  useEffect(load,[]);
  if(error&&!data)return <div className="panel error">{error}</div>;
  if(!data||!profile)return <Loading/>;
  const props={data,profile,budget,onNavigate,reload:load};
  if(view==="strategy")return <VipStrategyView {...props}/>;
  if(view==="recommendation")return <VipRecommendation {...props}/>;
  if(view==="projections")return <VipProjections {...props}/>;
  if(view==="scenarios")return <VipScenarios {...props}/>;
  if(view==="reality")return <VipReality {...props}/>;
  if(view==="emergency")return <VipEmergency {...props}/>;
  if(view==="preferences")return <VipPreferences {...props}/>;
  return <VipDashboard {...props}/>;
}

function VipDashboard({data,onNavigate}){
  const roadmap=data.roadmap||[], projection=data.projections?.find(x=>x.months===6)||data.projections?.[0];
  return <section className="finva-vip-screen">
    <VipHero title={tx("Tu estrategia hoy","Your strategy today")} subtitle={tx("FINVA coordina deuda, seguridad, metas y dinero libre.","FINVA coordinates debt, safety, goals, and free cash.")}/>
    <article className="vip-figma-focus"><small>{tx("DISPONIBLE ESTRATÉGICO","STRATEGIC AVAILABLE")}</small><strong>{money(data.safe_to_spend?.amount)}</strong><span>{tx(`FINVA encontró ${Math.min(roadmap.length,3)} acciones para este mes`,`FINVA found ${Math.min(roadmap.length,3)} actions for this month`)}</span></article>
    <article className="vip-figma-card"><h3>{tx("Prioridad recomendada","Recommended priority")}</h3>{roadmap.slice(0,3).map((item,index)=><Row key={item.title} label={item.title} value={item.amount?money(item.amount):"—"} tone={index===0?"violet":index===1?"mint":"gold"}/>)}</article>
    <article className="vip-figma-card"><h3>{tx("Si seguís este plan","If you follow this plan")}</h3><Row label={tx("Patrimonio estimado · 6 meses","Estimated net worth · 6 months")} value={projection?money(projection.net_worth):"—"} tone="mint"/><Row label={tx("Deuda estimada","Estimated debt")} value={projection?money(projection.debt):"—"}/></article>
    <article className="vip-figma-card"><h3>{tx("Plan vs realidad","Plan vs reality")}</h3><p className="vip-figma-positive">{data.reports?.current?.balance>=0?tx("El mes mantiene balance positivo con los datos actuales.","The month remains positive with current data."):tx("El mes requiere un ajuste para volver al plan.","The month needs an adjustment to return to plan.")}</p><button onClick={()=>onNavigate?.("vip-reality")}>{tx("Ver detalle","View details")} <ArrowRight size={15}/></button></article>
  </section>
}

function VipStrategyView({data,onNavigate}){
  const rows=data.roadmap||[];
  return <section className="finva-vip-screen"><VipHero title={tx("Estrategia dinámica","Dynamic strategy")} subtitle={tx("FINVA reajusta el orden cuando cambia tu realidad.","FINVA readjusts the order when your reality changes.")}/>
    <article className="vip-figma-focus"><small>{tx("PRIORIDAD ACTUAL","CURRENT PRIORITY")}</small><strong className="vip-title-small">{data.director?.headline}</strong><span>{data.director?.next_action}</span></article>
    <div className="vip-figma-stack">{rows.slice(0,4).map((item,index)=><article className="vip-figma-order" key={item.title}><header><strong>{index+1} · {item.title}</strong><b>{item.amount?money(item.amount):"—"}</b></header><p>{item.why}</p></article>)}</div>
    <button className="vip-figma-primary" onClick={()=>onNavigate?.("vip-recommendation")}>{tx("Ver recomendación","View recommendation")}</button>
  </section>
}

function VipRecommendation({data,onNavigate}){
  const action=data.roadmap?.find(x=>x.amount>0)||data.roadmap?.[0];
  const debt=data.debt_planner?.recommended;
  return <section className="finva-vip-screen"><VipHero title={action?.title||tx("Recomendación","Recommendation")}/>
    <article className="vip-figma-focus"><small>{tx("ACCIÓN RECOMENDADA","RECOMMENDED ACTION")}</small><strong className="vip-title-small">{action?.amount?money(action.amount):"—"}</strong><span>{action?.why}</span></article>
    <article className="vip-figma-card"><h3>{tx("Por qué","Why")}</h3><p>{action?.why||tx("La recomendación usa únicamente los datos financieros conocidos.","The recommendation only uses known financial data.")}</p></article>
    {debt&&<article className="vip-figma-card"><h3>{tx("Impacto estimado","Estimated impact")}</h3><Row label={tx("Deuda objetivo","Target debt")} value={debt.target||"—"} tone="violet"/><Row label={tx("Tiempo estimado","Estimated time")} value={debt.months==null?"—":`${debt.months} ${tx("meses","months")}`}/><Row label={tx("Interés estimado","Estimated interest")} value={debt.interest==null?"—":money(debt.interest)} tone="mint"/></article>}
    <button className="vip-figma-primary" onClick={()=>onNavigate?.("vip-scenarios")}>{tx("Simular antes de hacerlo","Simulate before doing it")}</button>
  </section>
}

function VipProjections({data,onNavigate}){
  const max=Math.max(...(data.projections||[]).map(x=>Math.abs(Number(x.net_worth)||0)),1);
  return <section className="finva-vip-screen"><VipHero title={tx("Proyecciones","Projections")} subtitle={tx("Estimaciones basadas en tus datos actuales; cambian cuando cambian tus números.","Estimates based on current data; they change when your numbers change.")}/>
    <article className="vip-figma-focus"><small>{tx("PRÓXIMOS 12 MESES","NEXT 12 MONTHS")}</small><strong className="vip-title-small">{tx("Así podría evolucionar tu dinero","How your money could evolve")}</strong></article>
    <article className="vip-figma-card"><h3>{tx("Patrimonio proyectado","Projected net worth")}</h3><div className="vip-projection-bars">{(data.projections||[]).map(row=><div key={row.months}><i style={{height:`${Math.max(Math.abs(Number(row.net_worth))/max*100,8)}%`}}/><small>{row.months===1?"30d":`${row.months}m`}</small></div>)}</div></article>
    {(data.projections||[]).map(row=><article className="vip-figma-card" key={row.months}><Row label={row.months===1?tx("30 días","30 days"):`${row.months} ${tx("meses","months")}`} value={money(row.net_worth)} tone="violet"/><Row label={tx("Efectivo","Cash")} value={money(row.cash)} tone="mint"/><Row label={tx("Deuda","Debt")} value={money(row.debt)}/></article>)}
    <button className="vip-figma-primary" onClick={()=>onNavigate?.("vip-scenarios")}>{tx("Crear escenario","Create scenario")}</button>
  </section>
}

function VipScenarios(){
  const [form,setForm]=useState({monthly_income_change:0,monthly_expense_change:0,one_time_extra:0}),[result,setResult]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const run=async(e)=>{e.preventDefault();setBusy(true);setError("");try{setResult(await simulateStrategyVip(Object.fromEntries(Object.entries(form).map(([k,v])=>[k,Number(v)||0]))))}catch(err){setError(err.message)}finally{setBusy(false)}};
  return <section className="finva-vip-screen"><VipHero title={tx("Escenarios","Scenarios")} subtitle={tx("Probá decisiones sin cambiar tus datos reales.","Try decisions without changing your real data.")}/>
    <article className="vip-figma-focus"><small>{tx("SIMULACIÓN","SIMULATION")}</small><strong className="vip-title-small">{tx("¿Qué pasaría si...?","What if...?")}</strong><span>{tx("Los escenarios nunca modifican tu plan real.","Scenarios never modify your real plan.")}</span></article>
    <form className="vip-scenario-builder" onSubmit={run}><label>{tx("Ingreso mensual adicional","Additional monthly income")}<input type="number" value={form.monthly_income_change} onChange={e=>setForm({...form,monthly_income_change:e.target.value})}/></label><label>{tx("Cambio en gastos","Change in expenses")}<input type="number" value={form.monthly_expense_change} onChange={e=>setForm({...form,monthly_expense_change:e.target.value})}/></label><label>{tx("Dinero único disponible","One-time money available")}<input type="number" min="0" value={form.one_time_extra} onChange={e=>setForm({...form,one_time_extra:e.target.value})}/></label><button className="vip-figma-primary" disabled={busy}>{busy?tx("Calculando…","Calculating…"):tx("Calcular escenario","Calculate scenario")}</button></form>
    {error&&<div className="panel error">{error}</div>}
    {result&&<article className="vip-figma-compare"><h3>{tx("Comparar escenario","Compare scenario")}</h3><div><section><small>{tx("Plan actual","Current plan")}</small><strong>{money(result.current?.strategic_margin)}</strong></section><section><small>{tx("Escenario VIP","VIP scenario")}</small><strong>{money(result.scenario?.strategic_margin)}</strong></section></div><p className={Number(result.delta?.strategic_margin)>=0?"vip-figma-positive":"vip-figma-negative"}>{tx("Cambio mensual","Monthly change")}: {money(result.delta?.strategic_margin)}</p></article>}
  </section>
}

function VipReality({data,budget}){
  const current=data.reports?.current||{}, previous=data.reports?.previous||{};
  const spent=(budget?.items||[]).reduce((s,x)=>s+Number(x.spent||0),0), planned=(budget?.items||[]).reduce((s,x)=>s+Number(x.monthly_limit||0),0);
  const delta=planned-spent;
  return <section className="finva-vip-screen"><VipHero title={tx("Plan vs realidad","Plan vs reality")} subtitle={tx("Lo planeado frente a lo que realmente ocurrió este mes.","What you planned versus what actually happened this month.")}/>
    <article className="vip-figma-focus"><small>{tx("ESTE MES","THIS MONTH")}</small><strong className="vip-title-small">{delta>=0?tx(`${money(delta)} mejor que el límite`,`${money(delta)} under the limit`):tx(`${money(Math.abs(delta))} sobre el límite`,`${money(Math.abs(delta))} over the limit`)}</strong></article>
    <article className="vip-figma-card"><Row label={tx("Presupuesto","Budget")} value={money(planned)}/><Row label={tx("Gasto real","Actual spending")} value={money(spent)} tone={delta>=0?"mint":"coral"}/><Row label={tx("Balance financiero","Financial balance")} value={money(current.balance)} tone={Number(current.balance)>=0?"mint":"coral"}/><Row label={tx("Balance mes anterior","Previous month balance")} value={money(previous.balance)}/></article>
  </section>
}

function VipEmergency({profile}){
  const saved=Number(profile.liquid_savings)||0,target=Number(profile.emergency_fund_target)||0,progress=target?Math.min(saved/target*100,100):0,essential=Number(profile.essential_monthly_expenses)||0,months=essential?saved/essential:0;
  return <section className="finva-vip-screen"><VipHero title={tx("Fondo de emergencia","Emergency fund")}/>
    <article className="vip-figma-focus"><small>{tx("PROTECCIÓN FINANCIERA","FINANCIAL PROTECTION")}</small><strong>{pct(progress)}</strong><span>{money(saved)} {tx("de","of")} {money(target)}</span><progress max="100" value={progress}/></article>
    <article className="vip-figma-card"><Row label={tx("Cobertura actual","Current coverage")} value={`${months.toFixed(1)} ${tx("meses","months")}`} tone="gold"/><Row label={tx("Falta para el objetivo","Remaining to target")} value={money(Math.max(target-saved,0))}/></article>
    <article className="vip-figma-note"><ShieldCheck size={18}/><span>{tx("FINVA protege primero tus obligaciones conocidas antes de sugerir dinero para otras prioridades.","FINVA protects known obligations before suggesting money for other priorities.")}</span></article>
  </section>
}

function VipPreferences({profile,reload}){
  const [form,setForm]=useState(()=>({...profile})),[saving,setSaving]=useState(false),[message,setMessage]=useState("");
  const save=async(e)=>{e.preventDefault();setSaving(true);setMessage("");try{await updateFinancialSituation({...form,essential_monthly_expenses:Number(form.essential_monthly_expenses)||0,liquid_savings:Number(form.liquid_savings)||0,emergency_fund_target:Number(form.emergency_fund_target)||0,discretionary_monthly_minimum:Number(form.discretionary_monthly_minimum)||0,fixed_monthly_salary:form.fixed_monthly_salary?Number(form.fixed_monthly_salary):null,hourly_rate:form.hourly_rate?Number(form.hourly_rate):null,hours_per_day:form.hours_per_day?Number(form.hours_per_day):null,work_days_per_week:Number(form.work_days_per_week)||5});setMessage(tx("Preferencias guardadas.","Preferences saved."));reload()}catch(err){setMessage(err.message)}finally{setSaving(false)}};
  return <section className="finva-vip-screen"><VipHero title={tx("Preferencias estratégicas","Strategic preferences")} subtitle={tx("Estas reglas orientan la estrategia; podés cambiarlas cuando tu vida cambie.","These rules guide the strategy; change them when your life changes.")}/>
    <form className="vip-preferences" onSubmit={save}><label>{tx("Prioridad estratégica","Strategic priority")}<select value={form.strategy_preference||"balanced"} onChange={e=>setForm({...form,strategy_preference:e.target.value})}><option value="balanced">{tx("Equilibrado","Balanced")}</option><option value="debt">{tx("Deuda","Debt")}</option><option value="emergency">{tx("Emergencia","Emergency")}</option><option value="goals">{tx("Metas","Goals")}</option></select></label><label>{tx("Fondo de emergencia objetivo","Emergency fund target")}<input type="number" min="0" value={form.emergency_fund_target||0} onChange={e=>setForm({...form,emergency_fund_target:e.target.value})}/></label><label>{tx("Dinero mínimo para tus gustos","Minimum discretionary money")}<input type="number" min="0" value={form.discretionary_monthly_minimum||0} onChange={e=>setForm({...form,discretionary_monthly_minimum:e.target.value})}/></label><article className="vip-figma-note"><Sparkles size={18}/><span>{tx("FINVA usa estas reglas para ordenar deuda, seguridad, metas y margen personal.","FINVA uses these rules to order debt, safety, goals, and personal margin.")}</span></article>{message&&<p className="vip-preference-message">{message}</p>}<button className="vip-figma-primary" disabled={saving}>{saving?tx("Guardando…","Saving…"):tx("Guardar preferencias","Save preferences")}</button></form>
  </section>
}
