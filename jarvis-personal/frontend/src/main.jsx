import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import PublicInfoPage from "./pages/PublicInfoPage";
// Keep this order: each module is a later visual layer over the previous one.
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
import "./pages/PublicInfoPage.css";
import "./pages/UnifiedOnboarding.css";
import { registerJarvisServiceWorker } from "./pushNotifications";

const publicPages = new Set(["/about", "/privacy"]);
const isPublicPage = publicPages.has(window.location.pathname);

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {isPublicPage ? <PublicInfoPage /> : <App />}
  </React.StrictMode>
);
if (!isPublicPage) {
  registerJarvisServiceWorker().catch(() => {});
}
