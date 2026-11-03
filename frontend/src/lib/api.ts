import type {
  AdminConfig,
  Chat,
  ChatParams,
  ChatSummary,
  Connection,
  CoworkSession,
  CoworkSummary,
  FileEntry,
  GitFile,
  GitHubStatus,
  GitStatus,
  LocalRepo,
  Model,
  PublicConfig,
  PullRequest,
  RemoteRepo,
  User,
  UserSettings,
} from "./types";

const TOKEN_KEY = "token";

export const tokenStore = {
  get: () => {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set: (t: string | null) => {
    try {
      if (t) localStorage.setItem(TOKEN_KEY, t);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* storage unavailable */
    }
  },
};

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export function authHeaders(json = true): Record<string, string> {
  const h: Record<string, string> = {};
  if (json) h["Content-Type"] = "application/json";
  const t = tokenStore.get();
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

export async function errorFrom(res: Response): Promise<ApiError> {
  let message = `${res.status} ${res.statusText}`;
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") message = data.detail;
    else if (Array.isArray(data?.detail)) message = data.detail.map((d: any) => d.msg ?? String(d)).join("; ");
  } catch {
    /* not json */
  }
  if (res.status === 401 && onUnauthorized) onUnauthorized();
  return new ApiError(message, res.status);
}

export async function request<T>(method: string, path: string, body?: unknown, init?: RequestInit): Promise<T> {
  const isForm = body instanceof FormData;
  const res = await fetch(path, {
    method,
    headers: authHeaders(!isForm),
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
    ...init,
  });
  if (!res.ok) throw await errorFrom(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T>(p: string) => request<T>("GET", p);
const post = <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {});
const put = <T>(p: string, b?: unknown) => request<T>("PUT", p, b ?? {});
const patch = <T>(p: string, b?: unknown) => request<T>("PATCH", p, b ?? {});
const del = <T>(p: string) => request<T>("DELETE", p);
const q = (params: Record<string, string | number | boolean | undefined | null>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  const str = s.toString();
  return str ? `?${str}` : "";
};

interface Session {
  token: string;
  user: User;
}

export const api = {
  config: () => get<PublicConfig>("/api/config"),

  // auth
  signin: (email: string, password: string) => post<Session>("/api/auths/signin", { email, password }),
  signup: (name: string, email: string, password: string) => post<Session>("/api/auths/signup", { name, email, password }),
  me: () => get<User>("/api/auths/me"),
  updateProfile: (name: string) => put<User>("/api/auths/me/profile", { name }),
  updatePassword: (password: string, new_password: string) => put("/api/auths/me/password", { password, new_password }),
  updateSettings: (s: Partial<UserSettings>) => put<UserSettings>("/api/auths/me/settings", s),

  // admin
  users: () => get<User[]>("/api/users"),
  createUser: (b: { name: string; email: string; password: string; role: string }) => post<User>("/api/users", b),
  updateUser: (id: string, b: Partial<{ name: string; email: string; role: string; password: string }>) =>
    patch<User>(`/api/users/${id}`, b),
  deleteUser: (id: string) => del(`/api/users/${id}`),
  adminConfig: () => get<AdminConfig>("/api/admin/config"),
  updateAdminConfig: (b: Partial<AdminConfig>) => put<AdminConfig>("/api/admin/config", b),
  connections: () => get<Connection[]>("/api/admin/connections"),
  createConnection: (b: Partial<Connection> & { api_key?: string }) => post<Connection>("/api/admin/connections", b),
  updateConnection: (id: string, b: Partial<Connection> & { api_key?: string }) =>
    patch<Connection>(`/api/admin/connections/${id}`, b),
  deleteConnection: (id: string) => del(`/api/admin/connections/${id}`),
  verifyConnection: (b: { type: string; base_url: string; api_key?: string; connection_id?: string }) =>
    post<{ ok: boolean; models: string[] }>("/api/admin/connections/verify", b),

  // models & chats
  models: (refresh = false) => get<{ data: Model[] }>(`/api/models${q({ refresh: refresh || undefined })}`),
  chats: (search?: string) => get<ChatSummary[]>(`/api/chats${q({ q: search })}`),
  chat: (id: string) => get<Chat>(`/api/chats/${id}`),
  createChat: (b: { model?: string; params?: ChatParams }) => post<Chat>("/api/chats", b),
  updateChat: (id: string, b: Partial<{ title: string; pinned: boolean; model: string; params: ChatParams }>) =>
    patch<Chat>(`/api/chats/${id}`, b),
  deleteChat: (id: string) => del(`/api/chats/${id}`),
  deleteAllChats: () => del(`/api/chats`),

  // cowork
  coworkSessions: () => get<CoworkSummary[]>("/api/cowork/sessions"),
  coworkSession: (id: string) => get<CoworkSession>(`/api/cowork/sessions/${id}`),
  createCoworkSession: (b: {
    prompt: string;
    model: string;
    approval_mode: "ask" | "auto";
    workspace: { type: "scratch" | "repo"; repo_id?: string; create_branch?: boolean; branch?: string };
  }) => post<CoworkSession>("/api/cowork/sessions", b),
  updateCoworkSession: (id: string, b: Partial<{ title: string; model: string; approval_mode: string }>) =>
    patch<CoworkSummary>(`/api/cowork/sessions/${id}`, b),
  deleteCoworkSession: (id: string, deleteFiles = false) =>
    del(`/api/cowork/sessions/${id}${q({ delete_files: deleteFiles || undefined })}`),
  coworkMessage: (id: string, content: string, model?: string) =>
    post<{ queued: boolean }>(`/api/cowork/sessions/${id}/messages`, { content, model }),
  coworkCancel: (id: string) => post(`/api/cowork/sessions/${id}/cancel`),
  coworkApprove: (id: string, tool_call_id: string, approved: boolean, always = false) =>
    post(`/api/cowork/sessions/${id}/approve`, { tool_call_id, approved, always }),
  coworkFiles: (id: string, path = ".") =>
    get<{ path: string; root: string; entries: FileEntry[] }>(`/api/cowork/sessions/${id}/files${q({ path })}`),
  coworkFile: (id: string, path: string) =>
    get<{ path: string; size: number; mime: string; binary: boolean; truncated: boolean; content: string | null }>(
      `/api/cowork/sessions/${id}/file${q({ path })}`,
    ),
  coworkUpload: (id: string, files: File[], path = ".") => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("path", path);
    return request<{ saved: string[] }>("POST", `/api/cowork/sessions/${id}/upload`, fd);
  },
  coworkDownload: async (id: string, path: string) => {
    const res = await fetch(`/api/cowork/sessions/${id}/download${q({ path })}`, { headers: authHeaders(false) });
    if (!res.ok) throw await errorFrom(res);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = path.split("/").pop() || "download";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },

  // github
  githubStatus: () => get<GitHubStatus>("/api/github/status"),
  githubConnect: (token: string) => put<GitHubStatus>("/api/github/token", { token }),
  githubDisconnect: () => del("/api/github/token"),
  githubRepos: (search?: string) => get<RemoteRepo[]>(`/api/github/repos${q({ q: search })}`),
  repos: () => get<LocalRepo[]>("/api/repos"),
  cloneRepo: (repo: string, branch?: string) => post<LocalRepo>("/api/repos/clone", { repo, branch }),
  removeRepo: (id: string, deleteFiles = false) => del(`/api/repos/${id}${q({ delete_files: deleteFiles || undefined })}`),
  repoStatus: (id: string) => get<GitStatus>(`/api/repos/${id}/status`),
  repoChanges: (id: string) => get<{ files: GitFile[] }>(`/api/repos/${id}/changes`),
  repoBranches: (id: string) => get<{ current: string | null; local: string[]; remote: string[] }>(`/api/repos/${id}/branches`),
  repoCheckout: (id: string, branch: string, create = false) => post<GitStatus>(`/api/repos/${id}/checkout`, { branch, create }),
  repoPull: (id: string) => post<{ message: string; status: GitStatus }>(`/api/repos/${id}/pull`),
  repoCommit: (id: string, message: string) => post<{ sha: string; status: GitStatus }>(`/api/repos/${id}/commit`, { message }),
  repoPush: (id: string) => post<{ message: string; status: GitStatus }>(`/api/repos/${id}/push`),
  repoPullRequest: (id: string) => get<{ pull_request: PullRequest | null }>(`/api/repos/${id}/pull-request`),
  createPullRequest: (id: string, b: { title: string; body: string; base?: string; draft?: boolean }) =>
    post<{ pull_request: PullRequest; existing: boolean }>(`/api/repos/${id}/pull-request`, b),
};
