import { useEffect, useMemo, useState } from "react";
import { CreditCard, HandCoins, MailSearch, ReceiptText, ShieldCheck } from "lucide-react";
import {
  getAdditionalCardsReport,
  getEmailMonitorStatus,
  getReceivables,
  getTransactions,
} from "../../../services/jarvisApi";
import { localeTag } from "../../../lib/locale";
import { JarvisGlassCard, JarvisMenuRow, JarvisScreen } from "../components/JarvisScreen";

const money = (value) => new Intl.NumberFormat(localeTag(), {
  style: "currency",
  currency: "CRC",
  maximumFractionDigits: 0,
}).format(Number(value) || 0);

const initialState = {
  loading: true,
  receivables: [],
  transactions: [],
  email: null,
  cards: null,
};

export default function MoneyControl({ onNavigate }) {
  const [state, setState] = useState(initialState);

  useEffect(() => {
    let active = true;
    Promise.allSettled([
      getReceivables(),
      getTransactions(),
      getEmailMonitorStatus(),
      getAdditionalCardsReport(),
    ]).then(([receivables, transactions, email, cards]) => {
      if (!active) return;
      setState({
        loading: false,
        receivables: receivables.status === "fulfilled" ? receivables.value : [],
        transactions: transactions.status === "fulfilled" ? transactions.value : [],
        email: email.status === "fulfilled" ? email.value : null,
        cards: cards.status === "fulfilled" ? cards.value : null,
      });
    });
    return () => { active = false; };
  }, []);

  const summary = useMemo(() => {
    const receivables = Array.isArray(state.receivables)
      ? state.receivables
      : state.receivables?.items || [];
    const pendingReceivables = receivables.reduce(
      (total, item) => total + Number(item.current_amount_due ?? item.pending_amount ?? 0),
      0,
    );
    const transactions = Array.isArray(state.transactions)
      ? state.transactions
      : state.transactions?.items || [];
    const cardGroups = state.cards?.cards || [];
    const cardTotal = cardGroups.reduce(
      (total, group) => total + (group.items || []).reduce((sum, item) => sum + Number(item.amount || 0), 0),
      0,
    );
    const cardOwners = cardGroups.map((group) => group.owner).filter(Boolean).join(" · ");
    const pendingEmails = Number(state.email?.totals?.pending ?? state.email?.pending ?? 0);

    return { receivables, pendingReceivables, transactions, cardTotal, cardOwners, pendingEmails };
  }, [state]);

  const pendingPeople = summary.receivables.filter(
    (item) => Number(item.current_amount_due ?? item.pending_amount ?? 0) > 0,
  ).length;

  return (
    <JarvisScreen
      eyebrow="Más"
      title="Control de dinero"
      subtitle="Tus herramientas y datos financieros"
      className="money-control-screen"
    >
      <JarvisGlassCard className="money-control-hero">
        <span>Centro financiero</span>
        <h3>Todo bajo control</h3>
        <p>Revisá movimientos, correos y saldos pendientes desde un solo lugar.</p>
        <ShieldCheck size={26} aria-hidden="true" />
      </JarvisGlassCard>

      <div className="money-control-list" aria-busy={state.loading}>
        <JarvisMenuRow
          icon={HandCoins}
          title="Cuentas por cobrar"
          detail={state.loading ? "Consultando saldos…" : `${money(summary.pendingReceivables)} pendientes`}
          meta={state.loading ? "" : `${pendingPeople} ${pendingPeople === 1 ? "persona" : "personas"}`}
          onClick={() => onNavigate("receivables")}
        />
        <JarvisMenuRow
          icon={ReceiptText}
          title="Historial"
          detail={state.loading ? "Consultando movimientos…" : `${summary.transactions.length.toLocaleString("es-CR")} movimientos`}
          meta="Buscar y analizar"
          onClick={() => onNavigate("transactions")}
        />
        <JarvisMenuRow
          icon={MailSearch}
          title="Email Monitor"
          detail={state.loading ? "Consultando Gmail…" : `${summary.pendingEmails} por revisar`}
          meta={state.email?.gmail_ready ? "Gmail conectado" : "Configurar Gmail"}
          onClick={() => onNavigate("emails")}
        />
        <JarvisMenuRow
          icon={CreditCard}
          title="Tarjetas adicionales"
          detail={state.loading ? "Consultando compras…" : `${money(summary.cardTotal)} este mes`}
          meta={summary.cardOwners || "Ver tarjetas"}
          onClick={() => onNavigate("additionalCards")}
        />
      </div>

      <p className="money-control-footnote">JARVIS sincroniza estos datos con Finanzas</p>
    </JarvisScreen>
  );
}
