import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";
import type { DailyPoint, LineDowntime, ReasonDowntime } from "../../api/types";
import { formatDay, formatHours, formatInt, formatLongDate, formatMinutes, formatPct } from "../../lib/format";

// Chart tokens (validated with the dataviz palette validator: light surface, 2 categorical slots, all checks pass).
export const viz = {
  surface: "#fcfcfb",
  series1: "#2a78d6", // unplanned downtime, attainment, downtime by line
  series2: "#eb6834", // planned downtime
  ink: "#0b0b0b",
  inkSecondary: "#52514e",
  muted: "#898781",
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  hover: "rgba(11,11,11,0.04)",
};

const axisTick = { fill: viz.muted, fontSize: 11 };

function TooltipBox({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div className="rounded-md border border-hairline bg-white px-3 py-2 text-xs shadow-sm">
      <p className="mb-1 font-medium text-ink">{title}</p>
      {rows.map(([k, v]) => (
        <p key={k} className="flex justify-between gap-6 text-ink-secondary">
          <span>{k}</span>
          <span className="tabular-nums text-ink">{v}</span>
        </p>
      ))}
    </div>
  );
}

/** Round percentage axis: bounds on multiples of 5, ticks every 5 or 10 points, capped at 0–100. */
export function percentAxis(values: number[]): { domain: [number, number]; ticks: number[] } {
  if (values.length === 0) return { domain: [0, 100], ticks: [0, 25, 50, 75, 100] };
  const lo = Math.max(0, Math.floor((Math.min(...values) - 2) / 5) * 5);
  const hi = Math.min(100, Math.ceil((Math.max(...values) + 2) / 5) * 5);
  const step = hi - lo > 30 ? 10 : 5;
  const ticks: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(t);
  return { domain: [lo, hi], ticks };
}

export function AttainmentTrendChart({ points }: { points: DailyPoint[] }) {
  const sparse = points.length <= 2;
  const axis = percentAxis(points.flatMap((p) => (p.attainmentPct == null ? [] : [p.attainmentPct])));
  return (
    <div className="h-64" role="img" aria-label="Daily production attainment in percent. Use the Table view for exact values.">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid vertical={false} stroke={viz.grid} />
          <XAxis dataKey="date" tickFormatter={formatDay} tick={axisTick} axisLine={{ stroke: viz.axis }} tickLine={false} minTickGap={24} />
          <YAxis
            domain={axis.domain}
            ticks={axis.ticks}
            tickFormatter={(v: number) => `${v}%`}
            tick={axisTick}
            axisLine={false}
            tickLine={false}
            width={48}
          />
          <Tooltip
            cursor={{ stroke: viz.axis, strokeWidth: 1 }}
            content={({ active, payload }: TooltipProps<number, string>) => {
              const p = payload?.[0]?.payload as DailyPoint | undefined;
              if (!active || !p) return null;
              return (
                <TooltipBox
                  title={formatLongDate(p.date)}
                  rows={[
                    ["Attainment", formatPct(p.attainmentPct)],
                    ["Produced", formatInt(p.producedQuantity)],
                    ["Planned", formatInt(p.plannedQuantity)],
                    ["Downtime", formatMinutes(p.downtimeMinutes)],
                  ]}
                />
              );
            }}
          />
          <Line
            type="linear"
            dataKey="attainmentPct"
            stroke={viz.series1}
            strokeWidth={2}
            dot={sparse ? { r: 4, fill: viz.series1, stroke: viz.surface, strokeWidth: 2 } : false}
            activeDot={{ r: 5, fill: viz.series1, stroke: viz.surface, strokeWidth: 2 }}
            isAnimationActive={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DowntimeByLineChart({ items }: { items: LineDowntime[] }) {
  return (
    <div style={{ height: Math.max(120, items.length * 36 + 24) }} role="img" aria-label="Downtime hours by production line, longest first. Use the Table view for exact values.">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={items} layout="vertical" margin={{ top: 4, right: 96, bottom: 4, left: 0 }} barCategoryGap={8}>
          <CartesianGrid horizontal={false} stroke={viz.grid} />
          <XAxis type="number" dataKey="downtimeHours" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={(v: number) => `${v} h`} />
          <YAxis type="category" dataKey="lineName" tick={{ ...axisTick, fill: viz.inkSecondary }} axisLine={{ stroke: viz.axis }} tickLine={false} width={64} />
          <Tooltip
            cursor={{ fill: viz.hover }}
            content={({ active, payload }: TooltipProps<number, string>) => {
              const d = payload?.[0]?.payload as LineDowntime | undefined;
              if (!active || !d) return null;
              return (
                <TooltipBox
                  title={d.lineName}
                  rows={[
                    ["Downtime", `${formatMinutes(d.downtimeMinutes)} (${formatHours(d.downtimeHours)})`],
                    ["Share of total", formatPct(d.sharePct)],
                    ["Events", formatInt(d.eventCount)],
                  ]}
                />
              );
            }}
          />
          <Bar dataKey="downtimeHours" fill={viz.series1} radius={[0, 4, 4, 0]} maxBarSize={20} isAnimationActive={false}>
            <LabelList
              dataKey="sharePct"
              position="right"
              content={({ x, y, width, height, index }) => {
                const d = items[index ?? -1];
                if (!d) return null;
                return (
                  <text x={Number(x) + Number(width) + 6} y={Number(y) + Number(height) / 2} dominantBaseline="central" fontSize={11} fill={viz.inkSecondary}>
                    {formatHours(d.downtimeHours)} · {formatPct(d.sharePct)}
                  </text>
                );
              }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DowntimeReasonsChart({ items }: { items: ReasonDowntime[] }) {
  return (
    <div>
      <ul className="mb-2 flex gap-4 text-xs text-ink-secondary" aria-label="Legend">
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: viz.series1 }} /> Unplanned
        </li>
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: viz.series2 }} /> Planned
        </li>
      </ul>
      <div style={{ height: Math.max(120, items.length * 36 + 24) }} role="img" aria-label="Downtime hours by reason, planned and unplanned, longest first. Use the Table view for exact values.">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={items} layout="vertical" margin={{ top: 4, right: 96, bottom: 4, left: 0 }} barCategoryGap={8}>
            <CartesianGrid horizontal={false} stroke={viz.grid} />
            <XAxis type="number" dataKey="downtimeHours" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={(v: number) => `${v} h`} />
            <YAxis type="category" dataKey="reasonName" tick={{ ...axisTick, fill: viz.inkSecondary }} axisLine={{ stroke: viz.axis }} tickLine={false} width={136} />
            <Tooltip
              cursor={{ fill: viz.hover }}
              content={({ active, payload }: TooltipProps<number, string>) => {
                const d = payload?.[0]?.payload as ReasonDowntime | undefined;
                if (!active || !d) return null;
                return (
                  <TooltipBox
                    title={`${d.reasonName} (${d.isPlanned ? "planned" : "unplanned"})`}
                    rows={[
                      ["Downtime", `${formatMinutes(d.downtimeMinutes)} (${formatHours(d.downtimeHours)})`],
                      ["Share of total", formatPct(d.sharePct)],
                      ["Events", formatInt(d.eventCount)],
                      ["Code", d.reasonCode],
                    ]}
                  />
                );
              }}
            />
            <Bar dataKey="downtimeHours" radius={[0, 4, 4, 0]} maxBarSize={20} isAnimationActive={false}>
              {items.map((d) => (
                <Cell key={d.reasonCode} fill={d.isPlanned ? viz.series2 : viz.series1} />
              ))}
              <LabelList
                dataKey="sharePct"
                position="right"
                content={({ x, y, width, height, index }) => {
                  const d = items[index ?? -1];
                  if (!d) return null;
                  return (
                    <text x={Number(x) + Number(width) + 6} y={Number(y) + Number(height) / 2} dominantBaseline="central" fontSize={11} fill={viz.inkSecondary}>
                      {formatHours(d.downtimeHours)} · {formatPct(d.sharePct)}
                    </text>
                  );
                }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
