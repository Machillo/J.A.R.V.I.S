import { useMemo, useState } from "react";
import {
  ArrowRight,
  BrainCircuit,
  Eye,
  EyeOff,
  Lock,
  Mail,
  ShieldCheck,
  User,
  UserPlus,
} from "lucide-react";
import { supabase } from "../lib/supabase";

function GoogleIcon() {
  return (
    <svg className="google-icon" viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.4-.4-3.5Z"
      />
      <path
        fill="#FF3D00"
        d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 16.2 4 9.5 8.5 6.3 14.7Z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.3 0-9.7-3.3-11.3-7.9l-6.5 5C9.4 39.6 16.1 44 24 44Z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.3 4.2-4.1 5.6l6.2 5.2C36.9 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5Z"
      />
    </svg>
  );
}

const initialForm = {
  name: "",
  email: "",
  password: "",
  confirmPassword: "",
};

export default function Login() {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState(initialForm);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const isRegister = mode === "register";

  const buttonLabel = useMemo(() => {
    if (loading) return isRegister ? "Creando acceso..." : "Validando acceso...";
    return isRegister ? "Crear cuenta" : "Entrar";
  }, [isRegister, loading]);

  const updateForm = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
    setError("");
    setMessage("");
  };

  const loginWithGoogle = async () => {
    setLoading(true);
    setError("");
    setMessage("");

    const { error: authError } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        queryParams: {
          prompt: "select_account",
        },
      },
    });

    if (authError) {
      setError(authError.message);
      setLoading(false);
    }
  };

  const handleAuthSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setMessage("");

    const email = form.email.trim();
    const password = form.password;
    const name = form.name.trim();

    if (!email || !password || (isRegister && !name)) {
      setError("Completá los datos necesarios.");
      return;
    }

    if (isRegister && password !== form.confirmPassword) {
      setError("Las contraseñas no coinciden.");
      return;
    }

    setLoading(true);

    const response = isRegister
      ? await supabase.auth.signUp({
          email,
          password,
          options: {
            data: {
              full_name: name,
              display_name: name,
            },
          },
        })
      : await supabase.auth.signInWithPassword({ email, password });

    setLoading(false);

    if (response.error) {
      setError(response.error.message);
      return;
    }

    if (isRegister) {
      setMessage("Cuenta creada. Revisá el correo si Supabase pide confirmación.");
      setMode("login");
      setForm((current) => ({ ...initialForm, email: current.email }));
      return;
    }

    setForm(initialForm);
  };

  return (
    <main className="login-page auth-shell">
      <div className="auth-grid-lines" aria-hidden="true"></div>
      <div className="auth-aura auth-aura-one" aria-hidden="true"></div>
      <div className="auth-aura auth-aura-two" aria-hidden="true"></div>

      <section className="login-card auth-card">
        <div className="auth-orb-wrap">
          <div className="auth-orb-glow"></div>
          <div className="auth-orb">
            <BrainCircuit size={58} />
          </div>
        </div>

        <p className="login-kicker">SISTEMA PRIVADO</p>
        <h1 className="auth-title">J.A.R.V.I.S.</h1>
        <p className="login-subtitle">
          Acceso seguro y verificado a tu núcleo financiero personal.
        </p>

        <div className="auth-tabs" role="tablist" aria-label="Acceso JARVIS">
          <button
            type="button"
            className={!isRegister ? "active" : ""}
            onClick={() => {
              setMode("login");
              setError("");
              setMessage("");
            }}
          >
            Iniciar sesión
          </button>
          <button
            type="button"
            className={isRegister ? "active" : ""}
            onClick={() => {
              setMode("register");
              setError("");
              setMessage("");
            }}
          >
            Crear cuenta
          </button>
        </div>

        <button
          className="login-google-btn auth-google-btn"
          onClick={loginWithGoogle}
          disabled={loading}
          type="button"
        >
          <GoogleIcon />
          Entrar con Google
        </button>

        <div className="auth-divider">
          <span></span>
          <small>o continuá con</small>
          <span></span>
        </div>

        <form className="auth-form" onSubmit={handleAuthSubmit}>
          {isRegister && (
            <label className="auth-field">
              <User size={18} />
              <input
                value={form.name}
                onChange={(event) => updateForm("name", event.target.value)}
                placeholder="Nombre completo"
                autoComplete="name"
              />
            </label>
          )}

          <label className="auth-field">
            <Mail size={18} />
            <input
              value={form.email}
              onChange={(event) => updateForm("email", event.target.value)}
              placeholder="Correo electrónico"
              type="email"
              autoComplete="email"
            />
          </label>

          <label className="auth-field">
            <Lock size={18} />
            <input
              value={form.password}
              onChange={(event) => updateForm("password", event.target.value)}
              placeholder="Contraseña"
              type={showPassword ? "text" : "password"}
              autoComplete={isRegister ? "new-password" : "current-password"}
            />
            <button
              type="button"
              className="auth-eye"
              onClick={() => setShowPassword((current) => !current)}
              aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
            >
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </label>

          {isRegister && (
            <label className="auth-field">
              <Lock size={18} />
              <input
                value={form.confirmPassword}
                onChange={(event) => updateForm("confirmPassword", event.target.value)}
                placeholder="Confirmar contraseña"
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
              />
            </label>
          )}

          {!isRegister && (
            <div className="auth-row">
              <label className="auth-check">
                <input type="checkbox" />
                <span>Recordarme</span>
              </label>
              <button type="button" className="auth-link">
                ¿Olvidaste tu contraseña?
              </button>
            </div>
          )}

          {error && <p className="auth-message auth-error">{error}</p>}
          {message && <p className="auth-message auth-success">{message}</p>}

          <button className="auth-submit" type="submit" disabled={loading}>
            <span>{buttonLabel}</span>
            {isRegister ? <UserPlus size={19} /> : <ArrowRight size={20} />}
          </button>
        </form>

        <p className="login-warning auth-secure-note">
          <ShieldCheck size={15} />
          Tu información está protegida y vinculada a tu usuario.
        </p>
      </section>
    </main>
  );
}
