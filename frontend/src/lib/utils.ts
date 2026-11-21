import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { NoteKind, Priority, ProjectStatus, TaskStatus } from "@/api/types";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

const dateFmt = new Intl.DateTimeFormat("pt-PT", { day: "2-digit", month: "short" });
const dateTimeFmt = new Intl.DateTimeFormat("pt-PT", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
const timeFmt = new Intl.DateTimeFormat("pt-PT", { hour: "2-digit", minute: "2-digit" });

export const fmtDate = (iso: string | null | undefined): string => (iso ? dateFmt.format(new Date(iso)) : "—");
export const fmtDateTime = (iso: string | null | undefined): string =>
  iso ? dateTimeFmt.format(new Date(iso)) : "—";
export const fmtTime = (iso: string): string => timeFmt.format(new Date(iso));

export function fmtRelative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "—";
  const diff = (new Date(iso).getTime() - now.getTime()) / 1000;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("pt-PT", { numeric: "auto" });
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}

export function fmtMinutes(min: number): string {
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(1)} GB`;
}

/** YYYY-MM-DD no fuso local. */
export function isoDay(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

export function startOfWeek(d: Date): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const wd = (x.getDay() + 6) % 7; // segunda = 0
  return addDays(x, -wd);
}

/** Converte valor de <input type="datetime-local"> para ISO com fuso. */
export function localInputToIso(v: string): string | null {
  if (!v) return null;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function isoToLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export const PROJECT_STATUS: Record<ProjectStatus, string> = {
  planned: "Planeado",
  active: "Activo",
  paused: "Pausado",
  blocked: "Bloqueado",
  done: "Concluído",
  archived: "Arquivado",
};

export const TASK_STATUS: Record<TaskStatus, string> = {
  todo: "Por fazer",
  in_progress: "Em curso",
  blocked: "Bloqueada",
  done: "Concluída",
};

export const PRIORITY: Record<Priority, string> = {
  low: "Baixa",
  medium: "Média",
  high: "Alta",
  critical: "Crítica",
};

export const NOTE_KIND: Record<NoteKind, string> = {
  note: "Nota",
  decision: "Decisão",
  idea: "Ideia",
  concept: "Conceito",
  solution: "Solução técnica",
  error: "Erro e resolução",
  documentation: "Documentação",
  reference: "Referência",
  lesson: "Lição aprendida",
};

export const ENTITY_LABEL: Record<string, string> = {
  project: "Projecto",
  task: "Tarefa",
  note: "Nota",
  event: "Evento",
  checklist: "Checklist",
  automation: "Automação",
  secret: "Segredo",
  backup: "Backup",
  integration: "Integração",
  review: "Revisão",
  settings: "Definições",
};

export function entityRoute(type: string, id: string): string {
  switch (type) {
    case "project":
      return `/projects/${id}`;
    case "task":
      return `/tasks/${id}`;
    case "note":
      return `/notes/${id}`;
    case "checklist":
      return `/templates/${id}`;
    case "automation":
      return `/automations/${id}`;
    case "event":
      return `/agenda?event=${id}`;
    default:
      return "/";
  }
}
