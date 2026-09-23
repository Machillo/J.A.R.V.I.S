import { Info } from "lucide-react";
import { tx } from "../../../lib/locale";

const COPY = {
  strategy: [
    "Estimaciones y sugerencias informativas calculadas con los datos que registraste o autorizaste. No constituyen asesoría financiera, contable, legal ni tributaria. Verificá la información antes de decidir.",
    "Informational estimates and suggestions based on the data you entered or authorized. They are not financial, accounting, legal, or tax advice. Verify the information before deciding.",
  ],
  aguinaldo: [
    "Estimación informativa a partir de las órdenes patronales disponibles. No sustituye el cálculo oficial de tu patrono ni asesoría laboral o legal.",
    "Informational estimate based on the available payroll orders. It does not replace your employer's official calculation or employment or legal advice.",
  ],
};

export default function FinancialDisclaimer({ kind = "strategy" }) {
  const [es, en] = COPY[kind] || COPY.strategy;
  return <p className="finva-disclaimer" role="note"><Info size={14} aria-hidden="true"/><span>{tx(es, en)}</span></p>;
}
