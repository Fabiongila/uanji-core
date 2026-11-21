import { AlertTriangle, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/api/client";
import { useApiMutation } from "@/api/hooks";
import type { AppSettings, Appearance, ProactiveRule, ProactiveSettings } from "@/api/types";
import { Button, Checkbox, Field, Panel, Select } from "@/components/ui";
import { appearanceOf } from "@/lib/appearance";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

function useSave(success: string) {
  return useApiMutation((values: Partial<AppSettings>) => api.patch<AppSettings>("/api/settings", { values }), {
    invalidate: [["settings"]],
    success,
  });
}

const THEMES: { value: Appearance["theme"]; label: string; swatch: string }[] = [
  { value: "uanji-dark", label: "UANJI (azul-noite)", swatch: "#050b16" },
  { value: "abyss", label: "Abismo (mais escuro)", swatch: "#02050c" },
  { value: "amber", label: "Âmbar (quente)", swatch: "#17110a" },
  { value: "contrast", label: "Alto contraste", swatch: "#000000" },
  { value: "light", label: "Claro (dia)", swatch: "#eef3f8" },
];
const ACCENTS: { value: Appearance["accent"]; label: string; color: string }[] = [
  { value: "cyan", label: "Ciano", color: "#22d3ee" },
  { value: "blue", label: "Azul eléctrico", color: "#3b82f6" },
  { value: "amber", label: "Âmbar", color: "#f5b942" },
  { value: "emerald", label: "Esmeralda", color: "#34d399" },
  { value: "violet", label: "Violeta", color: "#a78bfa" },
];

export function AppearancePanel({ settings }: { settings: AppSettings }) {
  const [a, setA] = useState<Appearance>(appearanceOf(settings));
  const [motion, setMotion] = useState(settings.reduced_motion);
  const [tz, setTz] = useState(settings.timezone);
  useEffect(() => {
    setA(appearanceOf(settings));
    setMotion(settings.reduced_motion);
    setTz(settings.timezone);
  }, [settings]);
  const save = useSave("Aparência guardada.");
  // Pré-visualização imediata (sem guardar): aplica os atributos ao documento.
  const savedTheme = appearanceOf(settings).theme;
  const savedAccent = appearanceOf(settings).accent;
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = a.theme;
    root.dataset.accent = a.accent;
    return () => {
      // Ao sair sem guardar, volta ao que está guardado.
      root.dataset.theme = savedTheme;
      root.dataset.accent = savedAccent;
    };
  }, [a.theme, a.accent, savedTheme, savedAccent]);
  return (
    <Panel title="Aparência e disposição">
      <div className="flex flex-col gap-3">
        <div role="radiogroup" aria-label="Tema" className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
          {THEMES.map((t) => (
            <button
              key={t.value}
              type="button"
              role="radio"
              aria-checked={a.theme === t.value}
              onClick={() => setA({ ...a, theme: t.value })}
              className={cn("flex items-center gap-2 rounded-md border px-2 py-1.5 text-left text-[12.5px]", a.theme === t.value ? "border-primary text-text" : "border-line text-text-2 hover:border-line-strong")}
            >
              <span className="h-4 w-4 rounded border border-line-strong" style={{ background: t.swatch }} />
              {t.label}
            </button>
          ))}
        </div>
        <div role="radiogroup" aria-label="Cor de destaque" className="flex flex-wrap gap-1.5">
          {ACCENTS.map((c) => (
            <button
              key={c.value}
              type="button"
              role="radio"
              aria-checked={a.accent === c.value}
              aria-label={c.label}
              title={c.label}
              onClick={() => setA({ ...a, accent: c.value })}
              className={cn("h-7 w-7 rounded-full border-2", a.accent === c.value ? "border-text" : "border-transparent")}
              style={{ background: c.color }}
            />
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Densidade" htmlFor="ap-d">
            <Select id="ap-d" value={a.density} onChange={(e) => setA({ ...a, density: e.target.value as Appearance["density"] })}>
              <option value="comfortable">Confortável</option>
              <option value="compact">Compacta</option>
            </Select>
          </Field>
          <Field label={`Tamanho da interface (${a.font_scale}%)`} htmlFor="ap-f">
            <input id="ap-f" type="range" min={85} max={130} step={5} value={a.font_scale} onChange={(e) => setA({ ...a, font_scale: Number(e.target.value) })} className="w-full accent-[var(--color-primary)]" />
          </Field>
          <Field label="Barra lateral" htmlFor="ap-s">
            <Select id="ap-s" value={a.sidebar} onChange={(e) => setA({ ...a, sidebar: e.target.value as Appearance["sidebar"] })}>
              <option value="left">À esquerda</option>
              <option value="right">À direita</option>
            </Select>
          </Field>
          <Field label="Disposição do painel" htmlFor="ap-l" hint="Adaptativa: ordena os cards pelo seu uso">
            <Select id="ap-l" value={a.layout_mode} onChange={(e) => setA({ ...a, layout_mode: e.target.value as Appearance["layout_mode"] })}>
              <option value="custom">Personalizada (a que definir)</option>
              <option value="adaptive">Adaptativa (aprende com o uso)</option>
            </Select>
          </Field>
          <Field label="Fuso horário" htmlFor="ap-tz">
            <Select id="ap-tz" value={tz} onChange={(e) => setTz(e.target.value)}>
              {[...new Set([tz, "Africa/Luanda", "Europe/Lisbon", "Africa/Maputo", "America/Sao_Paulo", "UTC"])].map((z) => (
                <option key={z} value={z}>{z}</option>
              ))}
            </Select>
          </Field>
        </div>
        <Checkbox checked={motion} onChange={setMotion} label="Reduzir animações (recomendado em hardware antigo)" />
        <p className="text-[11px] text-muted">A ordem, o tamanho e a visibilidade dos cards mudam-se no próprio painel, em «Personalizar painel».</p>
        <Button variant="primary" loading={save.isPending} onClick={() => save.mutate({ appearance: a, reduced_motion: motion, timezone: tz })}>
          Guardar aparência
        </Button>
      </div>
    </Panel>
  );
}

const RULES: { value: ProactiveRule; label: string }[] = [
  { value: "morning", label: "Bom dia com o plano do dia" },
  { value: "return", label: "Boas-vindas quando volta ao computador" },
  { value: "deadlines", label: "Prazos a terminar (1 h antes)" },
  { value: "events", label: "Compromissos (10 min antes)" },
  { value: "breaks", label: "Sugerir pausas após 90 min seguidos" },
  { value: "focus", label: "Sessões de foco longas" },
  { value: "context_switch", label: "Muitas mudanças de aplicação" },
  { value: "suggestions", label: "Sugestões a partir do que está a fazer" },
  { value: "automations", label: "Automações que falharam" },
  { value: "end_of_day", label: "Resumo no fim do dia" },
];

export function ProactivePanel({ settings }: { settings: AppSettings }) {
  const [p, setP] = useState<ProactiveSettings>(settings.proactive);
  useEffect(() => setP(settings.proactive), [settings]);
  const save = useSave("Iniciativa do assistente guardada.");
  const test = async () => {
    try {
      const r = await api.post<{ delivered: { text: string } | null; running: boolean }>("/api/proactive/check");
      toast.info(r.delivered ? r.delivered.text : r.running ? "Neste momento não há nada que justifique falar consigo." : "O motor de iniciativa não está activo (só na aplicação a correr).");
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };
  return (
    <Panel title="Iniciativa do assistente">
      <div className="flex flex-col gap-2.5">
        <p className="text-[12px] text-text-2">
          O assistente fala consigo sem esperar que carregue num botão: cumprimenta, avisa de prazos e compromissos, sugere pausas e oferece-se para ajudar. Com a
          escuta ligada, ouve logo a sua resposta («sim», «agora não»).
        </p>
        <Checkbox checked={p.enabled} onChange={(v) => setP({ ...p, enabled: v })} label="Tomar a iniciativa" />
        <Checkbox checked={p.voice} onChange={(v) => setP({ ...p, voice: v })} label="Falar em voz alta (não fala durante reuniões nem nas horas de silêncio)" />
        <Field label="Frequência" htmlFor="pr-i">
          <Select id="pr-i" value={p.intensity} onChange={(e) => setP({ ...p, intensity: e.target.value as ProactiveSettings["intensity"] })}>
            <option value="low">Discreta (no máximo de 45 em 45 min)</option>
            <option value="normal">Normal (20 min entre mensagens)</option>
            <option value="high">Presente (8 min entre mensagens)</option>
          </Select>
        </Field>
        <div className="grid gap-1 sm:grid-cols-2">
          {RULES.map((r) => (
            <Checkbox key={r.value} checked={p.rules[r.value] ?? true} onChange={(v) => setP({ ...p, rules: { ...p.rules, [r.value]: v } })} label={r.label} />
          ))}
        </div>
        <p className="text-[11px] text-muted">Prazos e compromissos ignoram o intervalo mínimo. As horas de silêncio definem-se em Notificações.</p>
        <div className="flex gap-2">
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate({ proactive: p })}>Guardar</Button>
          <Button variant="ghost" icon={<Sparkles className="h-3.5 w-3.5" />} onClick={() => void test()}>Verificar agora</Button>
        </div>
      </div>
    </Panel>
  );
}

export function SystemPanel({ settings }: { settings: AppSettings }) {
  const [s, setS] = useState(settings.system);
  useEffect(() => setS(settings.system), [settings]);
  const save = useSave("Permissões do sistema guardadas.");
  return (
    <Panel title="Sistema e comandos">
      <div className="flex flex-col gap-2.5">
        <p className="text-[12px] text-text-2">
          O assistente pode agir no Mac: «abre o VS Code», «fecha o Chrome», «volume a 30», «pesquisa na web …», «como está a bateria?», «abre a pasta Documents».
        </p>
        <Checkbox checked={s.allow_apps} onChange={(v) => setS({ ...s, allow_apps: v })} label="Abrir e fechar aplicações" />
        <Checkbox checked={s.confirm_system} onChange={(v) => setS({ ...s, confirm_system: v })} label="Pedir confirmação também para abrir apps, sites e pastas e ajustar o volume" />
        <p className="text-[11px] text-muted">Fechar aplicações pede confirmação conforme «alterar dados»; a aplicação pode pedir para guardar.</p>
        <Checkbox checked={s.allow_shell} onChange={(v) => setS({ ...s, allow_shell: v })} label="Permitir comandos de terminal («corre o comando …»)" />
        {s.allow_shell && (
          <p className="flex gap-1.5 rounded-md border border-amber/40 bg-amber/5 p-2 text-[12px] text-amber">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            Cada comando é mostrado e só corre depois de dizer «sim» ou carregar em Confirmar. Corre na sua pasta pessoal, com 30 s de limite; sudo, formatação de
            discos e apagar a pasta pessoal são sempre recusados. Mesmo assim, um comando pode alterar ou apagar ficheiros: confirme com atenção.
          </p>
        )}
        <Button variant="primary" loading={save.isPending} onClick={() => save.mutate({ system: s })}>Guardar</Button>
      </div>
    </Panel>
  );
}
