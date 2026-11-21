import { CheckCircle2, Cpu, PlugZap } from "lucide-react";
import { useState } from "react";
import { api, errorMessage } from "@/api/client";
import { useApiMutation } from "@/api/hooks";
import type { AppSettings, SecretEntry } from "@/api/types";
import { Badge, Button, Field, Input, Panel, Select } from "@/components/ui";

const PRESETS: { label: string; url: string; hint: string }[] = [
  { label: "Ollama (local)", url: "http://localhost:11434/v1", hint: "ex.: llama3.1, qwen2.5:7b, mistral" },
  { label: "LM Studio (local)", url: "http://localhost:1234/v1", hint: "o nome do modelo carregado no LM Studio" },
  { label: "llama.cpp server (local)", url: "http://localhost:8080/v1", hint: "o nome que deu ao modelo" },
  { label: "OpenRouter", url: "https://openrouter.ai/api/v1", hint: "ex.: meta-llama/llama-3.1-70b-instruct (requer chave)" },
];

/**
 * Fornecedor de IA: nenhum, Anthropic (Claude) ou um modelo próprio em qualquer servidor
 * compatível com a API OpenAI (Ollama, LM Studio, llama.cpp, vLLM, OpenRouter…).
 */
export function AIProviderPanel({ settings, setSettings, vault }: { settings: AppSettings; setSettings: (s: AppSettings) => void; vault: SecretEntry[] }) {
  const a = settings.assistant;
  const set = (patch: Partial<AppSettings["assistant"]>) => setSettings({ ...settings, assistant: { ...a, ...patch } });
  const [test, setTest] = useState<{ ok: boolean; reply?: string; models?: string[]; model_found?: boolean | null; error?: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const save = useApiMutation(() => api.patch<AppSettings>("/api/settings", { values: { assistant: a } }), {
    invalidate: [["settings"], ["assistant"]],
    success: "Fornecedor de IA guardado.",
  });
  const runTest = async () => {
    setTesting(true);
    setTest(null);
    try {
      await save.mutateAsync(undefined);
      setTest(await api.post("/api/assistant/test"));
    } catch (e) {
      setTest({ ok: false, error: errorMessage(e) });
    } finally {
      setTesting(false);
    }
  };
  const local = a.provider === "openai_compatible" && /localhost|127\.0\.0\.1/.test(a.base_url);
  return (
    <Panel title="Assistente de IA (opcional)">
      <div className="flex flex-col gap-3">
        <Field label="Fornecedor" htmlFor="a-p">
          <Select id="a-p" value={a.provider} onChange={(e) => set({ provider: e.target.value })}>
            <option value="none">Nenhum (só interpretação local)</option>
            <option value="anthropic">Anthropic (Claude)</option>
            <option value="openai_compatible">Modelo próprio (servidor compatível com OpenAI)</option>
          </Select>
        </Field>
        {a.provider === "openai_compatible" && (
          <>
            <div className="flex flex-wrap gap-1.5">
              {PRESETS.map((p) => (
                <Button key={p.url} size="sm" variant={a.base_url === p.url ? "primary" : "ghost"} onClick={() => set({ base_url: p.url })} title={p.hint}>
                  {p.label}
                </Button>
              ))}
            </div>
            <Field label="Endereço da API" htmlFor="a-u" hint="http só para localhost; servidores remotos com https">
              <Input id="a-u" value={a.base_url} placeholder="http://localhost:11434/v1" onChange={(e) => set({ base_url: e.target.value })} />
            </Field>
            <Field label="Modelo" htmlFor="a-mm" hint={PRESETS.find((p) => p.url === a.base_url)?.hint ?? "nome do modelo no servidor"}>
              <Input id="a-mm" value={a.model} placeholder="qwen2.5:7b" onChange={(e) => set({ model: e.target.value })} list="a-models" />
              {test?.models && test.models.length > 0 && (
                <datalist id="a-models">{test.models.map((m) => <option key={m} value={m} />)}</datalist>
              )}
            </Field>
            <Field label="Chave (opcional, do Cofre)" htmlFor="a-sk">
              <Select id="a-sk" value={a.secret_id ?? ""} onChange={(e) => set({ secret_id: e.target.value || null })}>
                <option value="">Sem chave (servidor local)</option>
                {vault.map((v) => <option key={v.id} value={v.id}>{v.name} {v.hint}</option>)}
              </Select>
            </Field>
            <p className="flex gap-1.5 text-[11.5px] text-muted">
              <Cpu className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {local
                ? "Modelo local: as conversas não saem deste Mac. Modelos grandes podem ser lentos neste computador; prefira modelos de 3B–8B quantizados."
                : "Servidor remoto: o texto dos pedidos e os dados consultados são enviados a esse serviço."}{" "}
              O modelo precisa de suportar «tools»/«function calling» para executar acções; sem isso responde só com texto.
            </p>
          </>
        )}
        {a.provider === "anthropic" && (
          <>
            <Field label="Chave da API (do Cofre)" htmlFor="a-s">
              <Select id="a-s" value={a.secret_id ?? ""} onChange={(e) => set({ secret_id: e.target.value || null })}>
                <option value="">Escolher segredo…</option>
                {vault.map((v) => <option key={v.id} value={v.id}>{v.name} {v.hint}</option>)}
              </Select>
            </Field>
            <Field label="Modelo" htmlFor="a-m" hint="Por omissão: claude-opus-5-5"><Input id="a-m" value={a.model} placeholder="claude-opus-5-5" onChange={(e) => set({ model: e.target.value })} /></Field>
            <p className="text-[11px] text-muted">Serviço externo pago, opcional. Os dados consultados pelo assistente são enviados ao fornecedor; os segredos nunca.</p>
          </>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" loading={save.isPending && !testing} onClick={() => save.mutate(undefined)}>Guardar</Button>
          {a.provider !== "none" && (
            <Button variant="secondary" loading={testing} icon={<PlugZap className="h-3.5 w-3.5" />} onClick={() => void runTest()}>Guardar e testar ligação</Button>
          )}
        </div>
        {test && (test.ok ? (
          <p className="flex flex-wrap items-center gap-1.5 text-[12.5px] text-success">
            <CheckCircle2 className="h-4 w-4" /> Ligação a funcionar. Resposta: «{test.reply}»
            {test.model_found === false && <Badge tone="amber">o modelo «{a.model}» não aparece na lista do servidor</Badge>}
          </p>
        ) : (
          <p className="text-[12.5px] text-danger">{test.error}</p>
        ))}
      </div>
    </Panel>
  );
}
