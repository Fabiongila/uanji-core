import { Eye, EyeOff, GitCommit, MonitorSmartphone, ShieldCheck, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useApiMutation, useSettings } from "@/api/hooks";
import type { ActivitySettings, ActivityStatus, ActivitySummary, AppSettings } from "@/api/types";
import { SimpleBars } from "@/components/charts";
import { HoloCard } from "@/components/holo";
import { Badge, Button, Checkbox, ConfirmDialog, EmptyState, Field, Input, Loading, PageHeader, Panel, Progress, Textarea } from "@/components/ui";

export function fmtDur(seconds: number): string {
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return `${h} h ${String(m % 60).padStart(2, "0")}`;
}

type Patterns = { days_with_data: number; avg_start: string | null; peak_hours: number[]; sentence: string };
type GitRepo = { repo: string; commits: { hash: string; message: string }[] };

function PrivacyPanel({ cfg }: { cfg: ActivitySettings }) {
  const [c, setC] = useState(cfg);
  const [confirmOn, setConfirmOn] = useState(false);
  const [wipe, setWipe] = useState(false);
  useEffect(() => setC(cfg), [cfg]);
  const qc = useQueryClient();
  const save = useApiMutation((values: Partial<AppSettings>) => api.patch<AppSettings>("/api/settings", { values }), {
    invalidate: [["settings"], ["activity"]],
    success: "Preferências de actividade guardadas.",
  });
  const del = useApiMutation(() => api.del<{ deleted: number }>("/api/activity", { confirm: true }), {
    invalidate: [["activity"]],
    success: (r) => `${r.deleted} registo(s) de actividade apagado(s).`,
    onSuccess: () => setWipe(false),
  });
  const toggle = (on: boolean) => save.mutate({ activity: { ...c, enabled: on } }, { onSuccess: () => void qc.invalidateQueries({ queryKey: ["activity"] }) });
  return (
    <Panel title="Privacidade e recolha">
      <div className="flex flex-col gap-3 text-[13px]">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant={cfg.enabled ? "primary" : "secondary"} icon={cfg.enabled ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />} onClick={() => (cfg.enabled ? toggle(false) : setConfirmOn(true))} loading={save.isPending}>
            {cfg.enabled ? "Monitor ligado — desligar" : "Ligar o monitor de actividade"}
          </Button>
          <Badge tone="success">
            <ShieldCheck className="h-3 w-3" /> Só local · sem teclas, capturas ou conteúdo
          </Badge>
        </div>
        <p className="text-[12px] text-muted">
          Regista a aplicação em primeiro plano a cada {c.sample_seconds} s, a pasta aberta no VS Code e, se quiser, o título da janela. A inactividade
          (mais de {Math.round(c.idle_seconds / 60)} min sem teclado/rato) não conta. Serve para o assistente responder com base no seu dia e para
          sugestões. Nada sai deste Mac.
        </p>
        <Checkbox checked={c.capture_titles} onChange={(v) => setC({ ...c, capture_titles: v })} label="Registar também o título das janelas (requer «Gravação de ecrã» nas Definições do Sistema)" />
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Amostra (s)" htmlFor="ac-s"><Input id="ac-s" type="number" min={5} max={120} value={c.sample_seconds} onChange={(e) => setC({ ...c, sample_seconds: Number(e.target.value) })} /></Field>
          <Field label="Inactivo após (min)" htmlFor="ac-i"><Input id="ac-i" type="number" min={1} max={60} value={Math.round(c.idle_seconds / 60)} onChange={(e) => setC({ ...c, idle_seconds: Number(e.target.value) * 60 })} /></Field>
          <Field label="Guardar (dias)" htmlFor="ac-r" hint="0 = sem limite"><Input id="ac-r" type="number" min={0} max={365} value={c.retention_days} onChange={(e) => setC({ ...c, retention_days: Number(e.target.value) })} /></Field>
        </div>
        <Field label="Aplicações nunca registadas (uma por linha)" htmlFor="ac-x">
          <Textarea id="ac-x" rows={3} value={c.excluded_apps.join("\n")} onChange={(e) => setC({ ...c, excluded_apps: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean) })} />
        </Field>
        <Field label="Pastas de projectos para ler os seus commits Git (uma por linha)" htmlFor="ac-g" hint="Ex.: ~/Documents/Projectos — lê só o histórico, nunca altera">
          <Textarea id="ac-g" rows={2} value={c.git_folders.join("\n")} onChange={(e) => setC({ ...c, git_folders: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean) })} />
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate({ activity: c })}>Guardar</Button>
          <Button variant="ghost" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setWipe(true)}>Apagar todo o registo</Button>
        </div>
      </div>
      <ConfirmDialog
        open={confirmOn}
        title="Ligar o monitor de actividade"
        confirmLabel="Ligar"
        onCancel={() => setConfirmOn(false)}
        onConfirm={() => {
          setConfirmOn(false);
          toggle(true);
        }}
        message={
          <div className="flex flex-col gap-2 text-[13px] text-text-2">
            <p>O UANJI CORE vai registar, enquanto estiver aberto, que aplicação usa e durante quanto tempo, para conhecer o seu dia e dar respostas e sugestões personalizadas.</p>
            <p>Não regista teclas, conteúdo, capturas de ecrã nem sites visitados. Os dados ficam só neste Mac, são apagados ao fim de {c.retention_days || "∞"} dias e pode desligar ou apagar tudo a qualquer momento.</p>
          </div>
        }
      />
      <ConfirmDialog open={wipe} title="Apagar registo de actividade" danger confirmLabel="Apagar" loading={del.isPending} message="Todo o registo de utilização do computador será eliminado." onConfirm={() => del.mutate(undefined)} onCancel={() => setWipe(false)} />
    </Panel>
  );
}

export default function ActivityPage() {
  const settings = useSettings();
  const status = useQuery({ queryKey: ["activity", "status"], queryFn: () => api.get<ActivityStatus>("/api/activity/status"), refetchInterval: 30_000 });
  const today = useQuery({ queryKey: ["activity", "today"], queryFn: () => api.get<ActivitySummary>("/api/activity/today"), refetchInterval: 60_000 });
  const patterns = useQuery({ queryKey: ["activity", "patterns"], queryFn: () => api.get<Patterns>("/api/activity/patterns") });
  const git = useQuery({ queryKey: ["activity", "git"], queryFn: () => api.get<GitRepo[]>("/api/activity/git"), staleTime: 120_000 });
  if (settings.isLoading || !settings.data) return <Loading />;
  const cfg = settings.data.activity;
  const t = today.data;
  const max = Math.max(1, ...(t?.categories.map((c) => c.seconds) ?? [1]));

  return (
    <div className="mx-auto flex max-w-[1300px] flex-col gap-4">
      <PageHeader
        title="Actividade"
        subtitle="O que o assistente sabe sobre o seu dia no computador — e como controla essa recolha."
        actions={<Badge tone={status.data?.running ? "success" : "neutral"}>{status.data?.running ? "Monitor activo" : "Monitor desligado"}</Badge>}
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <HoloCard title="Agora" icon={<MonitorSmartphone />} metric={status.data?.now?.app || "—"} metricLabel={status.data?.now?.context ? `pasta «${status.data.now.context}»` : undefined}>
          <p className="text-[12.5px] text-text-2">
            {status.data?.running
              ? status.data.now?.since
                ? `Nesta aplicação desde as ${new Date(status.data.now.since).toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" })}.`
                : "À espera da primeira amostra…"
              : "Ligue o monitor para o assistente saber o que está a fazer."}
          </p>
          {status.data?.last_error && <p className="mt-1 text-[12px] text-danger">{status.data.last_error}</p>}
        </HoloCard>
        <HoloCard title="Hoje" icon={<MonitorSmartphone />} tone="success" metric={t ? fmtDur(t.active_seconds) : undefined} metricLabel={t?.first_at ? `activo desde as ${t.first_at}` : "tempo activo"}>
          <p className="text-[12.5px] text-text-2">{t?.sentence}</p>
        </HoloCard>
        <HoloCard title="Os seus padrões" icon={<MonitorSmartphone />} tone="amber" metric={patterns.data?.avg_start ?? "—"} metricLabel="hora média de início">
          <p className="text-[12.5px] text-text-2">{patterns.data?.sentence}</p>
        </HoloCard>
      </div>

      {t && !t.has_data ? (
        <Panel>
          <EmptyState icon={<MonitorSmartphone className="h-8 w-8" />} title="Sem actividade registada hoje" description={cfg.enabled ? "Os dados aparecem aqui ao fim de alguns minutos." : "O monitor está desligado. Pode ligá-lo abaixo; os dados nunca saem deste Mac."} />
        </Panel>
      ) : t ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Por hora (minutos activos)">
            <SimpleBars data={t.hours.map((s, h) => ({ hora: `${h}h`, min: Math.round(s / 60) })).filter((_, h) => h >= 6 && h <= 23)} xKey="hora" yKey="min" label="Minutos" unit="min" height={180} />
          </Panel>
          <Panel title="Por tipo de actividade">
            <ul className="flex flex-col gap-2">
              {t.categories.map((c) => (
                <li key={c.category} className="text-[12.5px]">
                  <div className="mb-0.5 flex justify-between"><span className="text-text-2">{c.label}</span><span className="font-mono">{fmtDur(c.seconds)}</span></div>
                  <Progress value={Math.round((c.seconds / max) * 100)} />
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Aplicações">
            <ul>
              {t.apps.map((a) => (
                <li key={a.app} className="flex justify-between border-b border-line/50 py-1.5 text-[12.5px] last:border-0"><span>{a.app}</span><span className="font-mono text-text-2">{fmtDur(a.seconds)}</span></li>
              ))}
            </ul>
          </Panel>
          <Panel title="Projectos e pastas">
            <ul>
              {t.projects.map((p) => (
                <li key={p.id} className="flex justify-between border-b border-line/50 py-1.5 text-[12.5px]"><span>Projecto {p.name}</span><span className="font-mono text-text-2">{fmtDur(p.seconds)}</span></li>
              ))}
              {t.contexts.map((c) => (
                <li key={c.context} className="flex justify-between border-b border-line/50 py-1.5 text-[12.5px] last:border-0"><span className="text-text-2">Pasta «{c.context}»</span><span className="font-mono text-text-2">{fmtDur(c.seconds)}</span></li>
              ))}
              {!t.projects.length && !t.contexts.length && <li className="text-[12px] text-muted">Sem projectos identificados hoje.</li>}
            </ul>
          </Panel>
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <PrivacyPanel cfg={cfg} />
        <Panel title="Commits de hoje">
          {!cfg.git_folders.length ? (
            <p className="text-[12.5px] text-muted">Indique as pastas dos seus projectos em «Privacidade e recolha» para o assistente saber o que fez no Git.</p>
          ) : git.data?.length ? (
            <ul className="flex flex-col gap-2">
              {git.data.map((r) => (
                <li key={r.repo} className="text-[12.5px]">
                  <div className="font-semibold text-text">{r.repo} <span className="font-normal text-muted">· {r.commits.length} commit(s)</span></div>
                  <ul className="mt-0.5">
                    {r.commits.slice(0, 5).map((c) => (
                      <li key={c.hash} className="flex gap-1.5 text-text-2"><GitCommit className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" /><span className="font-mono text-[11px] text-muted">{c.hash}</span> {c.message}</li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[12.5px] text-muted">Sem commits seus hoje nas pastas indicadas.</p>
          )}
        </Panel>
      </div>
    </div>
  );
}
