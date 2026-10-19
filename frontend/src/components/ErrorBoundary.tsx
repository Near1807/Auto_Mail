import { AlertTriangle, Home, RotateCcw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

/** Envoie l'erreur au back, qui l'écrit dans %APPDATA%\AutoMail\logs\automail.log. */
export function reportClientError(error: unknown, componentStack = "", page = "") {
  const e = error instanceof Error ? error : new Error(String(error));
  try {
    void fetch("/api/client-error", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: `${e.name}: ${e.message}`, stack: e.stack ?? "", component_stack: componentStack, page }),
    }).catch(() => undefined);
  } catch {
    /* le log ne doit jamais faire planter l'appli */
  }
}

type Props = { children: ReactNode; page: string; onHome: () => void };
type State = { error: Error | null };

/**
 * Filet de sécurité global : si un écran plante, on affiche un message lisible
 * (jamais une page blanche) et la sidebar reste utilisable.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    reportClientError(error, info.componentStack ?? "", this.props.page);
  }

  componentDidUpdate(previous: Props) {
    // Changer d'écran depuis la sidebar efface l'erreur.
    if (this.state.error && previous.page !== this.props.page) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto mt-16 max-w-lg rounded-2xl border border-line bg-surface p-8 text-center">
        <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-bad-soft text-bad">
          <AlertTriangle size={26} />
        </div>
        <h1 className="mt-5 text-xl font-extrabold">Cet écran a rencontré un problème</h1>
        <p className="mt-2 text-sm text-muted">
          Tes campagnes et ton suivi ne sont pas touchés. L'erreur a été notée dans le journal
          (<code className="font-mono text-xs">logs\automail.log</code>).
        </p>
        <pre className="mt-4 max-h-28 overflow-auto rounded-lg bg-surface-2 p-3 text-left font-mono text-[11px] whitespace-pre-wrap text-muted">
          {this.state.error.message}
        </pre>
        <div className="mt-6 flex justify-center gap-2">
          <button
            onClick={() => this.setState({ error: null })}
            className="inline-flex h-10 items-center gap-2 rounded-xl border border-line px-4 text-sm font-semibold hover:bg-surface-2"
          >
            <RotateCcw size={15} /> Réessayer
          </button>
          <button
            onClick={() => {
              this.setState({ error: null });
              this.props.onHome();
            }}
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-accent px-4 text-sm font-semibold text-accent-ink"
          >
            <Home size={15} /> Retour à l'accueil
          </button>
        </div>
      </div>
    );
  }
}
