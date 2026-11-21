import { AlertTriangle, Inbox, Loader2, RefreshCw, X } from "lucide-react";
import {
  forwardRef,
  useEffect,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { errorMessage } from "@/api/client";
import { cn } from "@/lib/utils";

// --------------------------------------------------------------------------- Botões

type Variant = "primary" | "secondary" | "ghost" | "danger" | "amber";
const variants: Record<Variant, string> = {
  primary:
    "bg-primary/15 text-primary border-primary/50 hover:bg-primary/25 hover:shadow-[0_0_14px_rgb(34_211_238/0.25)]",
  secondary: "bg-surface-3 text-text border-line-strong hover:bg-surface-3/70 hover:border-primary/40",
  ghost: "bg-transparent text-text-2 border-transparent hover:bg-surface-3 hover:text-text",
  danger: "bg-danger/10 text-danger border-danger/40 hover:bg-danger/20",
  amber: "bg-amber/10 text-amber border-amber/40 hover:bg-amber/20",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "sm" | "md" | "icon";
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md border font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" && "h-7 px-2.5 text-xs",
        size === "md" && "h-8.5 px-3 text-[13px]",
        size === "icon" && "h-8 w-8 p-0",
        variants[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

// --------------------------------------------------------------------------- Campos

const fieldBase =
  "w-full rounded-md border border-line-strong bg-bg-2/80 px-2.5 text-[13px] text-text placeholder:text-muted " +
  "focus:border-primary/70 focus:outline-none focus:ring-1 focus:ring-primary/40 disabled:opacity-60";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref,
) {
  return <input ref={ref} className={cn(fieldBase, "h-8.5", className)} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...rest }, ref) {
    return <textarea ref={ref} className={cn(fieldBase, "min-h-20 py-2 leading-relaxed", className)} {...rest} />;
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest },
  ref,
) {
  return (
    <select ref={ref} className={cn(fieldBase, "h-8.5 pr-7", className)} {...rest}>
      {children}
    </select>
  );
});

export function Field({
  label,
  error,
  hint,
  children,
  htmlFor,
  className,
}: {
  label: string;
  error?: string;
  hint?: string;
  children: ReactNode;
  htmlFor?: string;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <label htmlFor={htmlFor} className="text-xs font-medium text-text-2">
        {label}
      </label>
      {children}
      {error ? (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-muted">{hint}</p>
      ) : null}
    </div>
  );
}

export function Checkbox({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 text-[13px] text-text-2">
      <input
        type="checkbox"
        className="h-4 w-4 accent-[var(--color-primary)]"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      {label}
    </label>
  );
}

// --------------------------------------------------------------------------- Painéis e tipografia

export function Panel({
  title,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("hud-panel flex min-w-0 flex-col", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-line px-3.5 py-2.5">
          {typeof title === "string" ? <h2 className="hud-label">{title}</h2> : title}
          {actions && <div className="flex items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={cn("min-h-0 flex-1 p-3.5", bodyClassName)}>{children}</div>
    </section>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight text-text">{title}</h1>
        {subtitle && <p className="mt-0.5 text-[13px] text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

const badgeTones = {
  neutral: "border-line-strong text-text-2 bg-surface-3/60",
  primary: "border-primary/40 text-primary bg-primary/10",
  blue: "border-electric/40 text-electric bg-electric/10",
  amber: "border-amber/40 text-amber bg-amber/10",
  success: "border-success/40 text-success bg-success/10",
  danger: "border-danger/40 text-danger bg-danger/10",
} as const;
export type Tone = keyof typeof badgeTones;

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 whitespace-nowrap rounded border px-1.5 text-[11px] font-medium",
        badgeTones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Progress({ value, tone = "primary" }: { value: number | null; tone?: "primary" | "amber" | "success" }) {
  const color = { primary: "bg-primary", amber: "bg-amber", success: "bg-success" }[tone];
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-surface-3"
      role="progressbar"
      aria-valuenow={value ?? undefined}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={cn("h-full rounded-full transition-[width]", color)} style={{ width: `${value ?? 0}%` }} />
    </div>
  );
}

// --------------------------------------------------------------------------- Estados

export function Loading({ label = "A carregar…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-[13px] text-muted" role="status">
      <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-2 rounded-md border border-danger/30 bg-danger/5 p-3">
      <div className="flex items-center gap-2 text-[13px] text-danger">
        <AlertTriangle className="h-4 w-4" aria-hidden />
        {errorMessage(error)}
      </div>
      {onRetry && (
        <Button size="sm" variant="ghost" onClick={onRetry} icon={<RefreshCw className="h-3.5 w-3.5" />}>
          Tentar novamente
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
      <div className="text-primary/70">{icon ?? <Inbox className="h-7 w-7" aria-hidden />}</div>
      <p className="text-sm font-medium text-text">{title}</p>
      {description && <p className="max-w-sm text-[13px] text-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

// --------------------------------------------------------------------------- Diálogos

export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      if (typeof d.showModal === "function") d.showModal();
      else d.setAttribute("open", "");
    } else if (!open && d.open) {
      if (typeof d.close === "function") d.close();
      else d.removeAttribute("open");
    }
  }, [open]);
  if (!open) return null;
  return (
    <dialog
      ref={ref}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      className={cn(
        "hud-panel m-auto max-h-[88vh] w-[calc(100%-2rem)] overflow-hidden p-0 text-text",
        wide ? "max-w-3xl" : "max-w-lg",
      )}
    >
      <div className="flex max-h-[88vh] flex-col">
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 className="text-[15px] font-semibold">{title}</h2>
          <Button size="icon" variant="ghost" onClick={onClose} aria-label="Fechar">
            <X className="h-4 w-4" />
          </Button>
        </header>
        <div className="min-h-0 flex-1 overflow-auto px-4 py-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-4 py-3">{footer}</footer>}
      </div>
    </dialog>
  );
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirmar",
  danger = true,
  loading,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      title={title}
      footer={
        <>
          <Button variant="ghost" onClick={onCancel}>
            Cancelar
          </Button>
          <Button variant={danger ? "danger" : "primary"} loading={loading} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-[13px] leading-relaxed text-text-2">{message}</div>
    </Dialog>
  );
}

// --------------------------------------------------------------------------- Separadores

export function Tabs<T extends string>({
  value,
  onChange,
  items,
}: {
  value: T;
  onChange: (v: T) => void;
  items: { value: T; label: ReactNode }[];
}) {
  return (
    <div role="tablist" className="inline-flex rounded-md border border-line bg-bg-2/70 p-0.5">
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          type="button"
          aria-selected={value === it.value}
          onClick={() => onChange(it.value)}
          className={cn(
            "h-7 rounded px-2.5 text-xs font-medium transition-colors",
            value === it.value ? "bg-primary/15 text-primary" : "text-muted hover:text-text",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-line-strong bg-surface-3 px-1.5 py-0.5 font-mono text-[10.5px] text-text-2">
      {children}
    </kbd>
  );
}
