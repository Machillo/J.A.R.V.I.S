import { useEffect, useMemo, useState } from "react";
import { CreditCard, Sparkles } from "lucide-react";
import { getAdditionalCardsReport } from "../services/jarvisApi";
import { deviceLanguage, localeTag } from "../lib/locale";
import { JarvisGlassCard, JarvisScreen } from "../products/jarvis/components/JarvisScreen";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const money = (value) => `₡${Math.round(Number(value || 0)).toLocaleString(localeTag(language))}`;

export default function AdditionalCards() {
  const [state, setState] = useState({ loading: true, data: null, error: "" });

  useEffect(() => {
    getAdditionalCardsReport()
      .then((data) => setState({ loading: false, data, error: "" }))
      .catch((error) => setState({ loading: false, data: null, error: error.message || "Error" }));
  }, []);

  const owners = useMemo(() => {
    const incoming = Array.isArray(state.data?.cards) ? state.data.cards : [];
    return incoming
      .map((group, index) => {
        const items = Array.isArray(group.items) ? group.items : [];
        return {
        owner: String(group.owner || `${tx("Titular", "Cardholder")} ${index + 1}`),
        cards: Array.isArray(group.cards) ? group.cards : [],
        items,
        count: items.length,
        total: items.reduce((sum, item) => sum + Number(item.amount || 0), 0),
      };
      })
      .sort((a, b) => b.total - a.total);
  }, [state.data]);

  const totals = useMemo(() => owners.reduce(
    (summary, owner) => ({ amount: summary.amount + owner.total, purchases: summary.purchases + owner.count }),
    { amount: 0, purchases: 0 },
  ), [owners]);

  if (state.loading) {
    return <section className="page"><div className="hud-card">{tx("Cargando tarjetas...", "Loading cards...")}</div></section>;
  }

  return (
    <JarvisScreen eyebrow={tx("Control de dinero", "Money control")} title={tx("Tarjetas adicionales", "Additional cards")} subtitle={tx("Compras agrupadas automáticamente por titular", "Purchases grouped automatically by cardholder")} className="additional-cards-screen">
      {state.error && <div className="jarvis-inline-message is-warning">{state.error}</div>}
      <JarvisGlassCard className="additional-cards-summary">
        <span>{tx("Consumo total", "Total spend")}</span><strong>{money(totals.amount)}</strong>
        <small>{totals.purchases} {tx("compras identificadas", "identified purchases")}</small>
      </JarvisGlassCard>
      <div className="additional-owner-list">
        {owners.length === 0 ? <JarvisGlassCard className="jarvis-empty-state">{tx("Aún no hay compras asociadas a tarjetas adicionales.", "No purchases are linked to additional cards yet.")}</JarvisGlassCard> : owners.map((owner) => (
          <JarvisGlassCard className="additional-owner-card" key={owner.owner}>
            <div className="additional-owner-card__header">
              <span className="additional-owner-avatar">{owner.owner.slice(0, 1).toUpperCase()}</span>
              <div><strong>{owner.owner}</strong><small>{owner.cards.length ? owner.cards.map((last4) => `•••• ${last4}`).join(" · ") : tx("Sin tarjeta identificada", "No card identified")}</small></div>
              <div className="additional-owner-card__total"><strong>{money(owner.total)}</strong><small>{owner.count} {tx("compras", "purchases")}</small></div>
            </div>
            <div className="additional-purchase-list">
              {owner.items.map((item) => (
                <div className="additional-purchase-row" key={item.id}>
                  <span className="additional-purchase-icon"><CreditCard size={15} /></span>
                  <span><strong>{item.description || tx("Compra", "Purchase")}</strong><small>{item.transaction_date}</small></span>
                  <b>{money(item.amount)}</b>
                </div>
              ))}
            </div>
          </JarvisGlassCard>
        ))}
      </div>
      <p className="additional-cards-note"><Sparkles size={13} /> {tx("JARVIS agrupa cada compra por los últimos 4 dígitos detectados.", "JARVIS groups each purchase by its detected last four digits.")}</p>
    </JarvisScreen>
  );
}
