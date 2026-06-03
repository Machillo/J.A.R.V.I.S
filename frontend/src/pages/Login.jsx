import { Shield, Sparkles } from "lucide-react";
import { supabase } from "../lib/supabase";

export default function Login() {
  const loginWithGoogle = async () => {
    await supabase.auth.signInWithOAuth({
      provider: "google",
    });
  };

  return (
    <main className="login-page">
      <section className="login-card">
        <div className="login-orb">
          <div className="login-ring"></div>
          <Shield size={54} />
        </div>

        <p className="login-kicker">
          SISTEMA PRIVADO
        </p>

        <h1>J.A.R.V.I.S.</h1>

        <p className="login-subtitle">
          Acceso seguro al núcleo financiero y personal.
        </p>

        <button className="login-google-btn" onClick={loginWithGoogle}>
          <Sparkles size={18} />
          Entrar con Google
        </button>

        <p className="login-warning">
          Solo usuarios autorizados pueden acceder.
        </p>
      </section>
    </main>
  );
}