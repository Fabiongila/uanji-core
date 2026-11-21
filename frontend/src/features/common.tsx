import { AlertCircle, CalendarClock, Circle, CircleCheck, CircleDot, Link2, OctagonX } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useApiMutation } from "@/api/hooks";
import type { Priority, ProjectStatus, Task, TaskStatus } from "@/api/types";
import { Badge, type Tone } from "@/components/ui";
import { cn, fmtDateTime, PRIORITY, PROJECT_STATUS, TASK_STATUS } from "@/lib/utils";

const projectTone: Record<ProjectStatus, Tone> = {
  planned: "neutral",
  active: "primary",
  paused: "amber",
  blocked: "danger",
  done: "success",
  archived: "neutral",
};
const taskTone: Record<TaskStatus, Tone> = { todo: "neutral", in_progress: "blue", blocked: "danger", done: "success" };
const prioTone: Record<Priority, Tone> = { low: "neutral", medium: "blue", high: "amber", critical: "danger" };

export const ProjectStatusBadge = ({ status }: { status: ProjectStatus }) => (
  <Badge tone={projectTone[status]}>{PROJECT_STATUS[status]}</Badge>
);
export const TaskStatusBadge = ({ status }: { status: TaskStatus }) => (
  <Badge tone={taskTone[status]}>{TASK_STATUS[status]}</Badge>
);
export const PriorityBadge = ({ priority }: { priority: Priority }) => (
  <Badge tone={prioTone[priority]}>{PRIORITY[priority]}</Badge>
);

export function StatusIcon({ status, className }: { status: TaskStatus; className?: string }) {
  const cls = cn("h-4 w-4", className);
  if (status === "done") return <CircleCheck className={cn(cls, "text-success")} aria-hidden />;
  if (status === "in_progress") return <CircleDot className={cn(cls, "text-electric")} aria-hidden />;
  if (status === "blocked") return <OctagonX className={cn(cls, "text-danger")} aria-hidden />;
  return <Circle className={cn(cls, "text-muted")} aria-hidden />;
}

export function useTaskStatus() {
  return useApiMutation(
    ({ id, status, blocked_reason }: { id: string; status: TaskStatus; blocked_reason?: string }) =>
      api.post<Task>(`/api/tasks/${id}/status`, { status, blocked_reason }),
    {
      invalidate: [["tasks"], ["projects"], ["agenda"], ["reviews"], ["automations"]],
      success: (t) => (t.status === "done" ? `Concluída: ${t.title}` : `Estado actualizado: ${TASK_STATUS[t.status]}`),
    },
  );
}

export function TaskRow({ task, showProject = true }: { task: Task; showProject?: boolean }) {
  const status = useTaskStatus();
  const done = task.status === "done";
  return (
    <li className="group flex items-center gap-2.5 border-b border-line/60 py-2 last:border-0">
      <button
        type="button"
        onClick={() => status.mutate({ id: task.id, status: done ? "todo" : "done" })}
        disabled={status.isPending}
        aria-label={done ? `Reabrir ${task.title}` : `Concluir ${task.title}`}
        className="shrink-0 rounded-full"
      >
        <StatusIcon status={task.status} />
      </button>
      <Link to={`/tasks/${task.id}`} className="min-w-0 flex-1">
        <span className={cn("block truncate text-[13px] text-text group-hover:text-primary", done && "text-muted line-through")}>
          {task.title}
        </span>
        <span className="flex flex-wrap items-center gap-x-2 text-[11.5px] text-muted">
          {task.number != null && <span className="font-mono">UJ-{task.number}</span>}
          {showProject && task.project_name && <span className="truncate">{task.project_name}</span>}
          {task.subtasks_total > 0 && (
            <span>
              {task.subtasks_done}/{task.subtasks_total} subtarefas
            </span>
          )}
          {task.blocked_by_open > 0 && (
            <span className="inline-flex items-center gap-0.5 text-amber">
              <Link2 className="h-3 w-3" /> {task.blocked_by_open} dependência(s)
            </span>
          )}
        </span>
      </Link>
      {task.due_at && (
        <span
          className={cn(
            "inline-flex shrink-0 items-center gap-1 text-[11.5px]",
            task.overdue ? "text-danger" : "text-muted",
          )}
        >
          {task.overdue ? <AlertCircle className="h-3.5 w-3.5" /> : <CalendarClock className="h-3.5 w-3.5" />}
          {fmtDateTime(task.due_at)}
        </span>
      )}
      <PriorityBadge priority={task.priority} />
    </li>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone = "primary",
  to,
}: {
  label: string;
  value: number | string;
  sub?: string;
  tone?: "primary" | "amber" | "danger" | "success" | "neutral";
  to?: string;
}) {
  const color = {
    primary: "text-primary",
    amber: "text-amber",
    danger: "text-danger",
    success: "text-success",
    neutral: "text-text",
  }[tone];
  const body = (
    <div className="hud-panel h-full px-3.5 py-3 transition-colors hover:border-line-strong">
      <div className="hud-label">{label}</div>
      <div className={cn("mt-1 font-mono text-2xl font-semibold", color)}>{value}</div>
      {sub && <div className="text-[11.5px] text-muted">{sub}</div>}
    </div>
  );
  return to ? (
    <Link to={to} className="block">
      {body}
    </Link>
  ) : (
    body
  );
}
