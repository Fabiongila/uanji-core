import {
  Activity as ActivityIcon,
  Archive,
  BarChart3,
  Bell,
  BookOpen,
  Bot,
  Calendar,
  CalendarRange,
  CheckSquare,
  ChevronsLeft,
  ChevronsRight,
  ClipboardCheck,
  FileText,
  FolderKanban,
  History,
  Home,
  KeyRound,
  ListChecks,
  Mic,
  MicOff,
  MonitorSmartphone,
  Plug,
  Search,
  Settings,
  Workflow,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useHealth, useNotifications, useSettings } from "@/api/hooks";
import { api } from "@/api/client";
import { CoreOrb, useCoreState } from "@/components/CoreOrb";
import { Kbd } from "@/components/ui";
import { cn, fmtRelative } from "@/lib/utils";
import { useToasts } from "@/lib/toast";
import { setProactiveListener, useStopSpeechShortcut, useVoice, useVoiceEvents } from "@/lib/voice";
import { toast } from "@/lib/toast";
import { appearanceOf, useApplyAppearance, useUsageTracking } from "@/lib/appearance";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { CommandBar } from "./CommandBar";
import { CommandPalette } from "./CommandPalette";
import { useQueryClient } from "@tanstack/react-query";

export const NAV: { to: string; label: string; icon: ReactNode; group: string }[] = [
  { to: "/", label: "Início", icon: <Home />, group: "Centro" },
  { to: "/projects", label: "Projectos", icon: <FolderKanban />, group: "Trabalho" },
  { to: "/tasks", label: "Tarefas", icon: <CheckSquare />, group: "Trabalho" },
  { to: "/agenda", label: "Agenda", icon: <Calendar />, group: "Trabalho" },
  { to: "/planning", label: "Planeamento semanal", icon: <CalendarRange />, group: "Trabalho" },
  { to: "/review", label: "Revisão diária", icon: <ClipboardCheck />, group: "Trabalho" },
  { to: "/notes", label: "Notas", icon: <FileText />, group: "Conhecimento" },
  { to: "/knowledge", label: "Base de conhecimento", icon: <BookOpen />, group: "Conhecimento" },
  { to: "/templates", label: "Modelos e checklists", icon: <ListChecks />, group: "Conhecimento" },
  { to: "/automations", label: "Automações", icon: <Workflow />, group: "Sistema" },
  { to: "/history", label: "Histórico", icon: <History />, group: "Sistema" },
  { to: "/metrics", label: "Desempenho", icon: <BarChart3 />, group: "Sistema" },
  { to: "/activity", label: "Actividade", icon: <MonitorSmartphone />, group: "Sistema" },
  { to: "/assistant", label: "Assistente", icon: <Bot />, group: "Sistema" },
  { to: "/integrations", label: "Integrações", icon: <Plug />, group: "Sistema" },
  { to: "/vault", label: "Cofre de segredos", icon: <KeyRound />, group: "Segurança" },
  { to: "/backups", label: "Backups", icon: <Archive />, group: "Segurança" },
  { to: "/settings", label: "Definições", icon: <Settings />, group: "Segurança" },
];

function readCollapsed(): boolean {
  try {
    return localStorage.getItem("uanji.sidebar") === "collapsed";
  } catch {
    return false;
  }
}

function Sidebar({ collapsed, onToggle, side = "left" }: { collapsed: boolean; onToggle: () => void; side?: "left" | "right" }) {
  const groups = [...new Set(NAV.map((n) => n.group))];
  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-line bg-bg-2/80 transition-[width] duration-200",
        side === "left" ? "border-r" : "border-l",
        collapsed ? "w-14" : "w-56",
      )}
    >
      <div className={cn("flex h-13 items-center gap-2 border-b border-line px-3", collapsed && "justify-center px-0")}>
        <img src="/uanji.svg" alt="" className="h-7 w-7" />
        {!collapsed && (
          <div className="leading-tight">
            <div className="text-[13px] font-semibold tracking-[0.18em] text-text">UANJI CORE</div>
            <div className="text-[10px] text-amber/80">Ideias. Projectos. Futuro.</div>
          </div>
        )}
      </div>
      <nav aria-label="Navegação principal" className="flex-1 overflow-y-auto py-2">
        {groups.map((g) => (
          <div key={g} className="mb-2">
            {!collapsed && <div className="hud-label px-4 pb-1 pt-2 text-[9.5px]">{g}</div>}
            {NAV.filter((n) => n.group === g).map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                title={collapsed ? n.label : undefined}
                className={({ isActive }) =>
                  cn(
                    "relative mx-2 flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] text-text-2 transition-colors",
                    "hover:bg-surface-3 hover:text-text [&_svg]:h-4 [&_svg]:w-4 [&_svg]:shrink-0",
                    collapsed && "justify-center px-0",
                    isActive && "bg-primary/10 text-primary before:absolute before:-left-2 before:h-5 before:w-0.5 before:rounded before:bg-primary",
                  )
                }
              >
                {n.icon}
                {!collapsed && <span className="truncate">{n.label}</span>}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <button
        type="button"
        onClick={onToggle}
        className="flex h-9 items-center justify-center gap-2 border-t border-line text-xs text-muted hover:text-text"
        aria-label={collapsed ? "Expandir barra lateral" : "Recolher barra lateral"}
      >
        {collapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
        {!collapsed && "Recolher"}
      </button>
    </aside>
  );
}

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    // Actualiza ao minuto (não a cada segundo) para poupar CPU em hardware antigo.
    const tick = () => setNow(new Date());
    const ms = 60_000 - (Date.now() % 60_000);
    let interval: number | undefined;
    const t = window.setTimeout(() => {
      tick();
      interval = window.setInterval(tick, 60_000);
    }, ms);
    return () => {
      window.clearTimeout(t);
      window.clearInterval(interval);
    };
  }, []);
  return (
    <div className="hidden text-right leading-tight md:block">
      <div className="font-mono text-[13px] text-text">
        {now.toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" })}
      </div>
      <div className="text-[10.5px] text-muted">
        {now.toLocaleDateString("pt-PT", { weekday: "short", day: "2-digit", month: "short" })}
      </div>
    </div>
  );
}

function NotificationsMenu() {
  const { data } = useNotifications();
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const unread = (data ?? []).filter((n) => !n.read_at).length;
  const markAll = async () => {
    await api.post("/api/notifications/read", {});
    await qc.invalidateQueries({ queryKey: ["notifications"] });
    await qc.invalidateQueries({ queryKey: ["dashboard"] });
  };
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="relative flex h-8 w-8 items-center justify-center rounded-md text-text-2 hover:bg-surface-3 hover:text-text"
        aria-label={`Notificações (${unread} por ler)`}
        aria-expanded={open}
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-amber px-1 text-center text-[10px] font-semibold leading-4 text-bg">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <>
          <button type="button" aria-hidden tabIndex={-1} className="fixed inset-0 z-30 cursor-default" onClick={() => setOpen(false)} />
          <div className="hud-panel absolute right-0 top-10 z-40 w-80 overflow-hidden" role="dialog" aria-label="Notificações">
            <div className="flex items-center justify-between border-b border-line px-3 py-2">
              <span className="hud-label">Notificações internas</span>
              {unread > 0 && (
                <button type="button" className="text-xs text-primary hover:underline" onClick={markAll}>
                  Marcar todas como lidas
                </button>
              )}
            </div>
            <ul className="max-h-96 overflow-auto">
              {(data ?? []).length === 0 && <li className="px-3 py-6 text-center text-[13px] text-muted">Sem notificações.</li>}
              {(data ?? []).slice(0, 30).map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    className={cn("block w-full border-b border-line/60 px-3 py-2 text-left hover:bg-surface-3", n.read_at && "opacity-60")}
                    onClick={async () => {
                      setOpen(false);
                      if (!n.read_at) {
                        await api.post("/api/notifications/read", { ids: [n.id] });
                        void qc.invalidateQueries({ queryKey: ["notifications"] });
                      }
                      if (n.link) navigate(n.link);
                    }}
                  >
                    <div className="flex items-center gap-1.5 text-[13px]">
                      <span
                        className={cn(
                          "h-1.5 w-1.5 shrink-0 rounded-full",
                          n.level === "error" ? "bg-danger" : n.level === "warning" ? "bg-amber" : "bg-primary",
                        )}
                      />
                      <span className="truncate text-text">{n.title}</span>
                    </div>
                    {n.body && <div className="mt-0.5 line-clamp-2 text-xs text-muted">{n.body}</div>}
                    <div className="mt-0.5 text-[10.5px] text-muted">{fmtRelative(n.created_at)}</div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}

/** Indicador permanente: o microfone está aberto? (privacidade) */
function MicIndicator() {
  const status = useVoice((s) => s.status);
  const connected = useVoice((s) => s.connected);
  if (!connected || !status) return null;
  const open = status.mic.active;
  const label = open
    ? status.state === "listening" || status.state === "confirming"
      ? "Microfone aberto: a ouvir o seu pedido"
      : `Microfone aberto: à espera de «${status.wake_word}» (análise local)`
    : "Microfone fechado";
  return (
    <Link
      to="/assistant"
      className={cn(
        "flex h-8 items-center gap-1.5 rounded border px-2",
        open ? "border-electric/50 text-electric" : "border-line text-muted hover:text-text",
      )}
      title={label}
      aria-label={label}
    >
      {open ? <Mic className="h-3.5 w-3.5" /> : <MicOff className="h-3.5 w-3.5" />}
      {open && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-danger" aria-hidden />}
      <span className="hidden font-mono text-[10.5px] uppercase tracking-wider lg:inline">{open ? status.label : "Voz"}</span>
    </Link>
  );
}

function Topbar({ onOpenPalette, backendDown }: { onOpenPalette: () => void; backendDown: boolean }) {
  const state = useCoreState(backendDown);
  return (
    <header className="flex h-13 shrink-0 items-center gap-3 border-b border-line bg-bg-2/60 px-4">
      <button
        type="button"
        onClick={onOpenPalette}
        className="flex h-8 min-w-0 max-w-md flex-1 items-center gap-2 rounded-md border border-line-strong bg-bg/60 px-2.5 text-[13px] text-muted hover:border-primary/50"
        aria-label="Pesquisa global e comandos (Command + K)"
      >
        <Search className="h-4 w-4 shrink-0" />
        <span className="truncate">Pesquisar projectos, tarefas, notas…</span>
        <span className="ml-auto hidden sm:inline">
          <Kbd>⌘K</Kbd>
        </span>
      </button>
      <div className="ml-auto flex items-center gap-3">
        <div
          className={cn(
            "hidden items-center gap-1.5 rounded border px-2 py-1 sm:flex",
            backendDown ? "border-danger/40 text-danger" : "border-success/30 text-success",
          )}
          title={backendDown ? "O backend local não responde" : "Backend local operacional"}
        >
          <ActivityIcon className="h-3.5 w-3.5" />
          <span className="font-mono text-[10.5px] uppercase tracking-wider">{backendDown ? "Offline" : "Online"}</span>
        </div>
        <MicIndicator />
        <CoreOrb state={state} size={30} showLabel={false} />
        <NotificationsMenu />
        <Clock />
        <Link
          to="/settings"
          className="flex h-8 w-8 items-center justify-center rounded-md text-text-2 hover:bg-surface-3 hover:text-text"
          aria-label="Definições"
        >
          <Settings className="h-4 w-4" />
        </Link>
      </div>
    </header>
  );
}

function Toaster() {
  const { toasts, dismiss } = useToasts();
  return (
    <div className="pointer-events-none fixed bottom-20 right-4 z-50 flex w-80 flex-col gap-2" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          role={t.kind === "error" ? "alert" : "status"}
          className={cn(
            "hud-panel pointer-events-auto px-3 py-2 text-[13px]",
            t.kind === "error" && "border-danger/50 text-danger",
            t.kind === "success" && "border-success/40 text-success",
          )}
        >
          <button type="button" className="block w-full text-left" onClick={() => dismiss(t.id)}>
            {t.message}
          </button>
        </div>
      ))}
    </div>
  );
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [narrow, setNarrow] = useState(() => typeof window.matchMedia === "function" && window.matchMedia("(max-width: 1023px)").matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    // Em janelas estreitas a barra lateral fica recolhida (os ícones continuam acessíveis).
    const mq = window.matchMedia("(max-width: 1023px)");
    const on = () => setNarrow(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  const [palette, setPalette] = useState(false);
  const health = useHealth();
  const settings = useSettings();
  const location = useLocation();
  const backendDown = health.isError;
  useVoiceEvents();
  useStopSpeechShortcut();
  useEffect(() => {
    // Fora da página do assistente, as mensagens por iniciativa aparecem como aviso.
    setProactiveListener((t) => {
      if (!window.location.pathname.startsWith("/assistant")) toast.info(t.reply);
    });
    return () => setProactiveListener(undefined);
  }, []);
  const appearance = appearanceOf(settings.data);
  useApplyAppearance(appearance);
  useUsageTracking(settings.isSuccess);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => setPalette(false), [location.pathname]);

  const toggle = () => {
    setCollapsed((c) => {
      try {
        localStorage.setItem("uanji.sidebar", c ? "expanded" : "collapsed");
      } catch {
        /* armazenamento indisponível */
      }
      return !c;
    });
  };

  return (
    <div className={cn("uanji-backdrop flex h-full", appearance.sidebar === "right" && "flex-row-reverse", settings.data?.reduced_motion && "reduce-motion")}>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:p-2">
        Saltar para o conteúdo
      </a>
      <Sidebar collapsed={collapsed || narrow} onToggle={toggle} side={appearance.sidebar} />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <Topbar onOpenPalette={() => setPalette(true)} backendDown={backendDown} />
        {backendDown && (
          <div role="alert" className="border-b border-danger/30 bg-danger/10 px-4 py-2 text-[13px] text-danger">
            O backend local não está a responder. Os dados não podem ser lidos nem gravados até o serviço voltar.
          </div>
        )}
        <main id="main" className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          <ErrorBoundary area={location.pathname} key={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
        <CommandBar />
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
      <Toaster />
    </div>
  );
}
