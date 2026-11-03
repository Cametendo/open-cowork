import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

const DAY = 86400;

export function groupByDate<T extends { updated_at: number; pinned?: boolean }>(items: T[]) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000;
  const groups: { label: string; items: T[] }[] = [];
  const push = (label: string, item: T) => {
    let g = groups.find((x) => x.label === label);
    if (!g) {
      g = { label, items: [] };
      groups.push(g);
    }
    g.items.push(item);
  };
  for (const it of items.filter((i) => i.pinned)) push("Pinned", it);
  for (const it of items.filter((i) => !i.pinned)) {
    const t = it.updated_at;
    if (t >= startOfToday) push("Today", it);
    else if (t >= startOfToday - DAY) push("Yesterday", it);
    else if (t >= startOfToday - 7 * DAY) push("Previous 7 days", it);
    else if (t >= startOfToday - 30 * DAY) push("Previous 30 days", it);
    else push(new Date(t * 1000).toLocaleDateString(undefined, { month: "long", year: "numeric" }), it);
  }
  return groups;
}

export function timeAgo(ts: number | null | undefined) {
  if (!ts) return "never";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < DAY) return `${Math.floor(s / 3600)}h ago`;
  if (s < 30 * DAY) return `${Math.floor(s / DAY)}d ago`;
  return new Date(ts * 1000).toLocaleDateString();
}

export function formatBytes(n: number | null | undefined) {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(1)} GB`;
}

export function initials(name: string) {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]!.toUpperCase())
      .join("") || "?"
  );
}

export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  }
}

/** Split `<think>…</think>` blocks (used by many local reasoning models) out of content. */
export function splitThinking(content: string): { thinking: string | null; answer: string; open: boolean } {
  const m = content.match(/^\s*<think>([\s\S]*?)(<\/think>|$)/);
  if (!m) return { thinking: null, answer: content, open: false };
  const open = m[2] !== "</think>";
  return { thinking: m[1]!.trim(), answer: content.slice(m[0].length).trimStart(), open };
}

const LANG_BY_EXT: Record<string, string> = {
  py: "python", js: "javascript", jsx: "javascript", ts: "typescript", tsx: "typescript", json: "json",
  md: "markdown", sh: "bash", bash: "bash", zsh: "bash", yml: "yaml", yaml: "yaml", html: "xml", xml: "xml",
  css: "css", scss: "scss", go: "go", rs: "rust", java: "java", kt: "kotlin", rb: "ruby", php: "php",
  c: "c", h: "c", cpp: "cpp", hpp: "cpp", cs: "csharp", swift: "swift", sql: "sql", toml: "ini", ini: "ini",
  dockerfile: "dockerfile", vue: "xml", svelte: "xml", lua: "lua", r: "r", dart: "dart",
};

export function languageFor(path: string) {
  const name = path.split("/").pop()!.toLowerCase();
  if (name === "dockerfile") return "dockerfile";
  if (name === "makefile") return "makefile";
  return LANG_BY_EXT[name.split(".").pop() ?? ""] ?? "plaintext";
}

export function modelLabel(id: string | null | undefined) {
  if (!id) return "Select a model";
  return id;
}
