import { Crown, ChevronRight, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { getFinanceSummary } from "../services/jarvisApi";

const money = (value) => new Intl.NumberFormat("es-CR", { style: "currency", currency: "CRC", maximumFractionDigits: 0 }).format(Number(value) || 0);

export default function Dashboard({ user, plan = "free", onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => { getFinanceSummary().then(setData).catch((e) => setError(e.message)); }, []);
  if (error) return <div className="panel error">{error}</div>;
  if (!data) return <div className="panel">Cargando resumen...</div>;

  return (
    <section className={`dashboard-plan dashboard-${plan}`}>
      <div className="hero"><span>Hola {user?.display_name || ""}</span><h1>{plan === "vip" ? "Tu panorama financiero" : "Tu resumen financiero"}</h1><p>{data.month}</p></div>
      <div className="kpis">
        <div className="card"><small>Ingresos</small><strong>{money(data.income)}</strong></div>
        <div className="card"><small>Gastos</small><strong>{money(data.expenses)}</strong></div>
        <div className="card"><small>Deuda pendiente</small><strong>{money(data.debt_balance)}</strong></div>
        <div className="card"><small>Disponible estimado</small><strong>{money(data.available_after_commitments)}</strong></div>
      </div>

      {plan === "free" && <button className="dashboard-plan-action free" type="button" onClick={() => onNavigate?.("situation")}>
        <span><strong>Completá tu base financiera</strong><small>Gratis organiza tus datos sin mostrar módulos de estrategia.</small></span><ChevronRight size={20}/>
      </button>}
      {plan === "basic" && <button className="dashboard-plan-action basic" type="button" onClick={() => onNavigate?.("strategy")}>
        <Sparkles size={21}/><span><strong>Ver estrategia Basic</strong><small>Priorización y recomendaciones determinísticas.</small></span><ChevronRight size={20}/>
      </button>}
      {plan === "vip" && <button className="dashboard-plan-action vip" type="button" onClick={() => onNavigate?.("strategy")}>
        <Crown size={21}/><span><strong>Abrir Dirección VIP</strong><small>Tu experiencia VIP incluye la base Basic y prepara funciones avanzadas.</small></span><ChevronRight size={20}/>
      </button>}
    </section>
  );
}
