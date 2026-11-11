import { useEffect, useRef } from "react";
import type { ChatResponse, ToolCall, ToolStatus } from "../../api/chat";
import { AgentChart } from "./AgentChart";

const STATUS: Record<ToolStatus | "skipped", { icon: string; label: string; className: string }> = {
  succeeded: { icon: "✓", label: "Succeeded", className: "text-[#006300]" },
  failed: { icon: "✕", label: "Failed", className: "text-status-critical" },
  timeout: { icon: "◷", label: "Timed out", className: "text-status-critical" },
  invalid_arguments: { icon: "!", label: "Invalid arguments", className: "text-[#a86b00]" },
  rejected: { icon: "⊘", label: "Refused", className: "text-ink-secondary" },
  skipped: { icon: "–", label: "Skipped", className: "text-ink-secondary" },
};

/** Charts, tool calls and the execution timeline behind the selected answer. */
export function EvidencePanel({ response, selectedTool }: { response: ChatResponse | undefined; selectedTool: string | null }) {
  if (!response) {
    return (
      <div className="rounded-lg border border-dashed border-hairline bg-surface p-5 text-sm text-ink-secondary">
        Charts, tool calls and the execution timeline for an answer appear here.
      </div>
    );
  }
  return (
    <div className="space-y-4">
      {response.charts.length > 0 && (
        <section aria-label="Charts" className="space-y-3">
          {response.charts.map((c) => (
            <AgentChart key={c.id} chart={c} />
          ))}
        </section>
      )}

      <section className="rounded-lg border border-hairline bg-surface">
        <h3 className="border-b border-hairline px-4 py-2.5 text-xs font-semibold text-ink">Tool calls</h3>
        {response.tool_calls.length === 0 ? (
          <p className="px-4 py-3 text-xs text-ink-secondary">No tools were called for this answer.</p>
        ) : (
          <ul>
            {response.tool_calls.map((t) => (
              <ToolCallRow key={t.id} call={t} selected={t.id === selectedTool} />
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-lg border border-hairline bg-surface">
        <h3 className="border-b border-hairline px-4 py-2.5 text-xs font-semibold text-ink">Execution timeline</h3>
        <ol className="px-4 py-3">
          {response.timeline.map((s, i) => {
            const st = STATUS[s.status];
            return (
              <li key={i} className="relative flex gap-3 pb-2 last:pb-0">
                <span aria-hidden className={`mt-0.5 w-4 shrink-0 text-center text-xs ${st.className}`}>{st.icon}</span>
                <span className="flex-1 text-xs text-ink">
                  <span className="text-ink-muted">{i + 1}.</span> {s.label}
                  <span className="sr-only"> ({st.label})</span>
                </span>
                <span className="text-[11px] tabular-nums text-ink-muted">{s.duration_ms} ms</span>
              </li>
            );
          })}
        </ol>
        <p className="border-t border-hairline px-4 py-2 text-[11px] text-ink-muted">
          {response.usage.tool_calls} of {response.usage.max_tool_calls} tool calls · {response.usage.planning_rounds} planning round
          {response.usage.planning_rounds === 1 ? "" : "s"}
          {response.usage.input_tokens + response.usage.output_tokens > 0 &&
            ` · ${(response.usage.input_tokens + response.usage.output_tokens).toLocaleString("en-US")} tokens`}
        </p>
      </section>
    </div>
  );
}

function ToolCallRow({ call, selected }: { call: ToolCall; selected: boolean }) {
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (selected) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected]);
  const st = STATUS[call.status];
  return (
    <li ref={ref} className={`border-b border-hairline px-4 py-2.5 last:border-0 ${selected ? "bg-[#eef4fc]" : ""}`}>
      <div className="flex items-center justify-between gap-2">
        <code className="truncate font-mono text-xs text-ink">{call.tool}</code>
        <span className={`shrink-0 text-[11px] font-medium ${st.className}`}>
          <span aria-hidden>{st.icon}</span> {st.label} · {call.duration_ms} ms
        </span>
      </div>
      {Object.keys(call.arguments).length > 0 && (
        <p className="mt-1 flex flex-wrap gap-1">
          {Object.entries(call.arguments).map(([k, v]) => (
            <span key={k} className="rounded bg-page px-1.5 py-px font-mono text-[10px] text-ink-secondary">
              {k}={Array.isArray(v) ? v.join(",") : String(v)}
            </span>
          ))}
        </p>
      )}
      <p className="mt-1 text-[11px] text-ink-secondary">{call.error ?? call.result_summary}</p>
    </li>
  );
}
