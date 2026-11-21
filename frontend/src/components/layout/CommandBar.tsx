import { CornerDownLeft, Loader2, Terminal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useApiMutation } from "@/api/hooks";
import type { CommandResult } from "@/api/types";
import { cn, ENTITY_LABEL } from "@/lib/utils";

const SUGGESTIONS = [
  { command: "tarefa ", label: "tarefa Título !alta @amanhã" },
  { command: "projecto ", label: "projecto Nome" },
  { command: "nota ", label: "nota Título" },
  { command: "pesquisar ", label: "pesquisar termo" },
  { command: "concluir ", label: "concluir parte do título" },
  { command: "foco iniciar", label: "foco iniciar / parar" },
  { command: "ir para ", label: "ir para agenda" },
];

/**
 * Barra de comando local. Os comandos são interpretados pelo backend de forma
 * determinística (sem IA). Entrada de voz não está implementada e por isso não é mostrada.
 */
export function CommandBar() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<CommandResult | null>(null);
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const run = useApiMutation((t: string) => api.post<CommandResult>("/api/commands", { text: t }), {
    invalidate: [["tasks"], ["projects"], ["notes"], ["focus"]],
    silentError: true,
    onSuccess: (r) => {
      setResult(r);
      if (r.kind === "navigate" && r.route) navigate(r.route);
      if (r.kind !== "error" && r.kind !== "unknown" && r.kind !== "ambiguous") setText("");
    },
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const tone =
    run.isError || result?.kind === "error" || result?.kind === "unknown"
      ? "text-danger"
      : result?.kind === "ambiguous"
        ? "text-amber"
        : "text-success";

  return (
    <div className="relative shrink-0 border-t border-line bg-bg-2/80 px-4 py-2">
      {focused && !text && (
        <div className="absolute bottom-full left-4 mb-1 flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button
              key={s.command}
              type="button"
              onMouseDown={(e) => {
                e.preventDefault();
                setText(s.command);
                inputRef.current?.focus();
              }}
              className="rounded border border-line-strong bg-surface-2 px-2 py-0.5 font-mono text-[11px] text-text-2 hover:border-primary/50 hover:text-text"
            >
              {s.label}
            </button>
          ))}
        </div>
      )}
      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) run.mutate(text);
        }}
      >
        <Terminal className="h-4 w-4 shrink-0 text-primary" aria-hidden />
        <label htmlFor="command-input" className="sr-only">
          Barra de comando
        </label>
        <input
          id="command-input"
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="Escreva um comando… (⌘J)"
          autoComplete="off"
          className="h-8 min-w-0 flex-1 bg-transparent font-mono text-[13px] text-text placeholder:text-muted focus:outline-none"
        />
        {run.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin text-primary" aria-label="A processar" />
        ) : (
          <button type="submit" className="text-muted hover:text-primary" aria-label="Executar comando">
            <CornerDownLeft className="h-4 w-4" />
          </button>
        )}
      </form>
      {(result || run.isError) && (
        <div className={cn("mt-1 flex flex-wrap items-center gap-2 pl-6 text-xs", tone)} role="status">
          <span>{run.isError ? (run.error as Error).message : result?.message}</span>
          {result?.route && result.kind !== "navigate" && (
            <Link to={result.route} className="text-primary underline">
              Abrir
            </Link>
          )}
          {result?.hits?.slice(0, 5).map((h) => (
            <Link key={h.entity_id} to={h.route ?? "/"} className="rounded border border-line px-1.5 text-text-2 hover:text-text">
              {ENTITY_LABEL[h.entity_type]}: {h.title}
            </Link>
          ))}
          <button type="button" className="ml-auto text-muted hover:text-text" onClick={() => { setResult(null); run.reset(); }}>
            Limpar
          </button>
        </div>
      )}
    </div>
  );
}
