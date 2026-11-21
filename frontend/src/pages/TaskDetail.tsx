import { TaskDevPanel } from "@/features/DevWork";
import { Archive, ArchiveRestore, Link2, Pencil, Play, Plus, RotateCcw, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "@/api/client";
import { useApiMutation, useChecklists, useNotes, useTask, useTasks } from "@/api/hooks";
import type { Checklist, Note } from "@/api/types";
import { Badge, Button, ConfirmDialog, EmptyState, ErrorState, Loading, Panel, Progress, Select } from "@/components/ui";
import { PriorityBadge, TaskRow, TaskStatusBadge, useTaskStatus } from "@/features/common";
import { TaskFormDialog } from "@/features/forms";
import { fmtDateTime, fmtMinutes } from "@/lib/utils";

export default function TaskDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: t, isLoading, error, refetch } = useTask(id);
  const all = useTasks({ project_id: t?.project_id ?? undefined });
  const notes = useNotes({ task_id: id });
  const checklists = useChecklists({ task_id: id });
  const status = useTaskStatus();
  const [editing, setEditing] = useState(false);
  const [newSub, setNewSub] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [dep, setDep] = useState("");
  const inv = [["tasks"], ["projects"]];

  const archive = useApiMutation((archived: boolean) => api.post(`/api/tasks/${id}/archive`, { archived }), {
    invalidate: inv,
    success: (_, a) => (a ? "Tarefa arquivada (continua no histórico)." : "Tarefa desarquivada."),
  });
  const del = useApiMutation(() => api.del(`/api/tasks/${id}`, { confirm: true }), {
    invalidate: inv,
    success: "Tarefa eliminada.",
    onSuccess: () => navigate("/tasks"),
  });
  const addDep = useApiMutation(() => api.post(`/api/tasks/${id}/dependencies`, { depends_on_id: dep }), {
    invalidate: inv,
    success: "Dependência adicionada.",
    onSuccess: () => setDep(""),
  });
  const rmDep = useApiMutation((d: string) => api.del(`/api/tasks/${id}/dependencies/${d}`), { invalidate: inv });
  const focus = useApiMutation(() => api.post("/api/focus/start", { task_id: id }), { success: "Sessão de foco iniciada para esta tarefa." });
  const newNote = useApiMutation(() => api.post<Note>("/api/notes", { title: `Notas — ${t?.title ?? ""}`, task_id: id, project_id: t?.project_id }), {
    invalidate: [["notes"]],
    onSuccess: (n) => navigate(`/notes/${n.id}`),
  });
  const newChecklist = useApiMutation(() => api.post<Checklist>("/api/checklists", { title: `Checklist — ${t?.title ?? ""}`, task_id: id }), {
    invalidate: [["checklists"]],
    onSuccess: (c) => navigate(`/templates/${c.id}`),
  });

  if (isLoading) return <Loading />;
  if (error || !t) return <ErrorState error={error} onRetry={() => void refetch()} />;
  const byId = new Map((all.data?.items ?? []).map((x) => [x.id, x]));
  const candidates = (all.data?.items ?? []).filter((x) => x.id !== t.id && !t.depends_on.includes(x.id));

  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to={t.project_id ? `/projects/${t.project_id}` : "/tasks"} className="text-xs text-muted hover:text-text">
            ← {t.project_name ?? "Tarefas"}
          </Link>
          <h1 className={`mt-1 text-xl font-semibold ${t.status === "done" ? "text-muted line-through" : ""}`}>
            {t.number != null && <span className="mr-2 font-mono text-sm font-normal text-muted">UJ-{t.number}</span>}
            {t.title}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
            <TaskStatusBadge status={t.status} />
            <PriorityBadge priority={t.priority} />
            {t.due_at && <span className={t.overdue ? "text-danger" : ""}>Prazo {fmtDateTime(t.due_at)}{t.overdue && " (atrasada)"}</span>}
            {t.estimate_minutes && <span>Estimativa {fmtMinutes(t.estimate_minutes)}</span>}
            {t.postponed_count > 0 && <Badge tone="amber">Adiada {t.postponed_count}×</Badge>}
            {t.archived_at && <Badge>Arquivada</Badge>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {t.status === "done" ? (
            <Button onClick={() => status.mutate({ id: t.id, status: "todo" })} icon={<RotateCcw className="h-3.5 w-3.5" />}>Reabrir</Button>
          ) : (
            <Button variant="primary" loading={status.isPending} onClick={() => status.mutate({ id: t.id, status: "done" })}>Concluir</Button>
          )}
          {t.status !== "done" && <Button onClick={() => focus.mutate(undefined)} icon={<Play className="h-3.5 w-3.5" />}>Foco</Button>}
          <Button onClick={() => setEditing(true)} icon={<Pencil className="h-3.5 w-3.5" />}>Editar</Button>
          <Button onClick={() => archive.mutate(!t.archived_at)} icon={t.archived_at ? <ArchiveRestore className="h-3.5 w-3.5" /> : <Archive className="h-3.5 w-3.5" />}>
            {t.archived_at ? "Desarquivar" : "Arquivar"}
          </Button>
          <Button variant="danger" onClick={() => setConfirmDelete(true)} icon={<Trash2 className="h-3.5 w-3.5" />}>Eliminar</Button>
        </div>
      </div>

      {t.status === "blocked" && (
        <div role="alert" className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-[13px] text-danger">Bloqueada: {t.blocked_reason}</div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Detalhes" className="lg:col-span-2">
          <div className="flex flex-col gap-4 text-[13px]">
            <div>
              <div className="hud-label mb-1">Descrição</div>
              <p className="whitespace-pre-wrap text-text-2">{t.description || "—"}</p>
            </div>
            <div>
              <div className="hud-label mb-1">Critérios de conclusão</div>
              <p className="whitespace-pre-wrap text-text-2">{t.completion_criteria || "Não definidos."}</p>
            </div>
            <div className="text-xs text-muted">
              Criada {fmtDateTime(t.created_at)} · Actualizada {fmtDateTime(t.updated_at)}
              {t.completed_at && ` · Concluída ${fmtDateTime(t.completed_at)}`}
            </div>
          </div>
        </Panel>
        <Panel title="Desenvolvimento e objectivos">
          <TaskDevPanel task={t} />
        </Panel>
        <Panel title="Dependências">
          <p className="mb-2 text-xs text-muted">Esta tarefa só pode ser concluída depois de:</p>
          <ul className="mb-2 flex flex-col gap-1">
            {t.depends_on.map((d) => {
              const x = byId.get(d);
              return (
                <li key={d} className="flex items-center gap-2 text-[13px]">
                  <Link2 className="h-3.5 w-3.5 text-amber" />
                  <Link to={`/tasks/${d}`} className={`truncate hover:text-primary ${x?.status === "done" ? "text-muted line-through" : "text-text"}`}>{x?.title ?? d}</Link>
                  <button type="button" className="ml-auto" onClick={() => rmDep.mutate(d)} aria-label="Remover dependência"><X className="h-3.5 w-3.5 text-muted hover:text-danger" /></button>
                </li>
              );
            })}
            {t.depends_on.length === 0 && <li className="text-xs text-muted">Sem dependências.</li>}
          </ul>
          <div className="flex gap-2">
            <Select aria-label="Adicionar dependência" value={dep} onChange={(e) => setDep(e.target.value)}>
              <option value="">Escolher tarefa…</option>
              {candidates.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
            </Select>
            <Button disabled={!dep} loading={addDep.isPending} onClick={() => addDep.mutate(undefined)}>Adicionar</Button>
          </div>
          <p className="mt-1 text-[11px] text-muted">Ciclos de dependências são recusados.</p>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel
          title={`Subtarefas (${t.subtasks_done}/${t.subtasks_total})`}
          className="lg:col-span-2"
          actions={!t.parent_id && <Button size="sm" variant="primary" onClick={() => setNewSub(true)} icon={<Plus className="h-3.5 w-3.5" />}>Subtarefa</Button>}
        >
          {t.subtasks.length ? <ul>{t.subtasks.map((s) => <TaskRow key={s.id} task={s} showProject={false} />)}</ul> : <EmptyState title="Sem subtarefas." />}
        </Panel>
        <div className="flex flex-col gap-4">
          <Panel title="Notas" actions={<Button size="sm" variant="ghost" onClick={() => newNote.mutate(undefined)}>Nova</Button>}>
            <ul className="flex flex-col gap-1">
              {notes.data?.items.map((n) => <li key={n.id}><Link className="text-[13px] text-text hover:text-primary" to={`/notes/${n.id}`}>{n.title}</Link></li>)}
              {!notes.data?.items.length && <li className="text-xs text-muted">Sem notas.</li>}
            </ul>
          </Panel>
          <Panel title="Checklists" actions={<Button size="sm" variant="ghost" onClick={() => newChecklist.mutate(undefined)}>Nova</Button>}>
            <ul className="flex flex-col gap-2">
              {checklists.data?.map((c) => (
                <li key={c.id}>
                  <Link className="text-[13px] text-text hover:text-primary" to={`/templates/${c.id}`}>{c.title}</Link>
                  <Progress value={c.percent} tone="amber" />
                </li>
              ))}
              {!checklists.data?.length && <li className="text-xs text-muted">Sem checklists.</li>}
            </ul>
          </Panel>
        </div>
      </div>

      <TaskFormDialog open={editing} onClose={() => setEditing(false)} task={t} />
      <TaskFormDialog open={newSub} onClose={() => setNewSub(false)} defaults={{ parent_id: t.id, project_id: t.project_id ?? undefined }} />
      <ConfirmDialog
        open={confirmDelete}
        title="Eliminar tarefa"
        message={<>Eliminar «{t.title}» e as suas subtarefas é irreversível. Para manter o histórico, use <strong>Arquivar</strong>.</>}
        confirmLabel="Eliminar"
        loading={del.isPending}
        onConfirm={() => del.mutate(undefined)}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  );
}
