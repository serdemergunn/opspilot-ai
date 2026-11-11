import { useMeta } from "../api/hooks";
import { PageHeader } from "../components/Layout";
import { Card, ErrorState, LoadingState } from "../components/ui";
import { formatLongDate } from "../lib/format";

export function SettingsPage() {
  const meta = useMeta();
  return (
    <>
      <PageHeader title="Settings" description="Read-only environment information. Configuration is set through environment variables." />
      <Card title="Environment">
        {meta.isError ? (
          <ErrorState error={meta.error} onRetry={() => meta.refetch()} />
        ) : !meta.data ? (
          <LoadingState className="h-32" />
        ) : (
          <dl className="grid grid-cols-1 gap-x-8 gap-y-3 text-sm sm:grid-cols-[max-content_1fr]">
            <dt className="text-ink-secondary">Clock</dt>
            <dd>
              {meta.data.clockPinned ? "Pinned (demo)" : "Wall clock"} · today is {formatLongDate(meta.data.today)}
            </dd>
            <dt className="text-ink-secondary">Plant time zone</dt>
            <dd>{meta.data.plantTimeZone}</dd>
            <dt className="text-ink-secondary">Dataset</dt>
            <dd>
              {meta.data.dataset.firstDate && meta.data.dataset.lastDate
                ? `${formatLongDate(meta.data.dataset.firstDate)} – ${formatLongDate(meta.data.dataset.lastDate)} (synthetic)`
                : "Empty"}
            </dd>
            <dt className="text-ink-secondary">Query limits</dt>
            <dd>
              Ranges up to {meta.data.limits.maxRangeDays} days · at most {meta.data.limits.maxTopN} items per list
            </dd>
            <dt className="text-ink-secondary">Access</dt>
            <dd>Anonymous, localhost only. Authentication is required before any public deployment.</dd>
          </dl>
        )}
      </Card>
    </>
  );
}
