import { AlertTriangle, Crown, FlaskConical, PiggyBank, Sparkles, Target, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";
import { getStrategyBasic, getStrategyVip, simulateStrategyBasic, simulateStrategyVip } from "../services/jarvisApi";

const money=(v)=>new Intl.NumberFormat("es-CR",{style:"currency",currency:"CRC",maximumFractionDigits:0}).format(Number(v)||0);
const priorityLabel={income:"Completar ingresos",stabilize:"Estabilizar flujo",debt:"Acelerar deuda",emergency:"Construir seguridad"};

export default function StrategyBasic({ plan = "basic" }){
  const vip=plan==="vip";
  const [d,setD]=useState(null); const [error,setError]=useState("");
  const [extra,setExtra]=useState(25000); const [simulation,setSimulation]=useState(null); const [loadingSim,setLoadingSim]=useState(false);
  const [vipScenario,setVipScenario]=useState({monthly_income_change:0,monthly_expense_change:0,one_time_extra:0});
  useEffect(()=>{setSimulation(null);(vip?getStrategyVip():getStrategyBasic()).then(setD).catch((e)=>setError(e.message))},[vip]);
  if(error)return <div className="panel error">{error}</div>;
  if(!d)return <div className="panel">Calculando tu estrategia...</div>;

  const runSimulation=async()=>{setLoadingSim(true);setError("");try{setSimulation(vip?await simulateStrategyVip(Object.fromEntries(Object.entries(vipScenario).map(([k,v])=>[k,Number(v)||0]))):await simulateStrategyBasic(Number(extra)||0))}catch(e){setError(e.message)}finally{setLoadingSim(false)}};
  const allocations=vip?(d.vip_allocations||[]):(d.allocations||[]);
  const insights=d.insights||{};
  return <section className={`strategy-page plan-view-${plan}`}>
    <div className="hero"><span className="strategy-plan-kicker">{vip?<><Crown size={15}/> VIP</>:<><Sparkles size={15}/> BASIC</>}</span><h1>{vip?"Dirección financiera VIP":"Estrategia Basic"}</h1><p>{vip?"Finva coordina tus prioridades, deuda, seguridad, metas y margen personal.":"Una estrategia matemática construida con tus datos. Si falta información, Finva te lo dice en vez de inventarla."}</p></div>

    <div className={`panel strategy strategy-status-${d.status}`}><small>Prioridad actual</small><h2>{priorityLabel[d.priority]||d.priority}</h2><p>{vip?d.director_note:d.recommendation}</p></div>
    <div className="strategy-metrics"><article><small>Ingreso mensual estimado</small><strong>{money(d.monthly_income)}</strong></article><article><small>Gastos esenciales</small><strong>{money(d.essential_expenses)}</strong></article><article><small>Cuotas conocidas</small><strong>{money(d.minimum_debt_payments)}</strong></article><article><small>Margen estratégico</small><strong>{money(d.strategic_margin)}</strong></article></div>

    {vip&&<div className="vip-health-grid"><article><small>Deuda activa</small><strong>{money(insights.total_debt)}</strong></article><article><small>Metas activas</small><strong>{insights.active_goals??0}</strong></article><article><small>Reserva</small><strong>{insights.emergency_progress==null?"Sin objetivo":`${insights.emergency_progress}%`}</strong></article><article><small>Meses cubiertos</small><strong>{insights.emergency_months==null?"—":insights.emergency_months}</strong></article></div>}

    {allocations.length>0&&<div className="panel"><div className="strategy-section-title"><Target size={18}/><h3>{vip?"Plan recomendado":"Qué hacer con tu margen"}</h3></div><div className="allocation-list">{allocations.map((a,i)=><div className="allocation-row" key={`${a.bucket}-${i}`}><span>{a.label}</span><strong>{money(a.amount)}</strong></div>)}</div></div>}

    {d.next_paycheck&&<div className="panel paycheck-card"><div className="strategy-section-title"><PiggyBank size={18}/><h3>Próximo ingreso</h3></div><p>Con tu frecuencia de pago actual, Finva estima {money(d.next_paycheck.estimated_paycheck)} por pago y propone separar:</p><div className="allocation-list">{d.next_paycheck.envelopes.map((a,i)=><div className="allocation-row" key={`pay-${a.bucket}-${i}`}><span>{a.label}</span><strong>{money(a.amount)}</strong></div>)}</div>{d.next_paycheck.unassigned>0&&<small>Sin asignar: {money(d.next_paycheck.unassigned)}</small>}</div>}

    {!vip&&d.projection&&<div className="panel projection-card"><div className="strategy-section-title"><PiggyBank size={18}/><h3>Proyección de deuda</h3></div><p>Objetivo actual: <b>{d.projection.name}</b></p><p>Con el abono recomendado: <b>{d.projection.months?`${d.projection.months} meses estimados`:"necesitamos más datos"}</b>.</p>{d.projection.baseline_months&&<small>Solo con la cuota registrada serían aproximadamente {d.projection.baseline_months} meses.</small>}</div>}

    {vip&&insights.goal_guidance?.length>0&&<div className="panel"><div className="strategy-section-title"><Target size={18}/><h3>Metas inteligentes</h3></div><div className="allocation-list">{insights.goal_guidance.map(g=><div className="smart-goal-row" key={g.id}><div><strong>{g.name}</strong><small>Faltan {money(g.remaining)}</small></div><b>{g.monthly_needed==null?"Sin fecha":`${money(g.monthly_needed)}/mes`}</b></div>)}</div>}

    {!vip&&<div className="panel simulator-card"><div className="strategy-section-title"><FlaskConical size={18}/><h3>¿Qué pasa si agrego más?</h3></div><p>Probá un monto mensual adicional sin modificar tus datos.</p><div className="simulator-controls"><input type="number" min="0" step="5000" value={extra} onChange={(e)=>setExtra(e.target.value)}/><button type="button" onClick={runSimulation} disabled={loadingSim}>{loadingSim?"Calculando...":"Simular"}</button></div>{simulation&&<div className="simulation-result"><strong>Nuevo margen para estrategia: {money((simulation.strategic_margin||0)+(simulation.simulation_extra||0))}</strong>{simulation.projection?.months&&<span>{simulation.projection.name}: ~{simulation.projection.months} meses con este escenario.</span>}</div>}</div>}

    {vip&&<div className="panel simulator-card vip-scenario"><div className="strategy-section-title"><TrendingUp size={18}/><h3>Laboratorio de escenarios</h3></div><p>Probá cambios sin tocar tus datos reales. Usá números negativos para una reducción mensual.</p><div className="vip-scenario-fields"><label><span>Cambio ingreso / mes</span><input type="number" step="10000" value={vipScenario.monthly_income_change} onChange={e=>setVipScenario({...vipScenario,monthly_income_change:e.target.value})}/></label><label><span>Cambio gastos / mes</span><input type="number" step="10000" value={vipScenario.monthly_expense_change} onChange={e=>setVipScenario({...vipScenario,monthly_expense_change:e.target.value})}/></label><label><span>Dinero extraordinario</span><input type="number" min="0" step="10000" value={vipScenario.one_time_extra} onChange={e=>setVipScenario({...vipScenario,one_time_extra:e.target.value})}/></label></div><button className="scenario-button" type="button" onClick={runSimulation} disabled={loadingSim}>{loadingSim?"Calculando...":"Comparar escenario"}</button>{simulation?.scenario&&<div className="simulation-result"><strong>{simulation.delta.strategic_margin>=0?"Ganás":"Perdés"} {money(Math.abs(simulation.delta.strategic_margin))} de margen mensual</strong><span>Margen actual: {money(simulation.current.strategic_margin)} → escenario: {money(simulation.scenario.strategic_margin)}</span></div>}</div>}

    {(vip?insights.alerts:d.warnings)?.length>0&&<div className="strategy-warnings"><div className="strategy-section-title"><AlertTriangle size={18}/><h3>{vip?"Alertas del Director":"Datos que mejorarían la precisión"}</h3></div>{(vip?insights.alerts:d.warnings).map((w,i)=><p key={i}>{typeof w==="string"?w:w.message}</p>)}</div>}
  </section>;
}
