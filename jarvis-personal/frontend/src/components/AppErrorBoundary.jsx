import { Component } from "react";
import { LifeBuoy, RotateCcw } from "lucide-react";
import { openSupport } from "../lib/apiErrors";
import { recordError } from "../lib/telemetry";

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
      <section className="mobile-panel finva-error-fallback" role="alert">
        <strong>Algo salió mal</strong>
        <p>Tu información sigue segura. Podés intentar de nuevo o contarnos qué estabas haciendo.</p>
        <div>
          <button type="button" className="finva-button finva-button-secondary" onClick={() => this.setState({ error: null })}>
            <RotateCcw size={18}/> Intentar de nuevo
          </button>
          <button type="button" className="finva-button finva-button-primary" onClick={() => {
            openSupport({ kind: "problem", screen: this.props.screen, summary: "La pantalla dejó de responder." });
            if (this.props.screen === "application") window.location.reload();
            else this.setState({ error: null });
          }}>
            <LifeBuoy size={18}/> Ir a soporte
          </button>
        </div>
      </section>
    );
  }
}
