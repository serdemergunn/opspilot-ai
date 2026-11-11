import { useState, type ReactNode } from "react";
import type { QueryMeta } from "../api/types";
import { ApiError } from "../api/client";

export function Card({
  title,
  subtitle,
  actions,
  footer,
  children,
  className = "",
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`flex flex-col rounded-lg border border-hairline bg-surface ${className}`}>
      <header className="flex items-start justify-between gap-4 px-5 pt-4">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-ink-secondary">{subtitle}</p>}
        </div>
        {actions}
      </header>
      <div className="flex-1 px-5 pb-4 pt-3">{children}</div>
      {footer && <footer className="border-t border-hairline px-5 py-2.5">{footer}</footer>}
    </section>
  );
}

/** Where a number came from: every chart and tile names its endpoint/tool, window and row count. */
export function SourceNote({ tool, meta }: { tool: string; meta: QueryMeta | undefined }) {
  if (!meta) return null;
  return (
    <p className="text-[11px] leading-4 text-ink-muted">
      <span className="font-medium text-ink-secondary">Source:</span> <code className="font-mono">{tool}</code> ·{" "}
      {meta.source.replace("sqlserver:", "SQL Server ")} · {meta.rowCount.toLocaleString("en-US")} rows · {meta.queryMs} ms ·
      metric definitions v{meta.metricDefinitionsVersion}
    </p>
  );
}

export function ViewToggle({ value, onChange }: { value: "chart" | "table"; onChange: (v: "chart" | "table") => void }) {
  return (
    <div role="group" aria-label="View" className="flex shrink-0 rounded-md border border-hairline p-0.5 text-xs">
      {(["chart", "table"] as const).map((v) => (
        <button
          key={v}
          type="button"
          aria-pressed={value === v}
          onClick={() => onChange(v)}
          className={`rounded px-2 py-0.5 capitalize ${value === v ? "bg-navy-900 text-white" : "text-ink-secondary hover:bg-page"}`}
        >
          {v}
        </button>
      ))}
    </div>
  );
}

export function useViewToggle() {
  return useState<"chart" | "table">("chart");
}

export function Skeleton({ className = "h-56" }: { className?: string }) {
  return <div aria-hidden className={`animate-pulse rounded-md bg-page ${className}`} />;
}

export function LoadingState({ className }: { className?: string }) {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">Loading…</span>
      <Skeleton className={className} />
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-hairline text-sm text-ink-secondary">
      {message}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof ApiError ? error.message : "Something went wrong while loading this data.";
  const fields = error instanceof ApiError ? Object.values(error.fieldErrors).flat() : [];
  return (
    <div role="alert" className="flex min-h-40 flex-col items-center justify-center gap-2 rounded-md border border-status-critical/30 bg-status-critical/5 p-4 text-center">
      <p className="flex items-center gap-1.5 text-sm font-medium text-ink">
        <span aria-hidden className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-status-critical text-[10px] font-bold text-white">!</span>
        Error: {message}
      </p>
      {fields.map((f) => (
        <p key={f} className="text-xs text-ink-secondary">{f}</p>
      ))}
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-1 rounded-md border border-hairline bg-white px-3 py-1 text-xs font-medium text-ink hover:bg-page">
          Retry
        </button>
      )}
    </div>
  );
}

export interface Column<T> {
  header: string;
  cell: (row: T) => ReactNode;
  numeric?: boolean;
}

export function DataTable<T>({ rows, columns, rowKey, caption }: { rows: T[]; columns: Column<T>[]; rowKey: (row: T) => string; caption: string }) {
  return (
    <div className="max-h-72 overflow-auto">
      <table className="w-full text-left text-xs">
        <caption className="sr-only">{caption}</caption>
        <thead className="sticky top-0 bg-surface text-ink-secondary">
          <tr className="border-b border-hairline">
            {columns.map((c) => (
              <th key={c.header} scope="col" className={`py-2 pr-3 font-medium ${c.numeric ? "text-right" : ""}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)} className="border-b border-hairline/60 last:border-0">
              {columns.map((c) => (
                <td key={c.header} className={`py-1.5 pr-3 text-ink ${c.numeric ? "text-right tabular-nums" : ""}`}>
                  {c.cell(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PhaseBadge({ phase }: { phase: string }) {
  return <span className="rounded bg-navy-800 px-1.5 py-px text-[10px] font-medium text-navy-300">{phase}</span>;
}
