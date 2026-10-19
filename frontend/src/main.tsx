import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ErrorBoundary, reportClientError } from "./components/ErrorBoundary";
import "./index.css";
import { StoreProvider } from "./store";

// Erreurs hors rendu React (gestionnaires d'évènements, promesses) : notées dans le journal.
window.addEventListener("error", (e) => reportClientError(e.error ?? e.message, "", "window"));
window.addEventListener("unhandledrejection", (e) => reportClientError(e.reason, "", "promise"));

function goHome() {
  try {
    localStorage.setItem("automail-page", "campaigns");
  } catch {
    /* stockage indisponible */
  }
  location.reload();
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* Dernier filet : même si la sidebar ou l'état global plantent, jamais de page blanche. */}
    <ErrorBoundary page="app" onHome={goHome}>
      <StoreProvider>
        <App />
      </StoreProvider>
    </ErrorBoundary>
  </StrictMode>,
);
