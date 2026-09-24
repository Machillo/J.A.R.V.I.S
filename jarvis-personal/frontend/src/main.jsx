import React from "react";
import ReactDOM from "react-dom/client";

// Keep this order: each module is a later visual layer over the previous one.
// The global stylesheets must be imported before App: importing App first loads
// the DINCR Users styles (UsersApp) first, and then every legacy/native sheet below
// overrides them at equal specificity (light mode and Movimientos broke that way).
import "./styles/01-base.css";
import "./styles/02-legacy-features.css";
import "./styles/03-theme.css";
import "./styles/04-strategy-premium.css";
import "./styles/05-email-monitor.css";
import "./styles/06-finance-cycle.css";
import "./styles/07-app-shell.css";
import "./styles/08-finance-modules.css";
import "./styles/09-mobile-system.css";
import "./styles/10-finance-stability.css";
import "./styles/11-strategy-v3.css";
import "./styles/12-mobile-native-compat.css";
import "./pages/PublicInfoPage.css";
import "./pages/FinvaOnboarding.css";
import "./pages/LegalConsent.css";
import "./pages/ProfileSetup.css";
import "./pages/FinvaEntryFlow.css";
import "./ui/native/styles/tokens.css";
import "./ui/native/styles/ios.css";
import "./ui/native/styles/android.css";
import "./ui/native/styles/sheets.css";
import "./products/finva/styles/product.css";
import "./products/jarvis/styles/product.css";
import "./products/jarvis/styles/foundation.css";
import "./products/jarvis/styles/disclosure.css";
import "./products/jarvis/styles/screens.css";
import "./products/jarvis/styles/debt.css";
import "./products/jarvis/styles/navigation.css";
import "./products/jarvis/styles/home.css";
import "./products/jarvis/styles/secondary-screens.css";
import "./products/jarvis/styles/operations.css";
import App from "./App";
import PublicInfoPage from "./pages/PublicInfoPage";
import { registerJarvisServiceWorker } from "./pushNotifications";
import { initializeTelemetry } from "./lib/telemetry";
import { initializeColorMode } from "./lib/colorMode";
import AppErrorBoundary from "./components/AppErrorBoundary";

const publicPages = new Set(["/about", "/privacy", "/terms", "/delete-account"]);
const isPublicPage = publicPages.has(window.location.pathname);
initializeTelemetry();
initializeColorMode();

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AppErrorBoundary resetKey={window.location.pathname} screen="application">
      {isPublicPage ? <PublicInfoPage /> : <App />}
    </AppErrorBoundary>
  </React.StrictMode>
);
if (!isPublicPage) {
  registerJarvisServiceWorker().catch(() => {});
}
