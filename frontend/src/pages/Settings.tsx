import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { useApiMutation, useDiagnostics, useSettings, useVault } from "@/api/hooks";
import type { AppSettings } from "@/api/types";
import { Badge, Button, Checkbox, ErrorState, Field, Input, Kbd, Loading, PageHeader, Panel, Select } from "@/components/ui";
import { VoiceSettingsPanel } from "@/features/VoiceSettings";
import { AIProviderPanel } from "@/features/AIProvider";
import { AppearancePanel, ProactivePanel, SystemPanel } from "@/features/AutonomySettings";
import { fmtBytes } from "@/lib/utils";

const CATS: Record<string, string> = { deadline: "Prazos próximos", overdue: "Tarefas atrasadas", review: "Revisões diária/semanal", automation: "Falhas de automações", backup: "Backups" };
const DAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

function Logs() {
  const [lines, setLines] = useState<string[] | null>(null);
  const load = async () => setLines((await api.get<{ lines: string[] }>("/api/diagnostics/logs", { lines: 200 })).lines);
  return (
    <div>
      <Button size="sm" onClick={() => void load()}>{lines ? "Actualizar logs" : "Mostrar logs técnicos"}</Button>
      {lines && (
        <pre className="mt-2 max-h-72 overflow-auto rounded-md border border-line bg-bg-2 p-2 font-mono text-[10.5px] leading-relaxed text-text-2">
          {lines.length ? lines.join("\n") : "Sem registos."}
        </pre>
      )}
      <p className="mt-1 text-[11px] text-muted">Os logs são redigidos na escrita: tokens e chaves aparecem como [REDACTED].</p>
    </div>
  );
}

export default function SettingsPage() {
  const { data, isLoading, error } = useSettings();
  const diag = useDiagnostics();
  const vault = useVault();
  const [s, setS] = useState<AppSettings | null>(null);
  useEffect(() => { if (data) setS(data); }, [data]);
  const save = useApiMutation((values: Partial<AppSettings>) => api.patch<AppSettings>("/api/settings", { values }), {
    invalidate: [["settings"], ["assistant"], ["backups"], ["diagnostics"]],
    success: "Definições guardadas.",
  });
  if (isLoading || !s) return error ? <ErrorState error={error} /> : <Loading />;
  const n = s.notifications;
  const setN = (patch: Partial<AppSettings["notifications"]>) => setS({ ...s, notifications: { ...n, ...patch } });

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-4">
      <PageHeader title="Definições" subtitle="Preferências locais e diagnóstico." />
      <div className="grid gap-4 lg:grid-cols-2">
        {data && <VoiceSettingsPanel settings={data} />}
        {data && <AppearancePanel settings={data} />}
        {data && <ProactivePanel settings={data} />}
        {data && <SystemPanel settings={data} />}
        <Panel title="Notificações">
          <div className="flex flex-col gap-2.5">
            <Checkbox checked={n.enabled} onChange={(v) => setN({ enabled: v })} label="Notificações internas activas" />
            <Checkbox checked={n.native} onChange={(v) => setN({ native: v })} label="Mostrar também no centro de notificações do macOS (app desktop)" />
            <div className="grid grid-cols-2 gap-1.5">
              {Object.entries(CATS).map(([k, v]) => <Checkbox key={k} checked={n.categories[k] ?? true} onChange={(c) => setN({ categories: { ...n.categories, [k]: c } })} label={v} />)}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Avisar prazos com antecedência (h)" htmlFor="n-h"><Input id="n-h" type="number" min={1} max={168} value={n.deadline_hours} onChange={(e) => setN({ deadline_hours: Number(e.target.value) })} /></Field>
              <Field label="Hora da revisão diária" htmlFor="n-r"><Input id="n-r" type="time" value={n.daily_review_time} onChange={(e) => setN({ daily_review_time: e.target.value })} /></Field>
              <Field label="Silêncio (nativas) de" htmlFor="n-qs"><Input id="n-qs" type="time" value={n.quiet_start} onChange={(e) => setN({ quiet_start: e.target.value })} /></Field>
              <Field label="até" htmlFor="n-qe"><Input id="n-qe" type="time" value={n.quiet_end} onChange={(e) => setN({ quiet_end: e.target.value })} /></Field>
              <Field label="Dia da revisão semanal" htmlFor="n-w">
                <Select id="n-w" value={n.weekly_review_day} onChange={(e) => setN({ weekly_review_day: Number(e.target.value) })}>
                  {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                </Select>
              </Field>
            </div>
            <Button variant="primary" loading={save.isPending} onClick={() => save.mutate({ notifications: n })}>Guardar</Button>
          </div>
        </Panel>
        <Panel title="Backups automáticos">
          <div className="flex flex-col gap-3">
            <Checkbox checked={s.backups.automatic} onChange={(v) => setS({ ...s, backups: { ...s.backups, automatic: v } })} label="Criar backups automaticamente" />
            <div className="grid grid-cols-2 gap-3">
              <Field label="Intervalo (horas)" htmlFor="b-i"><Input id="b-i" type="number" min={1} value={s.backups.interval_hours} onChange={(e) => setS({ ...s, backups: { ...s.backups, interval_hours: Number(e.target.value) } })} /></Field>
              <Field label="Manter (automáticos)" htmlFor="b-k"><Input id="b-k" type="number" min={1} value={s.backups.keep} onChange={(e) => setS({ ...s, backups: { ...s.backups, keep: Number(e.target.value) } })} /></Field>
            </div>
            <Button variant="primary" loading={save.isPending} onClick={() => save.mutate({ backups: s.backups })}>Guardar</Button>
          </div>
        </Panel>
        <AIProviderPanel settings={s} setSettings={setS} vault={vault.data ?? []} />
        <Panel title="Atalhos de teclado">
          <ul className="flex flex-col gap-1.5 text-[13px] text-text-2">
            <li className="flex justify-between"><span>Pesquisa global / Command Palette</span><Kbd>⌘ K</Kbd></li>
            <li className="flex justify-between"><span>Barra de comando</span><Kbd>⌘ J</Kbd></li>
            <li className="flex justify-between"><span>Fechar diálogo</span><Kbd>Esc</Kbd></li>
            <li className="flex justify-between"><span>Enviar mensagem ao assistente</span><Kbd>Enter</Kbd></li>
            <li className="flex justify-between"><span>Interromper a fala do assistente</span><Kbd>Esc</Kbd></li>
          </ul>
        </Panel>
        <Panel title="Diagnóstico">
          {diag.isLoading ? <Loading /> : diag.error ? <ErrorState error={diag.error} /> : diag.data && (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
              <dt className="text-muted">Versão</dt><dd>{diag.data.app_version} ({diag.data.env})</dd>
              <dt className="text-muted">Sistema</dt><dd className="break-all">{diag.data.platform} · {diag.data.machine}</dd>
              <dt className="text-muted">Python</dt><dd>{diag.data.python}</dd>
              <dt className="text-muted">Dados</dt><dd className="break-all font-mono">{diag.data.data_dir}</dd>
              <dt className="text-muted">Base de dados</dt><dd>{fmtBytes(diag.data.db_size_bytes)} · esquema {diag.data.schema_revision} {diag.data.schema_revision === diag.data.schema_head ? <Badge tone="success">actual</Badge> : <Badge tone="danger">desactualizado</Badge>}</dd>
              <dt className="text-muted">Pesquisa</dt><dd>{diag.data.search_engine === "fts5" ? "SQLite FTS5" : "Alternativa (LIKE)"}</dd>
              <dt className="text-muted">Cofre</dt><dd>{diag.data.vault.backend} {diag.data.vault.secure ? <Badge tone="success">seguro</Badge> : <Badge tone="danger">inseguro</Badge>}</dd>
              <dt className="text-muted">Assistente</dt><dd>{diag.data.assistant.message}</dd>
              <dt className="text-muted">Disco livre</dt><dd>{fmtBytes(diag.data.disk_free_bytes)}</dd>
              <dt className="text-muted">Agendador</dt><dd>{diag.data.scheduler_enabled ? "activo (60 s)" : "inactivo"}</dd>
            </dl>
          )}
          <div className="mt-3"><Logs /></div>
        </Panel>
      </div>
    </div>
  );
}
