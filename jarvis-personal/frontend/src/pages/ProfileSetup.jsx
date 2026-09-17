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

const GOALS = [
  { id: "debt", icon: WalletCards, label: "Salir de deudas", detail: "Ordenar pagos y avanzar con un plan claro." },
  { id: "save", icon: PiggyBank, label: "Ahorrar para algo importante", detail: "Convertir una meta en aportes alcanzables." },
  { id: "partner", icon: HeartHandshake, label: "Organizar dinero en pareja o familia", detail: "Entender juntos qué entra, qué sale y qué sigue." },
  { id: "life_change", icon: Sparkles, label: "Prepararme para un cambio importante", detail: "Planear una mudanza, viaje, estudio u otra etapa." },
  { id: "control", icon: Target, label: "Tomar control de mis finanzas", detail: "Ver mis números con claridad y tomar mejores decisiones." },
  { id: "explore", icon: LifeBuoy, label: "Todavía no estoy seguro", detail: "Explorar la app y descubrir por dónde empezar." },
];

const CURRENCIES = [
  { code: "CRC", name: "Colón costarricense", symbol: "₡" },
  { code: "USD", name: "Dólar estadounidense", symbol: "$" },
  { code: "ARS", name: "Peso argentino", symbol: "$" },
  { code: "EUR", name: "Euro", symbol: "€" },
  { code: "MXN", name: "Peso mexicano", symbol: "$" },
  { code: "COP", name: "Peso colombiano", symbol: "$" },
  { code: "GTQ", name: "Quetzal guatemalteco", symbol: "Q" },
  { code: "PAB", name: "Balboa panameño", symbol: "B/." },
];

const BANKS = [
  { name: "BAC Credomatic", short: "BAC", tone: "red" },
  { name: "Banco Nacional", short: "BN", tone: "blue" },
  { name: "Banco de Costa Rica", short: "BCR", tone: "navy" },
  { name: "Banco Popular", short: "BP", tone: "orange" },
  { name: "Davivienda", short: "DAV", tone: "yellow" },
  { name: "Scotiabank", short: "S", tone: "red" },
  { name: "Promerica", short: "PRO", tone: "green" },
  { name: "MultiMoney", short: "MM", tone: "violet" },
];

const firstName = (user) => {
  const source = user?.display_name || user?.user_metadata?.full_name || user?.email?.split("@")[0] || "";
  return source.trim().split(/\s+/)[0] || "";
};

function BrandArt({ isJarvis }) {
  return (
    <div className="profile-setup-art" aria-hidden="true">
      <span className="profile-setup-orbit orbit-one" />
      <span className="profile-setup-orbit orbit-two" />
      <span className="profile-setup-art-card art-card-one"><Banknote /></span>
      <span className="profile-setup-art-card art-card-two"><PiggyBank /></span>
      <span className="profile-setup-art-core">{isJarvis ? "J" : "F"}</span>
      <strong>{isJarvis ? "JARVIS" : "FINVA"}</strong>
    </div>
  );
}

export default function ProfileSetup({ user, onComplete }) {
  const isJarvis = user?.role === "owner" || user?.role === "admin";
  const product = isJarvis ? "JARVIS" : "FINVA";
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
      });
      onComplete(result.profile);
    } catch (requestError) {
      setError(requestError?.message || "No pudimos guardar tus preferencias. Intentá nuevamente.");
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
            aria-label="Volver"
            onClick={() => setStep((current) => Math.max(0, current - 1))}
            disabled={step === 0 || saving}
          >
            <ArrowLeft />
          </button>
          <div className="profile-setup-progress" aria-label={`Paso ${step + 1} de 4`}>
            {[0, 1, 2, 3].map((item) => <span key={item} className={item <= step ? "active" : ""} />)}
          </div>
          <span className="profile-setup-counter">{step + 1}/4</span>
        </header>

        <div className="profile-setup-scroll">
          {step === 0 && (
            <section className="profile-setup-step intro-step">
              <BrandArt isJarvis={isJarvis} />
              <div className="profile-setup-title">
                <span>EMPECEMOS</span>
                <h1>¿Cómo querés que te llamemos?</h1>
                <p>Usaremos este nombre para acompañarte dentro de {product}. Podés cambiarlo después.</p>
              </div>
              <label className="profile-setup-field">
                <span>Tu nombre</span>
                <input
                  type="text"
                  value={name}
                  maxLength={80}
                  autoComplete="given-name"
                  enterKeyHint="next"
                  onChange={(event) => setName(event.target.value)}
                  onKeyDown={(event) => { if (event.key === "Enter" && name.trim()) next(); }}
                  placeholder="Ejemplo: Ana"
                />
              </label>
            </section>
          )}

          {step === 1 && (
            <section className="profile-setup-step">
              <div className="profile-setup-title centered">
                <span>PERSONALICEMOS TU EXPERIENCIA</span>
                <h1>¿Qué es lo principal que querés lograr?</h1>
                <p>No hay una respuesta incorrecta. Esto nos ayuda a mostrarte primero lo que más te sirve.</p>
              </div>
              <div className="profile-goal-list" role="radiogroup" aria-label="Motivo principal">
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
                <span>TUS MONEDAS</span>
                <h1>Configurá cómo ves tu dinero</h1>
                <p>Elegí una moneda principal y agregá las que también usás. No convertiremos montos sin avisarte.</p>
              </div>

              <div className="profile-settings-card">
                <label>
                  <span>Moneda principal</span>
                  <select value={baseCurrency} onChange={(event) => chooseBaseCurrency(event.target.value)}>
                    {CURRENCIES.map((currency) => (
                      <option value={currency.code} key={currency.code}>{currency.name} · {currency.code}</option>
                    ))}
                  </select>
                </label>
                <fieldset>
                  <legend>Formato de números</legend>
                  <div className="profile-segmented-control">
                    <button type="button" className={numberFormat === "dot_comma" ? "active" : ""} onClick={() => setNumberFormat("dot_comma")}>123.456,78</button>
                    <button type="button" className={numberFormat === "comma_dot" ? "active" : ""} onClick={() => setNumberFormat("comma_dot")}>123,456.78</button>
                  </div>
                </fieldset>
                <fieldset>
                  <legend>Posición del símbolo</legend>
                  <div className="profile-segmented-control">
                    <button type="button" className={currencyPlacement === "before" ? "active" : ""} onClick={() => setCurrencyPlacement("before")}>Antes</button>
                    <button type="button" className={currencyPlacement === "after" ? "active" : ""} onClick={() => setCurrencyPlacement("after")}>Después</button>
                  </div>
                </fieldset>
                <div className="profile-currency-preview"><small>Así se verá</small><strong>{preview}</strong></div>
              </div>

              <div className="profile-extra-currencies">
                <h2>Otras monedas que utilizás</h2>
                <p>Podés elegir varias y modificarlas luego en Configuración.</p>
                <div>
                  {CURRENCIES.map((currency) => {
                    const checked = enabledCurrencies.includes(currency.code);
                    return (
                      <button
                        type="button"
                        key={currency.code}
                        className={checked ? "selected" : ""}
                        aria-pressed={checked}
                        onClick={() => toggleCurrency(currency.code)}
                      >
                        <span>{currency.symbol}</span><strong>{currency.code}</strong>{checked && <Check />}
                      </button>
                    );
                  })}
                </div>
              </div>
            </section>
          )}

          {step === 3 && (
            <section className="profile-setup-step bank-step">
              <div className="profile-setup-title">
                <span>PRÓXIMAMENTE EN COSTA RICA</span>
                <h1>Tus bancos en un solo lugar</h1>
                <p>Esta es una vista previa. Hoy podés registrar movimientos manualmente y, cuando habilitemos conexiones, te pediremos permiso de solo lectura.</p>
              </div>
              <div className="profile-bank-security"><ShieldCheck /><span><strong>Tu seguridad primero</strong><small>{product} nunca te pedirá la contraseña de tu banco.</small></span></div>
              <label className="profile-bank-search"><Search /><input value={bankSearch} onChange={(event) => setBankSearch(event.target.value)} placeholder="Buscar banco" /></label>
              <div className="profile-bank-grid">
                {filteredBanks.map((bank) => (
                  <div className="profile-bank-card" key={bank.name}>
                    <span className={`bank-mark bank-mark--${bank.tone}`}>{bank.short}</span>
                    <strong>{bank.name}</strong>
                    <small>Próximamente</small>
                  </div>
                ))}
              </div>
              {!filteredBanks.length && <p className="profile-bank-empty">Todavía no aparece ese banco. Podremos agregar más entidades después.</p>}
              <p className="profile-data-note">Tu configuración financiera existente se conserva. No volveremos a pedirte información que ya completaste.</p>
            </section>
          )}

          {error && <div className="profile-setup-error" role="alert">{error}</div>}
        </div>

        <footer className="profile-setup-footer">
          <button type="button" disabled={!canContinue || saving} onClick={step === 3 ? finish : next}>
            {saving ? "Guardando..." : step === 3 ? `Entrar a ${product}` : "Continuar"}
            {!saving && <ChevronRight />}
          </button>
          <small>{step === 3 ? "Estas preferencias quedarán guardadas en tu cuenta." : "Tus datos se guardarán cuando terminés los cuatro pasos."}</small>
        </footer>
      </section>
    </main>
  );
}
