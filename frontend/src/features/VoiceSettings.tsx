import { Download, Mic, Play, Trash2, Wand2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/api/client";
import { useApiMutation } from "@/api/hooks";
import type { AddressMode, AppSettings, SystemVoice, VoiceSettings as VS, VoiceStatus } from "@/api/types";
import { Badge, Button, Checkbox, ConfirmDialog, Field, Input, Panel, Select } from "@/components/ui";
import { ListeningToggle } from "@/features/assistant";
import { toast } from "@/lib/toast";
import { useVoice } from "@/lib/voice";

const GENDER: Record<SystemVoice["gender"], string> = { female: "feminina", male: "masculina", unspecified: "não indicado" };
const ADDRESS: { value: AddressMode; label: string; example: string }[] = [
  { value: "masculine", label: "Tratamento masculino", example: "«Estou aqui, senhor.»" },
  { value: "feminine", label: "Tratamento feminino", example: "«Estou aqui, senhora.»" },
  { value: "neutral", label: "Tratamento neutro", example: "«Estou aqui.»" },
  { value: "custom", label: "Personalizado", example: "«Estou aqui, <nome>.»" },
];

type VoicesResponse = { available: boolean; voices: SystemVoice[]; notes: string[] };

function WakeSamples({ status }: { status: VoiceStatus | null }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const run = async (key: string, fn: () => Promise<unknown>, ok?: (r: unknown) => string) => {
    setBusy(key);
    try {
      const r = await fn();
      if (ok) toast.success(ok(r));
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(null);
      void qc.invalidateQueries({ queryKey: ["voice"] });
    }
  };
  const wake = status?.wake;
  const user = wake?.samples.filter((s) => s.source === "user") ?? [];
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[12.5px] text-text-2">Amostras:</span>
        {wake?.mode === "user" && <Badge tone="success">{user.length} gravada(s) por si</Badge>}
        {wake?.mode === "system" && <Badge tone="amber">só vozes do sistema (menos fiável)</Badge>}
        {wake?.mode === "none" && <Badge tone="danger">nenhuma</Badge>}
        {wake?.preparing && <Badge tone="blue">a preparar amostras…</Badge>}
        {wake?.threshold != null && <span className="font-mono text-[11px] text-muted">limiar {wake.threshold}</span>}
      </div>
      <p className="text-[11.5px] text-muted">
        Para melhor detecção, grave 3 a 5 amostras com a sua voz: carregue em «Gravar amostra» e diga «{status?.wake_word ?? "UAJI"}» uma vez (2,5 s). O áudio
        fica só neste Mac, na pasta de dados, e serve apenas para comparação.
      </p>
      <div className="flex flex-wrap gap-1.5">
        <Button size="sm" variant="primary" icon={<Mic className="h-3.5 w-3.5" />} loading={busy === "rec"} onClick={() => void run("rec", () => api.post("/api/voice/wake/record"), () => "Amostra gravada.")}>
          Gravar amostra
        </Button>
        <Button
          size="sm"
          variant="secondary"
          loading={busy === "test"}
          disabled={!wake?.samples.length}
          onClick={() =>
            void run("test", () => api.post<{ detected: boolean; score: number | null }>("/api/voice/wake/test"), (r) => {
              const t = r as { detected: boolean; score: number | null };
              return t.detected ? `Reconhecido (distância ${t.score?.toFixed(3)}).` : `Não reconhecido (distância ${t.score?.toFixed(3) ?? "—"}). Grave mais amostras ou aumente a sensibilidade.`;
            })
          }
        >
          Testar detecção
        </Button>
        <Button size="sm" variant="ghost" icon={<Wand2 className="h-3.5 w-3.5" />} loading={busy === "sys"} onClick={() => void run("sys", () => api.post("/api/voice/wake/system"), () => "Amostras do sistema geradas.")}>
          Gerar amostras com vozes do sistema
        </Button>
      </div>
      {(wake?.samples.length ?? 0) > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {wake!.samples.map((s) => (
            <li key={s.name}>
              <Badge tone={s.source === "user" ? "primary" : "neutral"}>
                {s.source === "user" ? "voz própria" : "sistema"} · {s.name}
                <button type="button" aria-label={`Apagar amostra ${s.name}`} className="ml-0.5 hover:text-danger" onClick={() => void run(s.name, () => api.del(`/api/voice/wake/${s.name}`))}>
                  <Trash2 className="h-3 w-3" />
                </button>
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function VoiceSettingsPanel({ settings }: { settings: AppSettings }) {
  const status = useVoice((s) => s.status);
  const [v, setV] = useState<VS>(settings.voice);
  const [persona, setPersona] = useState(settings.persona);
  const [asst, setAsst] = useState(settings.assistant);
  const [gender, setGender] = useState<"all" | "female" | "male">("all");
  const [clearOpen, setClearOpen] = useState(false);
  useEffect(() => {
    setV(settings.voice);
    setPersona(settings.persona);
    setAsst(settings.assistant);
  }, [settings]);
  const voices = useQuery({ queryKey: ["voice", "voices"], queryFn: () => api.get<VoicesResponse>("/api/voice/voices"), staleTime: 300_000 });
  const list = useMemo(() => (voices.data?.voices ?? []).filter((x) => gender === "all" || x.gender === gender), [voices.data, gender]);
  const current = voices.data?.voices.find((x) => x.id === v.voice);
  const languages = [...new Set((voices.data?.voices ?? []).map((x) => x.language))];

  const save = useApiMutation(
    () => {
      // «listening» é controlado pelo interruptor (aplicado de imediato); não é sobrescrito aqui.
      const { listening: _ignored, ...voice } = v;
      void _ignored;
      return api.patch<AppSettings>("/api/settings", { values: { voice, persona, assistant: asst } });
    },
    { invalidate: [["settings"], ["assistant"]], success: "Voz e personalidade guardadas." },
  );
  const sample = async () => {
    try {
      await api.post("/api/voice/test", { voice: v.voice, rate: v.rate, volume: v.volume });
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };
  const download = async () => {
    try {
      await api.post("/api/voice/model/download");
      toast.success("A descarregar o modelo de reconhecimento de fala…");
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };
  const clearHistory = useApiMutation(() => api.del<{ deleted: number }>("/api/assistant/history", { confirm: true }), {
    success: (r) => `${r.deleted} mensagem(ns) apagada(s).`,
    onSuccess: () => setClearOpen(false),
  });
  const stt = status?.stt;

  return (
    <Panel title="Voz e personalidade" className="lg:col-span-2" bodyClassName="grid gap-5 lg:grid-cols-2">
      <div className="flex flex-col gap-3" id="voz">
        <h3 className="hud-label text-primary">Activação e escuta</h3>
        <div className="flex flex-wrap items-center gap-2">
          <ListeningToggle status={status} />
          {status && (
            <Badge tone={status.mic.permission === "authorized" ? "success" : status.mic.permission === "denied" ? "danger" : "amber"}>
              Microfone: {{ authorized: "autorizado", denied: "negado", restricted: "restrito", not_determined: "por pedir", unknown: "desconhecido" }[status.mic.permission]}
            </Badge>
          )}
          {status?.mic.permission === "not_determined" && (
            <Button size="sm" variant="ghost" onClick={() => void api.post("/api/voice/permission").catch(() => undefined)}>
              Pedir autorização
            </Button>
          )}
        </div>
        {status?.mic.permission === "denied" && (
          <p className="text-[12px] text-danger">
            O macOS negou o acesso. Autorize em Definições do Sistema → Privacidade e Segurança → Microfone e reinicie a aplicação.
          </p>
        )}
        <p className="text-[11.5px] text-muted">
          Com a escuta ligada e a aplicação aberta (mesmo minimizada), o microfone fica aberto e o áudio é analisado localmente para detectar a palavra. Com a
          aplicação fechada ou o Mac em repouso, nada é escutado. Desligada, o microfone só é usado quando carrega no botão do microfone.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Palavra de activação" htmlFor="v-wake" hint="Ao mudar, grave novas amostras">
            <Input id="v-wake" value={v.wake_word} maxLength={30} onChange={(e) => setV({ ...v, wake_word: e.target.value })} />
          </Field>
          <Field label={`Sensibilidade (${v.sensitivity.toFixed(1)})`} htmlFor="v-sens" hint="Mais alta: activa mais vezes, incluindo falsas">
            <input id="v-sens" type="range" min={0.5} max={2} step={0.1} value={v.sensitivity} onChange={(e) => setV({ ...v, sensitivity: Number(e.target.value) })} className="w-full accent-[var(--color-primary)]" />
          </Field>
          <Field label="Saudação" htmlFor="v-greet">
            <Input id="v-greet" value={v.greeting} maxLength={200} onChange={(e) => setV({ ...v, greeting: e.target.value })} />
          </Field>
          <Field label="Seguimento após resposta (s)" htmlFor="v-follow" hint="0 = volta logo a esperar a palavra">
            <Input id="v-follow" type="number" min={0} max={30} value={v.follow_up_seconds} onChange={(e) => setV({ ...v, follow_up_seconds: Number(e.target.value) })} />
          </Field>
        </div>
        <WakeSamples status={status} />

        <h3 className="hud-label mt-2 text-primary">Reconhecimento de fala (local)</h3>
        {stt ? (
          <div className="flex flex-col gap-1.5 text-[12.5px] text-text-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge tone={stt.model_installed ? "success" : "amber"}>{stt.model_installed ? "Modelo instalado" : "Modelo por instalar"}</Badge>
              <span>
                Vosk · {stt.model} · ~{stt.model_size_mb} MB · processamento neste Mac
              </span>
            </div>
            {!stt.model_installed && (
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" variant="primary" icon={<Download className="h-3.5 w-3.5" />} loading={stt.download?.active} onClick={() => void download()}>
                  Descarregar modelo ({stt.model_size_mb} MB)
                </Button>
                {stt.download?.active && <span className="font-mono text-[11px]">{Math.round((stt.download.progress ?? 0) * 100)}%</span>}
                <span className="text-[11px] text-muted">Requer Internet só desta vez (alphacephei.com).</span>
              </div>
            )}
            {stt.download?.error && <p className="text-[12px] text-danger">Falha no descarregamento: {stt.download.error}</p>}
          </div>
        ) : (
          <p className="text-[12px] text-muted">Serviço de voz a ligar…</p>
        )}
      </div>

      <div className="flex flex-col gap-3">
        <h3 className="hud-label text-primary">Voz do assistente</h3>
        <Checkbox checked={v.tts_enabled} onChange={(x) => setV({ ...v, tts_enabled: x })} label="Responder por voz" />
        {voices.data && !voices.data.available && <p className="text-[12px] text-danger">Síntese de fala indisponível neste sistema.</p>}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Tipo de voz" htmlFor="v-gender">
            <Select id="v-gender" value={gender} onChange={(e) => setGender(e.target.value as typeof gender)}>
              <option value="all">Todas</option>
              <option value="female">Feminina</option>
              <option value="male">Masculina</option>
            </Select>
          </Field>
          <Field label="Voz" htmlFor="v-voice" hint={current ? `${current.language} · ${GENDER[current.gender]}${current.gender_source === "catalog" ? " (catálogo Apple)" : ""}` : "Voz não instalada"}>
            <Select id="v-voice" value={v.voice} onChange={(e) => setV({ ...v, voice: e.target.value })}>
              {!current && <option value={v.voice}>{v.voice} (não instalada)</option>}
              {list.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name} — {x.language} ({GENDER[x.gender]})
                </option>
              ))}
            </Select>
          </Field>
          <Field label={`Velocidade (${v.rate} palavras/min)`} htmlFor="v-rate">
            <input id="v-rate" type="range" min={120} max={280} step={5} value={v.rate} onChange={(e) => setV({ ...v, rate: Number(e.target.value) })} className="w-full accent-[var(--color-primary)]" />
          </Field>
          <Field label={`Volume (${Math.round(v.volume * 100)}%)`} htmlFor="v-vol">
            <input id="v-vol" type="range" min={0} max={1} step={0.05} value={v.volume} onChange={(e) => setV({ ...v, volume: Number(e.target.value) })} className="w-full accent-[var(--color-primary)]" />
          </Field>
          <Field label="Idioma" htmlFor="v-lang" hint="O reconhecimento de fala usa português">
            <Select id="v-lang" value={v.language} onChange={(e) => setV({ ...v, language: e.target.value })}>
              {[...new Set([v.language, ...languages])].map((l) => (
                <option key={l} value={l}>
                  {{ "pt-PT": "Português (Portugal)", "pt-BR": "Português (Brasil)", "pt-AO": "Português (Angola)" }[l] ?? l}
                </option>
              ))}
            </Select>
          </Field>
          <div className="flex items-end">
            <Button size="sm" variant="secondary" icon={<Play className="h-3.5 w-3.5" />} disabled={!current} onClick={() => void sample()}>
              Ouvir amostra
            </Button>
          </div>
        </div>
        {gender !== "all" && list.length === 0 && <p className="text-[12px] text-amber">Não há nenhuma voz {gender === "female" ? "feminina" : "masculina"} instalada.</p>}
        {voices.data?.notes.map((n) => (
          <p key={n} className="text-[11.5px] text-muted">
            {n}
          </p>
        ))}

        <h3 className="hud-label mt-2 text-primary">Como o assistente o trata</h3>
        <div className="flex flex-col gap-1.5" role="radiogroup" aria-label="Forma de tratamento">
          {ADDRESS.map((a) => (
            <label key={a.value} className="flex items-center gap-2 text-[13px] text-text-2">
              <input type="radio" name="address" className="accent-[var(--color-primary)]" checked={persona.address === a.value} onChange={() => setPersona({ ...persona, address: a.value })} />
              {a.label} <span className="text-[11.5px] text-muted">{a.example}</span>
            </label>
          ))}
          {persona.address === "custom" && (
            <Input aria-label="Nome ou forma de tratamento" placeholder="Ex.: Fábio, Chefe, Engenheiro(a)…" maxLength={60} value={persona.custom} onChange={(e) => setPersona({ ...persona, custom: e.target.value })} />
          )}
          <p className="text-[11.5px] text-muted">A escolha é sua e pode mudá-la a qualquer momento. O assistente nunca deduz o género a partir do nome ou da voz.</p>
        </div>

        <h3 className="hud-label mt-2 text-primary">Acções e histórico</h3>
        <Checkbox checked={asst.confirm_creates} onChange={(x) => setAsst({ ...asst, confirm_creates: x })} label="Pedir confirmação antes de criar (tarefas, notas, projectos)" />
        <Checkbox checked={asst.confirm_updates} onChange={(x) => setAsst({ ...asst, confirm_updates: x })} label="Pedir confirmação antes de alterar dados existentes" />
        <p className="text-[11.5px] text-muted">Eliminações e operações irreversíveis pedem sempre confirmação. Acções propostas pela IA também.</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Guardar histórico (dias)" htmlFor="a-hist" hint="0 = não guardar conversas">
            <Input id="a-hist" type="number" min={0} max={3650} value={asst.history_days} onChange={(e) => setAsst({ ...asst, history_days: Number(e.target.value) })} />
          </Field>
          <Field label="Contexto da conversa (turnos)" htmlFor="a-ctx">
            <Input id="a-ctx" type="number" min={1} max={40} value={asst.context_turns} onChange={(e) => setAsst({ ...asst, context_turns: Number(e.target.value) })} />
          </Field>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate(undefined)}>
            Guardar voz e personalidade
          </Button>
          <Button variant="ghost" onClick={() => setClearOpen(true)}>
            Apagar histórico de conversas
          </Button>
        </div>
        <ConfirmDialog
          open={clearOpen}
          title="Apagar histórico"
          message="Todas as conversas guardadas com o assistente serão eliminadas. O áudio nunca é guardado."
          confirmLabel="Apagar"
          danger
          loading={clearHistory.isPending}
          onConfirm={() => clearHistory.mutate(undefined)}
          onCancel={() => setClearOpen(false)}
        />
      </div>
    </Panel>
  );
}
