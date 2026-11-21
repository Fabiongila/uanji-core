import { Component, type ErrorInfo, type ReactNode } from "react";
import { api } from "@/api/client";

/** Envia erros da interface para o log do backend (Definições → Diagnóstico). */
export function reportClientError(source: string, error: unknown) {
  const e = error instanceof Error ? error : new Error(String(error));
  void api
    .post("/api/diagnostics/client-error", {
      source,
      message: e.message.slice(0, 2000),
      stack: (e.stack ?? "").slice(0, 8000),
      url: window.location.pathname,
    })
    .catch(() => undefined);
}

let installed = false;
export function installGlobalErrorReporting() {
  if (installed) return;
  installed = true;
  window.addEventListener("error", (ev) => reportClientError("window", ev.error ?? ev.message));
  window.addEventListener("unhandledrejection", (ev) => reportClientError("promise", ev.reason));
}

/**
 * Impede que um erro numa parte da interface deixe o ecrã vazio:
 * mostra o erro e permite recarregar. O erro fica registado no log do backend.
 */
export class ErrorBoundary extends Component<{ children: ReactNode; area?: string }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    reportClientError(`react:${this.props.area ?? "app"}`, Object.assign(error, { stack: `${error.stack ?? ""}\n${info.componentStack ?? ""}` }));
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="m-6 rounded-lg border border-danger/40 bg-danger/10 p-4 text-[13px] text-text">
        <p className="font-semibold text-danger">Ocorreu um erro nesta área da interface.</p>
        <p className="mt-1 font-mono text-[12px] text-text-2">{this.state.error.message}</p>
        <p className="mt-1 text-[12px] text-muted">O erro foi registado em Definições → Diagnóstico. Os seus dados não foram afectados.</p>
        <div className="mt-3 flex gap-2">
          <button type="button" className="rounded border border-line-strong px-3 py-1 hover:border-primary/50" onClick={() => this.setState({ error: null })}>
            Tentar novamente
          </button>
          <button type="button" className="rounded border border-line-strong px-3 py-1 hover:border-primary/50" onClick={() => window.location.reload()}>
            Recarregar a aplicação
          </button>
        </div>
      </div>
    );
  }
}
