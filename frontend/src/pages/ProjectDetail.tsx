import { Archive, ArchiveRestore, ExternalLink, GitBranch, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, errorMessage } from "@/api/client";
import { useApiMutation, useChecklists, useNotes, useProject, useProjectHistory, useTasks } from "@/api/hooks";
import type { Note, ProjectStatus, RepoOverview } from "@/api/types";
import { Badge, Button, Checkbox, ConfirmDialog, Dialog, EmptyState, Field, ErrorState, Input, Loading, Panel, Progress, Select, Tabs } from "@/components/ui";
import { ProjectCode, ProjectVersions } from "@/features/DevWork";
import { PriorityBadge, ProjectStatusBadge, TaskRow } from "@/features/common";
import { ProjectFormDialog, TaskFormDialog } from "@/features/forms";
import { fmtDate, fmtDateTime, fmtRelative, NOTE_KIND, PROJECT_STATUS } from "@/lib/utils";

function GitHubPanel({ url }: { url: string }) {
  const [data, setData] = useState<RepoOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      setData(await api.post<RepoOverview>("/api/integrations/github/repo", { url }));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setLoading(false);
    }
  };
  return (
    <div className="mt-2 rounded-md border border-line bg-bg-2/60 p-2.5">
      {!data && !err && (
        <Button size="sm" variant="ghost" loading={loading} onClick={load} icon={<RefreshCw className="h-3.5 w-3.5" />}>
          Consultar GitHub
        </Button>
      )}
      {err && (
        <div className="text-xs text-danger">
          {err} <Link to="/integrations" className="text-primary underline">Configurar integração</Link>
        </div>
      )}
      {data && (
        <div className="text-xs">
          <div className="flex flex-wrap items-center gap-2 text-text-2">
            <span className="font-medium text-text">{data.repo.full_name}</span>
            {data.repo.private && <Badge>privado</Badge>}
            <span>★ {data.repo.stars}</span>
            <span>{data.repo.open_issues} issues/PRs abertos</span>
            <span>branch {data.repo.default_branch}</span>
            <span className="text-muted">push {fmtRelative(data.repo.pushed_at)}</span>
          </div>
          <ul className="mt-1.5">
            {data.commits.map((c) => (
              <li key={c.sha} className="truncate">
                <a href={c.url} target="_blank" rel="noreferrer" className="font-mono text-primary">{c.sha}</a>{" "}
                <span className="text-text-2">{c.message}</span> <span className="text-muted">— {c.author}</span>
              </li>
            ))}
          </ul>
          <div className="mt-1 text-[10.5px] text-muted">Fonte: {data.source} · obtido {fmtRelative(data.fetched_at)}</div>
        </div>
      )}
    </div>
  );
}

export default function ProjectDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: p, isLoading, error, refetch } = useProject(id);
  const tasks = useTasks({ project_id: id, include_archived: false });
  const notes = useNotes({ project_id: id });
  const checklists = useChecklists({ project_id: id });
  const history = useProjectHistory(id);
  const [tab, setTab] = useState<"tasks" | "code" | "versions" | "notes" | "checklists" | "history">("tasks");
  const [editing, setEditing] = useState(false);
  const [newTask, setNewTask] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [milestone, setMilestone] = useState("");
  const [link, setLink] = useState<{ url: string; title: string; kind?: string }>({ url: "", title: "", kind: "link" });
  const [showDone, setShowDone] = useState(true);
  const inv = [["projects"], ["tasks"]];

  const [blockReason, setBlockReason] = useState<string | null>(null);
  const setStatus = useApiMutation(
    ({ status, reason }: { status: ProjectStatus; reason?: string }) =>
      api.patch(`/api/projects/${id}`, { status, ...(reason ? { blocked_reason: reason } : {}) }),
    { invalidate: inv, success: "Estado actualizado.", onSuccess: () => setBlockReason(null) },
  );
  const archive = useApiMutation((archived: boolean) => api.post(`/api/projects/${id}/archive`, { archived }), {
    invalidate: inv,
    success: (_, a) => (a ? "Projecto arquivado." : "Projecto reactivado."),
  });
  const del = useApiMutation(() => api.del(`/api/projects/${id}`, { confirm: true }), {
    invalidate: inv,
    success: "Projecto eliminado.",
    onSuccess: () => navigate("/projects"),
  });
  const addMilestone = useApiMutation(() => api.post(`/api/projects/${id}/milestones`, { title: milestone }), {
    invalidate: inv,
    onSuccess: () => setMilestone(""),
  });
  const toggleMilestone = useApiMutation(
    (m: { id: string; title: string; due_date: string | null; done: boolean }) => api.put(`/api/milestones/${m.id}`, m),
    { invalidate: inv },
  );
  const delMilestone = useApiMutation((mid: string) => api.del(`/api/milestones/${mid}`), { invalidate: inv });
  const addLink = useApiMutation(() => api.post(`/api/projects/${id}/links`, link), {
    invalidate: inv,
    success: "Link adicionado.",
    onSuccess: () => setLink({ url: "", title: "", kind: link.kind }),
  });
  const delLink = useApiMutation((lid: string) => api.del(`/api/links/${lid}`), { invalidate: inv });
  const newNote = useApiMutation(() => api.post<Note>("/api/notes", { title: `Nota — ${p?.name ?? ""}`, project_id: id }), {
    invalidate: [["notes"]],
    onSuccess: (n) => navigate(`/notes/${n.id}`),
  });

  if (isLoading) return <Loading />;
  if (error || !p) return <ErrorState error={error} onRetry={() => void refetch()} />;
  const prog = p.progress;
  const visibleTasks = (tasks.data?.items ?? []).filter((t) => showDone || t.status !== "done");

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to="/projects" className="text-xs text-muted hover:text-text">← Projectos</Link>
          <h1 className="mt-1 text-xl font-semibold">{p.name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
            <ProjectStatusBadge status={p.status} />
            <PriorityBadge priority={p.priority} />
            {p.category && <Badge>{p.category}</Badge>}
            <span>Início {fmtDate(p.start_date)} · Fim {fmtDate(p.due_date)}</span>
            {p.stale && <Badge tone="amber">Sem actividade há 14+ dias</Badge>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select aria-label="Alterar estado" className="w-36" value={p.status} onChange={(e) => {
            const st = e.target.value as ProjectStatus;
            if (st === "blocked") setBlockReason(p.blocked_reason);
            else setStatus.mutate({ status: st });
          }}>
            {Object.entries(PROJECT_STATUS).filter(([k]) => k !== "archived").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            {p.status === "archived" && <option value="archived">Arquivado</option>}
          </Select>
          <Button onClick={() => setEditing(true)} icon={<Pencil className="h-3.5 w-3.5" />}>Editar</Button>
          {p.archived_at ? (
            <Button onClick={() => archive.mutate(false)} icon={<ArchiveRestore className="h-3.5 w-3.5" />}>Reactivar</Button>
          ) : (
            <Button onClick={() => archive.mutate(true)} icon={<Archive className="h-3.5 w-3.5" />}>Arquivar</Button>
          )}
          <Button variant="danger" onClick={() => setConfirmDelete(true)} icon={<Trash2 className="h-3.5 w-3.5" />}>Eliminar</Button>
        </div>
      </div>

      {p.status === "blocked" && (
        <div role="alert" className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-[13px] text-danger">
          Bloqueado: {p.blocked_reason || "motivo não indicado"}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Visão geral" className="lg:col-span-2">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="md:col-span-3">
              {p.description ? (
                <div className="prose-uanji text-[13px] text-text-2"><ReactMarkdown>{p.description}</ReactMarkdown></div>
              ) : (
                <p className="text-[13px] text-muted">Sem descrição.</p>
              )}
            </div>
            <div className="md:col-span-1">
              <div className="hud-label mb-1">Progresso</div>
              {prog?.percent == null ? (
                <p className="text-xs text-muted">Sem tarefas — progresso não mensurável.</p>
              ) : (
                <>
                  <div className="font-mono text-2xl text-primary">{prog.percent}%</div>
                  <Progress value={prog.percent} />
                  <p className="mt-1 text-xs text-muted">{prog.tasks_done} de {prog.tasks_total} tarefas · {prog.overdue_tasks} atrasada(s)</p>
                </>
              )}
            </div>
            <div>
              <div className="hud-label mb-1">Objectivos</div>
              <p className="whitespace-pre-wrap text-[13px] text-text-2">{p.objectives || "—"}</p>
            </div>
            <div>
              <div className="hud-label mb-1">Resultados esperados</div>
              <p className="whitespace-pre-wrap text-[13px] text-text-2">{p.expected_results || "—"}</p>
            </div>
          </div>
        </Panel>

        <Panel title={`Marcos (${prog?.milestones_done ?? 0}/${prog?.milestones_total ?? 0})`}>
          <ul className="mb-2 flex flex-col gap-1">
            {p.milestones.map((m) => (
              <li key={m.id} className="group flex items-center gap-2">
                <Checkbox
                  checked={!!m.done_at}
                  onChange={(done) => toggleMilestone.mutate({ id: m.id, title: m.title, due_date: m.due_date, done })}
                  label={<span className={m.done_at ? "text-muted line-through" : "text-text"}>{m.title}</span>}
                />
                <button type="button" className="ml-auto opacity-0 group-hover:opacity-100 focus:opacity-100" onClick={() => delMilestone.mutate(m.id)} aria-label={`Remover marco ${m.title}`}>
                  <Trash2 className="h-3.5 w-3.5 text-muted hover:text-danger" />
                </button>
              </li>
            ))}
            {p.milestones.length === 0 && <li className="text-xs text-muted">Sem marcos definidos.</li>}
          </ul>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (milestone.trim()) addMilestone.mutate(undefined); }}>
            <Input aria-label="Novo marco" placeholder="Novo marco" value={milestone} onChange={(e) => setMilestone(e.target.value)} />
            <Button type="submit" size="icon" aria-label="Adicionar marco" loading={addMilestone.isPending}><Plus className="h-4 w-4" /></Button>
          </form>

          <div className="hud-label mb-1 mt-4">Repositórios e links</div>
          <ul className="flex flex-col gap-2">
            {p.links.map((l) => (
              <li key={l.id} className="text-[13px]">
                <div className="group flex items-center gap-2">
                  {l.kind === "github" || l.kind === "folder" ? <GitBranch className="h-3.5 w-3.5 text-text-2" /> : <ExternalLink className="h-3.5 w-3.5 text-text-2" />}
                  {l.kind === "folder" ? (
                    <span className="truncate text-text-2" title={l.url}>{l.title} <span className="text-[11px] text-muted">(pasta local)</span></span>
                  ) : (
                    <a href={l.url} target="_blank" rel="noreferrer" className="truncate text-primary hover:underline">{l.title}</a>
                  )}
                  <button type="button" className="ml-auto opacity-0 group-hover:opacity-100 focus:opacity-100" onClick={() => delLink.mutate(l.id)} aria-label={`Remover link ${l.title}`}>
                    <Trash2 className="h-3.5 w-3.5 text-muted hover:text-danger" />
                  </button>
                </div>
                {l.kind === "github" && <GitHubPanel url={l.url} />}
              </li>
            ))}
          </ul>
          <form className="mt-2 flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); if (link.url) addLink.mutate(undefined); }}>
            <div className="flex gap-2">
              <Select aria-label="Tipo de link" className="w-40" value={link.kind ?? "link"} onChange={(e) => setLink({ ...link, kind: e.target.value })}>
                <option value="link">Link / GitHub</option>
                <option value="folder">Pasta local (Git)</option>
                <option value="docs">Documentação</option>
              </Select>
              <Input aria-label="URL" placeholder={link.kind === "folder" ? "~/Documents/Projectos/q360-backend" : "https://github.com/dono/repositorio"} value={link.url} onChange={(e) => setLink({ ...link, url: e.target.value })} />
            </div>
            <div className="flex gap-2">
              <Input aria-label="Título do link" placeholder="Título (opcional)" value={link.title} onChange={(e) => setLink({ ...link, title: e.target.value })} />
              <Button type="submit" loading={addLink.isPending}>Adicionar</Button>
            </div>
          </form>
        </Panel>
      </div>

      <Panel
        title={
          <Tabs value={tab} onChange={setTab} items={[
            { value: "tasks", label: `Tarefas (${tasks.data?.total ?? 0})` },
            { value: "code", label: "Código" },
            { value: "versions", label: "Versões" },
            { value: "notes", label: `Notas e decisões (${notes.data?.total ?? 0})` },
            { value: "checklists", label: `Checklists (${checklists.data?.length ?? 0})` },
            { value: "history", label: "Histórico" },
          ]} />
        }
        actions={
          tab === "tasks" ? (
            <>
              <Checkbox checked={showDone} onChange={setShowDone} label="Mostrar concluídas" />
              <Button size="sm" variant="primary" onClick={() => setNewTask(true)} icon={<Plus className="h-3.5 w-3.5" />}>Tarefa</Button>
            </>
          ) : tab === "notes" ? (
            <Button size="sm" variant="primary" loading={newNote.isPending} onClick={() => newNote.mutate(undefined)} icon={<Plus className="h-3.5 w-3.5" />}>Nota</Button>
          ) : tab === "checklists" ? (
            <Link to="/templates"><Button size="sm" variant="ghost">Aplicar modelo</Button></Link>
          ) : null
        }
      >
        {tab === "tasks" &&
          (tasks.isLoading ? <Loading /> : visibleTasks.length === 0 ? <EmptyState title="Sem tarefas neste projecto." /> : (
            <ul>{visibleTasks.map((t) => <TaskRow key={t.id} task={t} showProject={false} />)}</ul>
          ))}
        {tab === "notes" &&
          (notes.data?.items.length ? (
            <ul className="divide-y divide-line/60">
              {notes.data.items.map((n) => (
                <li key={n.id} className="py-2">
                  <Link to={`/notes/${n.id}`} className="text-[13px] text-text hover:text-primary">{n.title}</Link>
                  <span className="ml-2"><Badge tone={n.kind === "decision" ? "amber" : "neutral"}>{NOTE_KIND[n.kind]}</Badge></span>
                  <p className="truncate text-xs text-muted">{n.excerpt}</p>
                </li>
              ))}
            </ul>
          ) : <EmptyState title="Sem notas associadas." description="Registe decisões, ideias e documentação técnica deste projecto." />)}
        {tab === "checklists" &&
          (checklists.data?.length ? (
            <ul className="flex flex-col gap-2">
              {checklists.data.map((c) => (
                <li key={c.id} className="flex items-center gap-3">
                  <Link to={`/templates/${c.id}`} className="min-w-0 flex-1 truncate text-[13px] text-text hover:text-primary">{c.title}</Link>
                  <div className="w-40"><Progress value={c.percent} tone="amber" /></div>
                  <span className="w-10 text-right font-mono text-xs">{c.percent}%</span>
                </li>
              ))}
            </ul>
          ) : <EmptyState title="Sem checklists." />)}
        {tab === "code" && <ProjectCode projectId={p.id} />}
        {tab === "versions" && <ProjectVersions projectId={p.id} />}
        {tab === "history" && (
          <ul className="flex flex-col">
            {history.data?.map((a) => (
              <li key={a.id} className="flex gap-3 border-b border-line/50 py-1.5 text-[12.5px] last:border-0">
                <span className="w-32 shrink-0 font-mono text-[11px] text-muted">{fmtDateTime(a.created_at)}</span>
                <span className="text-text-2">{a.summary}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <ProjectFormDialog open={editing} onClose={() => setEditing(false)} project={p} />
      <TaskFormDialog open={newTask} onClose={() => setNewTask(false)} defaults={{ project_id: p.id }} />
      <Dialog
        open={blockReason !== null}
        onClose={() => setBlockReason(null)}
        title="Marcar projecto como bloqueado"
        footer={
          <>
            <Button variant="ghost" onClick={() => setBlockReason(null)}>Cancelar</Button>
            <Button variant="danger" disabled={!blockReason?.trim()} loading={setStatus.isPending}
              onClick={() => setStatus.mutate({ status: "blocked", reason: blockReason ?? "" })}>
              Bloquear
            </Button>
          </>
        }
      >
        <Field label="Motivo do bloqueio" htmlFor="block-reason">
          <Input id="block-reason" autoFocus value={blockReason ?? ""} onChange={(e) => setBlockReason(e.target.value)} />
        </Field>
      </Dialog>
      <ConfirmDialog
        open={confirmDelete}
        title="Eliminar projecto"
        message={<>Eliminar «{p.name}» é irreversível. As tarefas e notas associadas são mantidas mas ficam sem projecto. Para preservar o histórico, prefira <strong>Arquivar</strong>.</>}
        confirmLabel="Eliminar definitivamente"
        loading={del.isPending}
        onConfirm={() => del.mutate(undefined)}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  );
}
