import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import PublicInfoPage from "./pages/PublicInfoPage";
import "./index.css";
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
