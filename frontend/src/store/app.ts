import { create } from "zustand";
import { api } from "@/lib/api";
import type { ChatSummary, CoworkSummary, Model } from "@/lib/types";

interface AppState {
  sidebarOpen: boolean;
  setSidebarOpen: (v: boolean) => void;
  settingsOpen: boolean;
  settingsTab: string;
  openSettings: (tab?: string) => void;
  closeSettings: () => void;

  models: Model[];
  modelsLoaded: boolean;
  loadModels: (refresh?: boolean) => Promise<void>;

  chats: ChatSummary[];
  loadChats: () => Promise<void>;
  upsertChat: (c: Partial<ChatSummary> & { id: string }) => void;
  removeChat: (id: string) => void;

  sessions: CoworkSummary[];
  loadSessions: () => Promise<void>;
  upsertSession: (s: Partial<CoworkSummary> & { id: string }) => void;
  removeSession: (id: string) => void;
}

const isDesktop = () => typeof window !== "undefined" && window.innerWidth >= 768;

function readSidebar() {
  try {
    const v = localStorage.getItem("sidebar");
    return v === null ? isDesktop() : v === "1" && isDesktop();
  } catch {
    return isDesktop();
  }
}

export const useApp = create<AppState>((set, get) => ({
  sidebarOpen: readSidebar(),
  setSidebarOpen: (v) => {
    try {
      if (isDesktop()) localStorage.setItem("sidebar", v ? "1" : "0");
    } catch {
      /* ignore */
    }
    set({ sidebarOpen: v });
  },
  settingsOpen: false,
  settingsTab: "general",
  openSettings: (tab = "general") => set({ settingsOpen: true, settingsTab: tab }),
  closeSettings: () => set({ settingsOpen: false }),

  models: [],
  modelsLoaded: false,
  loadModels: async (refresh = false) => {
    try {
      const res = await api.models(refresh);
      set({ models: res.data, modelsLoaded: true });
    } catch {
      set({ modelsLoaded: true });
    }
  },

  chats: [],
  loadChats: async () => set({ chats: await api.chats() }),
  upsertChat: (c) => {
    const chats = get().chats;
    const i = chats.findIndex((x) => x.id === c.id);
    if (i === -1) {
      set({ chats: [{ title: "New Chat", model: null, pinned: false, created_at: 0, updated_at: Date.now() / 1000, ...c }, ...chats] });
    } else {
      const next = [...chats];
      next[i] = { ...next[i]!, ...c };
      next.sort((a, b) => b.updated_at - a.updated_at);
      set({ chats: next });
    }
  },
  removeChat: (id) => set({ chats: get().chats.filter((c) => c.id !== id) }),

  sessions: [],
  loadSessions: async () => {
    try {
      set({ sessions: await api.coworkSessions() });
    } catch {
      /* cowork disabled */
    }
  },
  upsertSession: (s) => {
    const sessions = get().sessions;
    const i = sessions.findIndex((x) => x.id === s.id);
    if (i === -1) {
      set({ sessions: [s as CoworkSummary, ...sessions] });
    } else {
      const next = [...sessions];
      next[i] = { ...next[i]!, ...s };
      next.sort((a, b) => b.updated_at - a.updated_at);
      set({ sessions: next });
    }
  },
  removeSession: (id) => set({ sessions: get().sessions.filter((c) => c.id !== id) }),
}));
