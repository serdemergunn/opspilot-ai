import type { Delta } from "../../lib/format";
import { Skeleton } from "../../components/ui";

/**
 * A headline number. Deltas carry an arrow and a text label, so the good/bad reading never depends
 * on color alone; `higherIsBetter` decides which direction counts as good.
 */
export function StatTile({
  label,
  value,
  detail,
  delta,
  comparison,
  higherIsBetter,
  loading,
}: {
  label: string;
  value: string;
  detail?: string;
  delta: Delta | null;
  comparison: string | null;
  higherIsBetter: boolean;
  loading: boolean;
}) {
  return (
    <div className="rounded-lg border border-hairline bg-surface px-5 py-4">
      <p className="text-xs font-medium text-ink-secondary">{label}</p>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-32" />
      ) : (
        <>
          <p className="mt-1 text-2xl font-semibold text-ink">{value}</p>
          {detail && <p className="text-xs text-ink-secondary">{detail}</p>}
          <DeltaLine delta={delta} comparison={comparison} higherIsBetter={higherIsBetter} />
        </>
      )}
    </div>
  );
}

function DeltaLine({ delta, comparison, higherIsBetter }: { delta: Delta | null; comparison: string | null; higherIsBetter: boolean }) {
  if (!comparison) return <p className="mt-1 text-xs text-ink-muted">No comparison period in the dataset</p>;
  if (!delta) return <p className="mt-1 text-xs text-ink-muted">{comparison}: not comparable</p>;
  const good = delta.direction === "flat" ? null : (delta.direction === "up") === higherIsBetter;
  const tone = good === null ? "text-ink-secondary" : good ? "text-[#006300]" : "text-status-critical";
  const arrow = delta.direction === "up" ? "▲" : delta.direction === "down" ? "▼" : "■";
  const verdict = good === null ? "no change" : good ? "better" : "worse";
  return (
    <p className="mt-1 text-xs text-ink-muted">
      <span className={`font-medium ${tone}`}>
        <span aria-hidden>{arrow}</span> {delta.label} ({verdict})
      </span>{" "}
      {comparison}
    </p>
  );
}
