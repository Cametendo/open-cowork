import { create } from "zustand";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { streamSSE } from "@/lib/sse";
import type { CoworkMessage, CoworkSession, PlanItem } from "@/lib/types";
import { useApp } from "./app";

export interface LiveSession {
  session: CoworkSession;
  messages: CoworkMessage[];
  plan: PlanItem[];
  running: boolean;
  approvals: string[]; // tool_call ids waiting for the user
  activeTools: string[]; // tool_call ids currently executing
  toolOutput: Record<string, string>; // live command output
  queued: CoworkMessage[];
  error: string | null;
  lastSeq: number;
  connected: boolean;
}

interface CoworkStore {
  live: Record<string, LiveSession>;
  open: (id: string) => Promise<void>;
  init: (s: CoworkSession) => void;
  send: (id: string, content: string, model?: string) => Promise<void>;
  cancel: (id: string) => Promise<void>;
  approve: (id: string, toolCallId: string, approved: boolean, always?: boolean) => Promise<void>;
  patchSession: (id: string, p: Partial<CoworkSession>) => void;
}

const streams = new Map<string, AbortController>();

function upsert(list: CoworkMessage[], msg: CoworkMessage): CoworkMessage[] {
  const i = list.findIndex((m) => m.id === msg.id);
  if (i === -1) return [...list, msg];
  const next = [...list];
  next[i] = msg;
  return next;
}

function apply(s: LiveSession, ev: any): LiveSession {
  switch (ev.type) {
    case "run_start":
      return { ...s, running: true, error: null };
    case "user_message":
      return {
        ...s,
        messages: upsert(s.messages, ev.message),
        queued: s.queued.filter((q) => q.id !== ev.message.id),
      };
    case "input_queued":
      return s.queued.some((q) => q.id === ev.message.id) ? s : { ...s, queued: [...s.queued, ev.message] };
    case "assistant_start":
      return s.messages.some((m) => m.id === ev.id)
        ? s
        : { ...s, messages: [...s.messages, { id: ev.id, role: "assistant", content: "", model: ev.model, created_at: Date.now() / 1000 }] };
    case "delta":
    case "reasoning": {
      const key = ev.type === "delta" ? "content" : "reasoning";
      let found = false;
      const messages = s.messages.map((m) => {
        if (m.id !== ev.id) return m;
        found = true;
        return { ...m, [key]: ((m as any)[key] ?? "") + ev.text };
      });
      if (!found) messages.push({ id: ev.id, role: "assistant", content: key === "content" ? ev.text : "", reasoning: key === "reasoning" ? ev.text : undefined, created_at: Date.now() / 1000 });
      return { ...s, messages };
    }
    case "assistant_end":
      return { ...s, messages: upsert(s.messages, ev.message) };
    case "approval_required":
      return { ...s, approvals: [...s.approvals.filter((a) => a !== ev.tool_call_id), ev.tool_call_id] };
    case "approval_resolved":
      return { ...s, approvals: s.approvals.filter((a) => a !== ev.tool_call_id) };
    case "tool_start":
      return { ...s, activeTools: [...s.activeTools, ev.tool_call_id] };
    case "tool_output":
      return { ...s, toolOutput: { ...s.toolOutput, [ev.tool_call_id]: (s.toolOutput[ev.tool_call_id] ?? "") + ev.text } };
    case "tool_result": {
      const id = ev.message.tool_call_id;
      const { [id]: _, ...toolOutput } = s.toolOutput;
      return { ...s, messages: upsert(s.messages, ev.message), activeTools: s.activeTools.filter((t) => t !== id), toolOutput };
    }
    case "plan":
      return { ...s, plan: ev.plan };
    case "session_update":
      return { ...s, session: { ...s.session, ...ev } };
    case "run_end":
      return { ...s, running: false, approvals: [], activeTools: [], queued: [], error: ev.error ?? null };
    default:
      return s;
  }
}

export const useCowork = create<CoworkStore>((set, get) => {
  const update = (id: string, fn: (s: LiveSession) => LiveSession) => {
    const cur = get().live[id];
    if (cur) set({ live: { ...get().live, [id]: fn(cur) } });
  };

  const subscribe = async (id: string, after: number) => {
    streams.get(id)?.abort();
    const ctrl = new AbortController();
    streams.set(id, ctrl);
    update(id, (s) => ({ ...s, connected: true }));
    let ended = false;
    let attempt = 0;
    while (!ctrl.signal.aborted && !ended) {
      try {
        await streamSSE(`/api/cowork/sessions/${id}/stream?after=${after}`, { signal: ctrl.signal }, (ev: any) => {
          if (ev.type === "idle") {
            ended = true;
            // The run finished while we were away and its events are gone: reload from the server.
            if (get().live[id]?.running) {
              api
                .coworkSession(id)
                .then((fresh) =>
                  update(id, (s) => ({ ...s, session: fresh, messages: fresh.messages, plan: fresh.plan, running: false, error: fresh.last_error })),
                )
                .catch(() => update(id, (s) => ({ ...s, running: false })));
            }
            return;
          }
          if (typeof ev.seq === "number") after = ev.seq;
          update(id, (s) => ({ ...apply(s, ev), lastSeq: after }));
          if (ev.type === "run_end") {
            ended = true;
            const app = useApp.getState();
            app.upsertSession({ id, status: ev.status === "error" ? "error" : "idle", updated_at: Date.now() / 1000 });
            // titles are generated after the first run
            setTimeout(() => app.loadSessions(), 2500);
            if (ev.status === "completed" && document.hidden) {
              try {
                new Notification("Cowork task finished", { body: get().live[id]?.session.title });
              } catch {
                /* notifications unavailable */
              }
            }
          }
        });
        if (!ended) {
          // stream closed by the server/proxy without run_end — reconnect
          await new Promise((r) => setTimeout(r, 500));
        }
        attempt = 0;
      } catch (e: any) {
        if (ctrl.signal.aborted) break;
        if (e?.status === 404) break;
        attempt += 1;
        await new Promise((r) => setTimeout(r, Math.min(8000, 500 * 2 ** attempt)));
      }
    }
    if (streams.get(id) === ctrl) streams.delete(id);
    update(id, (s) => ({ ...s, connected: false }));
  };

  const init = (session: CoworkSession) => {
    set({
      live: {
        ...get().live,
        [session.id]: {
          session,
          messages: session.messages,
          plan: session.plan,
          running: !!session.run && !session.run.done,
          approvals: [],
          activeTools: [],
          toolOutput: {},
          queued: [],
          error: session.status === "error" ? session.last_error : null,
          lastSeq: -1,
          connected: false,
        },
      },
    });
    if (session.run) subscribe(session.id, -1);
  };

  return {
    live: {},

    open: async (id) => {
      const existing = get().live[id];
      if (existing && streams.has(id)) return; // already live
      const session = await api.coworkSession(id);
      init(session);
    },

    init,

    send: async (id, content, model) => {
      const s = get().live[id];
      if (!s) return;
      try {
        const res = await api.coworkMessage(id, content, model);
        useApp.getState().upsertSession({ id, status: "running", updated_at: Date.now() / 1000 });
        if (!res.queued) {
          update(id, (x) => ({ ...x, running: true, error: null }));
          subscribe(id, -1);
        }
      } catch (e: any) {
        toast.error(e.message);
      }
    },

    cancel: async (id) => {
      try {
        await api.coworkCancel(id);
      } catch (e: any) {
        toast.error(e.message);
      }
    },

    approve: async (id, toolCallId, approved, always = false) => {
      update(id, (s) => ({ ...s, approvals: s.approvals.filter((a) => a !== toolCallId) }));
      try {
        await api.coworkApprove(id, toolCallId, approved, always);
      } catch (e: any) {
        toast.error(e.message);
      }
    },

    patchSession: (id, p) => update(id, (s) => ({ ...s, session: { ...s.session, ...p } })),
  };
});
