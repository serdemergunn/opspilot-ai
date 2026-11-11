import { Bar, BarChart, CartesianGrid, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AgentChart as ChartSpec } from "../../api/chat";
import { DataTable, ViewToggle, useViewToggle } from "../../components/ui";
import { formatDay, formatLongDate } from "../../lib/format";
import { percentAxis, viz } from "../overview/charts";

const tick = { fill: viz.muted, fontSize: 11 };

const label = (key: string) => key.replace(/_/g, " ").replace(/\bpct\b/, "%").replace(/^./, (c) => c.toUpperCase());

/** "48.4 h" / "81.5%" with a non-breaking space, so SVG labels never wrap between value and unit. */
const NBSP = String.fromCharCode(0xa0);
export const withUnit = (v: number, unit: string) => (unit === "%" ? `${v}%` : `${v}${NBSP}${unit}`);

const show = (v: unknown) => (v == null ? "—" : typeof v === "number" ? v.toLocaleString("en-US") : String(v));

/** Renders a chart spec produced by the AI service from a tool result. Values are drawn, never recomputed. */
export function AgentChart({ chart }: { chart: ChartSpec }) {
  const [view, setView] = useViewToggle();
  const series = chart.series[0]!;
  const columns = Object.keys(chart.data[0] ?? {});

  return (
    <figure className="rounded-md border border-hairline bg-surface p-3">
      <figcaption className="mb-2 flex items-start justify-between gap-3">
        <span className="text-xs font-medium text-ink">{chart.title}</span>
        <ViewToggle value={view} onChange={setView} />
      </figcaption>
      {view === "table" ? (
        <DataTable<ChartSpec["data"][number]>
          caption={chart.title}
          rows={chart.data}
          rowKey={(r) => String(r[chart.x_key])}
          columns={columns.map((c) => ({ header: label(c), cell: (r) => (c === "date" ? formatLongDate(String(r[c])) : show(r[c])), numeric: typeof chart.data[0]?.[c] === "number" }))}
        />
      ) : chart.type === "bar" ? (
        <div style={{ height: Math.max(110, chart.data.length * 30 + 20) }} role="img" aria-label={`${chart.title}. Use the Table view for exact values.`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart.data} layout="vertical" margin={{ top: 0, right: 56, bottom: 0, left: 0 }} barCategoryGap={6}>
              <CartesianGrid horizontal={false} stroke={viz.grid} />
              <XAxis type="number" dataKey={series.key} tick={tick} axisLine={false} tickLine={false} tickFormatter={(v: number) => withUnit(v, chart.unit)} />
              <YAxis type="category" dataKey={chart.x_key} tick={{ ...tick, fill: viz.inkSecondary }} axisLine={{ stroke: viz.axis }} tickLine={false} width={124} />
              <Tooltip cursor={{ fill: viz.hover }} formatter={(v: number) => [withUnit(v, chart.unit), series.label]} />
              <Bar dataKey={series.key} fill={viz.series1} radius={[0, 4, 4, 0]} maxBarSize={18} isAnimationActive={false}>
                <LabelList dataKey={series.key} position="right" fontSize={11} fill={viz.inkSecondary} formatter={(v: number) => withUnit(v, chart.unit)} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <LineView chart={chart} />
      )}
    </figure>
  );
}

function LineView({ chart }: { chart: ChartSpec }) {
  const key = chart.series[0]!.key;
  const values = chart.data.flatMap((d) => (typeof d[key] === "number" ? [d[key] as number] : []));
  const axis = chart.unit === "%" ? percentAxis(values) : undefined;
  return (
    <div className="h-48" role="img" aria-label={`${chart.title}. Use the Table view for exact values.`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chart.data} margin={{ top: 6, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={viz.grid} />
          <XAxis dataKey={chart.x_key} tickFormatter={(v: string) => formatDay(v)} tick={tick} axisLine={{ stroke: viz.axis }} tickLine={false} minTickGap={20} />
          <YAxis domain={axis?.domain} ticks={axis?.ticks} tickFormatter={(v: number) => `${v}${chart.unit}`} tick={tick} axisLine={false} tickLine={false} width={44} />
          <Tooltip labelFormatter={(v: string) => formatLongDate(v)} formatter={(v: number) => [`${v}${chart.unit}`, chart.series[0]!.label]} />
          <Line type="linear" dataKey={key} stroke={viz.series1} strokeWidth={2} dot={chart.data.length <= 2} activeDot={{ r: 4 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
