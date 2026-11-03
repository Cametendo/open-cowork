import { create } from "zustand";
import { api, setUnauthorizedHandler, tokenStore } from "@/lib/api";
import type { PublicConfig, User, UserSettings } from "@/lib/types";

type Theme = "system" | "dark" | "light";

interface AuthState {
  config: PublicConfig | null;
  user: User | null;
  ready: boolean;
  theme: Theme;
  init: () => Promise<void>;
  refreshConfig: () => Promise<void>;
  signin: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  signout: () => void;
  refreshUser: () => Promise<void>;
  setUser: (u: User) => void;
  saveSettings: (s: Partial<UserSettings>) => Promise<void>;
  setTheme: (t: Theme) => void;
}

function readTheme(): Theme {
  try {
    return (localStorage.getItem("theme") as Theme) || "system";
  } catch {
    return "system";
  }
}

export function applyTheme(t: Theme) {
  const dark = t === "dark" || (t === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#171717" : "#ffffff");
}

export const useAuth = create<AuthState>((set, get) => ({
  config: null,
  user: null,
  ready: false,
  theme: readTheme(),

  init: async () => {
    setUnauthorizedHandler(() => {
      if (get().user) get().signout();
    });
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyTheme(get().theme));
    applyTheme(get().theme);
    try {
      const config = await api.config();
      set({ config });
      document.title = config.name;
    } catch {
      /* backend unreachable; the login screen will show an error on submit */
    }
    if (tokenStore.get()) {
      try {
        const user = await api.me();
        set({ user });
        const t = user.settings?.theme;
        if (t && t !== get().theme) get().setTheme(t);
      } catch {
        tokenStore.set(null);
      }
    }
    set({ ready: true });
  },

  refreshConfig: async () => {
    const config = await api.config();
    document.title = config.name;
    set({ config });
  },

  signin: async (email, password) => {
    const res = await api.signin(email, password);
    tokenStore.set(res.token);
    set({ user: await api.me() });
  },

  signup: async (name, email, password) => {
    const res = await api.signup(name, email, password);
    tokenStore.set(res.token);
    set({ user: await api.me() });
    await get().refreshConfig();
  },

  signout: () => {
    tokenStore.set(null);
    set({ user: null });
    window.location.href = "/auth";
  },

  refreshUser: async () => set({ user: await api.me() }),
  setUser: (u) => set({ user: { ...get().user, ...u } }),

  saveSettings: async (s) => {
    const settings = await api.updateSettings(s);
    const user = get().user;
    if (user) set({ user: { ...user, settings } });
  },

  setTheme: (t) => {
    try {
      localStorage.setItem("theme", t);
    } catch {
      /* ignore */
    }
    applyTheme(t);
    set({ theme: t });
  },
}));
