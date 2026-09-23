import { useMemo, useState } from "react";
import { Capacitor } from "@capacitor/core";
import {
  ArrowLeft,
  Banknote,
  Check,
  ChevronRight,
  HeartHandshake,
  LifeBuoy,
  PiggyBank,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  WalletCards,
} from "lucide-react";
import { completeProfileSetup } from "../services/jarvisApi";
import { deviceLanguage } from "../lib/locale";
import bacLogo from "../assets/institutions/bac.svg";
import multimoneyLogo from "../assets/institutions/multimoney.svg";
import popularLogo from "../assets/institutions/popular.svg";
import promericaLogo from "../assets/institutions/promerica.png";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const GOALS = [
  { id: "debt", icon: WalletCards, label: tx("Salir de deudas", "Pay off debt"), detail: tx("Ordenar pagos y avanzar con un plan claro.", "Organize payments and move forward with a clear plan.") },
  { id: "save", icon: PiggyBank, label: tx("Ahorrar para algo importante", "Save for something important"), detail: tx("Convertir una meta en aportes alcanzables.", "Turn a goal into achievable contributions.") },
  { id: "partner", icon: HeartHandshake, label: tx("Organizar dinero en pareja o familia", "Manage money with a partner or family"), detail: tx("Entender juntos qué entra, qué sale y qué sigue.", "Understand together what comes in, what goes out, and what comes next.") },
  { id: "life_change", icon: Sparkles, label: tx("Prepararme para un cambio importante", "Prepare for an important change"), detail: tx("Planear una mudanza, viaje, estudio u otra etapa.", "Plan a move, trip, education, or another life stage.") },
  { id: "control", icon: Target, label: tx("Tomar control de mis finanzas", "Take control of my finances"), detail: tx("Ver mis números con claridad y tomar mejores decisiones.", "See my numbers clearly and make better decisions.") },
  { id: "explore", icon: LifeBuoy, label: tx("Todavía no estoy seguro", "I’m not sure yet"), detail: tx("Explorar la app y descubrir por dónde empezar.", "Explore the app and discover where to begin.") },
];

const CURRENCIES = [
  { code: "CRC", name: tx("Colón costarricense", "Costa Rican colón"), symbol: "₡", flag: "🇨🇷" },
  { code: "USD", name: tx("Dólar estadounidense", "US dollar"), symbol: "$", flag: "🇺🇸" },
  { code: "ARS", name: tx("Peso argentino", "Argentine peso"), symbol: "$", flag: "🇦🇷" },
  { code: "EUR", name: "Euro", symbol: "€", flag: "🇪🇺" },
  { code: "MXN", name: tx("Peso mexicano", "Mexican peso"), symbol: "$", flag: "🇲🇽" },
  { code: "COP", name: tx("Peso colombiano", "Colombian peso"), symbol: "$", flag: "🇨🇴" },
  { code: "GTQ", name: tx("Quetzal guatemalteco", "Guatemalan quetzal"), symbol: "Q", flag: "🇬🇹" },
  { code: "PAB", name: tx("Balboa panameño", "Panamanian balboa"), symbol: "B/.", flag: "🇵🇦" },
];

const BANKS = [
  { id: "bac", name: "BAC Credomatic", short: "BAC", tone: "red", logo: bacLogo, supported: true },
  { id: "bn", name: "Banco Nacional", short: "BN", tone: "blue" },
  { id: "bcr", name: "Banco de Costa Rica", short: "BCR", tone: "navy" },
  { id: "popular", name: "Banco Popular", short: "BP", tone: "orange", logo: popularLogo },
  { id: "davivienda", name: "Davivienda", short: "DAV", tone: "yellow" },
  { id: "scotiabank", name: "Scotiabank", short: "S", tone: "red" },
  { id: "promerica", name: "Promerica", short: "PRO", tone: "green", logo: promericaLogo },
  { id: "multimoney", name: "MultiMoney", short: "MM", tone: "violet", logo: multimoneyLogo, supported: true },
];

const firstName = (user) => {
  const source = user?.display_name || user?.user_metadata?.full_name || user?.email?.split("@")[0] || "";
  return source.trim().split(/\s+/)[0] || "";
};

function BrandArt({ isJarvis }) {
  const product = "DINCR";
  return (
    <div className="profile-setup-art" aria-hidden="true">
      <span className="profile-setup-orbit orbit-one" />
      <span className="profile-setup-orbit orbit-two" />
      <span className="profile-setup-art-card art-card-one"><Banknote /></span>
      <span className="profile-setup-art-card art-card-two"><PiggyBank /></span>
      <span className="profile-setup-art-core">D</span>
      <div className="profile-setup-art-copy">
        <strong>{product}</strong>
        <span>{isJarvis
          ? tx("Tu inteligencia financiera, desde el inicio", "Your financial intelligence, from the start")
          : tx("Tu experiencia empieza con vos", "Your experience starts with you")}
        </span>
      </div>
    </div>
  );
}

export default function ProfileSetup({ user, onComplete }) {
  const isJarvis = user?.role === "owner" || user?.role === "admin";
  const product = "DINCR";
  const platform = Capacitor.getPlatform();
  const initialCurrency = user?.base_currency || "CRC";
  const [step, setStep] = useState(0);
  const [name, setName] = useState(firstName(user));
  const [goal, setGoal] = useState(user?.usage_goal || "");
  const [baseCurrency, setBaseCurrency] = useState(initialCurrency);
  const [enabledCurrencies, setEnabledCurrencies] = useState(() => {
    const current = Array.isArray(user?.enabled_currencies) ? user.enabled_currencies : [initialCurrency];
    return [...new Set([initialCurrency, ...current])];
  });
  const [numberFormat, setNumberFormat] = useState(user?.number_format || "dot_comma");
  const [currencyPlacement, setCurrencyPlacement] = useState(user?.currency_placement || "before");
  const [bankSearch, setBankSearch] = useState("");
  const [selectedBanks, setSelectedBanks] = useState(() => user?.selected_financial_institutions || []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const selectedCurrency = CURRENCIES.find((item) => item.code === baseCurrency) || CURRENCIES[0];
  const amount = numberFormat === "dot_comma" ? "123.456,78" : "123,456.78";
  const preview = currencyPlacement === "before"
    ? `${selectedCurrency.symbol}${amount} ${selectedCurrency.code}`
    : `${amount} ${selectedCurrency.symbol} ${selectedCurrency.code}`;
  const filteredBanks = useMemo(() => {
    const query = bankSearch.trim().toLowerCase();
    return query ? BANKS.filter((bank) => bank.name.toLowerCase().includes(query)) : BANKS;
  }, [bankSearch]);

  const canContinue = step === 0 ? Boolean(name.trim()) : step === 1 ? Boolean(goal) : true;

  const chooseBaseCurrency = (code) => {
    setBaseCurrency(code);
    setEnabledCurrencies((current) => [...new Set([code, ...current])]);
  };

  const toggleCurrency = (code) => {
    if (code === baseCurrency) return;
    setEnabledCurrencies((current) => current.includes(code)
      ? current.filter((item) => item !== code)
      : [...current, code]);
  };

  const toggleBank = (id) => {
    setSelectedBanks((current) => current.includes(id)
      ? current.filter((item) => item !== id)
      : [...current, id]);
  };

  const next = () => {
    setError("");
    if (!canContinue) return;
    setStep((current) => Math.min(current + 1, 3));
  };

  const finish = async () => {
    setSaving(true);
    setError("");
    try {
      const result = await completeProfileSetup({
        display_name: name.trim(),
        usage_goal: goal,
        base_currency: baseCurrency,
        enabled_currencies: [...new Set([baseCurrency, ...enabledCurrencies])],
        number_format: numberFormat,
        currency_placement: currencyPlacement,
        selected_financial_institutions: selectedBanks,
      });
      onComplete(result.profile);
    } catch (requestError) {
      setError(requestError?.message || tx("No pudimos guardar tus preferencias. Intentá nuevamente.", "We couldn’t save your preferences. Please try again."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className={`profile-setup profile-setup--${platform} ${isJarvis ? "profile-setup--jarvis" : "profile-setup--finva"}`}>
      <section className="profile-setup-shell">
        <header className="profile-setup-header">
          <button
            type="button"
            className="profile-setup-back"
            aria-label={tx("Volver", "Back")}
            onClick={() => setStep((current) => Math.max(0, current - 1))}
            disabled={step === 0 || saving}
          >
            <ArrowLeft />
          </button>
          <div className="profile-setup-progress" aria-label={`${tx("Paso", "Step")} ${step + 1} ${tx("de", "of")} 4`}>
            {[0, 1, 2, 3].map((item) => <span key={item} className={item <= step ? "active" : ""} />)}
          </div>
          <span className="profile-setup-counter">{step + 1}/4</span>
        </header>

        <div className="profile-setup-scroll">
          {step === 0 && (
            <section className="profile-setup-step intro-step">
              <BrandArt isJarvis={isJarvis} />
              <div className="profile-setup-title">
                <span>{tx("EMPECEMOS", "LET’S GET STARTED")}</span>
                <h1>{tx("¿Cómo querés que te llamemos?", "What would you like us to call you?")}</h1>
                <p>{tx(`Usaremos este nombre para acompañarte dentro de ${product}. Podés cambiarlo después.`, `We’ll use this name throughout ${product}. You can change it later.`)}</p>
              </div>
              <label className="profile-setup-field">
                <span>{tx("Tu nombre", "Your name")}</span>
                <input
                  type="text"
                  value={name}
                  maxLength={80}
                  autoComplete="given-name"
                  enterKeyHint="next"
                  onChange={(event) => setName(event.target.value)}
                  onKeyDown={(event) => { if (event.key === "Enter" && name.trim()) next(); }}
                  placeholder={tx("Ejemplo: Ana", "Example: Ana")}
                />
              </label>
            </section>
          )}

          {step === 1 && (
            <section className="profile-setup-step">
              <div className="profile-setup-title centered">
                <span>{tx("PERSONALICEMOS TU EXPERIENCIA", "LET’S PERSONALIZE YOUR EXPERIENCE")}</span>
                <h1>{tx("¿Qué es lo principal que querés lograr?", "What is the main thing you want to achieve?")}</h1>
                <p>{tx("No hay una respuesta incorrecta. Esto nos ayuda a mostrarte primero lo que más te sirve.", "There’s no wrong answer. This helps us show you what matters most first.")}</p>
              </div>
              <div className="profile-goal-list" role="radiogroup" aria-label={tx("Motivo principal", "Main goal")}>
                {GOALS.map(({ id, icon: Icon, label, detail }) => (
                  <button
                    type="button"
                    role="radio"
                    aria-checked={goal === id}
                    key={id}
                    className={goal === id ? "selected" : ""}
                    onClick={() => setGoal(id)}
                  >
                    <span className="profile-goal-icon"><Icon /></span>
                    <span><strong>{label}</strong><small>{detail}</small></span>
                    <span className="profile-goal-check">{goal === id ? <Check /> : <ChevronRight />}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {step === 2 && (
            <section className="profile-setup-step">
              <div className="profile-setup-title">
                <span>{tx("PERSONALIZÁ TU DINERO", "PERSONALIZE YOUR MONEY")}</span>
                <h1>{tx("Configurá cómo ves tu dinero", "Set how you view your money")}</h1>
                <p>{tx("Elegí una moneda principal y agregá las que también usás. No convertiremos montos sin avisarte.", "Choose a primary currency and add any others you use. We won’t convert amounts without telling you.")}</p>
              </div>

              <div className="profile-settings-card">
                <label>
                  <span>{tx("Moneda principal", "Primary currency")}</span>
                  <select value={baseCurrency} onChange={(event) => chooseBaseCurrency(event.target.value)}>
                    {CURRENCIES.map((currency) => (
                      <option value={currency.code} key={currency.code}>{currency.flag} {currency.code} — {currency.name}</option>
                    ))}
                  </select>
                </label>
                <div className="profile-extra-currencies">
                  <h2>{tx("Otras monedas que utilizás", "Other currencies you use")}</h2>
                  <p>{tx("Elegí todas las que necesitás. Podés cambiarlas después.", "Choose all the ones you need. You can change them later.")}</p>
                  <div>
                    {CURRENCIES.filter((currency) => currency.code !== baseCurrency).map((currency) => {
                      const checked = enabledCurrencies.includes(currency.code);
                      return (
                        <button
                          type="button"
                          key={currency.code}
                          className={checked ? "selected" : ""}
                          aria-pressed={checked}
                          onClick={() => toggleCurrency(currency.code)}
                        >
                          <span>{currency.flag}</span><strong>{currency.code}</strong>{checked && <Check />}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <fieldset>
                  <legend>{tx("Formato de números", "Number format")}</legend>
                  <div className="profile-segmented-control">
                    <button type="button" className={numberFormat === "dot_comma" ? "active" : ""} onClick={() => setNumberFormat("dot_comma")}>123.456,78</button>
                    <button type="button" className={numberFormat === "comma_dot" ? "active" : ""} onClick={() => setNumberFormat("comma_dot")}>123,456.78</button>
                  </div>
                </fieldset>
                <fieldset>
                  <legend>{tx("Posición del símbolo", "Symbol position")}</legend>
                  <div className="profile-segmented-control">
                    <button type="button" className={currencyPlacement === "before" ? "active" : ""} onClick={() => setCurrencyPlacement("before")}>{tx("Antes", "Before")}</button>
                    <button type="button" className={currencyPlacement === "after" ? "active" : ""} onClick={() => setCurrencyPlacement("after")}>{tx("Después", "After")}</button>
                  </div>
                </fieldset>
                <div className="profile-currency-preview"><small>{tx("Así se verá", "Preview")}</small><strong>{preview}</strong></div>
              </div>
              <p className="profile-currency-note">{tx("No convertiremos montos sin avisarte.", "We won’t convert amounts without telling you.")}</p>
            </section>
          )}

          {step === 3 && (
            <section className="profile-setup-step bank-step">
              <div className="profile-setup-title">
                <span>{tx("TUS INSTITUCIONES", "YOUR INSTITUTIONS")}</span>
                <h1>{tx("Tus bancos en un solo lugar", "Your banks in one place")}</h1>
                <p>{tx("Seleccioná las instituciones que utilizás. Esta selección no conecta tus cuentas; podrás autorizar por separado la lectura de correos financieros compatibles.", "Select the institutions you use. This selection does not connect your accounts; you can separately authorize reading compatible financial emails.")}</p>
              </div>
              <div className="profile-bank-security"><ShieldCheck /><span><strong>{tx("Tu seguridad primero", "Your security comes first")}</strong><small>{tx(`${product} nunca te pedirá la contraseña de tu banco.`, `${product} will never ask for your bank password.`)}</small></span></div>
              <label className="profile-bank-search"><Search /><input value={bankSearch} onChange={(event) => setBankSearch(event.target.value)} placeholder={tx("Buscar banco", "Search bank")} /></label>
              <div className="profile-bank-grid">
                {filteredBanks.map((bank) => (
                  <button type="button" className={`profile-bank-card ${selectedBanks.includes(bank.id) ? "selected" : ""}`} aria-pressed={selectedBanks.includes(bank.id)} key={bank.name} onClick={() => toggleBank(bank.id)}>
                    <span className={`bank-mark bank-mark--${bank.tone} ${bank.logo ? "bank-mark--logo" : ""}`} aria-hidden="true">{bank.logo ? <img src={bank.logo} alt="" /> : bank.short}</span>
                    <span className="profile-bank-copy"><strong>{bank.name}</strong><small>{bank.supported ? tx("Disponible para la suscripción VIP", "Available with the VIP subscription") : tx("Solo para personalizar tu perfil", "Only to personalize your profile")}</small></span>
                    {selectedBanks.includes(bank.id) && <Check />}
                  </button>
                ))}
              </div>
              {!filteredBanks.length && <p className="profile-bank-empty">{tx("Todavía no aparece ese banco. Podremos agregar más entidades después.", "That bank isn’t listed yet. We’ll be able to add more institutions later.")}</p>}
              <p className="profile-data-note">{tx("Esto no conecta ninguna cuenta ni comparte contraseñas. Solo personaliza DINCR y prepara la automatización que vos autoricés después.", "This does not connect any account or share passwords. It only personalizes DINCR and prepares automation you authorize later.")}</p>
            </section>
          )}

          {error && <div className="profile-setup-error" role="alert">{error}</div>}
        </div>

        <footer className="profile-setup-footer">
          <button type="button" disabled={!canContinue || saving} onClick={step === 3 ? finish : next}>
            {saving ? tx("Guardando...", "Saving...") : step === 3 ? `${tx("Entrar a", "Enter")} ${product}` : tx("Continuar", "Continue")}
            {!saving && <ChevronRight />}
          </button>
          <small>{step === 3
            ? tx("Estas preferencias quedarán guardadas en tu cuenta.", "These preferences will be saved to your account.")
            : tx("Tus datos se guardarán cuando terminés los cuatro pasos.", "Your data will be saved after you finish all four steps.")}
          </small>
        </footer>
      </section>
    </main>
  );
}
