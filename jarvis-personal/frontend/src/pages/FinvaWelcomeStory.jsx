import { useEffect, useState } from "react";
import { ArrowRight, Check, Compass, ShieldCheck, Sparkles, WalletCards } from "lucide-react";

const AUTO_ADVANCE_MS = 3500;

const story = [
  {
    eyebrow: "ENTENDÉ TU PRESENTE",
    title: "Todo empieza con claridad",
    copy: "DINCR reúne lo importante para que entendás dónde estás, sin pedirte llenar un formulario financiero al entrar.",
    Icon: WalletCards,
  },
  {
    eyebrow: "ORDENÁ SIN COMPLICARTE",
    title: "Tus decisiones toman forma",
    copy: "Ingresos, gastos, deudas y metas se convierten en una vista clara que vas completando cuando realmente la necesitás.",
    Icon: ShieldCheck,
  },
  {
    eyebrow: "AVANZÁ CON DIRECCIÓN",
    title: "Siempre sabés qué sigue",
    copy: "DINCR transforma tu información en próximos pasos concretos para recuperar control y construir tranquilidad.",
    Icon: Compass,
  },
];

export default function FinvaWelcomeStory({ onFinish }) {
  const [step, setStep] = useState(0);
  const current = story[step];
  const lastStep = step === story.length - 1;
  const Icon = current.Icon;

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (lastStep) onFinish();
      else setStep((value) => value + 1);
    }, AUTO_ADVANCE_MS);
    return () => window.clearTimeout(timer);
  }, [lastStep, onFinish, step]);

  const next = () => {
    if (lastStep) onFinish();
    else setStep((value) => value + 1);
  };

  return (
    <main className="finva-welcome-story">
      <div className="finva-welcome-orb finva-welcome-orb--one" />
      <div className="finva-welcome-orb finva-welcome-orb--two" />
      <header className="finva-welcome-brand">
        <span><Sparkles size={16} /> DINCR</span>
        <button type="button" onClick={onFinish}>Omitir</button>
      </header>

      <section className="finva-welcome-stage" aria-live="polite" key={step}>
        <div className="finva-welcome-symbol"><Icon size={46} strokeWidth={1.7} /></div>
        <small>{current.eyebrow}</small>
        <h1>{current.title}</h1>
        <p>{current.copy}</p>
      </section>

      <footer className="finva-welcome-footer">
        <div className="finva-welcome-progress" aria-label={`Paso ${step + 1} de ${story.length}`}>
          {story.map((item, index) => <span className={index <= step ? "active" : ""} key={item.title} />)}
        </div>
        <button className="finva-welcome-next" type="button" onClick={next}>
          {lastStep ? <><Check size={19} /> Elegir mi plan</> : <>Continuar <ArrowRight size={19} /></>}
        </button>
      </footer>
    </main>
  );
}
