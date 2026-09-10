import { useEffect, useState } from "react";
import {
  AlertTriangle, BarChart3, Bot, CalendarDays, CircleDollarSign, Crown,
  FileInput, Flag, Gauge, Landmark, PiggyBank, RefreshCw, Repeat2, Route,
  ShieldCheck, Sparkles, Target, TrendingUp, WalletCards,
} from "lucide-react";
import { getVipCommandCenter, simulateStrategyVip } from "../services/jarvisApi";

const money = (value) => new Intl.NumberFormat("es-CR", { style: "currency", currency: "CRC", maximumFractionDigits: 0 }).format(Number(value) || 0);
const number = (value) => new Intl.NumberFormat("es-CR", { maximumFractionDigits: 1 }).format(Number(value) || 0);
const names = { avalanche: "Avalancha", snowball: "Bola de nieve", finva: "Finva" };

function Section({ id, icon: Icon, title, subtitle, children }) {
  return <article className="vip-module" id={`vip-${id}`}><header><span><Icon size={19}/></span><div><small>VIP {String(id).padStart(2,"0")}</small><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div></header>{children}</article>;
}

function Metric({ label, value, tone="" }) {
  return <div className={`vip-metric ${tone}`}><small>{label}</small><strong>{value}</strong></div>;
}

export default function VipCenter() {
  const [data,setData]=useState(null),[error,setError]=useState(""),[loading,setLoading]=useState(true);
  const [scenario,setScenario]=useState({monthly_income_change:0,monthly_expense_change:0,one_time_extra:0});
  const [result,setResult]=useState(null),[simulating,setSimulating]=useState(false);
  const load=async()=>{setLoading(true);setError("");try{setData(await getVipCommandCenter());}catch(err){setError(err.message);}finally{setLoading(false);}};
  useEffect(()=>{load();},[]);
  const simulate=async(e)=>{e.preventDefault();setSimulating(true);setError("");try{setResult(await simulateStrategyVip(Object.fromEntries(Object.entries(scenario).map(([key,value])=>[key,Number(value)||0]))));}catch(err){setError(err.message);}finally{setSimulating(false);}};
  if(loading)return <div className="panel">Construyendo tu Dirección VIP…</div>;
  if(error&&!data)return <div className="panel error">{error}</div>;
  const score=data.score||{}, director=data.director||{}, debt=data.debt_planner||{}, report=data.reports||{}, variable=data.variable_income||{};
  return <section className="vip-center">
    <div className="hero vip-hero"><span><Crown size={15}/> FINVA VIP</span><h1>Dirección financiera</h1><p>Una sola lectura de tu dinero: qué proteger, qué pagar y qué hacer después.</p><button type="button" onClick={load}><RefreshCw size={17}/> Actualizar análisis</button></div>
    {error&&<div className="panel error">{error}</div>}

    <Section id={1} icon={Bot} title="Director Financiero proactivo" subtitle="La prioridad se calcula con tus datos; la explicación nunca cambia los números.">
      <div className="vip-director"><small>PRIORIDAD VIGENTE</small><h3>{director.headline}</h3><p>{director.next_action}</p><span className={director.data_complete?"ok":"warning"}>{director.data_complete?"Datos suficientes":"Faltan datos para máxima precisión"}</span></div>
    </Section>

    <Section id={2} icon={Gauge} title="Finva Score" subtitle="Salud financiera explicable de 0 a 100.">
      <div className="vip-score"><strong>{score.value}</strong><span>{score.label}</span><progress max="100" value={score.value||0}/></div>
      <div className="vip-factor-list">{score.factors?.map(item=><div key={item.label}><span>{item.label}</span><b className={item.impact}>{typeof item.value==="number"?number(item.value):item.value}</b></div>)}</div>
    </Section>

    <Section id={3} icon={Target} title="Metas inteligentes" subtitle="Aporte requerido, viabilidad y alternativa automática.">
      {data.goals?.length?data.goals.map(goal=><div className="vip-list-row" key={goal.id}><div><strong>{goal.name}</strong><small>{money(goal.remaining)} pendientes · {goal.months_left||"sin fecha"} meses</small></div><div><b>{goal.monthly_required?`${money(goal.monthly_required)}/mes`:"Definí fecha"}</b><span className={goal.viable?"positive":"warning"}>{goal.viable?"Viable":goal.alternative_months?`Alternativa: ${goal.alternative_months} meses`:"Sin margen"}</span></div></div>):<p className="muted-row">No hay metas activas.</p>}
    </Section>

    <Section id={4} icon={Landmark} title="Estrategia avanzada de deudas" subtitle="Comparación sin modificar tus deudas reales.">
      <div className="vip-three-grid">{debt.strategies?.map(row=><div className={debt.recommended?.method===row.method?"selected":""} key={row.method}><small>{names[row.method]}</small><strong>{row.target||"Sin deuda"}</strong><span>{row.months==null?"No amortiza":`${row.months} meses`}</span><em>{row.interest==null?"Cuota insuficiente":`${money(row.interest)} en interés`}</em></div>)}</div>
    </Section>

    <Section id={5} icon={Sparkles} title="¿Qué pasa si…?" subtitle="Sandbox: probá cambios sin alterar datos reales.">
      <form className="vip-scenario" onSubmit={simulate}><label>Ingreso mensual adicional<input type="number" value={scenario.monthly_income_change} onChange={e=>setScenario({...scenario,monthly_income_change:e.target.value})}/></label><label>Cambio en gastos<input type="number" value={scenario.monthly_expense_change} onChange={e=>setScenario({...scenario,monthly_expense_change:e.target.value})}/></label><label>Dinero único disponible<input type="number" min="0" value={scenario.one_time_extra} onChange={e=>setScenario({...scenario,one_time_extra:e.target.value})}/></label><button disabled={simulating}>{simulating?"Calculando…":"Simular"}</button></form>
      {result&&<div className="vip-simulation-result"><Metric label="Margen actual" value={money(result.current?.strategic_margin)}/><Metric label="Margen simulado" value={money(result.scenario?.strategic_margin)} tone={(result.delta?.strategic_margin||0)>=0?"positive":"negative"}/><Metric label="Cambio" value={money(result.delta?.strategic_margin)}/></div>}
    </Section>

    <Section id={6} icon={WalletCards} title="Presupuesto adaptativo" subtitle="Lo que realmente podés gastar sin tocar obligaciones ni reserva.">
      <div className="safe-spend"><small>SAFE TO SPEND</small><strong>{money(data.safe_to_spend?.amount)}</strong><p>Margen mensual: {money(data.safe_to_spend?.monthly_margin)} · punto mínimo próximos 45 días: {money(data.safe_to_spend?.next_45_days_minimum)}</p></div>
    </Section>

    <Section id={7} icon={AlertTriangle} title="Alertas inteligentes" subtitle="Solo cambios que necesitan una acción.">
      {data.alerts?.length?data.alerts.map((alert,index)=><div className={`vip-alert ${alert.severity}`} key={`${alert.title}-${index}`}><strong>{alert.title}</strong><p>{alert.context}</p><small>{alert.action}</small></div>):<div className="vip-clear"><ShieldCheck size={20}/> No hay alertas críticas con los datos actuales.</div>}
    </Section>

    <Section id={8} icon={CalendarDays} title="Calendario predictivo" subtitle="Saldo proyectado después de cada compromiso durante 45 días.">
      {data.calendar?.length?data.calendar.map((event,index)=><div className="vip-timeline" key={`${event.date}-${index}`}><time>{event.date}</time><span><strong>{event.label}</strong><small>{event.kind}</small></span><div><b className={event.kind==="income"?"positive":"negative"}>{event.kind==="income"?"+":"−"}{money(event.amount)}</b><small>queda {money(event.projected_balance)}</small></div></div>):<p className="muted-row">No hay compromisos fechados en los próximos 45 días.</p>}
    </Section>

    <Section id={9} icon={TrendingUp} title="Proyecciones financieras" subtitle="30 días, 3, 6 y 12 meses con supuestos visibles.">
      <div className="vip-projections">{data.projections?.map(row=><div key={row.months}><small>{row.months===1?"30 días":`${row.months} meses`}</small><strong>{money(row.cash)}</strong><span>Deuda {money(row.debt)}</span><em>Patrimonio {money(row.net_worth)}</em></div>)}</div>
    </Section>

    <Section id={10} icon={CircleDollarSign} title="Patrimonio neto completo">
      <div className="vip-metrics"><Metric label="Activos" value={money(data.net_worth?.assets)}/><Metric label="Pasivos" value={money(data.net_worth?.liabilities)} tone="negative"/><Metric label="Patrimonio neto" value={money(data.net_worth?.value)} tone={(data.net_worth?.value||0)>=0?"positive":"negative"}/></div>
      <small className="vip-note">{data.net_worth?.accounts?.length||0} cuentas activas incluidas.</small>
    </Section>

    <Section id={11} icon={Repeat2} title="Recurrentes y suscripciones" subtitle="Costo mensual y anual que alimenta estrategia y proyecciones.">
      <div className="vip-metrics"><Metric label="Mensual" value={money(data.recurring?.monthly_expenses)}/><Metric label="Anual" value={money(data.recurring?.annual_expenses)}/><Metric label="Patrones detectados" value={data.recurring?.detected?.length||0}/></div>
      {data.recurring?.items?.slice(0,5).map(item=><div className="vip-list-row" key={item.id}><span>{item.name}</span><b>{money(item.amount)} · {item.frequency}</b></div>)}
      {data.recurring?.detected?.slice(0,3).map(item=><div className="vip-list-row" key={item.merchant}><span>{item.merchant}</span><b>{money(item.average_amount)} promedio · {item.months_seen} meses</b></div>)}
    </Section>

    <Section id={12} icon={BarChart3} title="Reportes avanzados" subtitle="Comparativa anual preparada para exportación.">
      <div className="vip-report-bars">{report.months?.map(row=>{const max=Math.max(...report.months.map(x=>Math.max(Number(x.income)||0,Number(x.expenses)||0)),1);return <div key={row.month}><small>{row.month.slice(5)}</small><span><i style={{height:`${Math.max(Number(row.income)/max*100,2)}%`}}/><i className="expense" style={{height:`${Math.max(Number(row.expenses)/max*100,2)}%`}}/></span></div>})}</div>
      <p className="vip-note">Mes actual: {money(report.current?.income)} ingresos · {money(report.current?.expenses)} gastos.</p>
    </Section>

    <Section id={13} icon={PiggyBank} title="Motor de ingresos variables" subtitle="Decisiones con una base conservadora, no con el mejor mes.">
      <div className="vip-metrics"><Metric label="Estimado del perfil" value={money(variable.estimated)}/><Metric label="Base conservadora" value={money(variable.conservative)}/><Metric label="Variabilidad" value={`${number(variable.variability_percent)}%`}/></div>
    </Section>

    <Section id={14} icon={FileInput} title="Importación y automatización" subtitle="Correo autorizado, clasificación, deduplicación y revisión por confianza.">
      <div className="vip-metrics"><Metric label="Confirmados" value={data.automation?.confirmed||0} tone="positive"/><Metric label="Por revisar" value={data.automation?.review||0} tone="warning"/><Metric label="Duplicados evitados" value={data.automation?.duplicates||0}/></div>
    </Section>

    <Section id={15} icon={Route} title="Plan financiero dinámico" subtitle="El orden cambia cuando cambia tu realidad financiera.">
      <div className="vip-roadmap">{data.roadmap?.map(item=><div key={`${item.order}-${item.title}`}><span>{item.order}</span><section><strong>{item.title}</strong><p>{item.why}</p></section><b>{item.amount?money(item.amount):"—"}</b></div>)}</div>
      <div className="vip-assumptions"><Flag size={17}/><span>{data.assumptions?.join(" · ")}</span></div>
    </Section>
  </section>;
}
