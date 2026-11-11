import type { ProductionLine } from "../api/types";
import { PRESETS, type PresetId } from "../lib/dateRange";

/** One row of filters above the charts: date preset and production line. */
export function Filters({
  preset,
  onPresetChange,
  lineCode,
  onLineChange,
  lines,
}: {
  preset: PresetId;
  onPresetChange: (p: PresetId) => void;
  lineCode: string;
  onLineChange: (code: string) => void;
  lines: ProductionLine[] | undefined;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div role="radiogroup" aria-label="Date range" className="flex rounded-md border border-hairline bg-surface p-0.5 text-sm">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            role="radio"
            aria-checked={preset === p.id}
            onClick={() => onPresetChange(p.id)}
            className={`rounded px-3 py-1 ${preset === p.id ? "bg-navy-900 font-medium text-white" : "text-ink-secondary hover:bg-page"}`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <label className="flex items-center gap-2 text-sm text-ink-secondary">
        <span>Line</span>
        <select
          value={lineCode}
          onChange={(e) => onLineChange(e.target.value)}
          className="rounded-md border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All lines</option>
          {lines
            ?.filter((l) => l.isActive)
            .map((l) => (
              <option key={l.code} value={l.code}>
                {l.name} · {l.department}
              </option>
            ))}
        </select>
      </label>
    </div>
  );
}
