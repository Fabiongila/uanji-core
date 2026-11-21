import { Plus, Search } from "lucide-react";
import { useState, type DragEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useProjects, useTasks, type TaskFilters } from "@/api/hooks";
import type { Task, TaskStatus } from "@/api/types";
import { Button, Checkbox, Dialog, EmptyState, ErrorState, Field, Input, Loading, PageHeader, Panel, Select, Tabs } from "@/components/ui";
import { PriorityBadge, StatusIcon, TaskRow, useTaskStatus } from "@/features/common";
import { TaskFormDialog } from "@/features/forms";
import { useDebounced } from "@/lib/useDebounced";
import { cn, fmtDateTime, PRIORITY, TASK_STATUS } from "@/lib/utils";

const COLUMNS: TaskStatus[] = ["todo", "in_progress", "blocked", "done"];

function Board({ tasks }: { tasks: Task[] }) {
  const status = useTaskStatus();
  const [over, setOver] = useState<TaskStatus | null>(null);
  const [blocking, setBlocking] = useState<{ task: Task; reason: string } | null>(null);

  const move = (t: Task, to: TaskStatus) => {
    if (t.status === to) return;
    if (to === "blocked" && !t.blocked_reason) setBlocking({ task: t, reason: "" });
    else status.mutate({ id: t.id, status: to });
  };
  const onDrop = (e: DragEvent, to: TaskStatus) => {
    e.preventDefault();
    setOver(null);
    const t = tasks.find((x) => x.id === e.dataTransfer.getData("text/task-id"));
    if (t) move(t, to);
  };

  return (
    <>
      <div className="grid min-h-[50vh] gap-3 md:grid-cols-2 xl:grid-cols-4">
        {COLUMNS.map((col) => {
          const items = tasks.filter((t) => t.status === col);
          return (
            <section
              key={col}
              aria-label={TASK_STATUS[col]}
              onDragOver={(e) => {
                e.preventDefault();
                setOver(col);
              }}
              onDragLeave={() => setOver(null)}
              onDrop={(e) => onDrop(e, col)}
              className={cn("hud-panel flex min-h-40 flex-col", over === col && "border-primary/60")}
            >
              <header className="flex items-center gap-2 border-b border-line px-3 py-2">
                <StatusIcon status={col} />
                <span className="hud-label">{TASK_STATUS[col]}</span>
                <span className="ml-auto font-mono text-xs text-muted">{items.length}</span>
              </header>
              <ul className="flex flex-1 flex-col gap-2 overflow-y-auto p-2" style={{ maxHeight: "65vh" }}>
                {items.map((t) => (
                  <li
                    key={t.id}
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData("text/task-id", t.id)}
                    className="cursor-grab rounded-md border border-line bg-surface-2 p-2.5 hover:border-line-strong active:cursor-grabbing"
                  >
                    <Link to={`/tasks/${t.id}`} className="block text-[13px] text-text hover:text-primary">
                      {t.title}
                    </Link>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
                      <PriorityBadge priority={t.priority} />
                      {t.project_name && <span className="truncate">{t.project_name}</span>}
                      {t.due_at && <span className={t.overdue ? "text-danger" : ""}>{fmtDateTime(t.due_at)}</span>}
                    </div>
                    {t.status === "blocked" && t.blocked_reason && <p className="mt-1 text-[11px] text-danger">{t.blocked_reason}</p>}
                    <label className="sr-only" htmlFor={`mv-${t.id}`}>Mover {t.title}</label>
                    <Select
                      id={`mv-${t.id}`}
                      value={t.status}
                      onChange={(e) => move(t, e.target.value as TaskStatus)}
                      className="mt-2 h-7 text-xs"
                    >
                      {COLUMNS.map((c) => <option key={c} value={c}>{TASK_STATUS[c]}</option>)}
                    </Select>
                  </li>
                ))}
                {items.length === 0 && <li className="py-6 text-center text-xs text-muted">Arraste tarefas para aqui</li>}
              </ul>
            </section>
          );
        })}
      </div>
      <Dialog
        open={!!blocking}
        onClose={() => setBlocking(null)}
        title="Registar bloqueio"
        footer={
          <>
            <Button variant="ghost" onClick={() => setBlocking(null)}>Cancelar</Button>
            <Button
              variant="danger"
              disabled={!blocking?.reason.trim()}
              loading={status.isPending}
              onClick={() => {
                if (!blocking) return;
                status.mutate({ id: blocking.task.id, status: "blocked", blocked_reason: blocking.reason }, { onSuccess: () => setBlocking(null) });
              }}
            >
              Marcar como bloqueada
            </Button>
          </>
        }
      >
        <Field label={`Porque está «${blocking?.task.title}» bloqueada?`} htmlFor="block-r">
          <Input id="block-r" autoFocus value={blocking?.reason ?? ""} onChange={(e) => blocking && setBlocking({ ...blocking, reason: e.target.value })} />
        </Field>
      </Dialog>
    </>
  );
}

export default function TasksPage() {
  const [params, setParams] = useSearchParams();
  const view = (params.get("view") as "list" | "board") || "list";
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const dq = useDebounced(q);
  const filters: TaskFilters = {
    project_id: params.get("project") || undefined,
    priority: params.get("priority") ? [params.get("priority")!] : undefined,
    status: params.get("status") ? [params.get("status")!] : undefined,
    due: params.get("due") || undefined,
    include_archived: params.get("archived") === "1",
    q: dq || undefined,
  };
  const { data, isLoading, error, refetch } = useTasks(filters);
  const projects = useProjects();
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  };

  return (
    <div className="mx-auto max-w-[1500px]">
      <PageHeader
        title="Tarefas"
        subtitle={data ? `${data.total} tarefa(s)` : undefined}
        actions={
          <>
            <Tabs value={view} onChange={(v) => set("view", v === "list" ? "" : v)} items={[{ value: "list", label: "Lista" }, { value: "board", label: "Kanban" }]} />
            <Button variant="primary" onClick={() => setCreating(true)} icon={<Plus className="h-4 w-4" />}>Nova tarefa</Button>
          </>
        }
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative min-w-48 flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted" />
          <Input aria-label="Pesquisar tarefas" placeholder="Pesquisar tarefas" className="pl-8" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Select aria-label="Projecto" className="w-44" value={params.get("project") ?? ""} onChange={(e) => set("project", e.target.value)}>
          <option value="">Todos os projectos</option>
          {projects.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
        {view === "list" && (
          <Select aria-label="Estado" className="w-36" value={params.get("status") ?? ""} onChange={(e) => set("status", e.target.value)}>
            <option value="">Todos os estados</option>
            {Object.entries(TASK_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        )}
        <Select aria-label="Prioridade" className="w-36" value={params.get("priority") ?? ""} onChange={(e) => set("priority", e.target.value)}>
          <option value="">Todas as prioridades</option>
          {Object.entries(PRIORITY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select aria-label="Prazo" className="w-36" value={params.get("due") ?? ""} onChange={(e) => set("due", e.target.value)}>
          <option value="">Qualquer prazo</option>
          <option value="overdue">Atrasadas</option>
          <option value="today">Hoje</option>
          <option value="week">Próximos 7 dias</option>
          <option value="none">Sem prazo</option>
        </Select>
        <Checkbox checked={params.get("archived") === "1"} onChange={(v) => set("archived", v ? "1" : "")} label="Arquivadas" />
      </div>
      {isLoading ? (
        <Loading />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : view === "board" ? (
        <Board tasks={data?.items ?? []} />
      ) : (
        <Panel>
          {data?.items.length ? (
            <ul>{data.items.map((t) => <TaskRow key={t.id} task={t} />)}</ul>
          ) : (
            <EmptyState title="Nenhuma tarefa encontrada." action={<Button variant="primary" onClick={() => setCreating(true)}>Criar tarefa</Button>} />
          )}
          {data && data.total > data.items.length && (
            <p className="pt-2 text-xs text-muted">A mostrar {data.items.length} de {data.total}. Refine os filtros.</p>
          )}
        </Panel>
      )}
      <TaskFormDialog open={creating} onClose={() => setCreating(false)} defaults={{ project_id: params.get("project") ?? undefined }} />
    </div>
  );
}
