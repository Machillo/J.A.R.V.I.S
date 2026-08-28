import { Crown, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { getStrategyBasic } from "../services/jarvisApi";
const money=(v)=>new Intl.NumberFormat("es-CR",{style:"currency",currency:"CRC",maximumFractionDigits:0}).format(Number(v)||0);

export default function StrategyBasic({ plan = "basic" }){
  const [d,setD]=useState(null);
  const [error,setError]=useState("");
  useEffect(()=>{getStrategyBasic().then(setD).catch((e)=>setError(e.message))},[]);
  if(error)return <div className="panel error">{error}</div>;
  if(!d)return <div className="panel">Calculando...</div>;

  const vip = plan === "vip";
  return <section className={`strategy-page plan-view-${plan}`}>
    <div className="hero">
      <span className="strategy-plan-kicker">{vip ? <><Crown size={15}/> VIP</> : <><Sparkles size={15}/> BASIC</>}</span>
      <h1>{vip ? "Dirección financiera VIP" : "Estrategia Basic"}</h1>
      <p>{vip ? "Tu vista VIP parte de reglas determinísticas y crecerá con proyecciones, escenarios y metas inteligentes." : "Recomendaciones claras basadas en reglas determinísticas, sin depender de IA generativa."}</p>
    </div>
    <div className="panel strategy">
      <h2>{d.recommendation}</h2>
      <p>Compromisos: <b>{d.commitment_ratio}%</b> de tus ingresos.</p>
      <p>Disponible estimado: <b>{money(d.available_after_commitments)}</b></p>
      <p>Prioridad actual: <b>{d.priority}</b></p>
    </div>
    {vip && <div className="vip-foundation-grid">
      <article><strong>Proyecciones</strong><span>Base preparada</span><small>Se activarán cuando implementemos el motor VIP.</small></article>
      <article><strong>Metas inteligentes</strong><span>Base preparada</span><small>Usarán tus metas y preferencias financieras.</small></article>
      <article><strong>Escenarios</strong><span>Base preparada</span><small>Compararán decisiones sin inventar recomendaciones.</small></article>
    </div>}
  </section>
}
