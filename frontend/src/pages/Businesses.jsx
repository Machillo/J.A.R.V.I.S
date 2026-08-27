import { useEffect, useState } from "react";
import { BriefcaseBusiness, CircleDollarSign, Plus, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";
import { createBusiness, createBusinessMovement, getBusinessCenter } from "../services/jarvisApi";
const crc=(v)=>`₡${Math.round(Number(v||0)).toLocaleString("es-CR")}`;
export default function Businesses(){
 const [data,setData]=useState(null),[error,setError]=useState(""),[showBusiness,setShowBusiness]=useState(false),[showMovement,setShowMovement]=useState(false);
 const [business,setBusiness]=useState({name:"",description:"",ownership_pct:100});
 const [movement,setMovement]=useState({business_id:"",movement_type:"income",amount:"",description:"",category:""});
 const load=async()=>{try{setError("");setData(await getBusinessCenter())}catch(e){setError(e.message||"No pude cargar negocios.")}};
 useEffect(()=>{load()},[]);
 const addBusiness=async(e)=>{e.preventDefault();await createBusiness({...business,ownership_pct:Number(business.ownership_pct||100)});setBusiness({name:"",description:"",ownership_pct:100});setShowBusiness(false);load()};
 const addMovement=async(e)=>{e.preventDefault();await createBusinessMovement({...movement,business_id:Number(movement.business_id),amount:Number(movement.amount)});setMovement({business_id:"",movement_type:"income",amount:"",description:"",category:""});setShowMovement(false);load()};
 if(!data&&!error)return <section className="business-page"><div className="hud-panel"><RefreshCw className="spin"/> Cargando negocios...</div></section>;
 const d=data||{};
 return <section className="business-page investments-page">
  <div className="investment-hero hud-panel"><div><span className="strategy-eyebrow">WEALTH · BUSINESS</span><h2>Negocios</h2><p>Medí cuánto aportás, cuánto producen tus proyectos y cuánto ingreso no laboral generan.</p></div><button className="strategy-refresh-btn" onClick={load}><RefreshCw size={17}/> Actualizar</button></div>
  {error&&<div className="hud-panel strategy-warning">{error}</div>}
  <div className="investment-kpi-grid">
   <div className="hud-card"><CircleDollarSign/><span>Ingresos</span><strong>{crc(d.income)}</strong><small>Conectados a tus ingresos generales</small></div>
   <div className="hud-card negative"><TrendingDown/><span>Gastos</span><strong>{crc(d.expenses)}</strong><small>Conectados a Spending</small></div>
   <div className={`hud-card ${Number(d.profit||0)<0?'negative':'positive'}`}><TrendingUp/><span>Ganancia</span><strong>{crc(d.profit)}</strong><small>Ingresos menos gastos</small></div>
   <div className="hud-card"><BriefcaseBusiness/><span>Capital aportado</span><strong>{crc(d.capital)}</strong><small>No se confunde con gasto</small></div>
  </div>
  <div className="business-actions"><button className="strategy-refresh-btn" onClick={()=>setShowBusiness(!showBusiness)}><Plus size={17}/> Nuevo negocio</button><button className="strategy-refresh-btn" onClick={()=>setShowMovement(!showMovement)} disabled={!d.businesses?.length}><Plus size={17}/> Registrar movimiento</button></div>
  {showBusiness&&<form className="hud-panel business-form" onSubmit={addBusiness}><h3>Nuevo negocio / proyecto</h3><input required placeholder="Nombre: JARVIS, Bot IBKR..." value={business.name} onChange={e=>setBusiness({...business,name:e.target.value})}/><input placeholder="Descripción" value={business.description} onChange={e=>setBusiness({...business,description:e.target.value})}/><label>Participación %<input type="number" min="0" max="100" step="0.01" value={business.ownership_pct} onChange={e=>setBusiness({...business,ownership_pct:e.target.value})}/></label><button className="strategy-refresh-btn" type="submit">Guardar</button></form>}
  {showMovement&&<form className="hud-panel business-form" onSubmit={addMovement}><h3>Movimiento del negocio</h3><select required value={movement.business_id} onChange={e=>setMovement({...movement,business_id:e.target.value})}><option value="">Seleccioná negocio</option>{(d.businesses||[]).map(b=><option key={b.id} value={b.id}>{b.name}</option>)}</select><select value={movement.movement_type} onChange={e=>setMovement({...movement,movement_type:e.target.value})}><option value="income">Ingreso</option><option value="expense">Gasto</option><option value="capital">Capital aportado</option></select><input required type="number" min="0.01" step="0.01" placeholder="Monto CRC" value={movement.amount} onChange={e=>setMovement({...movement,amount:e.target.value})}/><input required placeholder="Descripción" value={movement.description} onChange={e=>setMovement({...movement,description:e.target.value})}/><input placeholder="Categoría (opcional)" value={movement.category} onChange={e=>setMovement({...movement,category:e.target.value})}/><button className="strategy-refresh-btn" type="submit">Registrar</button></form>}
  <div className="hud-panel"><div className="panel-heading"><div><span className="strategy-eyebrow">PORTAFOLIO DE NEGOCIOS</span><h3>Mis negocios</h3></div></div>{!d.businesses?.length?<p className="muted-text">Todavía no hay negocios. Podés crear JARVIS, el futuro bot o una participación en otro emprendimiento.</p>:<div className="business-list">{d.businesses.map(b=>{const ms=(d.movements||[]).filter(m=>Number(m.business_id)===Number(b.id));const inc=ms.filter(m=>m.movement_type==='income').reduce((a,m)=>a+Number(m.amount),0),exp=ms.filter(m=>m.movement_type==='expense').reduce((a,m)=>a+Number(m.amount),0);return <div className="business-card" key={b.id}><div><strong>{b.name}</strong><small>{Number(b.ownership_pct||100).toFixed(0)}% participación</small></div><div><span>Ingresos {crc(inc)}</span><span>Gastos {crc(exp)}</span><b>{crc(inc-exp)}</b></div></div>})}</div>}</div>
 </section>
}
