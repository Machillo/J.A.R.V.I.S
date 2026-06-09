import { useEffect, useState } from "react";
import { CreditCard, UserRound } from "lucide-react";
import { getAdditionalCardsReport } from "../services/jarvisApi";

const money = (value) => `₡${Math.round(Number(value || 0)).toLocaleString("es-CR")}`;

export default function AdditionalCards() {
  const [state, setState] = useState({ loading: true, data: null, error: "" });

  useEffect(() => {
    getAdditionalCardsReport()
      .then((data) => setState({ loading: false, data, error: "" }))
      .catch((error) => setState({ loading: false, data: null, error: error.message || "Error" }));
  }, []);

  if (state.loading) return <section className="page"><div className="hud-card">Cargando tarjetas...</div></section>;

  const cards = state.data?.cards || [];
  const aliases = state.data?.aliases || [];

  return (
    <section className="page additional-cards-page">
      <div className="page-section-header">
        <div>
          <span className="eyebrow">Control familiar</span>
          <h2>Tarjetas adicionales</h2>
          <p>Montos reales ya aceptados desde correos. Solo muestra tarjetas adicionales: Emily y Sidey.</p>
        </div>
      </div>

      {state.error && <div className="alert-card">{state.error}</div>}

      <div className="cards-grid">
        {cards.map((card) => (
          <article className="hud-card additional-card" key={card.owner}>
            <div className="card-owner-row">
              <UserRound size={22} />
              <div><strong>{card.owner}</strong><span>{(card.cards || [card.card_last4]).map((last4) => `****${last4}`).join(" · ")}</span></div>
            </div>
            <h3>{money(card.total)}</h3>
            <p>{card.count} movimientos detectados · se muestran todos</p>
            <div className="mini-transaction-list">
              {(card.items || []).map((item) => (
                <div key={item.id}>
                  <span>{item.description}</span>
                  <b>{money(item.amount)}</b>
                </div>
              ))}
            </div>
          </article>
        ))}
      </div>

      <div className="hud-panel">
        <h3><CreditCard size={18} /> Alias configurados</h3>
        <div className="alias-list">
          {aliases.map((alias) => (
            <span key={alias.id}>{alias.owner_label} · ****{alias.card_last4} · {alias.relationship || "sin relación"}</span>
          ))}
        </div>
      </div>
    </section>
  );
}
