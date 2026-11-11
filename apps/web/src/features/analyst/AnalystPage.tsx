import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { buildHistory, sendChat, type AgentMode, type ChatResponse } from "../../api/chat";
import { PageHeader } from "../../components/Layout";
import { ErrorState } from "../../components/ui";
import { AnswerView } from "./AnswerView";
import { EvidencePanel } from "./EvidencePanel";

interface Turn {
  id: number;
  question: string;
  mode: AgentMode;
  response?: ChatResponse;
  error?: unknown;
}

export const EXAMPLE_QUESTIONS = [
  "Which production line had the most downtime last week?",
  "What are the three most common causes of production interruptions?",
  "Compare the performance of Line 01 and Line 04.",
  "Why did production efficiency decrease yesterday?",
  "Summarize the operational performance of the previous month.",
  "What does the maintenance documentation say about error code E104?",
];

const MAX_QUESTION = 2_000;

export function AnalystPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<AgentMode>("demo");
  const [selected, setSelected] = useState<{ turn: number; tool: string | null } | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const chat = useMutation({
    mutationFn: ({ history, mode }: { id: number; history: ReturnType<typeof buildHistory>; mode: AgentMode }) => sendChat(history, mode),
    onSuccess: (response, { id }) => {
      setTurns((ts) => ts.map((t) => (t.id === id ? { ...t, response } : t)));
      setSelected({ turn: id, tool: null });
    },
    onError: (error, { id }) => setTurns((ts) => ts.map((t) => (t.id === id ? { ...t, error } : t))),
  });

  // Block body on purpose: an effect must return nothing or a cleanup function, and scrollIntoView may return a Promise.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns]);

  const ask = (question: string) => {
    const q = question.trim();
    if (!q || chat.isPending) return;
    const id = (turns.at(-1)?.id ?? 0) + 1;
    const history = buildHistory(turns, q);
    setTurns((ts) => [...ts, { id, question: q, mode }]);
    setDraft("");
    chat.mutate({ id, history, mode });
  };

  const selectedTurn = turns.find((t) => t.id === selected?.turn) ?? [...turns].reverse().find((t) => t.response);

  return (
    <>
      <PageHeader title="AI Analyst" description="Ask about production and downtime. Every number comes from a read-only tool call and is checked before it is shown.">
        <div role="radiogroup" aria-label="Answer mode" className="flex rounded-md border border-hairline bg-surface p-0.5 text-sm">
          {(["demo", "live"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={mode === m}
              onClick={() => setMode(m)}
              className={`rounded px-3 py-1 ${mode === m ? "bg-navy-900 font-medium text-white" : "text-ink-secondary hover:bg-page"}`}
            >
              {m === "demo" ? "Demo (no LLM)" : "Live (Claude)"}
            </button>
          ))}
        </div>
      </PageHeader>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
        <section aria-label="Conversation" className="flex min-h-[60vh] flex-col rounded-lg border border-hairline bg-surface">
          <div className="flex-1 space-y-5 overflow-y-auto p-5">
            {turns.length === 0 && <Welcome onAsk={ask} mode={mode} />}
            {turns.map((t) => (
              <article key={t.id} className="space-y-3">
                <div className="flex justify-end">
                  <p className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-navy-900 px-3.5 py-2 text-sm text-white">{t.question}</p>
                </div>
                <div
                  className={`rounded-lg border p-4 ${selectedTurn?.id === t.id && t.response ? "border-[#2a78d6]/40" : "border-hairline"}`}
                  onClick={() => t.response && setSelected({ turn: t.id, tool: selected?.turn === t.id ? selected.tool : null })}
                >
                  {t.response ? (
                    <AnswerView response={t.response} onSelectTool={(tool) => setSelected({ turn: t.id, tool })} />
                  ) : t.error ? (
                    <ErrorState error={t.error} onRetry={() => ask(t.question)} />
                  ) : (
                    <p role="status" className="flex items-center gap-2 text-sm text-ink-secondary">
                      <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-[#2a78d6]" />
                      Planning tool calls and checking results…
                    </p>
                  )}
                </div>
              </article>
            ))}
            <div ref={endRef} />
          </div>

          <form
            className="border-t border-hairline p-3"
            onSubmit={(e) => {
              e.preventDefault();
              ask(draft);
            }}
          >
            <label htmlFor="question" className="sr-only">Question</label>
            <div className="flex items-end gap-2">
              <textarea
                id="question"
                rows={2}
                maxLength={MAX_QUESTION}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    ask(draft);
                  }
                }}
                placeholder="Ask about production, attainment or downtime…"
                className="min-h-[44px] flex-1 resize-y rounded-md border border-hairline bg-white px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-[#2a78d6] focus:outline-none"
              />
              <button
                type="submit"
                disabled={!draft.trim() || chat.isPending}
                className="h-[44px] rounded-md bg-navy-900 px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                Ask
              </button>
            </div>
            <p className="mt-1.5 text-[11px] text-ink-muted">
              Enter to send · Shift+Enter for a new line · {mode === "demo" ? "Demo answers are rule-based and labeled as such." : "Live mode needs ANTHROPIC_API_KEY on the AI service; without it, answers fall back to demo and say so."}
            </p>
          </form>
        </section>

        <aside aria-label="Evidence" className="xl:sticky xl:top-6 xl:max-h-[calc(100vh-3rem)] xl:self-start xl:overflow-y-auto">
          <EvidencePanel response={selectedTurn?.response} selectedTool={selected?.turn === selectedTurn?.id ? (selected?.tool ?? null) : null} />
        </aside>
      </div>
    </>
  );
}

function Welcome({ onAsk, mode }: { onAsk: (q: string) => void; mode: AgentMode }) {
  return (
    <div className="mx-auto max-w-xl py-6 text-center">
      <h2 className="text-base font-semibold text-ink">Ask an operational question</h2>
      <p className="mt-1 text-sm text-ink-secondary">
        The analyst picks read-only tools, runs them against the database and explains the results. Findings are labeled as measurements,
        calculations, patterns, hypotheses or suggested actions.
        {mode === "demo" && " Demo mode answers a fixed set of question types without an LLM."}
      </p>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        {EXAMPLE_QUESTIONS.map((q) => (
          <button key={q} type="button" onClick={() => onAsk(q)} className="rounded-full border border-hairline bg-white px-3 py-1.5 text-left text-xs text-ink hover:border-[#2a78d6]">
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
