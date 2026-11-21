import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ApiError, api } from "@/api/client";
import { useApiMutation, useProjects } from "@/api/hooks";
import type { Priority, Project, ProjectDetail, ProjectStatus, Task, TaskDetail, TaskStatus } from "@/api/types";
import { Button, Dialog, Field, Input, Select, Textarea } from "@/components/ui";
import { isoToLocalInput, localInputToIso, PRIORITY, PROJECT_STATUS, TASK_STATUS } from "@/lib/utils";

const priorities = ["low", "medium", "high", "critical"] as const;

// --------------------------------------------------------------------------- Projecto

export const projectSchema = z
  .object({
    name: z.string().trim().min(1, "O nome é obrigatório.").max(200),
    description: z.string().max(20000),
    category: z.string().max(80),
    status: z.enum(["planned", "active", "paused", "blocked", "done", "archived"]),
    priority: z.enum(priorities),
    start_date: z.string(),
    due_date: z.string(),
    objectives: z.string().max(20000),
    expected_results: z.string().max(20000),
    blocked_reason: z.string().max(5000),
  })
  .refine((v) => !(v.start_date && v.due_date && v.due_date < v.start_date), {
    message: "A data de fim não pode ser anterior à de início.",
    path: ["due_date"],
  })
  .refine((v) => v.status !== "blocked" || v.blocked_reason.trim().length > 0, {
    message: "Indique o motivo do bloqueio.",
    path: ["blocked_reason"],
  });

type ProjectValues = z.infer<typeof projectSchema>;

function applyServerErrors<T extends Record<string, unknown>>(
  e: unknown,
  setError: (name: keyof T & string, err: { message: string }) => void,
) {
  if (e instanceof ApiError) {
    for (const f of e.fieldErrors) if (f.field) setError(f.field as keyof T & string, { message: f.message });
  }
}

export function ProjectFormDialog({
  open,
  onClose,
  project,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  project?: Project;
  onSaved?: (p: ProjectDetail) => void;
}) {
  const form = useForm<ProjectValues>({
    resolver: zodResolver(projectSchema),
    values: {
      name: project?.name ?? "",
      description: project?.description ?? "",
      category: project?.category ?? "",
      status: (project?.status ?? "active") as ProjectStatus,
      priority: (project?.priority ?? "medium") as Priority,
      start_date: project?.start_date ?? "",
      due_date: project?.due_date ?? "",
      objectives: project?.objectives ?? "",
      expected_results: project?.expected_results ?? "",
      blocked_reason: project?.blocked_reason ?? "",
    },
  });
  const save = useApiMutation(
    (v: ProjectValues) => {
      const body = { ...v, start_date: v.start_date || null, due_date: v.due_date || null };
      return project
        ? api.patch<ProjectDetail>(`/api/projects/${project.id}`, body)
        : api.post<ProjectDetail>("/api/projects", body);
    },
    {
      invalidate: [["projects"]],
      success: project ? "Projecto actualizado." : "Projecto criado.",
      onSuccess: (p) => {
        onSaved?.(p);
        onClose();
      },
    },
  );
  const { register, handleSubmit, formState, watch } = form;
  const errors = formState.errors;
  const submit = handleSubmit((v) =>
    save.mutate(v, { onError: (e) => applyServerErrors<ProjectValues>(e, form.setError) }),
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={project ? "Editar projecto" : "Novo projecto"}
      wide
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={submit}>
            Guardar
          </Button>
        </>
      }
    >
      <form className="grid grid-cols-1 gap-3 sm:grid-cols-2" onSubmit={submit} noValidate>
        <Field label="Nome" error={errors.name?.message} htmlFor="p-name" className="sm:col-span-2">
          <Input id="p-name" autoFocus {...register("name")} />
        </Field>
        <Field label="Estado" htmlFor="p-status">
          <Select id="p-status" {...register("status")}>
            {Object.entries(PROJECT_STATUS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Prioridade" htmlFor="p-prio">
          <Select id="p-prio" {...register("priority")}>
            {priorities.map((p) => (
              <option key={p} value={p}>
                {PRIORITY[p]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Categoria" htmlFor="p-cat" hint="Ex.: Software, Dados, Visão computacional">
          <Input id="p-cat" {...register("category")} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Início" htmlFor="p-start">
            <Input id="p-start" type="date" {...register("start_date")} />
          </Field>
          <Field label="Fim" error={errors.due_date?.message} htmlFor="p-due">
            <Input id="p-due" type="date" {...register("due_date")} />
          </Field>
        </div>
        {watch("status") === "blocked" && (
          <Field label="Motivo do bloqueio" error={errors.blocked_reason?.message} htmlFor="p-block" className="sm:col-span-2">
            <Input id="p-block" {...register("blocked_reason")} />
          </Field>
        )}
        <Field label="Descrição" htmlFor="p-desc" className="sm:col-span-2">
          <Textarea id="p-desc" rows={3} {...register("description")} />
        </Field>
        <Field label="Objectivos" htmlFor="p-obj">
          <Textarea id="p-obj" rows={3} {...register("objectives")} />
        </Field>
        <Field label="Resultados esperados" htmlFor="p-res">
          <Textarea id="p-res" rows={3} {...register("expected_results")} />
        </Field>
      </form>
    </Dialog>
  );
}

// --------------------------------------------------------------------------- Tarefa

export const taskSchema = z
  .object({
    title: z.string().trim().min(1, "O título é obrigatório.").max(300),
    description: z.string().max(20000),
    project_id: z.string(),
    status: z.enum(["todo", "in_progress", "blocked", "done"]),
    priority: z.enum(priorities),
    due_at: z.string(),
    estimate_minutes: z.string().refine((v) => v === "" || (/^\d+$/.test(v) && Number(v) > 0), "Minutos inválidos."),
    completion_criteria: z.string().max(5000),
    blocked_reason: z.string().max(5000),
  })
  .refine((v) => v.status !== "blocked" || v.blocked_reason.trim().length > 0, {
    message: "Indique o motivo do bloqueio.",
    path: ["blocked_reason"],
  });

type TaskValues = z.infer<typeof taskSchema>;

export function TaskFormDialog({
  open,
  onClose,
  task,
  defaults,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  task?: Task;
  defaults?: { project_id?: string; parent_id?: string; status?: TaskStatus; due_at?: string };
  onSaved?: (t: TaskDetail) => void;
}) {
  const projects = useProjects();
  const form = useForm<TaskValues>({
    resolver: zodResolver(taskSchema),
    values: {
      title: task?.title ?? "",
      description: task?.description ?? "",
      project_id: task?.project_id ?? defaults?.project_id ?? "",
      status: (task?.status ?? defaults?.status ?? "todo") as TaskStatus,
      priority: (task?.priority ?? "medium") as Priority,
      due_at: isoToLocalInput(task?.due_at ?? defaults?.due_at),
      estimate_minutes: task?.estimate_minutes ? String(task.estimate_minutes) : "",
      completion_criteria: task?.completion_criteria ?? "",
      blocked_reason: task?.blocked_reason ?? "",
    },
  });
  const save = useApiMutation(
    (v: TaskValues) => {
      const body = {
        title: v.title,
        description: v.description,
        project_id: v.project_id || null,
        priority: v.priority,
        due_at: localInputToIso(v.due_at),
        estimate_minutes: v.estimate_minutes ? Number(v.estimate_minutes) : null,
        completion_criteria: v.completion_criteria,
        blocked_reason: v.blocked_reason,
      };
      if (task) {
        return api.patch<TaskDetail>(`/api/tasks/${task.id}`, { ...body, status: v.status });
      }
      return api.post<TaskDetail>("/api/tasks", { ...body, status: v.status, parent_id: defaults?.parent_id ?? null });
    },
    {
      invalidate: [["tasks"], ["projects"], ["agenda"]],
      success: task ? "Tarefa actualizada." : "Tarefa criada.",
      onSuccess: (t) => {
        onSaved?.(t);
        onClose();
      },
    },
  );
  const { register, handleSubmit, formState, watch } = form;
  const errors = formState.errors;
  const submit = handleSubmit((v) => save.mutate(v, { onError: (e) => applyServerErrors<TaskValues>(e, form.setError) }));

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={task ? "Editar tarefa" : defaults?.parent_id ? "Nova subtarefa" : "Nova tarefa"}
      wide
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={submit}>
            Guardar
          </Button>
        </>
      }
    >
      <form className="grid grid-cols-1 gap-3 sm:grid-cols-2" onSubmit={submit} noValidate>
        <Field label="Título" error={errors.title?.message} htmlFor="t-title" className="sm:col-span-2">
          <Input id="t-title" autoFocus {...register("title")} />
        </Field>
        <Field label="Projecto" htmlFor="t-proj">
          <Select id="t-proj" {...register("project_id")} disabled={!!defaults?.parent_id}>
            <option value="">Sem projecto</option>
            {projects.data?.items.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Estado" htmlFor="t-status">
            <Select id="t-status" {...register("status")}>
              {Object.entries(TASK_STATUS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Prioridade" htmlFor="t-prio">
            <Select id="t-prio" {...register("priority")}>
              {priorities.map((p) => (
                <option key={p} value={p}>
                  {PRIORITY[p]}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Prazo" htmlFor="t-due" hint="Hora local do computador">
          <Input id="t-due" type="datetime-local" {...register("due_at")} />
        </Field>
        <Field label="Duração estimada (min)" error={errors.estimate_minutes?.message} htmlFor="t-est">
          <Input id="t-est" inputMode="numeric" {...register("estimate_minutes")} />
        </Field>
        {watch("status") === "blocked" && (
          <Field label="Motivo do bloqueio" error={errors.blocked_reason?.message} htmlFor="t-block" className="sm:col-span-2">
            <Input id="t-block" {...register("blocked_reason")} />
          </Field>
        )}
        <Field label="Descrição" htmlFor="t-desc" className="sm:col-span-2">
          <Textarea id="t-desc" rows={3} {...register("description")} />
        </Field>
        <Field label="Critérios de conclusão" htmlFor="t-crit" className="sm:col-span-2" hint="Quando é que esta tarefa está realmente terminada?">
          <Textarea id="t-crit" rows={2} {...register("completion_criteria")} />
        </Field>
      </form>
    </Dialog>
  );
}
