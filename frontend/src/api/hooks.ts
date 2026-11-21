import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useCore } from "@/lib/core-state";
import { toast } from "@/lib/toast";
import { api, errorMessage } from "./client";
import type {
  ActionSpec,
  Activity,
  AppSettings,
  Automation,
  AutomationRun,
  BackupItem,
  Checklist,
  Dashboard,
  Diagnostics,
  EventItem,
  GraphEdge,
  GraphNode,
  IntegrationStatus,
  Metrics,
  Note,
  NoteRevision,
  NoteSummary,
  NotificationItem,
  Page,
  Project,
  ProjectDetail,
  RelationView,
  ReviewContext,
  SearchResult,
  SecretEntry,
  Task,
  TaskDetail,
  VaultStatus,
} from "./types";

// Grupos de invalidação: uma escrita num domínio refresca tudo o que dele depende.
const DERIVED: QueryKey[] = [["dashboard"], ["metrics"], ["activity"], ["notifications"], ["search"]];

export function useApiMutation<TVars, TResult>(
  fn: (v: TVars) => Promise<TResult>,
  opts: {
    invalidate?: QueryKey[];
    success?: string | ((r: TResult, v: TVars) => string | null);
    silentError?: boolean;
    onSuccess?: (r: TResult, v: TVars) => void;
  } = {},
) {
  const qc = useQueryClient();
  const setFlash = useCore((s) => s.setFlash);
  return useMutation({
    mutationFn: fn,
    onSuccess: async (r, v) => {
      await Promise.all([...(opts.invalidate ?? []), ...DERIVED].map((k) => qc.invalidateQueries({ queryKey: k })));
      const msg = typeof opts.success === "function" ? opts.success(r, v) : opts.success;
      if (msg) toast.success(msg);
      setFlash("success");
      opts.onSuccess?.(r, v);
    },
    onError: (e) => {
      setFlash("error");
      if (!opts.silentError) toast.error(errorMessage(e));
    },
  });
}

// --------------------------------------------------------------------------- Leitura

export const useHealth = () =>
  useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<{ status: string; version: string }>("/health"),
    refetchInterval: 30_000,
    retry: 1,
  });

export const useDashboard = () =>
  useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dashboard>("/api/dashboard"), refetchInterval: 60_000 });

export const useProjects = (params: Record<string, string | boolean | undefined> = {}) =>
  useQuery({ queryKey: ["projects", params], queryFn: () => api.get<Page<Project>>("/api/projects", params) });

export const useProject = (id: string | undefined) =>
  useQuery({
    queryKey: ["projects", "detail", id],
    queryFn: () => api.get<ProjectDetail>(`/api/projects/${id}`),
    enabled: !!id,
  });

export const useProjectHistory = (id: string | undefined) =>
  useQuery({
    queryKey: ["projects", "history", id],
    queryFn: () => api.get<Activity[]>(`/api/projects/${id}/history`),
    enabled: !!id,
  });

export type TaskFilters = {
  project_id?: string;
  status?: string[];
  priority?: string[];
  q?: string;
  due?: string;
  include_archived?: boolean;
  parent_id?: string;
  include_subtasks?: boolean;
};

export const useTasks = (filters: TaskFilters = {}) =>
  useQuery({ queryKey: ["tasks", filters], queryFn: () => api.get<Page<Task>>("/api/tasks", filters) });

export const useTask = (id: string | undefined) =>
  useQuery({ queryKey: ["tasks", "detail", id], queryFn: () => api.get<TaskDetail>(`/api/tasks/${id}`), enabled: !!id });

export const useChecklists = (params: { is_template?: boolean; project_id?: string; task_id?: string } = {}) =>
  useQuery({ queryKey: ["checklists", params], queryFn: () => api.get<Checklist[]>("/api/checklists", params) });

export const useChecklist = (id: string | undefined) =>
  useQuery({
    queryKey: ["checklists", "detail", id],
    queryFn: () => api.get<Checklist>(`/api/checklists/${id}`),
    enabled: !!id,
  });

export const useNotes = (params: Record<string, string | boolean | undefined> = {}) =>
  useQuery({ queryKey: ["notes", params], queryFn: () => api.get<Page<NoteSummary>>("/api/notes", params) });

export const useNote = (id: string | undefined) =>
  useQuery({
    queryKey: ["notes", "detail", id],
    queryFn: () => api.get<Note>(`/api/notes/${id}`),
    enabled: !!id,
    // O editor gere o seu próprio estado: não sobrescrever enquanto o utilizador escreve.
    refetchOnWindowFocus: false,
  });

export const useNoteRevisions = (id: string | undefined, enabled: boolean) =>
  useQuery({
    queryKey: ["notes", "revisions", id],
    queryFn: () => api.get<NoteRevision[]>(`/api/notes/${id}/revisions`),
    enabled: !!id && enabled,
  });

export const useRelations = (entity_type: string, entity_id: string | undefined) =>
  useQuery({
    queryKey: ["relations", entity_type, entity_id],
    queryFn: () => api.get<RelationView[]>("/api/relations", { entity_type, entity_id }),
    enabled: !!entity_id,
  });

export const useGraph = (include_tasks: boolean) =>
  useQuery({
    queryKey: ["relations", "graph", include_tasks],
    queryFn: () => api.get<{ nodes: GraphNode[]; edges: GraphEdge[] }>("/api/knowledge/graph", { include_tasks }),
  });

export const useAgenda = (start: string, days: number) =>
  useQuery({
    queryKey: ["agenda", start, days],
    queryFn: () => api.get<{ events: EventItem[]; tasks: Task[]; start: string; end: string }>("/api/agenda", { start, days }),
  });

export const useReview = (kind: "daily" | "weekly", day: string) =>
  useQuery({
    queryKey: ["reviews", kind, day],
    queryFn: () => api.get<ReviewContext>(`/api/reviews/${kind}`, { day }),
    refetchOnWindowFocus: false,
  });

export const useSearch = (q: string) =>
  useQuery({
    queryKey: ["search", q],
    queryFn: () => api.get<SearchResult>("/api/search", { q }),
    enabled: q.trim().length > 0,
    staleTime: 5_000,
  });

export const useActivity = (params: Record<string, string | number | undefined> = {}) =>
  useQuery({ queryKey: ["activity", params], queryFn: () => api.get<Activity[]>("/api/activity", params) });

export const useNotifications = () =>
  useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<NotificationItem[]>("/api/notifications"),
    refetchInterval: 60_000,
  });

export const useAutomations = () =>
  useQuery({ queryKey: ["automations"], queryFn: () => api.get<Automation[]>("/api/automations") });

export const useAutomation = (id: string | undefined) =>
  useQuery({
    queryKey: ["automations", "detail", id],
    queryFn: () => api.get<Automation>(`/api/automations/${id}`),
    enabled: !!id && id !== "new",
  });

export const useAutomationRuns = (id: string | undefined) =>
  useQuery({
    queryKey: ["automations", "runs", id],
    queryFn: () => api.get<AutomationRun[]>(`/api/automations/${id}/runs`),
    enabled: !!id && id !== "new",
  });

export const useRun = (id: string | null) =>
  useQuery({ queryKey: ["runs", id], queryFn: () => api.get<AutomationRun>(`/api/automation-runs/${id}`), enabled: !!id });

export const useActionCatalog = () =>
  useQuery({ queryKey: ["automations", "catalog"], queryFn: () => api.get<ActionSpec[]>("/api/automations/actions"), staleTime: Infinity });

export const useMetrics = (start: string, end: string) =>
  useQuery({ queryKey: ["metrics", start, end], queryFn: () => api.get<Metrics>("/api/metrics", { start, end }) });

export const useVault = () => useQuery({ queryKey: ["vault"], queryFn: () => api.get<SecretEntry[]>("/api/vault") });
export const useVaultStatus = () =>
  useQuery({ queryKey: ["vault", "status"], queryFn: () => api.get<VaultStatus>("/api/vault/status") });

export const useBackups = () =>
  useQuery({
    queryKey: ["backups"],
    queryFn: () => api.get<{ directory: string; items: BackupItem[]; automatic: AppSettings["backups"] }>("/api/backups"),
  });

export const useIntegrations = () =>
  useQuery({ queryKey: ["integrations"], queryFn: () => api.get<IntegrationStatus[]>("/api/integrations") });

export const useSettings = () =>
  useQuery({ queryKey: ["settings"], queryFn: () => api.get<AppSettings>("/api/settings"), staleTime: 60_000 });

export const useDiagnostics = () =>
  useQuery({ queryKey: ["diagnostics"], queryFn: () => api.get<Diagnostics>("/api/diagnostics") });

export const useAssistantStatus = () =>
  useQuery({
    queryKey: ["assistant", "status"],
    queryFn: () => api.get<{ configured: boolean; provider: string; model: string; message: string }>("/api/assistant/status"),
  });
