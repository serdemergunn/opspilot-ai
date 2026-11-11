// Contract of POST /api/chat, passed through unchanged from the AI service (snake_case).
import { ApiError } from "./client";

export type FindingKind = "measurement" | "calculation" | "pattern" | "hypothesis" | "recommendation";
export type ToolStatus = "succeeded" | "failed" | "rejected" | "timeout" | "invalid_arguments";
export type AgentMode = "demo" | "live";

export interface Finding {
  id: string;
  kind: FindingKind;
  text: string;
  evidence: { tool_call_id: string }[];
  grounding: "verified" | "derived" | "no_numbers";
}

export interface AgentChart {
  id: string;
  type: "bar" | "line";
  title: string;
  x_key: string;
  series: { key: string; label: string }[];
  data: Record<string, string | number | boolean | null>[];
  unit: string;
  source_tool_call_id: string;
}

export interface ToolCall {
  id: string;
  tool: string;
  status: ToolStatus;
  arguments: Record<string, unknown>;
  duration_ms: number;
  result_summary: string;
  error: string | null;
}

export interface TimelineStep {
  step: string;
  label: string;
  status: "succeeded" | "failed" | "skipped";
  duration_ms: number;
}

export interface ChatResponse {
  answer_id: string;
  mode: AgentMode;
  provider: string;
  summary: string;
  findings: Finding[];
  charts: AgentChart[];
  tool_calls: ToolCall[];
  timeline: TimelineStep[];
  warnings: string[];
  usage: { tool_calls: number; max_tool_calls: number; planning_rounds: number; input_tokens: number; output_tokens: number };
}

export interface ChatTurnMessage {
  role: "user" | "assistant";
  content: string;
}

export async function sendChat(messages: ChatTurnMessage[], mode: AgentMode, signal?: AbortSignal): Promise<ChatResponse> {
  let response: Response;
  try {
    response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ messages, mode }),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "The API is unreachable. Is it running on 127.0.0.1:8080?");
  }
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as { title?: string; errors?: Record<string, string[]> } | null;
    if (response.status === 429) throw new ApiError(429, "Too many questions in a short time. Wait a minute and try again.");
    throw new ApiError(response.status, problem?.title ?? `The request failed (HTTP ${response.status}).`, problem?.errors ?? {});
  }
  return (await response.json()) as ChatResponse;
}

/** Conversation history sent with a new question: earlier questions and the summaries that answered them. */
export function buildHistory(turns: { question: string; response?: ChatResponse }[], question: string, maxTurns = 9): ChatTurnMessage[] {
  const history: ChatTurnMessage[] = [];
  for (const t of turns.slice(-maxTurns)) {
    if (!t.response) continue;
    history.push({ role: "user", content: t.question }, { role: "assistant", content: t.response.summary });
  }
  history.push({ role: "user", content: question });
  return history;
}
