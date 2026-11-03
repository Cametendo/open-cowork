import { create } from "zustand";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { streamSSE } from "@/lib/sse";
import type { Chat, ChatMessage } from "@/lib/types";
import { uid } from "@/lib/utils";
import { useApp } from "./app";

interface SendOptions {
  model: string;
  content?: string;
  images?: string[];
  regenerate?: boolean;
  editMessageId?: string;
}

interface ChatStore {
  chats: Record<string, Chat>;
  streaming: Record<string, AbortController>;
  load: (id: string) => Promise<Chat>;
  set: (chat: Chat) => void;
  patch: (id: string, p: Partial<Chat>) => void;
  send: (chatId: string, opts: SendOptions) => Promise<void>;
  stop: (chatId: string) => void;
}

export const useChats = create<ChatStore>((set, get) => {
  const update = (id: string, fn: (c: Chat) => Chat) => {
    const c = get().chats[id];
    if (c) set({ chats: { ...get().chats, [id]: fn(c) } });
  };
  const updateMessage = (id: string, msgId: string, fn: (m: ChatMessage) => ChatMessage) =>
    update(id, (c) => ({ ...c, messages: c.messages.map((m) => (m.id === msgId ? fn(m) : m)) }));

  return {
    chats: {},
    streaming: {},

    load: async (id) => {
      const chat = await api.chat(id);
      // Don't clobber a chat that is currently streaming
      if (!get().streaming[id]) set({ chats: { ...get().chats, [id]: chat } });
      return get().chats[id] ?? chat;
    },

    set: (chat) => set({ chats: { ...get().chats, [chat.id]: chat } }),
    patch: (id, p) => update(id, (c) => ({ ...c, ...p })),

    stop: (chatId) => {
      get().streaming[chatId]?.abort();
    },

    send: async (chatId, opts) => {
      const chat = get().chats[chatId];
      if (!chat || get().streaming[chatId]) return;
      const now = Date.now() / 1000;
      let messages = [...chat.messages];
      if (opts.regenerate) {
        while (messages.length && messages[messages.length - 1]!.role === "assistant") messages.pop();
      } else if (opts.editMessageId) {
        const idx = messages.findIndex((m) => m.id === opts.editMessageId);
        messages = [...messages.slice(0, idx), { ...messages[idx]!, content: opts.content ?? "" }];
      } else {
        messages.push({ id: uid(), role: "user", content: opts.content ?? "", images: opts.images, created_at: now });
      }
      let assistantId = uid();
      messages.push({ id: assistantId, role: "assistant", content: "", model: opts.model, created_at: now });
      update(chatId, (c) => ({ ...c, messages, model: opts.model }));

      const ctrl = new AbortController();
      set({ streaming: { ...get().streaming, [chatId]: ctrl } });
      useApp.getState().upsertChat({ id: chatId, updated_at: Date.now() / 1000, model: opts.model });

      try {
        await streamSSE(
          `/api/chats/${chatId}/messages`,
          {
            method: "POST",
            body: {
              model: opts.model,
              content: opts.content,
              images: opts.images,
              regenerate: !!opts.regenerate,
              edit_message_id: opts.editMessageId,
            },
            signal: ctrl.signal,
          },
          (ev: any) => {
            switch (ev.type) {
              case "start": {
                const serverId = ev.message.id as string;
                update(chatId, (c) => {
                  const msgs = c.messages.map((m) => (m.id === assistantId ? { ...m, id: serverId } : m));
                  // sync the optimistic user message id with the server's
                  const i = msgs.map((m) => m.role).lastIndexOf("user");
                  if (i >= 0 && ev.user_message) msgs[i] = { ...msgs[i]!, id: ev.user_message.id };
                  return { ...c, messages: msgs };
                });
                assistantId = serverId;
                break;
              }
              case "delta":
                updateMessage(chatId, assistantId, (m) => ({ ...m, content: m.content + ev.text }));
                break;
              case "reasoning":
                updateMessage(chatId, assistantId, (m) => ({ ...m, reasoning: (m.reasoning ?? "") + ev.text }));
                break;
              case "done":
                updateMessage(chatId, assistantId, () => ev.message);
                break;
              case "error":
                updateMessage(chatId, assistantId, () => ev.message);
                break;
              case "title":
                update(chatId, (c) => ({ ...c, title: ev.title }));
                useApp.getState().upsertChat({ id: chatId, title: ev.title });
                break;
            }
          },
        );
      } catch (e: any) {
        if (e?.name === "AbortError") {
          updateMessage(chatId, assistantId, (m) => ({ ...m, stopped: true }));
        } else {
          updateMessage(chatId, assistantId, (m) => ({ ...m, error: e?.message ?? "Request failed" }));
          toast.error(e?.message ?? "Request failed");
        }
      } finally {
        const { [chatId]: _, ...rest } = get().streaming;
        set({ streaming: rest });
      }
    },
  };
});
