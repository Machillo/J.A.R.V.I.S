import { useState } from "react";
import { ArrowRight, Check, Compass, ShieldCheck, Sparkles, Target, WalletCards } from "lucide-react";

const goals = {
  debt: "ordenar tus deudas y avanzar con un plan claro",
  save: "ahorrar para una meta importante",
  partner: "entender las finanzas de tu hogar o familia",
  life_change: "prepararte para un cambio importante",
  control: "tener más control sobre lo que entra y lo que sale",
  explore: "conocer tus números y descubrir por dónde empezar",
};

const story = (user) => [
  {
    eyebrow: "BIENVENIDO A DINCR",
    title: "Tus finanzas, organizadas automáticamente",
    copy: "DINCR te ayuda a ordenar ingresos, gastos, cuentas, deudas y metas para entender tu situación financiera.",
    Icon: Sparkles,
  },
  {
    eyebrow: "ENTENDÉ TU PRESENTE",
    title: "Todo empieza con claridad",
    copy: "Vas completando tus datos cuando los necesitás. No tenés que llenar un formulario financiero para empezar.",
    Icon: WalletCards,
  },
  {
    eyebrow: "TU MOTIVO PARA EMPEZAR",
    title: "Un espacio para tus objetivos",
    copy: `Elegiste ${goals[user?.usage_goal] || goals.explore}. DINCR organiza tu información para ayudarte a seguir ese objetivo.`,
    Icon: Target,
  },
  {
    eyebrow: "ORDENÁ SIN COMPLICARTE",
    title: "Tus decisiones toman forma",
    copy: "Podés registrar movimientos y cuentas. Si autorizás una conexión compatible, DINCR también puede ayudarte a organizar información que llegue por esa vía.",
    Icon: ShieldCheck,
  },
  {
    eyebrow: "ELEGÍ CÓMO EMPEZAR",
    title: "Tu plan, tu decisión",
    copy: "Ahora elegí Free, Basic o VIP. Cada plan tiene funciones distintas y podrás cambiarlo después desde Ajustes.",
    Icon: Compass,
  },
];

export default function DincrWelcomeStory({ user, onFinish }) {
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
    <main className="dincr-welcome-story">
      <div className="dincr-welcome-orb dincr-welcome-orb--one" />
      <div className="dincr-welcome-orb dincr-welcome-orb--two" />
      <header className="dincr-welcome-brand">
        <span><Sparkles size={16} /> DINCR</span>
        <button type="button" onClick={onFinish}>Omitir</button>
      </header>

      <section className="dincr-welcome-stage" aria-live="polite" key={step}>
        <div className="dincr-welcome-symbol"><Icon size={46} strokeWidth={1.7} /></div>
        <small>{current.eyebrow}</small>
        <h1>{current.title}</h1>
        <p>{current.copy}</p>
      </section>

      <footer className="dincr-welcome-footer">
        <div className="dincr-welcome-progress" aria-label={`Paso ${step + 1} de ${slides.length}`}>
          {slides.map((item, index) => <span className={index <= step ? "active" : ""} key={item.title} />)}
        </div>
        <button className="dincr-welcome-next" type="button" onClick={next}>
          {lastStep ? <><Check size={19} /> Elegir mi plan</> : <>Continuar <ArrowRight size={19} /></>}
        </button>
      </footer>
    </main>
  );
}
