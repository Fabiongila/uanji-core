import { ArrowUpRight } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

/**
 * Card holográfico. A hierarquia é explícita: `emphasis="high"` (alertas, atrasos) destaca
 * o card; `metric` mostra o número principal; o cabeçalho abre a área respectiva.
 */
export function HoloCard({
  title,
  icon,
  to,
  tone = "primary",
  emphasis = "normal",
  metric,
  metricLabel,
  actions,
  children,
  className,
}: {
  title: string;
  icon: ReactNode;
  to?: string;
  tone?: "primary" | "amber" | "danger" | "success";
  emphasis?: "normal" | "high";
  metric?: ReactNode;
  metricLabel?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  const color = { primary: "text-primary", amber: "text-amber", danger: "text-danger", success: "text-success" }[tone];
  const head = (
    <>
      <span className={cn("[&_svg]:h-4 [&_svg]:w-4", color)}>{icon}</span>
      <h2 className="hud-label text-text-2">{title}</h2>
      {to && <ArrowUpRight className="h-3.5 w-3.5 text-muted opacity-0 transition-opacity group-hover/head:opacity-100" aria-hidden />}
    </>
  );
  return (
    <section className={cn("holo-card", className)} data-tone={tone} data-emphasis={emphasis} aria-label={title}>
      <header className="relative z-10 flex items-center gap-2 px-3.5 pt-3">
        {to ? (
          <Link to={to} className="group/head flex min-w-0 items-center gap-2 rounded hover:text-text" aria-label={`Abrir ${title}`}>
            {head}
          </Link>
        ) : (
          <div className="flex min-w-0 items-center gap-2">{head}</div>
        )}
        {actions && <div className="ml-auto flex items-center gap-1">{actions}</div>}
      </header>
      {metric !== undefined && (
        <div className="relative z-10 flex items-baseline gap-2 px-3.5 pt-1.5">
          <span className={cn("font-mono text-[26px] font-semibold leading-none text-glow", color)}>{metric}</span>
          {metricLabel && <span className="text-[12px] text-text-2">{metricLabel}</span>}
        </div>
      )}
      <div className="relative z-10 min-h-0 flex-1 px-3.5 pb-3 pt-2">{children}</div>
    </section>
  );
}

/** Indicador circular (SVG). `value` em percentagem; `null` = sem dados mensuráveis. */
export function Ring({
  value,
  size = 44,
  tone = "primary",
  label,
}: {
  value: number | null;
  size?: number;
  tone?: "primary" | "amber" | "danger" | "success";
  label?: string;
}) {
  const r = 16;
  const circ = 2 * Math.PI * r;
  const color = { primary: "#22d3ee", amber: "#f5b942", danger: "#f87171", success: "#34d399" }[tone];
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" role="img" aria-label={label ?? (value == null ? "Sem dados" : `${value}%`)}>
      <circle cx="20" cy="20" r={r} fill="none" stroke="rgb(120 170 220 / 0.15)" strokeWidth="3" />
      {value != null && (
        <circle
          cx="20"
          cy="20"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={`${(Math.max(0, Math.min(100, value)) / 100) * circ} ${circ}`}
          transform="rotate(-90 20 20)"
          style={{ filter: `drop-shadow(0 0 3px ${color}88)`, transition: "stroke-dasharray 0.6s" }}
        />
      )}
      <text x="20" y="23" textAnchor="middle" fontSize="9" fill="#e6edf7" fontFamily="ui-monospace, monospace">
        {value == null ? "—" : `${value}%`}
      </text>
    </svg>
  );
}

/** Linha de informação compacta usada dentro dos cards. */
export function HoloRow({ children, to, tone }: { children: ReactNode; to?: string; tone?: "danger" | "amber" }) {
  const cls = cn(
    "flex min-w-0 items-center gap-2 border-b border-line/50 py-1.5 text-[12.5px] last:border-0",
    tone === "danger" && "text-danger",
    tone === "amber" && "text-amber",
    !tone && "text-text-2",
  );
  return to ? (
    <li>
      <Link to={to} className={cn(cls, "hover:text-text")}>
        {children}
      </Link>
    </li>
  ) : (
    <li className={cls}>{children}</li>
  );
}
