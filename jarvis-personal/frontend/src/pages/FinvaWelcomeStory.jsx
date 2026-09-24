import { useState } from "react";
import { ArrowRight, Check, Compass, ShieldCheck, Sparkles, Target, WalletCards } from "lucide-react";
import { tx } from "../lib/locale";

const goals = {
  debt: ["ordenar tus deudas y avanzar con un plan claro", "to organize your debts and move forward with a clear plan"],
  save: ["ahorrar para una meta importante", "to save for an important goal"],
  partner: ["entender las finanzas de tu hogar o familia", "to understand your household or family finances"],
  life_change: ["prepararte para un cambio importante", "to prepare for a big change"],
  control: ["tener más control sobre lo que entra y lo que sale", "to have more control over what comes in and goes out"],
  explore: ["conocer tus números y descubrir por dónde empezar", "to know your numbers and find where to start"],
};

const story = (user) => {
  const goal = goals[user?.usage_goal] || goals.explore;
  return [
    {
      eyebrow: tx("BIENVENIDO A DINCR", "WELCOME TO DINCR"),
      title: tx("Tus finanzas, organizadas automáticamente", "Your finances, organized automatically"),
      copy: tx("DINCR te ayuda a ordenar ingresos, gastos, cuentas, deudas y metas para entender tu situación financiera.", "DINCR helps you organize income, expenses, accounts, debts, and goals so you understand your financial situation."),
      Icon: Sparkles,
    },
    {
      eyebrow: tx("ENTENDÉ TU PRESENTE", "UNDERSTAND WHERE YOU ARE"),
      title: tx("Todo empieza con claridad", "It all starts with clarity"),
      copy: tx("Vas completando tus datos cuando los necesitás. No tenés que llenar un formulario financiero para empezar.", "You add your details as you need them. You don’t have to fill out a financial form to get started."),
      Icon: WalletCards,
    },
    {
      eyebrow: tx("TU MOTIVO PARA EMPEZAR", "YOUR REASON TO START"),
      title: tx("Un espacio para tus objetivos", "A space for your goals"),
      copy: tx(`Elegiste ${goal[0]}. DINCR organiza tu información para ayudarte a seguir ese objetivo.`, `You chose ${goal[1]}. DINCR organizes your information to help you pursue that goal.`),
      Icon: Target,
    },
    {
      eyebrow: tx("ORDENÁ SIN COMPLICARTE", "GET ORGANIZED, KEEP IT SIMPLE"),
      title: tx("Tus decisiones toman forma", "Your decisions take shape"),
      copy: tx("Podés registrar movimientos y cuentas. Si autorizás una conexión compatible, DINCR también puede ayudarte a organizar información que llegue por esa vía.", "You can record transactions and accounts. If you authorize a supported connection, DINCR can also help organize the information that arrives through it."),
      Icon: ShieldCheck,
    },
    {
      eyebrow: tx("ELEGÍ CÓMO EMPEZAR", "CHOOSE HOW TO START"),
      title: tx("Tu plan, tu decisión", "Your plan, your choice"),
      copy: tx("Ahora elegí Gratis, Basic o VIP. Cada plan tiene funciones distintas y podrás cambiarlo después desde Ajustes.", "Now choose Free, Basic, or VIP. Each plan has different features, and you can change it later in Settings."),
      Icon: Compass,
    },
  ];
};

export default function FinvaWelcomeStory({ user, onFinish }) {
  const [step, setStep] = useState(0);
  const slides = story(user);
  const current = slides[step];
  const lastStep = step === slides.length - 1;
  const Icon = current.Icon;

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
        <button type="button" onClick={onFinish}>{tx("Omitir", "Skip")}</button>
      </header>

      <section className="finva-welcome-stage" aria-live="polite" key={step}>
        <div className="finva-welcome-symbol"><Icon size={46} strokeWidth={1.7} /></div>
        <small>{current.eyebrow}</small>
        <h1>{current.title}</h1>
        <p>{current.copy}</p>
      </section>

      <footer className="finva-welcome-footer">
        <div className="finva-welcome-progress" aria-label={tx(`Paso ${step + 1} de ${slides.length}`, `Step ${step + 1} of ${slides.length}`)}>
          {slides.map((item, index) => <span className={index <= step ? "active" : ""} key={item.title} />)}
        </div>
        <button className="finva-welcome-next" type="button" onClick={next}>
          {lastStep ? <><Check size={19} /> {tx("Elegir mi plan", "Choose my plan")}</> : <>{tx("Continuar", "Continue")} <ArrowRight size={19} /></>}
        </button>
      </footer>
    </main>
  );
}
