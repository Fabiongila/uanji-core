import { useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";
import { Tabs } from "@/components/ui";

/**
 * Paleta categórica validada (scripts/validate_palette.js da skill dataviz, modo escuro,
 * superfície #0b1626): banda de luminosidade, croma, separação CVD e contraste — PASS.
 * Ordem fixa: série 1 = ciano, série 2 = âmbar, série 3 = azul.
 */
export const SERIES = ["#0891b2", "#b97f1c", "#3b82f6"] as const;
const GRID = "rgb(120 170 220 / 0.10)";
const AXIS = "#7a8ba3";

function HudTooltip({ active, payload, label, unit }: Partial<TooltipContentProps<number, string>> & { unit?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="hud-panel px-2.5 py-1.5 text-xs">
      <div className="mb-0.5 text-muted">{label}</div>
      {payload.map((p) => (
        <div key={String(p.dataKey)} className="flex items-center gap-1.5 text-text">
          <span className="h-2 w-2 rounded-sm" style={{ background: p.color }} />
          <span className="text-text-2">{p.name}:</span>
          <span className="font-mono">
            {p.value}
            {unit ? ` ${unit}` : ""}
          </span>
        </div>
      ))}
    </div>
  );
}

const axisProps = {
  stroke: AXIS,
  tick: { fill: AXIS, fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;

export function TrendArea({
  data,
  xKey,
  series,
  height = 160,
  unit,
}: {
  data: Record<string, string | number>[];
  xKey: string;
  series: { key: string; label: string }[];
  height?: number;
  unit?: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} {...axisProps} minTickGap={18} />
        <YAxis {...axisProps} allowDecimals={false} width={44} />
        <Tooltip content={<HudTooltip unit={unit} />} cursor={{ stroke: "rgb(34 211 238 / 0.4)" }} />
        {series.map((s, i) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={SERIES[i]}
            strokeWidth={2}
            fill={SERIES[i]}
            fillOpacity={0.12}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: "#0b1626" }}
            isAnimationActive={false}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function SimpleBars({
  data,
  xKey,
  yKey,
  label,
  height = 200,
  unit,
  layout = "vertical",
}: {
  data: Record<string, string | number>[];
  xKey: string;
  yKey: string;
  label: string;
  height?: number;
  unit?: string;
  layout?: "vertical" | "horizontal";
}) {
  const horizontal = layout === "horizontal";
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={data}
        layout={horizontal ? "vertical" : "horizontal"}
        margin={{ top: 6, right: 12, left: horizontal ? 8 : -18, bottom: 0 }}
        barCategoryGap={4}
      >
        <CartesianGrid stroke={GRID} vertical={horizontal} horizontal={!horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" {...axisProps} allowDecimals={false} />
            <YAxis type="category" dataKey={xKey} {...axisProps} width={120} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} {...axisProps} minTickGap={12} />
            <YAxis {...axisProps} allowDecimals={false} width={44} />
          </>
        )}
        <Tooltip content={<HudTooltip unit={unit} />} cursor={{ fill: "rgb(34 211 238 / 0.06)" }} />
        <Bar
          dataKey={yKey}
          name={label}
          fill={SERIES[0]}
          radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
          maxBarSize={28}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Legend({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-text-2">
      {items.map((it, i) => (
        <span key={it} className="inline-flex items-center gap-1.5">
          <span className="h-2 w-3 rounded-sm" style={{ background: SERIES[i] }} />
          {it}
        </span>
      ))}
    </div>
  );
}

/** Alterna entre gráfico e tabela (acessibilidade: os dados nunca dependem só da cor). */
export function ChartOrTable({
  chart,
  columns,
  rows,
}: {
  chart: React.ReactNode;
  columns: { key: string; label: string }[];
  rows: Record<string, string | number | null>[];
}) {
  const [mode, setMode] = useState<"chart" | "table">("chart");
  return (
    <div>
      <div className="mb-2 flex justify-end">
        <Tabs
          value={mode}
          onChange={setMode}
          items={[
            { value: "chart", label: "Gráfico" },
            { value: "table", label: "Tabela" },
          ]}
        />
      </div>
      {mode === "chart" ? (
        chart
      ) : (
        <div className="max-h-64 overflow-auto">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-surface">
              <tr>
                {columns.map((c) => (
                  <th key={c.key} className="border-b border-line px-2 py-1.5 font-medium text-muted">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-line/50">
                  {columns.map((c) => (
                    <td key={c.key} className="px-2 py-1 font-mono text-text-2">
                      {r[c.key] ?? "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
