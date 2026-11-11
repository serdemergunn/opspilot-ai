import { useState } from "react";
import { Link } from "react-router-dom";
import { useDailyTrend, useDowntimeByLine, useDowntimeReasons, useLines, useMeta, useProductionSummary } from "../../api/hooks";
import { PageHeader } from "../../components/Layout";
import { Filters } from "../../components/Filters";
import { Card, DataTable, EmptyState, ErrorState, LoadingState, SourceNote, ViewToggle, useViewToggle } from "../../components/ui";
import { isWithin, PRESETS, previousPeriod, resolvePreset, type PresetId } from "../../lib/dateRange";
import { formatHours, formatInt, formatLongDate, formatMinutes, formatPct, formatRange, pointDelta, relativeDelta } from "../../lib/format";
import { AttainmentTrendChart, DowntimeByLineChart, DowntimeReasonsChart } from "./charts";
import { StatTile } from "./StatTile";

export function OverviewPage() {
  const meta = useMeta();
  const lines = useLines();
  const [preset, setPreset] = useState<PresetId>("last7");
  const [lineCode, setLineCode] = useState("");

  const today = meta.data?.today;
  const range = today ? resolvePreset(preset, today) : undefined;
  const previous = range ? previousPeriod(range) : undefined;
  const comparable = previous !== undefined && isWithin(previous, meta.data?.dataset.firstDate ?? null, meta.data?.dataset.lastDate ?? null);
  const lineFilter = lineCode ? [lineCode] : [];

  const summary = useProductionSummary(range, lineFilter);
  const previousSummary = useProductionSummary(comparable ? previous : undefined, lineFilter);
  const byLine = useDowntimeByLine(range, lineFilter);
  const reasons = useDowntimeReasons(range, lineFilter);
  const trend = useDailyTrend(range, lineFilter);

  if (meta.isError) {
    return (
      <>
        <PageHeader title="Overview" />
        <ErrorState error={meta.error} onRetry={() => meta.refetch()} />
      </>
    );
  }

  const t = summary.data?.data.totals;
  const p = comparable ? previousSummary.data?.data.totals : undefined;
  const comparison = comparable ? (PRESETS.find((x) => x.id === preset)?.comparison ?? null) : null;
  const scope = lineCode ? (lines.data?.find((l) => l.code === lineCode)?.name ?? lineCode) : "All lines";

  return (
    <>
      <PageHeader
        title="Overview"
        description={
          range && meta.data
            ? `${scope} · ${formatRange(range.start, range.end)} · ${meta.data.plantTimeZone}${meta.data.clockPinned ? ` · demo clock pinned to ${formatLongDate(meta.data.today)}` : ""}`
            : "Loading…"
        }
      >
        <Filters preset={preset} onPresetChange={setPreset} lineCode={lineCode} onLineChange={setLineCode} lines={lines.data} />
      </PageHeader>

      {summary.isError ? (
        <div className="mb-6">
          <ErrorState error={summary.error} onRetry={() => summary.refetch()} />
        </div>
      ) : (
        <div className="mb-2 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile
            label="Units produced"
            value={formatInt(t?.producedQuantity)}
            detail={t ? `of ${formatInt(t.plannedQuantity)} planned` : undefined}
            delta={relativeDelta(t?.producedQuantity ?? null, p?.producedQuantity ?? null)}
            comparison={comparison}
            higherIsBetter
            loading={!t}
          />
          <StatTile
            label="Attainment"
            value={formatPct(t?.attainmentPct)}
            detail="produced ÷ planned"
            delta={pointDelta(t?.attainmentPct ?? null, p?.attainmentPct ?? null)}
            comparison={comparison}
            higherIsBetter
            loading={!t}
          />
          <StatTile
            label="Downtime"
            value={formatHours(t?.downtimeHours)}
            detail={t ? formatMinutes(t.downtimeMinutes) : undefined}
            delta={relativeDelta(t?.downtimeMinutes ?? null, p?.downtimeMinutes ?? null)}
            comparison={comparison}
            higherIsBetter={false}
            loading={!t}
          />
          <StatTile
            label="Defect rate"
            value={formatPct(t?.defectRatePct)}
            detail={t ? `${formatInt(t.defectiveQuantity)} defective units` : undefined}
            delta={pointDelta(t?.defectRatePct ?? null, p?.defectRatePct ?? null)}
            comparison={comparison}
            higherIsBetter={false}
            loading={!t}
          />
        </div>
      )}
      <div className="mb-6">
        <SourceNote tool="GET /api/analytics/production-summary" meta={summary.data?.meta} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <TrendCard query={trend} />
        <FindingsCard />
        <DowntimeByLineCard query={byLine} />
        <DowntimeReasonsCard query={reasons} />
      </div>
    </>
  );
}

type Q<T> = { data?: { data: T; meta: import("../../api/types").QueryMeta }; isError: boolean; error: unknown; refetch: () => unknown };

function TrendCard({ query }: { query: Q<import("../../api/types").DailyTrend> }) {
  const [view, setView] = useViewToggle();
  const points = query.data?.data.items ?? [];
  return (
    <Card
      title="Daily attainment"
      subtitle="Produced ÷ planned units per day"
      actions={<ViewToggle value={view} onChange={setView} />}
      footer={<SourceNote tool="GET /api/analytics/daily-trend" meta={query.data?.meta} />}
    >
      {query.isError ? (
        <ErrorState error={query.error} onRetry={query.refetch} />
      ) : !query.data ? (
        <LoadingState className="h-64" />
      ) : points.every((d) => d.plannedQuantity === 0) ? (
        <EmptyState message="No production records in this period." />
      ) : view === "chart" ? (
        <AttainmentTrendChart points={points} />
      ) : (
        <DataTable
          caption="Daily production"
          rows={points}
          rowKey={(r) => r.date}
          columns={[
            { header: "Date", cell: (r) => formatLongDate(r.date) },
            { header: "Planned", cell: (r) => formatInt(r.plannedQuantity), numeric: true },
            { header: "Produced", cell: (r) => formatInt(r.producedQuantity), numeric: true },
            { header: "Attainment", cell: (r) => formatPct(r.attainmentPct), numeric: true },
            { header: "Defect rate", cell: (r) => formatPct(r.defectRatePct), numeric: true },
            { header: "Downtime", cell: (r) => formatMinutes(r.downtimeMinutes), numeric: true },
          ]}
        />
      )}
    </Card>
  );
}

function DowntimeByLineCard({ query }: { query: Q<import("../../api/types").DowntimeByLine> }) {
  const [view, setView] = useViewToggle();
  const d = query.data?.data;
  return (
    <Card
      title="Downtime by line"
      subtitle={d ? `${formatHours(d.totalDowntimeMinutes / 60)} total, planned and unplanned` : "Planned and unplanned"}
      actions={<ViewToggle value={view} onChange={setView} />}
      footer={<SourceNote tool="GET /api/analytics/downtime-by-line" meta={query.data?.meta} />}
    >
      {query.isError ? (
        <ErrorState error={query.error} onRetry={query.refetch} />
      ) : !d ? (
        <LoadingState />
      ) : d.totalDowntimeMinutes === 0 ? (
        <EmptyState message="No downtime recorded in this period." />
      ) : view === "chart" ? (
        <DowntimeByLineChart items={d.items} />
      ) : (
        <DataTable
          caption="Downtime by line"
          rows={d.items}
          rowKey={(r) => r.lineCode}
          columns={[
            { header: "Line", cell: (r) => r.lineName },
            { header: "Minutes", cell: (r) => formatInt(r.downtimeMinutes), numeric: true },
            { header: "Hours", cell: (r) => formatHours(r.downtimeHours), numeric: true },
            { header: "Share", cell: (r) => formatPct(r.sharePct), numeric: true },
            { header: "Events", cell: (r) => formatInt(r.eventCount), numeric: true },
          ]}
        />
      )}
    </Card>
  );
}

function DowntimeReasonsCard({ query }: { query: Q<import("../../api/types").DowntimeReasons> }) {
  const [view, setView] = useViewToggle();
  const d = query.data?.data;
  return (
    <Card
      title="Downtime reasons"
      subtitle="Share of all downtime minutes in the period"
      actions={<ViewToggle value={view} onChange={setView} />}
      footer={<SourceNote tool="GET /api/analytics/downtime-reasons" meta={query.data?.meta} />}
    >
      {query.isError ? (
        <ErrorState error={query.error} onRetry={query.refetch} />
      ) : !d ? (
        <LoadingState />
      ) : d.items.length === 0 ? (
        <EmptyState message="No downtime recorded in this period." />
      ) : view === "chart" ? (
        <DowntimeReasonsChart items={d.items} />
      ) : (
        <DataTable
          caption="Downtime by reason"
          rows={d.items}
          rowKey={(r) => r.reasonCode}
          columns={[
            { header: "Reason", cell: (r) => r.reasonName },
            { header: "Type", cell: (r) => (r.isPlanned ? "Planned" : "Unplanned") },
            { header: "Minutes", cell: (r) => formatInt(r.downtimeMinutes), numeric: true },
            { header: "Share", cell: (r) => formatPct(r.sharePct), numeric: true },
            { header: "Events", cell: (r) => formatInt(r.eventCount), numeric: true },
          ]}
        />
      )}
    </Card>
  );
}

function FindingsCard() {
  return (
    <Card title="AI findings" subtitle="Evidence-based observations from the AI Analyst">
      <div className="flex h-full min-h-48 flex-col justify-center gap-3 rounded-md border border-dashed border-hairline p-5 text-sm text-ink-secondary">
        <p>
          Ask the{" "}
          <Link to="/analyst" className="font-medium text-[#1c5cab] underline underline-offset-2">
            AI Analyst
          </Link>{" "}
          a question. Its findings are labeled as verified measurements, calculations, patterns, hypotheses or suggested actions, and each
          one links to the tool call that produced its numbers.
        </p>
        <p className="text-xs text-ink-muted">Every number on this page is computed by the API from database records. Nothing here is generated by an LLM.</p>
      </div>
    </Card>
  );
}
