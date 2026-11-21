import { useIsFetching, useIsMutating } from "@tanstack/react-query";
import { useCore } from "@/lib/core-state";
import { useVoice } from "@/lib/voice";
import { cn } from "@/lib/utils";

/**
 * Estados do núcleo. Os estados do assistente vêm do serviço de voz real (SSE);
 * «processing» reflecte pedidos à API em curso; «idle» é o estado inactivo.
 */
export type CoreState =
  | "idle"
  | "wake"
  | "listening"
  | "interpreting"
  | "preparing"
  | "speaking"
  | "executing"
  | "confirming"
  | "processing"
  | "success"
  | "error";

export const CORE_LABELS: Record<CoreState, string> = {
  idle: "Inactivo",
  wake: "À espera da palavra de activação",
  listening: "A ouvir",
  interpreting: "A interpretar o pedido",
  preparing: "A preparar a resposta",
  speaking: "A falar",
  executing: "A executar uma acção",
  confirming: "A aguardar confirmação",
  processing: "A processar",
  success: "Concluído",
  error: "Erro",
};

const COLORS: Record<CoreState, string> = {
  idle: "#22d3ee",
  wake: "#22d3ee",
  listening: "#3b82f6",
  interpreting: "#60a5fa",
  preparing: "#22d3ee",
  speaking: "#38bdf8",
  executing: "#f5b942",
  confirming: "#f5b942",
  processing: "#22d3ee",
  success: "#34d399",
  error: "#f87171",
};

const BUSY: CoreState[] = ["interpreting", "preparing", "executing", "processing"];

/** Deriva o estado do núcleo a partir de condições reais (voz, pedidos à API, resultados). */
export function useCoreState(backendDown = false): CoreState {
  const fetching = useIsFetching();
  const mutating = useIsMutating();
  const { flash, executing, responding } = useCore();
  const voice = useVoice((s) => s.status?.state);
  if (backendDown) return "error";
  switch (voice) {
    case "listening":
    case "interpreting":
    case "preparing":
    case "executing":
    case "confirming":
    case "speaking":
    case "error":
      return voice;
    case "done":
      return "success";
    default:
      break;
  }
  if (flash) return flash;
  if (executing > 0) return "executing";
  if (responding) return "preparing";
  if (fetching + mutating > 0) return "processing";
  return voice === "wake" ? "wake" : "idle";
}

export function CoreOrb({
  state,
  size = 168,
  className,
  showLabel = true,
}: {
  state: CoreState;
  size?: number;
  className?: string;
  showLabel?: boolean;
}) {
  const c = COLORS[state];
  const busy = BUSY.includes(state);
  const ticks = Array.from({ length: 48 }, (_, i) => i);
  const bars = Array.from({ length: 24 }, (_, i) => i);
  return (
    <div className={cn("relative inline-flex flex-col items-center", className)} data-state={state}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 200 200"
        role="img"
        aria-label={`Núcleo UANJI: ${CORE_LABELS[state]}`}
        style={{ filter: `drop-shadow(0 0 ${busy || state === "listening" ? 14 : 8}px ${c}55)` }}
      >
        <defs>
          <radialGradient id={`core-fill-${size}`} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor={c} stopOpacity="0.55" />
            <stop offset="45%" stopColor={c} stopOpacity="0.12" />
            <stop offset="100%" stopColor={c} stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* A ouvir: ondas concêntricas a entrar no núcleo */}
        {state === "listening" && (
          <>
            <circle cx="100" cy="100" r="80" fill="none" stroke={c} strokeOpacity="0.45" className="core-wave-in" />
            <circle cx="100" cy="100" r="80" fill="none" stroke={c} strokeOpacity="0.45" className="core-wave-in" style={{ animationDelay: "0.6s" }} />
          </>
        )}
        {/* Actividade: onda exterior */}
        {(busy || state === "success") && (
          <circle cx="100" cy="100" r="78" fill="none" stroke={c} strokeOpacity="0.35" className="core-wave" />
        )}
        {/* A falar: barras radiais tipo forma de onda */}
        {state === "speaking" && (
          <g>
            {bars.map((i) => {
              const a = (i / bars.length) * Math.PI * 2;
              return (
                <line
                  key={i}
                  x1={100 + Math.cos(a) * 72}
                  y1={100 + Math.sin(a) * 72}
                  x2={100 + Math.cos(a) * 80}
                  y2={100 + Math.sin(a) * 80}
                  stroke={c}
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  className="core-bar"
                  style={{ animationDelay: `${(i % 6) * 0.11}s`, transformOrigin: `${100 + Math.cos(a) * 72}px ${100 + Math.sin(a) * 72}px` }}
                />
              );
            })}
          </g>
        )}
        {/* Anel de marcas técnicas */}
        <g className={busy ? "core-spin-fast" : "core-spin"}>
          {ticks.map((i) => {
            const a = (i / ticks.length) * Math.PI * 2;
            const long = i % 4 === 0;
            const r1 = long ? 84 : 87;
            return (
              <line
                key={i}
                x1={100 + Math.cos(a) * r1}
                y1={100 + Math.sin(a) * r1}
                x2={100 + Math.cos(a) * 91}
                y2={100 + Math.sin(a) * 91}
                stroke={long ? "#d4a64a" : c}
                strokeOpacity={long ? 0.7 : state === "idle" ? 0.22 : 0.35}
                strokeWidth={long ? 1.6 : 1}
              />
            );
          })}
        </g>
        {/* Anel médio tracejado (rotação inversa) */}
        <g className="core-spin" style={{ animationDirection: "reverse", animationDuration: busy ? "6s" : "40s" }}>
          <circle cx="100" cy="100" r="66" fill="none" stroke={c} strokeOpacity="0.55" strokeWidth="1.2" strokeDasharray="14 7 3 7" />
        </g>
        {/* Losango geométrico (acento dourado); pisca ao aguardar confirmação */}
        <g className={state === "confirming" ? "core-blink" : "core-pulse"}>
          <path d="M100 52 L148 100 L100 148 L52 100 Z" fill="none" stroke="#d4a64a" strokeOpacity={state === "confirming" ? 0.95 : 0.55} strokeWidth="1.2" />
          <path d="M100 68 L132 100 L100 132 L68 100 Z" fill="none" stroke={c} strokeOpacity="0.4" strokeWidth="1" />
        </g>
        <circle cx="100" cy="100" r="46" fill={`url(#core-fill-${size})`} className={state === "wake" ? "core-breathe" : undefined} />
        <circle cx="100" cy="100" r="18" fill="none" stroke={c} strokeWidth="2" strokeOpacity="0.9" />
        {state === "error" ? (
          <path d="M93 93 L107 107 M107 93 L93 107" stroke={c} strokeWidth="2.4" strokeLinecap="round" />
        ) : state === "success" ? (
          <path d="M92 100 L98 106 L109 94" fill="none" stroke={c} strokeWidth="2.4" strokeLinecap="round" />
        ) : (
          <circle cx="100" cy="100" r={state === "listening" ? 8 : 6} fill={c} className={busy || state === "listening" ? "core-pulse" : undefined} />
        )}
      </svg>
      {showLabel && (
        <div className="mt-1 flex items-center gap-1.5" aria-live="polite">
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: c, boxShadow: `0 0 8px ${c}` }} />
          <span className="hud-label" style={{ color: c }}>
            {CORE_LABELS[state]}
          </span>
        </div>
      )}
    </div>
  );
}
