import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Eye,
  EyeOff,
  LayoutGrid,
  BarChart3,
  BookOpen,
  Bot,
  Calendar,
  CheckSquare,
  FolderKanban,
  FolderPlus,
  Info,
  OctagonAlert,
  Play,
  Plug,
  Server,
  Square,
  Workflow,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useAgenda, useApiMutation, useAutomations, useDashboard, useDiagnostics, useHealth, useIntegrations, useNotes, useSettings } from "@/api/hooks";
import type { AppSettings, CardId, CardLayout, CardSize, FocusSession } from "@/api/types";
import { TrendArea } from "@/components/charts";
import { CoreOrb, useCoreState } from "@/components/CoreOrb";
import { HoloCard, HoloRow, Ring } from "@/components/holo";
import { Button, EmptyState, ErrorState, Loading, Panel } from "@/components/ui";
import { TaskRow } from "@/features/common";
import { AssistantInput, ListeningToggle, MicButton, SpeechControls, TurnView } from "@/features/assistant";
import { ProjectFormDialog } from "@/features/forms";
import { adaptiveOrder, CARD_LABEL, DEFAULT_CARDS, moveCard, normalizeLayout, SIZE_CLASS, SIZE_LABEL, updateCard } from "@/features/dashboard-layout";
import { appearanceOf } from "@/lib/appearance";
import { cn, fmtBytes, fmtMinutes, fmtRelative, isoDay, NOTE_KIND } from "@/lib/utils";
import { sendMessage, useVoice } from "@/lib/voice";

function greeting(d = new Date()): string {
  const h = d.getHours();
  return h < 12 ? "Bom dia" : h < 19 ? "Boa tarde" : "Boa noite";
}

function FocusControl({ active }: { active: FocusSession | null }) {
  const start = useApiMutation(() => api.post("/api/focus/start", {}), { success: "Sessão de foco iniciada." });
  const stop = useApiMutation(() => api.post<FocusSession>("/api/focus/stop"), {
    success: (s) => `Sessão registada: ${Math.round(s.duration_seconds / 60)} min.`,
  });
  return active ? (
    <Button variant="amber" size="sm" loading={stop.isPending} onClick={() => stop.mutate(undefined)} icon={<Square className="h-3.5 w-3.5" />}>
      Terminar foco (desde {new Date(active.started_at).toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" })})
    </Button>
  ) : (
    <Button variant="secondary" size="sm" loading={start.isPending} onClick={() => start.mutate(undefined)} icon={<Play className="h-3.5 w-3.5" />}>
      Iniciar sessão de foco
    </Button>
  );
}

const Unavailable = () => <p className="text-[12px] text-muted">Dados indisponíveis de momento.</p>;

// --------------------------------------------------------------------------- Cards secundários (dados próprios)

function AgendaCard() {
  const today = isoDay(new Date());
  const { data, error } = useAgenda(today, 1);
  const open = data?.tasks.filter((t) => t.status !== "done") ?? [];
  const events = data?.events ?? [];
  return (
    <HoloCard title="Agenda de hoje" icon={<Calendar />} to="/agenda" metric={data ? events.length : undefined} metricLabel={data ? `compromisso(s) · ${open.length} prazo(s)` : undefined}>
      {error ? <Unavailable /> : (
        <ul>
          {events.slice(0, 4).map((e) => (
            <HoloRow key={e.id} to={`/agenda?event=${e.id}`}>
              <span className="font-mono text-[11px] text-primary">{new Date(e.start_at).toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" })}</span>
              <span className="truncate">{e.title}</span>
            </HoloRow>
          ))}
          {open.slice(0, 3).map((t) => (
            <HoloRow key={t.id} to={`/tasks/${t.id}`} tone={t.overdue ? "danger" : undefined}>
              <span className="font-mono text-[11px] text-amber">prazo</span>
              <span className="truncate">{t.title}</span>
            </HoloRow>
          ))}
          {data && !events.length && !open.length && <li className="text-[12px] text-muted">Sem compromissos nem prazos hoje.</li>}
        </ul>
      )}
    </HoloCard>
  );
}

function KnowledgeCard() {
  const { data, error } = useNotes({});
  return (
    <HoloCard title="Conhecimento" icon={<BookOpen />} to="/notes" metric={data?.total} metricLabel={data ? "notas" : undefined}>
      {error ? <Unavailable /> : (
        <ul>
          {(data?.items ?? []).slice(0, 3).map((n) => (
            <HoloRow key={n.id} to={`/notes/${n.id}`}>
              <span className="shrink-0 text-[10px] uppercase tracking-wide text-gold">{NOTE_KIND[n.kind] ?? n.kind}</span>
              <span className="truncate">{n.title}</span>
            </HoloRow>
          ))}
          {data && data.items.length === 0 && <li className="text-[12px] text-muted">Sem notas. Diga «Regista uma ideia: …».</li>}
        </ul>
      )}
    </HoloCard>
  );
}

function AutomationsCard({ failedWeek }: { failedWeek: number }) {
  const { data, error } = useAutomations();
  const active = data?.filter((a) => a.enabled) ?? [];
  const next = active.filter((a) => a.next_run_at).sort((a, b) => (a.next_run_at! < b.next_run_at! ? -1 : 1))[0];
  const failing = data?.filter((a) => a.last_run?.status === "failed") ?? [];
  return (
    <HoloCard
      title="Automações"
      icon={<Workflow />}
      to="/automations"
      tone={failing.length || failedWeek ? "danger" : "primary"}
      metric={data ? active.length : undefined}
      metricLabel={data ? `activa(s) de ${data.length}` : undefined}
    >
      {error ? <Unavailable /> : (
        <ul>
          {next && (
            <HoloRow to={`/automations/${next.id}`}>
              <span className="text-[11px] text-muted">próxima</span>
              <span className="truncate">{next.name}</span>
              <span className="ml-auto shrink-0 font-mono text-[11px]">{fmtRelative(next.next_run_at)}</span>
            </HoloRow>
          )}
          {failing.slice(0, 2).map((a) => (
            <HoloRow key={a.id} to={`/automations/${a.id}`} tone="danger">
              <OctagonAlert className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">Falhou: {a.name}</span>
            </HoloRow>
          ))}
          {data && !next && !failing.length && <li className="text-[12px] text-muted">{data.length ? "Sem execuções agendadas." : "Sem automações."}</li>}
        </ul>
      )}
    </HoloCard>
  );
}

function IntegrationsCard() {
  const { data, error } = useIntegrations();
  const connected = data?.filter((i) => i.status === "connected").length ?? 0;
  return (
    <HoloCard title="Integrações" icon={<Plug />} to="/integrations" tone={data?.some((i) => i.status === "error") ? "danger" : "primary"} metric={data ? connected : undefined} metricLabel={data ? `ligada(s) de ${data.length}` : undefined}>
      {error ? <Unavailable /> : (
        <ul>
          {(data ?? []).map((i) => (
            <HoloRow key={i.provider} tone={i.status === "error" ? "danger" : undefined}>
              <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", i.status === "connected" ? "bg-success" : i.status === "error" ? "bg-danger" : "bg-neutral")} />
              <span className="truncate">{i.label}</span>
              <span className="ml-auto shrink-0 text-[11px] text-muted">{{ connected: "ligada", error: "erro", not_configured: "não configurada" }[i.status]}</span>
            </HoloRow>
          ))}
        </ul>
      )}
    </HoloCard>
  );
}

function SystemCard({ backendDown }: { backendDown: boolean }) {
  const { data, error } = useDiagnostics();
  const voice = useVoice((s) => s.status);
  const outdated = data && data.schema_revision !== data.schema_head;
  return (
    <HoloCard title="Sistema" icon={<Server />} to="/settings" tone={backendDown || outdated ? "danger" : "success"} metric={backendDown ? "OFF" : "ON"} metricLabel={backendDown ? "backend sem resposta" : "backend local"}>
      {error || !data ? (backendDown ? <Unavailable /> : null) : (
        <ul>
          <HoloRow>
            <span className="text-muted">Base de dados</span>
            <span className="ml-auto font-mono text-[11px]">{fmtBytes(data.db_size_bytes)}</span>
          </HoloRow>
          <HoloRow>
            <span className="text-muted">Disco livre</span>
            <span className="ml-auto font-mono text-[11px]">{fmtBytes(data.disk_free_bytes)}</span>
          </HoloRow>
          <HoloRow tone={data.vault.secure ? undefined : "danger"}>
            <span className="text-muted">Cofre</span>
            <span className="ml-auto text-[11px]">{data.vault.secure ? "Keychain" : "inseguro"}</span>
          </HoloRow>
          <HoloRow>
            <span className="text-muted">Voz local</span>
            <span className="ml-auto text-[11px]">{voice ? (voice.stt.model_installed ? "pronta" : "modelo por instalar") : "—"}</span>
          </HoloRow>
          <HoloRow>
            <span className="text-muted">Conectividade</span>
            <span className="ml-auto text-[11px]">funciona offline</span>
          </HoloRow>
        </ul>
      )}
    </HoloCard>
  );
}

function AssistantCard({ backendDown }: { backendDown: boolean }) {
  const core = useCoreState(backendDown);
  const status = useVoice((s) => s.status);
  const entries = useVoice((s) => s.entries);
  const partial = useVoice((s) => s.partial);
  const last = entries.slice(-2);
  return (
    <section className="holo-card uanji-pattern h-full" aria-label="Assistente UANJI">
      <div className="holo-scan" aria-hidden />
      <div className="relative z-10 flex flex-1 flex-col items-center gap-2.5 p-4">
        <div className="flex w-full items-center gap-2">
          <Bot className="h-4 w-4 text-primary" />
          <Link to="/assistant" className="hud-label text-text-2 hover:text-text">Assistente UANJI</Link>
          <span className="ml-auto text-[12px] text-text-2">{greeting()}.</span>
        </div>
        <CoreOrb state={core} size={176} />
        <div className="flex items-center gap-2">
          <MicButton status={status} />
          <ListeningToggle status={status} />
        </div>
        <SpeechControls status={status} compact />
        <div className="flex w-full flex-col gap-2">
          {partial && <p className="text-right text-[12.5px] italic text-electric">{partial}…</p>}
          {last.map((e) => (
            <TurnView key={e.id} entry={e} compact />
          ))}
        </div>
        <div className="mt-auto w-full">
          <AssistantInput placeholder="Pergunte ou dê uma ordem ao UANJI…" />
          <div className="mt-1.5 flex flex-wrap gap-1">
            <Button size="sm" variant="ghost" onClick={() => void sendMessage("faz o relatório do meu dia", true).catch(() => undefined)}>
              Ouvir relatório do dia
            </Button>
            <Button size="sm" variant="ghost" onClick={() => void sendMessage("diz-me o que devo fazer a seguir", true).catch(() => undefined)}>
              O que faço a seguir?
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------- Cards com dados do painel

type Dash = NonNullable<ReturnType<typeof useDashboard>["data"]>;

function TasksCard({ data }: { data: Dash }) {
  const c = data.counters;
  return (
    <HoloCard
      title="Tarefas"
      icon={<CheckSquare />}
      to="/tasks"
      tone={c.overdue_tasks ? "danger" : "primary"}
      emphasis={c.overdue_tasks ? "high" : "normal"}
      metric={c.pending_tasks}
      metricLabel={
        <>
          pendentes · {c.done_today} concluídas hoje
          {c.overdue_tasks > 0 && (
            <Link to="/tasks?due=overdue" className="ml-1 text-danger hover:underline">
              · {c.overdue_tasks} atrasadas
            </Link>
          )}
        </>
      }
    >
      {data.priority_tasks.length === 0 ? (
        <p className="text-[12.5px] text-muted">Sem tarefas em aberto.</p>
      ) : (
        <ul>
          {data.priority_tasks.slice(0, 5).map((t) => (
            <TaskRow key={t.id} task={t} />
          ))}
        </ul>
      )}
    </HoloCard>
  );
}

function ProjectsCard({ data, onNew }: { data: Dash; onNew: () => void }) {
  const c = data.counters;
  const blocked = data.active_projects.filter((p) => p.status === "blocked");
  return (
    <HoloCard
      title="Projectos"
      icon={<FolderKanban />}
      to="/projects"
      tone={blocked.length ? "amber" : "primary"}
      metric={c.active_projects}
      metricLabel={`activos${c.blocked_projects ? ` · ${c.blocked_projects} bloqueado(s)` : ""}`}
      actions={<Button size="sm" variant="ghost" onClick={onNew}>Novo</Button>}
    >
      {data.active_projects.length === 0 ? (
        <p className="text-[12.5px] text-muted">Nenhum projecto activo.</p>
      ) : (
        <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
          {data.active_projects.slice(0, 6).map((p) => (
            <li key={p.id}>
              <Link to={`/projects/${p.id}`} className="flex items-center gap-2 rounded-md border border-line/60 px-2 py-1.5 hover:border-primary/40">
                <Ring value={p.progress?.percent ?? null} size={38} tone={p.status === "blocked" ? "danger" : p.stale ? "amber" : "primary"} label={`Progresso de ${p.name}`} />
                <span className="min-w-0">
                  <span className="block truncate text-[12.5px] text-text">{p.name}</span>
                  <span className={cn("block text-[10.5px]", p.status === "blocked" ? "text-danger" : p.stale ? "text-amber" : "text-muted")}>
                    {p.status === "blocked" ? "bloqueado" : p.stale ? "sem actividade" : fmtRelative(p.last_activity_at)}
                    {p.progress && p.progress.overdue_tasks > 0 ? ` · ${p.progress.overdue_tasks} atrasada(s)` : ""}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </HoloCard>
  );
}

function AlertsCard({ data }: { data: Dash }) {
  return (
    <HoloCard
      title="Alertas e recomendações"
      icon={<AlertTriangle />}
      tone={data.alerts.some((a) => a.level === "error") ? "danger" : data.alerts.length ? "amber" : "success"}
      emphasis={data.alerts.length ? "high" : "normal"}
      metric={data.alerts.length}
      metricLabel={data.alerts.length ? "a tratar" : "tudo em ordem"}
    >
      {data.alerts.length === 0 ? (
        <p className="text-[12.5px] text-muted">Sem alertas. Nada atrasado, bloqueado ou parado.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {data.alerts.map((a, i) => (
            <li key={i}>
              <Link
                to={a.link}
                className={cn(
                  "flex gap-2 rounded-md border px-2.5 py-1.5 text-[12.5px] hover:bg-surface-3",
                  a.level === "error" ? "border-danger/40" : a.level === "warning" ? "border-amber/30" : "border-line",
                )}
              >
                {a.level === "error" ? (
                  <OctagonAlert className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
                ) : a.level === "warning" ? (
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber" />
                ) : (
                  <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                )}
                <span>
                  <span className="text-text">{a.title}</span>
                  {a.body && <span className="block text-xs text-muted">{a.body}</span>}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </HoloCard>
  );
}

function PerformanceCard({ data }: { data: Dash }) {
  const c = data.counters;
  return (
    <HoloCard title="Desempenho" icon={<BarChart3 />} to="/metrics" tone="success" metric={c.done_week} metricLabel={`concluídas em 7 dias · foco ${fmtMinutes(c.focus_minutes_week)}`}>
      {data.trend.length > 0 && (
        <TrendArea
          data={data.trend.map((d) => ({ ...d, label: d.date.slice(5).split("-").reverse().join("/") }))}
          xKey="label"
          series={[
            { key: "done", label: "Concluídas" },
            { key: "created", label: "Criadas" },
          ]}
          height={70}
        />
      )}
      <div className="mt-1.5">
        <FocusControl active={data.focus_active} />
      </div>
    </HoloCard>
  );
}

// --------------------------------------------------------------------------- Página

function EditBar({ card, index, total, layout, setLayout }: { card: CardLayout; index: number; total: number; layout: CardLayout[]; setLayout: (l: CardLayout[]) => void }) {
  const label = CARD_LABEL[card.id];
  return (
    <div className="absolute right-2 top-2 z-20 flex items-center gap-0.5 rounded-md border border-line-strong bg-bg/90 p-0.5 shadow">
      <button type="button" className="rounded p-1 hover:bg-surface-3 disabled:opacity-30" disabled={index === 0} aria-label={`Mover ${label} para trás`} onClick={() => setLayout(moveCard(layout, card.id, -1))}>
        <ArrowLeft className="h-3.5 w-3.5" />
      </button>
      <button type="button" className="rounded p-1 hover:bg-surface-3 disabled:opacity-30" disabled={index === total - 1} aria-label={`Mover ${label} para a frente`} onClick={() => setLayout(moveCard(layout, card.id, 1))}>
        <ArrowRight className="h-3.5 w-3.5" />
      </button>
      <select
        aria-label={`Tamanho de ${label}`}
        className="h-6 rounded bg-surface-3 px-1 text-[11px] text-text"
        value={card.size}
        onChange={(e) => setLayout(updateCard(layout, card.id, { size: e.target.value as CardSize }))}
      >
        {(Object.keys(SIZE_LABEL) as CardSize[]).map((sz) => (
          <option key={sz} value={sz}>{SIZE_LABEL[sz]}</option>
        ))}
      </select>
      <button type="button" className="rounded p-1 hover:bg-surface-3" aria-label={`Esconder ${label}`} onClick={() => setLayout(updateCard(layout, card.id, { hidden: true }))}>
        <EyeOff className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export default function DashboardPage() {
  const { data, isLoading, error, refetch } = useDashboard();
  const health = useHealth();
  const settings = useSettings();
  const [newProject, setNewProject] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<CardLayout[] | null>(null);
  const appearance = appearanceOf(settings.data);
  const save = useApiMutation(
    (cards: CardLayout[]) => api.patch<AppSettings>("/api/settings", { values: { appearance: { ...appearance, cards, layout_mode: "custom" } } }),
    { invalidate: [["settings"]], success: "Disposição do painel guardada.", onSuccess: () => { setEditing(false); setDraft(null); } },
  );

  if (isLoading) return <Loading label="A carregar o centro de comando…" />;
  if (error || !data) return <ErrorState error={error} onRetry={() => void refetch()} />;
  const failedWeek = data.alerts.filter((a) => a.link === "/automations" && a.level === "error").length;
  const saved = normalizeLayout(appearance.cards);
  const urgent: CardId[] = [...(data.alerts.length ? (["alerts"] as CardId[]) : []), ...(data.counters.overdue_tasks ? (["tasks"] as CardId[]) : [])];
  const layout = draft ?? (appearance.layout_mode === "adaptive" ? adaptiveOrder(saved, settings.data?.usage ?? {}, urgent) : saved);
  const visible = layout.filter((c) => !c.hidden);
  const hidden = layout.filter((c) => c.hidden);

  const render = (id: CardId) => {
    switch (id) {
      case "tasks": return <TasksCard data={data} />;
      case "projects": return <ProjectsCard data={data} onNew={() => setNewProject(true)} />;
      case "assistant": return <AssistantCard backendDown={health.isError} />;
      case "alerts": return <AlertsCard data={data} />;
      case "agenda": return <AgendaCard />;
      case "performance": return <PerformanceCard data={data} />;
      case "knowledge": return <KnowledgeCard />;
      case "automations": return <AutomationsCard failedWeek={failedWeek} />;
      case "integrations": return <IntegrationsCard />;
      case "system": return <SystemCard backendDown={health.isError} />;
    }
  };

  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-end gap-2">
        {appearance.layout_mode === "adaptive" && !editing && (
          <span className="mr-auto text-[11.5px] text-muted">Disposição adaptativa: os cards que mais usa aparecem primeiro; alertas e atrasos sobem sempre.</span>
        )}
        {editing ? (
          <>
            <span className="mr-auto text-[12px] text-text-2">Mova, redimensione ou esconda os cards. As alterações só ficam guardadas ao carregar em «Guardar».</span>
            <Button size="sm" variant="ghost" onClick={() => setDraft(DEFAULT_CARDS)}>Repor original</Button>
            <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setDraft(null); }}>Cancelar</Button>
            <Button size="sm" variant="primary" loading={save.isPending} onClick={() => save.mutate(layout)}>Guardar disposição</Button>
          </>
        ) : (
          <Button size="sm" variant="ghost" icon={<LayoutGrid className="h-3.5 w-3.5" />} onClick={() => { setDraft(layout); setEditing(true); }}>
            Personalizar painel
          </Button>
        )}
      </div>
      {editing && hidden.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-text-2">
          Escondidos:
          {hidden.map((c) => (
            <Button key={c.id} size="sm" variant="secondary" icon={<Eye className="h-3 w-3" />} onClick={() => setDraft(updateCard(layout, c.id, { hidden: false }))}>
              {CARD_LABEL[c.id]}
            </Button>
          ))}
        </div>
      )}

      {data.is_empty && (
        <Panel>
          <EmptyState
            icon={<FolderPlus className="h-8 w-8" />}
            title="O centro de comando está vazio"
            description="Comece por criar o primeiro projecto, ou diga ao assistente «Cria um projecto chamado …». Também pode criar um projecto a partir de um modelo (ex.: Desenvolvimento de uma API)."
            action={
              <div className="flex gap-2">
                <Button variant="primary" onClick={() => setNewProject(true)}>
                  Criar primeiro projecto
                </Button>
                <Link to="/templates">
                  <Button variant="ghost">Ver modelos</Button>
                </Link>
              </div>
            }
          />
        </Panel>
      )}

      <div className="grid grid-flow-row-dense gap-4 lg:grid-cols-2 xl:grid-cols-12">
        {visible.map((c, i) => (
          <div key={c.id} className={cn("relative flex min-w-0 flex-col [&>section]:flex-1", SIZE_CLASS[c.size], editing && "card-editing")}>
            {editing && <EditBar card={c} index={i} total={visible.length} layout={layout} setLayout={setDraft} />}
            {render(c.id)}
          </div>
        ))}
      </div>
      <ProjectFormDialog open={newProject} onClose={() => setNewProject(false)} />
    </div>
  );
}
