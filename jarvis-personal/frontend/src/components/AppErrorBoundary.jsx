import { Component } from "react";
import { LifeBuoy, RotateCcw } from "lucide-react";
import { openSupport } from "../lib/apiErrors";
import { recordError } from "../lib/telemetry";
import { tx } from "../lib/locale";

export default class AppErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    recordError(error, `react:${info?.componentStack || "render"}`);
  }

  componentDidUpdate(previousProps) {
    if (previousProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <section className="mobile-panel dincr-error-fallback" role="alert">
        <strong>{tx("Algo salió mal", "Something went wrong")}</strong>
        <p>{tx("Tu información sigue segura. Podés intentar de nuevo o contarnos qué estabas haciendo.", "Your information is safe. Try again or tell us what you were doing.")}</p>
        <div>
          <button type="button" className="dincr-button dincr-button-secondary" onClick={() => this.setState({ error: null })}>
            <RotateCcw size={18}/> {tx("Intentar de nuevo", "Try again")}
          </button>
          <button type="button" className="dincr-button dincr-button-primary" onClick={() => {
            openSupport({ kind: "problem", screen: this.props.screen, summary: tx("La pantalla dejó de responder.", "The screen stopped responding.") });
            if (this.props.screen === "application") window.location.reload();
            else this.setState({ error: null });
          }}>
            <LifeBuoy size={18}/> {tx("Ir a soporte", "Go to support")}
          </button>
        </div>
      </section>
    );
  }
}
