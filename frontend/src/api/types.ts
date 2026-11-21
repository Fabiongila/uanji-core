// Contratos espelhados de backend/uanji/schemas.py

export type ProjectStatus = "planned" | "active" | "paused" | "blocked" | "done" | "archived";
export type Priority = "low" | "medium" | "high" | "critical";
export type TaskStatus = "todo" | "in_progress" | "blocked" | "done";
export type NoteKind =
  | "note"
  | "decision"
  | "idea"
  | "concept"
  | "solution"
  | "error"
  | "documentation"
  | "reference"
  | "lesson";
export type EntityType = "project" | "task" | "note" | "event" | "checklist" | "automation";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProjectProgress {
  tasks_total: number;
  tasks_done: number;
  milestones_total: number;
  milestones_done: number;
  percent: number | null;
  overdue_tasks: number;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  category: string;
  status: ProjectStatus;
  priority: Priority;
  start_date: string | null;
  due_date: string | null;
  objectives: string;
  expected_results: string;
  blocked_reason: string;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  progress: ProjectProgress | null;
  last_activity_at: string | null;
  stale: boolean;
}

export interface Milestone {
  id: string;
  title: string;
  due_date: string | null;
  done_at: string | null;
  position: number;
}

export interface ProjectLink {
  id: string;
  kind: string;
  title: string;
  url: string;
}

export interface ProjectDetail extends Project {
  milestones: Milestone[];
  links: ProjectLink[];
}

export interface Task {
  id: string;
  title: string;
  description: string;
  project_id: string | null;
  parent_id: string | null;
  status: TaskStatus;
  priority: Priority;
  due_at: string | null;
  estimate_minutes: number | null;
  completion_criteria: string;
  blocked_reason: string;
  notes: string;
  position: number;
  completed_at: string | null;
  archived_at: string | null;
  postponed_count: number;
  created_at: string;
  updated_at: string;
  overdue: boolean;
  subtasks_total: number;
  subtasks_done: number;
  project_name: string | null;
  number?: number | null;
  started_at?: string | null;
  blocked_seconds?: number;
  goal_id?: string | null;
  version_id?: string | null;
  depends_on: string[];
  blocked_by_open: number;
}

export interface TaskDetail extends Task {
  subtasks: Task[];
}

export interface FocusSession {
  id: string;
  task_id: string | null;
  project_id: string | null;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number;
  note: string;
}

export interface ChecklistItem {
  id: string;
  section: string;
  text: string;
  done: boolean;
  position: number;
}

export interface Checklist {
  id: string;
  title: string;
  description: string;
  category: string;
  is_template: boolean;
  builtin_key: string | null;
  project_id: string | null;
  task_id: string | null;
  source_template_id: string | null;
  created_at: string;
  updated_at: string;
  items: ChecklistItem[];
  percent: number;
}

export interface Note {
  id: string;
  title: string;
  content: string;
  kind: NoteKind;
  in_knowledge_base: boolean;
  project_id: string | null;
  task_id: string | null;
  tags: string[];
  source_url: string;
  pinned: boolean;
  archived_at: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface NoteSummary extends Omit<Note, "content" | "source_url" | "created_at"> {
  excerpt: string;
}

export interface NoteRevision {
  id: string;
  revision: number;
  title: string;
  content: string;
  created_at: string;
}

export interface RelationView {
  id: string;
  label: string;
  direction: "in" | "out";
  entity_type: EntityType;
  entity_id: string;
  title: string;
}

export interface GraphNode {
  id: string;
  type: EntityType;
  entity_id: string;
  label: string;
  kind: string | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  implicit: boolean;
}

export interface EventItem {
  id: string;
  title: string;
  description: string;
  kind: "event" | "work_block";
  start_at: string;
  end_at: string;
  all_day: boolean;
  location: string;
  project_id: string | null;
  task_id: string | null;
}

export interface ReviewGoal {
  text: string;
  done: boolean;
}

export interface Review {
  id: string;
  kind: "daily" | "weekly";
  period_start: string;
  goals: ReviewGoal[];
  wins: string;
  blockers: string;
  reflection: string;
  next_plan: string;
  closed_at: string | null;
  updated_at: string;
}

export interface ReviewContext {
  review: Review;
  completed: Task[];
  postponed: Task[];
  overdue: Task[];
  due_next: Task[];
  focus_minutes: number;
  events: EventItem[];
}

export interface Activity {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  summary: string;
  created_at: string;
}

export interface NotificationItem {
  id: string;
  category: string;
  level: "info" | "warning" | "error";
  title: string;
  body: string;
  link: string;
  created_at: string;
  read_at: string | null;
}

export interface Alert {
  level: "info" | "warning" | "error";
  title: string;
  body?: string;
  link: string;
}

export interface Dashboard {
  generated_at: string;
  is_empty: boolean;
  counters: {
    active_projects: number;
    blocked_projects: number;
    pending_tasks: number;
    overdue_tasks: number;
    done_today: number;
    done_week: number;
    focus_minutes_today: number;
    focus_minutes_week: number;
    automations_running: number;
    unread_notifications: number;
  };
  active_projects: Project[];
  priority_tasks: Task[];
  upcoming: Task[];
  recent_activity: Activity[];
  alerts: Alert[];
  trend: { date: string; done: number; created: number; focus_minutes: number }[];
  focus_active: FocusSession | null;
}

export interface SearchHit {
  entity_type: EntityType;
  entity_id: string;
  title: string;
  snippet: string;
  route: string;
}

export interface SearchResult {
  engine: string;
  query: string;
  hits: SearchHit[];
}

export interface CommandResult {
  kind: "created" | "navigate" | "search" | "result" | "error" | "unknown" | "help" | "ambiguous";
  message: string;
  route?: string;
  entity_type?: string;
  entity_id?: string;
  hits?: SearchHit[];
  suggestions?: { command: string; label: string; hint: string }[];
}

export interface AutomationCondition {
  field: string;
  op: string;
  value: unknown;
}

export interface AutomationStep {
  id: string;
  action: string;
  params: Record<string, unknown>;
  /** Nó «Condição» antes desta etapa. */
  conditions?: AutomationCondition[];
  on_false?: "skip" | "stop";
}

export type TriggerType = "manual" | "schedule" | "task_completed" | "deadline_approaching" | "webhook" | "github" | "app_opened";

export interface AutomationDefinition {
  trigger: { type: TriggerType; config: Record<string, unknown> };
  conditions: AutomationCondition[];
  steps: AutomationStep[];
  ui?: Record<string, unknown>;
}

export interface AutomationRunStep {
  index: number;
  node_id: string;
  action: string;
  status: string;
  attempts: number;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  error: string;
  started_at: string;
  finished_at: string | null;
}

export interface AutomationRun {
  id: string;
  automation_id: string;
  version: number;
  trigger: string;
  status: "pending" | "running" | "success" | "failed" | "cancelled" | "skipped";
  error: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  cancel_requested: boolean;
  steps?: AutomationRunStep[];
  context?: Record<string, unknown>;
}

export interface Automation {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  version: number;
  trigger_type: string;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
  updated_at: string;
  definition: AutomationDefinition;
  last_run: AutomationRun | null;
  run_counts: Record<string, number>;
}

export interface ActionSpec {
  name: string;
  label: string;
  description: string;
  mutates: boolean;
  reversible: boolean;
  category?: "action" | "result";
  schema: {
    properties: Record<string, { type?: string; title?: string; enum?: string[]; default?: unknown; anyOf?: unknown[]; $ref?: string }>;
    required?: string[];
    $defs?: Record<string, { enum?: string[] }>;
  };
}

export interface SecretEntry {
  id: string;
  name: string;
  service: string;
  description: string;
  hint: string;
  created_at: string;
  updated_at: string;
  last_accessed_at: string | null;
}

export interface VaultStatus {
  backend: string;
  available: boolean;
  secure: boolean;
  message: string;
}

export interface BackupItem {
  id: string;
  filename: string;
  kind: string;
  size_bytes: number;
  sha256: string;
  schema_revision: string;
  status: "ok" | "failed" | "missing";
  error: string;
  verified_at: string | null;
  created_at: string;
}

export interface IntegrationStatus {
  provider: string;
  label: string;
  status: "not_configured" | "connected" | "error";
  config: Record<string, unknown>;
  has_token: boolean;
  secret_id: string | null;
  last_checked_at: string | null;
  last_error: string;
  capabilities: string[];
  help: string;
}

export interface RepoOverview {
  source: string;
  fetched_at: string;
  repo: {
    full_name: string;
    description: string | null;
    html_url: string;
    private: boolean;
    default_branch: string;
    stars: number;
    open_issues: number;
    pushed_at: string;
    language: string | null;
  };
  commits: { sha: string; message: string; author: string | null; date: string | null; url: string }[];
  pull_requests: { number: number; title: string; url: string; author: string | null }[];
}

export interface AppSettings {
  theme: string;
  reduced_motion: boolean;
  timezone: string;
  notifications: {
    enabled: boolean;
    native: boolean;
    categories: Record<string, boolean>;
    deadline_hours: number;
    quiet_start: string;
    quiet_end: string;
    daily_review_time: string;
    weekly_review_day: number;
  };
  backups: { automatic: boolean; interval_hours: number; keep: number };
  assistant: {
    provider: string;
    model: string;
    base_url: string;
    secret_id: string | null;
    confirm_creates: boolean;
    confirm_updates: boolean;
    history_days: number;
    context_turns: number;
  };
  voice: VoiceSettings;
  persona: { address: AddressMode; custom: string };
  activity: ActivitySettings;
  proactive: ProactiveSettings;
  system: { allow_apps: boolean; confirm_system: boolean; allow_shell: boolean };
  appearance: Appearance;
  usage: Record<string, number>;
}

export interface ActivitySettings {
  enabled: boolean;
  sample_seconds: number;
  idle_seconds: number;
  capture_titles: boolean;
  excluded_apps: string[];
  retention_days: number;
  git_folders: string[];
}

export type ProactiveRule =
  | "morning"
  | "return"
  | "deadlines"
  | "events"
  | "breaks"
  | "focus"
  | "context_switch"
  | "end_of_day"
  | "automations"
  | "suggestions";

export interface ProactiveSettings {
  enabled: boolean;
  voice: boolean;
  intensity: "low" | "normal" | "high";
  rules: Partial<Record<ProactiveRule, boolean>>;
}

export type CardId = "tasks" | "projects" | "assistant" | "alerts" | "agenda" | "performance" | "knowledge" | "automations" | "integrations" | "system";
export type CardSize = "s" | "m" | "l" | "xl";
export interface CardLayout {
  id: CardId;
  size: CardSize;
  hidden: boolean;
}

export interface Appearance {
  theme: "uanji-dark" | "abyss" | "amber" | "contrast" | "light";
  accent: "cyan" | "blue" | "amber" | "emerald" | "violet";
  density: "comfortable" | "compact";
  font_scale: number;
  sidebar: "left" | "right";
  layout_mode: "custom" | "adaptive";
  cards: CardLayout[];
}

export interface ActivitySummary {
  date: string;
  monitor_enabled: boolean;
  has_data: boolean;
  active_seconds: number;
  first_at: string | null;
  last_at: string | null;
  apps: { app: string; seconds: number }[];
  categories: { category: string; label: string; seconds: number }[];
  projects: { id: string; name: string; seconds: number }[];
  contexts: { context: string; seconds: number }[];
  hours: number[];
  switches: number;
  sentence: string;
}

export interface ActivityStatus {
  enabled: boolean;
  running: boolean;
  last_error: string;
  now: { app: string; category: string; context: string; since: string | null; idle_seconds: number; active_since: string | null } | null;
  titles_permission: boolean | null;
  stored_sessions: number;
}

export type AddressMode = "masculine" | "feminine" | "neutral" | "custom";

export interface VoiceSettings {
  listening: boolean;
  wake_word: string;
  sensitivity: number;
  greeting: string;
  tts_enabled: boolean;
  voice: string;
  rate: number;
  volume: number;
  language: string;
  follow_up_seconds: number;
}

// --------------------------------------------------------------------------- Voz e assistente

export type VoiceState =
  | "off"
  | "wake"
  | "listening"
  | "interpreting"
  | "preparing"
  | "executing"
  | "confirming"
  | "speaking"
  | "done"
  | "error";

export type MicPermission = "authorized" | "denied" | "restricted" | "not_determined" | "unknown";

export interface VoiceStatus {
  state: VoiceState;
  label: string;
  listening_enabled: boolean;
  wake_word: string;
  conversation_id: string | null;
  mic: { permission: MicPermission; active: boolean; temporary: boolean; device: { name: string; samplerate: number } | null };
  wake: {
    mode: "user" | "system" | "none";
    samples: { name: string; source: "user" | "system" }[];
    threshold: number | null;
    last_score: number | null;
    preparing: boolean;
  };
  stt: {
    engine: string;
    local: boolean;
    package_installed?: boolean;
    model?: string;
    model_installed: boolean;
    model_size_mb?: number;
    loaded?: boolean;
    download?: { active: boolean; progress: number; error: string };
  };
  tts: { available: boolean; enabled: boolean; speaking: boolean; can_resume: boolean; voice: string; voice_found: boolean; last_error: string };
  external_audio: boolean;
  audio_stored: boolean;
  last_error: string;
  partial: string;
  last_transcript: string;
}

export interface SystemVoice {
  id: string;
  name: string;
  language: string;
  gender: "female" | "male" | "unspecified";
  gender_source: "system" | "catalog" | "none";
  quality: string;
}

export type ReportSectionKind = "facts" | "derived" | "recommendations" | "unavailable";

export interface Report {
  kind: string;
  title: string;
  sections: { kind: ReportSectionKind; title: string; items: string[] }[];
  speech: string;
}

export interface ProposedAction {
  id: string;
  tool: string;
  summary: string;
  risk: "read" | "system" | "create" | "update" | "destructive";
  details: string[];
  status: "pending" | "confirmed" | "rejected" | "failed" | "expired";
  message: string;
}

export interface AssistantTurn {
  id: string;
  conversation_id: string;
  reply: string;
  speech: string;
  engine: "local" | "ai" | "none";
  report: Report | null;
  actions: ProposedAction[];
  executed: { tool: string; message: string; entity: { type: string; id: string; label: string } | null }[];
  consulted: { tool: string; input: Record<string, unknown> }[];
  navigate: string | null;
  awaiting: "confirmation" | "slot" | "choice" | "offer" | null;
  control: string | null;
  error: boolean;
  /** Mensagem por iniciativa do assistente (regra que a originou). */
  proactive?: string;
  offer?: { tool: string; label: string } | null;
  link?: string;
}

export interface Diagnostics {
  app_version: string;
  env: string;
  python: string;
  platform: string;
  machine: string;
  data_dir: string;
  db_path: string;
  db_size_bytes: number;
  schema_revision: string;
  schema_head: string;
  search_engine: string;
  fts5_available: boolean;
  vault: VaultStatus;
  assistant: { provider: string; model: string; configured: boolean; message: string };
  disk_free_bytes: number;
  scheduler_enabled: boolean;
  log_file: string;
}

export interface Metrics {
  period: { start: string; end: string };
  totals: { done: number; created: number; focus_minutes: number; late_done: number; overdue_now: number };
  series: { date: string; done: number; created: number; focus_minutes: number }[];
  weekly_done: { week: string; done: number }[];
  done_by_project: { project: string; done: number }[];
  focus_by_project: { project: string; minutes: number }[];
  automation_runs: Record<string, number>;
  project_progress: { id: string; name: string; status: string; percent: number | null; tasks_total: number }[];
  sources: Record<string, string>;
}
