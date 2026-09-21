import { useEffect, useMemo, useState } from "react";
import { Sparkles, X } from "lucide-react";
import { tx } from "../../lib/locale";
import { getFinancialSituation } from "../services/jarvisApi";

const dismissedKey = (user, prompt) => `finva:profile-prompt:${user?.id || user?.email || "account"}:${prompt}`;

export default function ProgressiveProfileNudge({ user, plan, page, onNavigate }) {
  const [data, setData] = useState(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (page !== "overview") return;
    let active = true;
    getFinancialSituation().then((value) => { if (active) setData(value); }).catch(() => {});
    return () => { active = false; };
  }, [page]);

  const prompt = useMemo(() => {
    if (!data) return null;
    const profile = data.financial_profile;
    if (!profile && Number(data.observed?.income_count || 0) > 0) return "income";
    if (!profile) return "profile";
    if (plan !== "free" && profile.essential_monthly_expenses == null && Number(data.observed?.expense_count || 0) > 0) return "expenses";
    if (plan !== "free" && Number(data.debts?.missing_interest || 0) > 0) return "debt-interest";
    if (plan === "vip" && Number(data.goals?.count || 0) === 0) return "goals";
    return null;
  }, [data, plan]);

  useEffect(() => {
    setDismissed(prompt ? window.sessionStorage.getItem(dismissedKey(user, prompt)) === "1" : false);
  }, [prompt, user]);

  if (!prompt || dismissed || page !== "overview") return null;
  const content = {
    income: [tx("FINVA ya encontró ingresos reales", "FINVA already found real income"), tx("Podés usarlos como referencia y confirmar el dato, sin volver a escribir todo.", "Use them as a reference and confirm the value without entering everything again."), "situation"],
    profile: [tx("Completá solo el siguiente dato útil", "Add only the next useful detail"), tx("Tu perfil es opcional. FINVA te lo pedirá poco a poco cuando mejore una recomendación.", "Your profile is optional. FINVA will ask gradually when it improves a recommendation."), "situation"],
    expenses: [tx("Ya hay gastos para revisar", "There are expenses ready to review"), tx("FINVA calculó una referencia con tus movimientos; confirmá cuánto es realmente esencial.", "FINVA calculated a reference from your transactions; confirm how much is truly essential."), "situation"],
    "debt-interest": [tx("Una deuda necesita su tasa", "A debt needs its interest rate"), tx("Agregarla mejora el orden de pago sin pedirte de nuevo los demás datos.", "Adding it improves payoff ordering without asking for the other details again."), "debts"],
    goals: [tx("¿Qué querés lograr primero?", "What do you want to achieve first?"), tx("Una meta concreta permite que VIP ordene mejor sus recomendaciones.", "A concrete goal helps VIP prioritize recommendations."), "goals"],
  }[prompt];
  const dismiss = () => { window.sessionStorage.setItem(dismissedKey(user, prompt), "1"); setDismissed(true); };
  return <aside className="finva-profile-nudge" role="status">
    <Sparkles size={20}/><div><strong>{content[0]}</strong><span>{content[1]}</span></div>
    <button type="button" onClick={() => onNavigate(content[2])}>{tx("Revisar", "Review")}</button>
    <button className="finva-profile-nudge-close" type="button" aria-label={tx("Recordar después", "Remind me later")} onClick={dismiss}><X size={16}/></button>
  </aside>;
}
