import { AlertTriangle, Crown, FlaskConical, PiggyBank, Sparkles, Target } from "lucide-react";
import { useEffect, useState } from "react";
import { getStrategyBasic, getStrategyVip, simulateStrategyBasic } from "../services/jarvisApi";

const money=(v)=>new Intl.NumberFormat("es-CR",{style:"currency",currency:"CRC",maximumFractionDigits:0}).format(Number(v)||0);
const priorityLabel={income:"Completar ingresos",stabilize:"Estabilizar flujo",debt:"Acelerar deuda",emergency:"Construir seguridad"};

export default function StrategyBasic({ plan = "basic" }){
  const vip=plan==="vip";
  const [d,setD]=useState(null); const [error,setError]=useState("");
  const [extra,setExtra]=useState(25000); const [simulation,setSimulation]=useState(null); const [loadingSim,setLoadingSim]=useState(false);
  useEffect(()=>{(vip?getStrategyVip():getStrategyBasic()).then(setD).catch((e)=>setError(e.message))},[vip]);
  if(error)return <div className="panel error">{error}</div>;
  if(!d)return <div className="panel">Calculando tu estrategia...</div>;

  const runSimulation=async()=>{setLoadingSim(true);setError("");try{setSimulation(await simulateStrategyBasic(Number(extra)||0))}catch(e){setError(e.message)}finally{setLoadingSim(false)}};
  const allocations=vip?(d.vip_allocations||[]):(d.allocations||[]);
  return <section className={`strategy-page plan-view-${plan}`}>
    <div className="hero">
      <span className="strategy-plan-kicker">{vip?<><Crown size={15}/> VIP</>:<><Sparkles size={15}/> BASIC</>}</span>
      <h1>{vip?"Dirección financiera VIP":"Estrategia Basic"}</h1>
      <p>{vip?"JARVIS coordina tus prioridades, deuda, seguridad, metas y margen personal.":"Una estrategia matemática construida con tus datos. Si falta información, JARVIS te lo dice en vez de inventarla."}</p>
    </div>

    <div className={`panel strategy strategy-status-${d.status}`}>
      <small>Prioridad actual</small><h2>{priorityLabel[d.priority]||d.priority}</h2><p>{vip?d.director_note:d.recommendation}</p>
    </div>

    <div className="strategy-metrics">
      <article><small>Ingreso mensual estimado</small><strong>{money(d.monthly_income)}</strong></article>
      <article><small>Gastos esenciales</small><strong>{money(d.essential_expenses)}</strong></article>
      <article><small>Cuotas conocidas</small><strong>{money(d.minimum_debt_payments)}</strong></article>
      <article><small>Margen estratégico</small><strong>{money(d.strategic_margin)}</strong></article>
    </div>

    {allocations.length>0&&<div className="panel"><div className="strategy-section-title"><Target size={18}/><h3>{vip?"Plan recomendado":"Qué hacer con tu margen"}</h3></div><div className="allocation-list">{allocations.map((a,i)=><div className="allocation-row" key={`${a.bucket}-${i}`}><span>{a.label}</span><strong>{money(a.amount)}</strong></div>)}</div></div>}

    {!vip&&d.projection&&<div className="panel projection-card"><div className="strategy-section-title"><PiggyBank size={18}/><h3>Proyección de deuda</h3></div><p>Objetivo actual: <b>{d.projection.name}</b></p><p>Con el abono recomendado: <b>{d.projection.months?`${d.projection.months} meses estimados`:"necesitamos más datos"}</b>.</p>{d.projection.baseline_months&&<small>Solo con la cuota registrada serían aproximadamente {d.projection.baseline_months} meses.</small>}</div>}

    {!vip&&<div className="panel simulator-card"><div className="strategy-section-title"><FlaskConical size={18}/><h3>¿Qué pasa si agrego más?</h3></div><p>Probá un monto mensual adicional sin modificar tus datos.</p><div className="simulator-controls"><input type="number" min="0" step="5000" value={extra} onChange={(e)=>setExtra(e.target.value)}/><button type="button" onClick={runSimulation} disabled={loadingSim}>{loadingSim?"Calculando...":"Simular"}</button></div>{simulation&&<div className="simulation-result"><strong>Nuevo margen para estrategia: {money((simulation.strategic_margin||0)+(simulation.simulation_extra||0))}</strong>{simulation.projection?.months&&<span>{simulation.projection.name}: ~{simulation.projection.months} meses con este escenario.</span>}</div>}</div>}

    {d.warnings?.length>0&&<div className="strategy-warnings"><div className="strategy-section-title"><AlertTriangle size={18}/><h3>Datos que mejorarían la precisión</h3></div>{d.warnings.map((w,i)=><p key={i}>{w}</p>)}</div>}

    {vip&&<div className="vip-foundation-grid"><article><strong>Prioridad elegida</strong><span>{d.strategy_preference||"balanced"}</span><small>La distribución cambia de forma determinística según esta preferencia.</small></article><article><strong>Metas coordinadas</strong><span>Activas</span><small>Las metas compiten por el margen junto con deuda y emergencia.</small></article><article><strong>Escenarios</strong><span>Siguiente profundidad</span><small>La base matemática ya está separada de la presentación.</small></article></div>}
  </section>;
}
