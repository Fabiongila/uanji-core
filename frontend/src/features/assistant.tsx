import {
  AlertTriangle,
  Check,
  Cpu,
  Ear,
  EarOff,
  Keyboard,
  Mic,
  MicOff,
  Pause,
  Play,
  RotateCcw,
  Send,
  ShieldCheck,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { errorMessage } from "@/api/client";
import { useAssistantStatus } from "@/api/hooks";
import type { AssistantTurn, ProposedAction, ReportSectionKind, VoiceStatus } from "@/api/types";
import { Badge, Button, Checkbox, ConfirmDialog, Textarea, type Tone } from "@/components/ui";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { decideAction, sendMessage, voiceApi, type Entry } from "@/lib/voice";

const PERMISSION: Record<string, { label: string; tone: Tone }> = {
  authorized: { label: "Microfone autorizado", tone: "success" },
  denied: { label: "Microfone negado", tone: "danger" },
  restricted: { label: "Microfone restrito", tone: "danger" },
  not_determined: { label: "Microfone: permissão ainda não pedida", tone: "amber" },
  unknown: { label: "Microfone: permissão desconhecida", tone: "neutral" },
};

function readFlag(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : v === "1";
  } catch {
    return fallback;
  }
}
function writeFlag(key: string, v: boolean) {
  try {
    localStorage.setItem(key, v ? "1" : "0");
  } catch {
    /* armazenamento indisponível */
  }
}

const MIC_ACK = "uanji.mic.explained";

/** Explicação mostrada antes da primeira utilização do microfone. */
function MicExplainer({ open, onAccept, onCancel }: { open: boolean; onAccept: () => void; onCancel: () => void }) {
  return (
    <ConfirmDialog
      open={open}
      title="Utilizar o microfone"
      confirmLabel="Compreendo, continuar"
      onConfirm={onAccept}
      onCancel={onCancel}
      message={
        <div className="flex flex-col gap-2 text-[13px] text-text-2">
          <p>
            <strong className="text-text">Finalidade:</strong> detectar a palavra de activação e transcrever os seus pedidos ao assistente.
          </p>
          <p>
            <strong className="text-text">Processamento local:</strong> a detecção da palavra e a transcrição correm neste Mac. O áudio não é
            enviado para a Internet nem guardado em disco.
          </p>
          <p>
            Se tiver um fornecedor de IA configurado, só o <em>texto</em> dos pedidos que o assistente não reconhece localmente lhe é enviado.
          </p>
          <p>O macOS vai pedir autorização. Pode desligar a escuta a qualquer momento; o indicador no topo mostra quando o microfone está aberto.</p>
        </div>
      }
    />
  );
}

function useMicGate() {
  const [pending, setPending] = useState<null | (() => void)>(null);
  const run = (fn: () => void) => {
    if (readFlag(MIC_ACK, false)) fn();
    else setPending(() => fn);
  };
  const dialog = (
    <MicExplainer
      open={pending !== null}
      onAccept={() => {
        writeFlag(MIC_ACK, true);
        const fn = pending;
        setPending(null);
        fn?.();
      }}
      onCancel={() => setPending(null)}
    />
  );
  return { run, dialog };
}

async function guard(p: Promise<unknown>) {
  try {
    await p;
  } catch (e) {
    toast.error(errorMessage(e));
  }
}

// --------------------------------------------------------------------------- Controlos

export function MicButton({ status, size = "md" }: { status: VoiceStatus | null; size?: "md" | "lg" }) {
  const gate = useMicGate();
  const active = status?.state === "listening" || status?.state === "confirming";
  const label = active ? "Parar de ouvir" : "Falar com o assistente";
  return (
    <>
      <button
        type="button"
        aria-label={label}
        aria-pressed={active}
        title={label}
        disabled={!status}
        onClick={() => (active ? void guard(voiceApi.cancel()) : gate.run(() => void guard(voiceApi.activate())))}
        className={cn(
          "relative flex shrink-0 items-center justify-center rounded-full border transition-colors disabled:opacity-40",
          size === "lg" ? "h-14 w-14" : "h-10 w-10",
          active
            ? "border-electric bg-electric/20 text-electric shadow-[0_0_18px_rgb(59_130_246/0.45)]"
            : "border-primary/50 bg-primary/10 text-primary hover:bg-primary/20",
        )}
      >
        {active ? <MicOff className={size === "lg" ? "h-6 w-6" : "h-4.5 w-4.5"} /> : <Mic className={size === "lg" ? "h-6 w-6" : "h-4.5 w-4.5"} />}
        {active && <span className="absolute inset-0 animate-ping rounded-full border border-electric/50" aria-hidden />}
      </button>
      {gate.dialog}
    </>
  );
}

export function ListeningToggle({ status }: { status: VoiceStatus | null }) {
  const gate = useMicGate();
  const on = !!status?.listening_enabled;
  const qc = useQueryClient();
  const set = (v: boolean) =>
    void guard(voiceApi.setListening(v).then(() => qc.invalidateQueries({ queryKey: ["settings"] })));
  return (
    <>
      <Button
        size="sm"
        variant={on ? "primary" : "secondary"}
        aria-pressed={on}
        disabled={!status}
        icon={on ? <Ear className="h-3.5 w-3.5" /> : <EarOff className="h-3.5 w-3.5" />}
        onClick={() => (on ? set(false) : gate.run(() => set(true)))}
        title={on ? "Desligar a escuta: o microfone é fechado" : `Escutar «${status?.wake_word ?? "UAJI"}» enquanto a aplicação estiver aberta`}
      >
        {on ? `A escutar «${status?.wake_word}»` : "Escuta desligada"}
      </Button>
      {gate.dialog}
    </>
  );
}

export function SpeechControls({ status, compact = false }: { status: VoiceStatus | null; compact?: boolean }) {
  if (!status) return null;
  const speak = readFlag("uanji.voice.reply", true);
  return (
    <div className="flex flex-wrap items-center gap-1">
      {status.tts.speaking && (
        <Button size="sm" variant="amber" icon={<Square className="h-3 w-3" />} onClick={() => void guard(voiceApi.stopSpeaking())}>
          {compact ? "Parar" : "Interromper a fala"}
        </Button>
      )}
      {!status.tts.speaking && status.tts.can_resume && (
        <Button size="sm" variant="ghost" icon={<Play className="h-3 w-3" />} onClick={() => void guard(voiceApi.resumeSpeaking())}>
          Retomar leitura
        </Button>
      )}
      {!compact && (
        <Button size="sm" variant="ghost" icon={<RotateCcw className="h-3 w-3" />} onClick={() => void guard(sendMessage("repete", speak))}>
          Repetir
        </Button>
      )}
      {["listening", "interpreting", "preparing", "confirming"].includes(status.state) && (
        <Button size="sm" variant="ghost" icon={<Pause className="h-3 w-3" />} onClick={() => void guard(voiceApi.cancel())}>
          Cancelar
        </Button>
      )}
    </div>
  );
}

/** Indicadores de privacidade e estado (sempre visíveis no assistente). */
export function VoiceIndicators({ status }: { status: VoiceStatus | null }) {
  const ai = useAssistantStatus();
  if (!status) return <Badge tone="neutral">Serviço de voz a ligar…</Badge>;
  const perm = PERMISSION[status.mic.permission] ?? { label: "Microfone: permissão desconhecida", tone: "neutral" as Tone };
  const recording = status.mic.active && ["listening", "confirming"].includes(status.state);
  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Estado do microfone e privacidade">
      <Badge tone={perm.tone}>{perm.label}</Badge>
      <Badge tone={status.mic.active ? "blue" : "neutral"}>
        {status.mic.active ? (recording ? "● A ouvir o pedido" : "● Microfone aberto (análise local)") : "Microfone fechado"}
      </Badge>
      {status.listening_enabled && <Badge tone="primary">À espera de «{status.wake_word}»</Badge>}
      {["interpreting", "preparing"].includes(status.state) && <Badge tone="blue">A processar</Badge>}
      <Badge tone="success">
        <ShieldCheck className="h-3 w-3" /> Áudio processado localmente{status.external_audio ? "" : " · nada é gravado"}
      </Badge>
      {ai.data?.configured && (
        <Badge tone="amber" className="whitespace-normal">
          Texto não reconhecido localmente → fornecedor de IA (Internet)
        </Badge>
      )}
      {status.last_error && status.state !== "listening" && (
        <Badge tone="danger" className="h-auto whitespace-normal py-0.5">
          <AlertTriangle className="h-3 w-3 shrink-0" /> {status.last_error}
        </Badge>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- Conversa

const SECTION_TONE: Record<ReportSectionKind, string> = {
  facts: "text-primary border-primary/30",
  derived: "text-electric border-electric/30",
  recommendations: "text-amber border-amber/30",
  unavailable: "text-muted border-line-strong",
};

const RISK: Record<ProposedAction["risk"], { label: string; tone: Tone }> = {
  read: { label: "consulta", tone: "neutral" },
  system: { label: "acção no sistema", tone: "blue" },
  create: { label: "cria dados", tone: "primary" },
  update: { label: "altera dados", tone: "amber" },
  destructive: { label: "irreversível", tone: "danger" },
};

function ActionCard({ action }: { action: ProposedAction }) {
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();
  const decide = async (approve: boolean) => {
    setBusy(true);
    try {
      const r = await decideAction(action.id, approve);
      if (r.actions[0]?.status === "confirmed") await qc.invalidateQueries();
      if (r.error) toast.error(r.reply);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const risk = RISK[action.risk];
  return (
    <div
      className={cn(
        "mt-2 rounded-md border px-2.5 py-2 text-xs",
        action.risk === "destructive" ? "border-danger/50 bg-danger/5" : "border-amber/40 bg-amber/5",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-amber">Acção proposta:</span>
        <span className="text-text">{action.summary}</span>
        <Badge tone={risk.tone}>{risk.label}</Badge>
        {action.status === "pending" ? (
          <span className="ml-auto flex gap-1">
            <Button size="sm" variant={action.risk === "destructive" ? "danger" : "primary"} loading={busy} onClick={() => void decide(true)} icon={<Check className="h-3 w-3" />}>
              Confirmar
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => void decide(false)} icon={<X className="h-3 w-3" />}>
              Rejeitar
            </Button>
          </span>
        ) : (
          <Badge tone={action.status === "confirmed" ? "success" : action.status === "failed" ? "danger" : "neutral"} className="ml-auto">
            {{ confirmed: "Executada", rejected: "Rejeitada", failed: "Falhou", expired: "Expirou", pending: "" }[action.status]}
          </Badge>
        )}
      </div>
      {action.details.length > 0 && (
        <ul className="mt-1.5 list-inside list-disc text-text-2">
          {action.details.map((d, i) => (
            <li key={i}>{d}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function TurnView({ entry, compact = false }: { entry: Entry; compact?: boolean }) {
  if (entry.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-lg bg-primary/10 px-3 py-2 text-[13px] text-text">
          <span className="mr-1.5 inline-flex align-[-2px] text-primary/70" title={entry.source === "voice" ? "Dito por voz" : "Escrito"}>
            {entry.source === "voice" ? <Mic className="h-3.5 w-3.5" /> : <Keyboard className="h-3.5 w-3.5" />}
          </span>
          {entry.text}
        </div>
      </div>
    );
  }
  const t = entry.turn as AssistantTurn;
  const label: ReactNode = t.proactive ? (
    <span className="inline-flex items-center gap-1 text-amber"><Sparkles className="h-3 w-3" /> Por iniciativa do assistente</span>
  ) : t.engine === "ai" ? "Resposta gerada por IA" : t.engine === "none" ? "Assistente" : (
      <span className="inline-flex items-center gap-1"><Cpu className="h-3 w-3" /> Interpretado localmente</span>
    );
  return (
    <div className="max-w-[95%]">
      <div className="hud-label mb-1">{t.error ? "Erro" : label}</div>
      {t.report && !compact ? (
        <div className="rounded-md border border-line bg-bg-2/50 p-2.5">
          <div className="mb-1.5 text-[13.5px] font-semibold text-text">{t.report.title}</div>
          <div className="flex flex-col gap-2">
            {t.report.sections.map((s) => (
              <div key={s.kind} className={cn("border-l-2 pl-2.5", SECTION_TONE[s.kind])}>
                <div className="hud-label" style={{ color: "inherit" }}>{s.title}</div>
                <ul className="mt-0.5 flex flex-col gap-0.5 text-[12.5px] text-text-2">
                  {s.items.map((it, i) => (
                    <li key={i}>{it}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className={cn("whitespace-pre-wrap text-[13px]", t.error ? "text-danger" : "text-text", compact && "line-clamp-3")}>{t.reply}</div>
      )}
      {!compact && t.executed.length > 0 && (
        <Badge tone="success" className="mt-1">
          <Check className="h-3 w-3" /> Executado e confirmado pelo serviço
        </Badge>
      )}
      {!compact && t.consulted.length > 0 && (
        <div className="mt-1 text-[11px] text-muted">Dados consultados: {t.consulted.map((c) => c.tool).join(", ")}</div>
      )}
      {t.actions.map((a) => (
        <ActionCard key={a.id} action={a} />
      ))}
      {t.offer && !compact && <OfferButtons label={t.offer.label} />}
    </div>
  );
}

/** Resposta rápida a uma pergunta feita por iniciativa do assistente. */
function OfferButtons({ label }: { label: string }) {
  const [done, setDone] = useState<null | "sim" | "não">(null);
  const qc = useQueryClient();
  const answer = async (a: "sim" | "não") => {
    setDone(a);
    try {
      const t = await sendMessage(a, readFlag("uanji.voice.reply", true));
      if (t.executed.length) await qc.invalidateQueries();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };
  if (done) return <div className="mt-1 text-[11px] text-muted">Respondeu «{done}».</div>;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      <Button size="sm" variant="primary" icon={<Check className="h-3 w-3" />} onClick={() => void answer("sim")}>
        Sim — {label}
      </Button>
      <Button size="sm" variant="ghost" onClick={() => void answer("não")}>
        Agora não
      </Button>
    </div>
  );
}

// --------------------------------------------------------------------------- Entrada de texto

export function AssistantInput({ autoFocus = false, placeholder }: { autoFocus?: boolean; placeholder?: string }) {
  const [text, setText] = useState("");
  const [speak, setSpeak] = useState(() => readFlag("uanji.voice.reply", true));
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();
  const submit = async () => {
    const m = text.trim();
    if (!m || busy) return;
    setText("");
    setBusy(true);
    try {
      const t = await sendMessage(m, speak);
      if (t.executed.length) await qc.invalidateQueries();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className="flex flex-col gap-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="flex gap-2">
        <Textarea
          aria-label="Mensagem para o assistente"
          rows={2}
          autoFocus={autoFocus}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
          placeholder={placeholder ?? "Escreva um pedido (Enter envia). Ex.: «Quais são as minhas tarefas prioritárias?»"}
        />
        <Button type="submit" variant="primary" loading={busy} icon={<Send className="h-4 w-4" />} aria-label="Enviar">
          Enviar
        </Button>
      </div>
      <Checkbox
        checked={speak}
        onChange={(v) => {
          setSpeak(v);
          writeFlag("uanji.voice.reply", v);
        }}
        label="Responder também por voz"
      />
    </form>
  );
}
