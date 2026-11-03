import { AlertTriangle, GitBranch, Info } from "lucide-react";
import type { CoworkMessage } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { LiveSession } from "@/store/cowork";
import { AssistantContent } from "../Markdown";
import { ToolStep } from "./ToolStep";

export function Transcript({
  live,
  onApprove,
}: {
  live: LiveSession;
  onApprove: (toolCallId: string, approved: boolean, always?: boolean) => void;
}) {
  const results = new Map<string, CoworkMessage>();
  for (const m of live.messages) if (m.role === "tool" && m.tool_call_id) results.set(m.tool_call_id, m);
  const last = live.messages[live.messages.length - 1];
  const streamingText = live.running && last?.role === "assistant" && !last.tool_calls?.length;
  const waitingForModel = live.running && live.approvals.length === 0 && live.activeTools.length === 0 && !streamingText;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-3 px-4 py-6">
      {live.messages.map((m, idx) => {
        if (m.role === "tool") return null;
        if (m.role === "event") {
          return (
            <div key={m.id} className="flex items-center justify-center gap-1.5 py-1 text-xs text-gray-500">
              {m.content.toLowerCase().includes("branch") ? <GitBranch className="size-3.5" /> : <Info className="size-3.5" />}
              {m.content}
            </div>
          );
        }
        if (m.role === "user") {
          return (
            <div key={m.id} className="flex justify-end pt-3">
              <div className="max-w-[85%] rounded-3xl bg-gray-50 px-4 py-2.5 text-[15px] whitespace-pre-wrap dark:bg-gray-850">{m.content}</div>
            </div>
          );
        }
        const isStreaming = live.running && idx === live.messages.length - 1;
        const hasText = !!(m.content?.trim() || m.reasoning);
        return (
          <div key={m.id} className="flex flex-col gap-2">
            {hasText && (
              <div className={cn("text-[15px]", m.notice && "rounded-2xl bg-amber-500/10 px-4 py-3 text-sm", isStreaming && !m.tool_calls?.length && "streaming")}>
                <AssistantContent content={m.content} reasoning={m.reasoning} streaming={isStreaming} />
              </div>
            )}
            {m.stopped && <div className="text-xs text-gray-500">Stopped</div>}
            {m.tool_calls?.map((tc) => (
              <ToolStep
                key={tc.id}
                call={tc}
                result={results.get(tc.id)}
                waitingApproval={live.approvals.includes(tc.id)}
                active={live.activeTools.includes(tc.id)}
                liveOutput={live.toolOutput[tc.id]}
                interrupted={!live.running}
                onApprove={(ok, always) => onApprove(tc.id, ok, always)}
              />
            ))}
          </div>
        );
      })}

      {live.queued.map((q) => (
        <div key={q.id} className="flex justify-end">
          <div className="max-w-[85%] rounded-3xl border border-dashed border-gray-300 px-4 py-2.5 text-[15px] whitespace-pre-wrap text-gray-500 dark:border-gray-700">
            {q.content}
            <div className="mt-1 text-[11px]">Queued — Cowork will read this after the current step</div>
          </div>
        </div>
      ))}

      {waitingForModel && (
        <div className="flex items-center gap-2 py-1 text-sm text-gray-500">
          <span className="relative flex size-2.5">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent-400 opacity-75" />
            <span className="relative inline-flex size-2.5 rounded-full bg-accent-500" />
          </span>
          <span className="shimmer">Working…</span>
        </div>
      )}

      {!live.running && live.error && (
        <div className="flex items-start gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <div className="min-w-0 break-words whitespace-pre-wrap">{live.error}</div>
        </div>
      )}
    </div>
  );
}
