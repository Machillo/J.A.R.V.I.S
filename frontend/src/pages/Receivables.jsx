import { useEffect, useState } from "react";
import { getReceivables } from "../services/jarvisApi";
import { ReceivablesPanel } from "./Finance";

export default function Receivables({ onRefresh }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true); setError("");
    try { setData(await getReceivables()); }
    catch (err) { setError(err.message || "Could not load receivables."); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  if (loading) return <section className="dashboard-page"><div className="empty-state full-width"><div className="jarvis-loader"></div><h3>Loading receivables...</h3></div></section>;
  if (error) return <section className="dashboard-page"><div className="empty-state full-width danger"><h3>Receivables unavailable</h3><p>{error}</p><button className="hud-action-button" onClick={load}>Retry</button></div></section>;

  return <section className="dashboard-page receivables-page"><ReceivablesPanel data={data} onPaymentSaved={async () => { await load(); await onRefresh?.(); }} /></section>;
}
