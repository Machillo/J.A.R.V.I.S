import { useEffect, useMemo, useState } from "react";
import { UserRound } from "lucide-react";
import { getAdditionalCardsReport } from "../services/jarvisApi";
import { deviceLanguage, localeTag } from "../lib/locale";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const money = (value) => `₡${Math.round(Number(value || 0)).toLocaleString(localeTag(language))}`;

const OWNER_ORDER = ["Emily", "Sidey"];

export default function AdditionalCards() {
  const [state, setState] = useState({ loading: true, data: null, error: "" });

  useEffect(() => {
    getAdditionalCardsReport()
      .then((data) => setState({ loading: false, data, error: "" }))
      .catch((error) => setState({ loading: false, data: null, error: error.message || "Error" }));
  }, []);

  const cards = useMemo(() => {
    const incoming = state.data?.cards || [];
    return OWNER_ORDER.map((owner) => {
      const found = incoming.find((card) => String(card.owner || "").toLowerCase() === owner.toLowerCase());
      const items = found?.items || [];
      return {
        owner,
        cards: found?.cards || [],
        items,
        count: items.length,
        total: items.reduce((sum, item) => sum + Number(item.amount || 0), 0),
      };
    });
  }, [state.data]);

  if (state.loading) {
    return <section className="page"><div className="hud-card">{tx("Cargando tarjetas...", "Loading cards...")}</div></section>;
  }

  return (
    <section className="page additional-cards-page additional-cards-clean-page">
      <div className="page-section-header">
        <div>
          <h2>{tx("Tarjetas adicionales", "Additional cards")}</h2>
        </div>
      </div>

      {state.error && <div className="alert-card">{state.error}</div>}

      <div className="cards-grid additional-owner-grid">
        {cards.map((card) => (
          <article className="hud-card additional-card additional-card-clean" key={card.owner}>
            <div className="card-owner-row">
              <UserRound size={22} />
              <div>
                <strong>{card.owner}</strong>
                <span>{card.cards.length ? card.cards.map((last4) => `****${last4}`).join(" · ") : tx("Sin tarjetas asociadas", "No linked cards")}</span>
              </div>
            </div>

            <h3>{money(card.total)}</h3>
            <p>{card.count} {tx("compras", "purchases")}</p>

            <div className="mini-transaction-list additional-full-list">
              {card.items.length === 0 ? (
                <div className="additional-empty-row"><span>Sin {tx("compras", "purchases")} aceptadas</span><b>{money(0)}</b></div>
              ) : (
                card.items.map((item) => (
                  <div key={item.id}>
                    <span>{item.transaction_date} · {item.description}</span>
                    <b>{money(item.amount)}</b>
                  </div>
                ))
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
