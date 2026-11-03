import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  ArrowLeft,
  Bot,
  CheckCircle2,
  Pencil,
  Plug,
  Plus,
  Search,
  Server,
  Settings,
  Trash2,
  Users,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { AdminConfig, Connection, Role, User } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";
import {
  Avatar,
  Badge,
  Button,
  ConfirmDialog,
  IconButton,
  Input,
  Label,
  Modal,
  Select,
  SettingRow,
  Spinner,
  Toggle,
} from "@/components/ui";
import { TopBar } from "./ChatPage";

const TABS = [
  { id: "users", label: "Users", icon: Users },
  { id: "connections", label: "Connections", icon: Plug },
  { id: "general", label: "General", icon: Settings },
  { id: "cowork", label: "Cowork & GitHub", icon: Bot },
];

const ROLE_STYLE: Record<Role, string> = {
  admin: "bg-accent-500/15 text-accent-700 dark:text-accent-300",
  user: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  pending: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
};

// ---------------------------------------------------------------- Users

function UserModal({ user, onClose, onSaved }: { user: User | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ name: user?.name ?? "", email: user?.email ?? "", password: "", role: user?.role ?? "user" });
  const [busy, setBusy] = useState(false);
  return (
    <Modal open onClose={onClose} title={user ? "Edit user" : "Add user"}>
      <form
        className="space-y-3 px-5 pb-5"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            if (user) {
              await api.updateUser(user.id, {
                name: form.name,
                email: form.email,
                role: form.role,
                ...(form.password ? { password: form.password } : {}),
              });
            } else {
              await api.createUser(form);
            }
            onSaved();
            onClose();
          } catch (err: any) {
            toast.error(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div>
          <Label>Name</Label>
          <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <Label>Email</Label>
          <Input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </div>
        <div>
          <Label hint={user ? "Leave empty to keep the current password." : undefined}>Password</Label>
          <Input
            type="password"
            required={!user}
            minLength={8}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            autoComplete="new-password"
          />
        </div>
        <div>
          <Label>Role</Label>
          <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })} className="w-full">
            <option value="pending">Pending</option>
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </Select>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={busy}>
            Save
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function UsersTab() {
  const me = useAuth((s) => s.user);
  const [users, setUsers] = useState<User[] | null>(null);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<User | null | "new">(null);
  const [deleting, setDeleting] = useState<User | null>(null);
  const load = () => api.users().then(setUsers).catch((e) => toast.error(e.message));
  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(
    () => (users ?? []).filter((u) => `${u.name} ${u.email}`.toLowerCase().includes(q.toLowerCase())),
    [users, q],
  );
  const pendingCount = (users ?? []).filter((u) => u.role === "pending").length;

  const setRole = async (u: User, role: Role) => {
    try {
      await api.updateUser(u.id, { role });
      load();
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex flex-1 items-center gap-2 rounded-xl border border-gray-200 px-3 dark:border-gray-800">
          <Search className="size-4 text-gray-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search users" className="w-full bg-transparent py-2 text-sm outline-none" />
        </div>
        <Button variant="primary" onClick={() => setEditing("new")}>
          <Plus className="size-4" /> Add user
        </Button>
      </div>
      {pendingCount > 0 && (
        <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
          {pendingCount} account{pendingCount > 1 ? "s are" : " is"} waiting for activation. Change the role to <strong>User</strong> to approve.
        </div>
      )}
      {!users ? (
        <Spinner />
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-gray-100 dark:border-gray-850">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-850">
              <tr>
                <th className="px-4 py-2.5 font-medium">User</th>
                <th className="px-4 py-2.5 font-medium">Role</th>
                <th className="hidden px-4 py-2.5 font-medium sm:table-cell">Last active</th>
                <th className="hidden px-4 py-2.5 font-medium md:table-cell">Created</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr key={u.id} className="border-t border-gray-100 dark:border-gray-850">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <Avatar name={u.name} />
                      <div className="min-w-0">
                        <div className="truncate font-medium">
                          {u.name} {u.id === me?.id && <span className="text-xs text-gray-500">(you)</span>}
                        </div>
                        <div className="truncate text-xs text-gray-500">{u.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={u.role}
                      disabled={u.id === me?.id}
                      onChange={(e) => setRole(u, e.target.value as Role)}
                      className={cn("cursor-pointer rounded-full border-0 px-2.5 py-1 text-xs font-medium outline-none disabled:cursor-default", ROLE_STYLE[u.role])}
                    >
                      <option value="pending">pending</option>
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                  <td className="hidden px-4 py-3 text-gray-500 sm:table-cell">{timeAgo(u.last_active_at)}</td>
                  <td className="hidden px-4 py-3 text-gray-500 md:table-cell">{new Date(u.created_at * 1000).toLocaleDateString()}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <IconButton label="Edit" onClick={() => setEditing(u)}>
                        <Pencil className="size-4" />
                      </IconButton>
                      {u.id !== me?.id && (
                        <IconButton label="Delete" onClick={() => setDeleting(u)}>
                          <Trash2 className="size-4" />
                        </IconButton>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && <UserModal user={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={load} />}
      <ConfirmDialog
        open={!!deleting}
        title="Delete user?"
        danger
        confirmLabel="Delete"
        message={
          <>
            <strong>{deleting?.name}</strong> and all of their chats and tasks will be deleted.
          </>
        }
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          try {
            await api.deleteUser(deleting!.id);
            load();
          } catch (e: any) {
            toast.error(e.message);
          }
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------- Connections

const PRESETS: Record<string, { name: string; type: "ollama" | "openai"; base_url: string }> = {
  ollama: { name: "Ollama", type: "ollama", base_url: "http://localhost:11434" },
  openai: { name: "OpenAI", type: "openai", base_url: "https://api.openai.com/v1" },
  lmstudio: { name: "LM Studio", type: "openai", base_url: "http://localhost:1234/v1" },
  vllm: { name: "vLLM", type: "openai", base_url: "http://localhost:8000/v1" },
  llamacpp: { name: "llama.cpp", type: "openai", base_url: "http://localhost:8080/v1" },
  openrouter: { name: "OpenRouter", type: "openai", base_url: "https://openrouter.ai/api/v1" },
};

function ConnectionModal({ conn, onClose, onSaved }: { conn: Connection | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    type: conn?.type ?? ("ollama" as "ollama" | "openai"),
    name: conn?.name ?? "Ollama",
    base_url: conn?.base_url ?? "http://localhost:11434",
    api_key: "",
    prefix_id: conn?.prefix_id ?? "",
    model_ids: (conn?.model_ids ?? []).join(", "),
  });
  const [busy, setBusy] = useState(false);
  const [verify, setVerify] = useState<{ ok: boolean; text: string } | null>(null);

  const doVerify = async () => {
    setVerify(null);
    try {
      const r = await api.verifyConnection({
        type: form.type,
        base_url: form.base_url,
        api_key: form.api_key || undefined,
        connection_id: conn?.id,
      });
      setVerify({ ok: true, text: `Connected — ${r.models.length} model${r.models.length === 1 ? "" : "s"} found` });
    } catch (e: any) {
      setVerify({ ok: false, text: e.message });
    }
  };

  return (
    <Modal open onClose={onClose} title={conn ? "Edit connection" : "Add connection"}>
      <form
        className="space-y-3 px-5 pb-5"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          const body = {
            type: form.type,
            name: form.name,
            base_url: form.base_url,
            prefix_id: form.prefix_id,
            model_ids: form.model_ids.split(",").map((s) => s.trim()).filter(Boolean),
            ...(form.api_key ? { api_key: form.api_key } : {}),
          };
          try {
            if (conn) await api.updateConnection(conn.id, body);
            else await api.createConnection(body);
            onSaved();
            onClose();
          } catch (err: any) {
            toast.error(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {!conn && (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(PRESETS).map(([k, p]) => (
              <button
                type="button"
                key={k}
                onClick={() => setForm({ ...form, ...p })}
                className="rounded-full border border-gray-200 px-2.5 py-1 text-xs hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-850"
              >
                {p.name}
              </button>
            ))}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Type</Label>
            <Select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as any })} className="w-full" disabled={!!conn}>
              <option value="ollama">Ollama</option>
              <option value="openai">OpenAI-compatible</option>
            </Select>
          </div>
          <div>
            <Label>Name</Label>
            <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
        </div>
        <div>
          <Label hint={form.type === "openai" ? "Usually ends in /v1" : "In Docker, use http://host.docker.internal:11434"}>Base URL</Label>
          <Input required value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} />
        </div>
        <div>
          <Label hint={conn?.has_api_key ? "A key is stored. Leave empty to keep it." : "Optional for local servers."}>API key</Label>
          <Input type="password" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} autoComplete="off" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label hint="Keeps model ids unique">Prefix (optional)</Label>
            <Input value={form.prefix_id} placeholder="e.g. work" onChange={(e) => setForm({ ...form, prefix_id: e.target.value })} />
          </div>
          <div>
            <Label hint="Comma-separated; empty = all">Model allow-list</Label>
            <Input value={form.model_ids} placeholder="All models" onChange={(e) => setForm({ ...form, model_ids: e.target.value })} />
          </div>
        </div>
        {verify && (
          <div className={cn("flex items-start gap-2 rounded-xl px-3 py-2 text-sm", verify.ok ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-red-500/10 text-red-700 dark:text-red-300")}>
            {verify.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <XCircle className="mt-0.5 size-4 shrink-0" />}
            <span className="break-all">{verify.text}</span>
          </div>
        )}
        <div className="flex justify-between gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={doVerify}>
            Test connection
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy}>
              Save
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

function ConnectionsTab() {
  const [conns, setConns] = useState<Connection[] | null>(null);
  const [editing, setEditing] = useState<Connection | null | "new">(null);
  const [deleting, setDeleting] = useState<Connection | null>(null);
  const [health, setHealth] = useState<Record<string, { ok: boolean; text: string } | "loading">>({});
  const loadModels = useApp((s) => s.loadModels);

  const load = async () => {
    const list = await api.connections();
    setConns(list);
    loadModels(true);
    for (const c of list.filter((c) => c.enabled)) check(c);
  };
  const check = async (c: Connection) => {
    setHealth((h) => ({ ...h, [c.id]: "loading" }));
    try {
      const r = await api.verifyConnection({ type: c.type, base_url: c.base_url, connection_id: c.id });
      setHealth((h) => ({ ...h, [c.id]: { ok: true, text: `${r.models.length} models` } }));
    } catch (e: any) {
      setHealth((h) => ({ ...h, [c.id]: { ok: false, text: e.message } }));
    }
  };
  useEffect(() => {
    load().catch((e) => toast.error(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <div className="mb-4 flex items-start justify-between gap-4">
        <p className="text-sm text-gray-500">
          Connect Ollama servers and any OpenAI-compatible API (OpenAI, LM Studio, vLLM, llama.cpp, LiteLLM, OpenRouter…). Models
          from all enabled connections are available to every user.
        </p>
        <Button variant="primary" onClick={() => setEditing("new")} className="shrink-0">
          <Plus className="size-4" /> Add
        </Button>
      </div>
      {!conns ? (
        <Spinner />
      ) : conns.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-gray-200 p-8 text-center text-sm text-gray-500 dark:border-gray-800">No connections yet.</div>
      ) : (
        <div className="space-y-2">
          {conns.map((c) => {
            const h = health[c.id];
            return (
              <div key={c.id} className="flex items-center gap-3 rounded-2xl border border-gray-100 p-3 dark:border-gray-850">
                <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gray-100 dark:bg-gray-850">
                  <Server className="size-5 text-gray-500" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{c.name}</span>
                    <Badge className="bg-gray-100 text-gray-600 dark:bg-gray-850 dark:text-gray-300">{c.type === "ollama" ? "Ollama" : "OpenAI API"}</Badge>
                    {c.prefix_id && <Badge className="bg-gray-100 text-gray-600 dark:bg-gray-850 dark:text-gray-300">{c.prefix_id}.</Badge>}
                  </div>
                  <div className="truncate text-xs text-gray-500">{c.base_url}</div>
                  {c.enabled && h && (
                    <div className={cn("mt-0.5 flex items-center gap-1 truncate text-xs", h === "loading" ? "text-gray-400" : h.ok ? "text-emerald-600" : "text-red-500")}>
                      {h === "loading" ? <Spinner className="size-3" /> : h.ok ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}
                      <span className="truncate">{h === "loading" ? "Checking…" : h.text}</span>
                    </div>
                  )}
                </div>
                <Toggle
                  checked={c.enabled}
                  label="Enabled"
                  onChange={async (v) => {
                    await api.updateConnection(c.id, { enabled: v });
                    load();
                  }}
                />
                <IconButton label="Edit" onClick={() => setEditing(c)}>
                  <Pencil className="size-4" />
                </IconButton>
                <IconButton label="Delete" onClick={() => setDeleting(c)}>
                  <Trash2 className="size-4" />
                </IconButton>
              </div>
            );
          })}
        </div>
      )}
      {editing && <ConnectionModal conn={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={load} />}
      <ConfirmDialog
        open={!!deleting}
        title="Delete connection?"
        danger
        confirmLabel="Delete"
        message={<>Models from <strong>{deleting?.name}</strong> will no longer be available.</>}
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          await api.deleteConnection(deleting!.id);
          load();
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------- Settings

function useAdminConfig() {
  const [cfg, setCfg] = useState<AdminConfig | null>(null);
  const refreshConfig = useAuth((s) => s.refreshConfig);
  useEffect(() => {
    api.adminConfig().then(setCfg).catch((e) => toast.error(e.message));
  }, []);
  const save = async (p: Partial<AdminConfig>) => {
    try {
      setCfg(await api.updateAdminConfig(p));
      refreshConfig();
    } catch (e: any) {
      toast.error(e.message);
    }
  };
  return { cfg, save };
}

function GeneralTab() {
  const { cfg, save } = useAdminConfig();
  const [name, setName] = useState("");
  useEffect(() => setName(cfg?.webui_name ?? ""), [cfg?.webui_name]);
  if (!cfg) return <Spinner />;
  return (
    <div className="divide-y divide-gray-100 dark:divide-gray-850">
      <div className="pb-4">
        <Label>Instance name</Label>
        <div className="flex gap-2">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
          <Button variant="primary" disabled={name === cfg.webui_name} onClick={() => save({ webui_name: name })}>
            Save
          </Button>
        </div>
      </div>
      <SettingRow title="Allow new sign-ups" description="When off, only admins can create accounts. The very first account can always sign up.">
        <Toggle checked={cfg.enable_signup} onChange={(v) => save({ enable_signup: v })} />
      </SettingRow>
      <SettingRow title="Default role for new accounts" description="Pending accounts must be activated by an admin before they can use the app.">
        <Select value={cfg.default_user_role} onChange={(e) => save({ default_user_role: e.target.value as any })}>
          <option value="pending">Pending</option>
          <option value="user">User</option>
        </Select>
      </SettingRow>
      <SettingRow title="Automatic titles" description="Ask the model for a short title after the first reply.">
        <Toggle checked={cfg.enable_title_generation} onChange={(v) => save({ enable_title_generation: v })} />
      </SettingRow>
    </div>
  );
}

function NumberSetting({ value, onSave, min = 1, step = 1 }: { value: number; onSave: (v: number) => void; min?: number; step?: number }) {
  const [v, setV] = useState(String(value));
  useEffect(() => setV(String(value)), [value]);
  return (
    <Input
      type="number"
      min={min}
      step={step}
      value={v}
      className="w-28"
      onChange={(e) => setV(e.target.value)}
      onBlur={() => {
        const n = Number(v);
        if (Number.isFinite(n) && n !== value && n >= min) onSave(Math.round(n));
        else setV(String(value));
      }}
    />
  );
}

function CoworkTab() {
  const { cfg, save } = useAdminConfig();
  if (!cfg) return <Spinner />;
  return (
    <div className="divide-y divide-gray-100 dark:divide-gray-850">
      <SettingRow title="Enable Cowork for users" description="Admins always have access.">
        <Toggle checked={cfg.cowork_enabled} onChange={(v) => save({ cowork_enabled: v })} />
      </SettingRow>
      <SettingRow
        title="Allow shell commands"
        description="Lets the agent run commands (tests, builds, git…) in the task's workspace with the server's permissions. Turn off to limit it to reading and editing files."
      >
        <Toggle checked={cfg.cowork_allow_shell} onChange={(v) => save({ cowork_allow_shell: v })} />
      </SettingRow>
      <SettingRow title="Command timeout" description="Seconds before a command is stopped.">
        <NumberSetting value={cfg.cowork_command_timeout} onSave={(v) => save({ cowork_command_timeout: v })} />
      </SettingRow>
      <SettingRow title="Max steps per run" description="Model calls per run before the agent pauses and asks to continue.">
        <NumberSetting value={cfg.cowork_max_steps} onSave={(v) => save({ cowork_max_steps: v })} />
      </SettingRow>
      <SettingRow title="Ollama context length" description="num_ctx for Cowork runs on Ollama. Agents need room for tool output; 0 uses the model default.">
        <NumberSetting value={cfg.cowork_ollama_num_ctx} min={0} step={1024} onSave={(v) => save({ cowork_ollama_num_ctx: v })} />
      </SettingRow>
      <SettingRow title="GitHub integration" description="Let users connect GitHub, clone repositories and open pull requests.">
        <Toggle checked={cfg.github_enabled} onChange={(v) => save({ github_enabled: v })} />
      </SettingRow>
    </div>
  );
}

export function AdminPage() {
  const { tab = "users" } = useParams();
  const navigate = useNavigate();
  const current = TABS.find((t) => t.id === tab) ?? TABS[0]!;
  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      <TopBar>
        <Link to="/" className="flex items-center gap-2 rounded-xl px-2.5 py-1.5 text-lg font-medium hover:bg-gray-100 dark:hover:bg-gray-850">
          <ArrowLeft className="size-4" /> Admin panel
        </Link>
      </TopBar>
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-4 md:flex-row">
          <nav className="flex shrink-0 gap-1 overflow-x-auto md:w-52 md:flex-col">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => navigate(`/admin/${t.id}`)}
                className={cn(
                  "flex items-center gap-2 rounded-xl px-3 py-2 text-left text-sm whitespace-nowrap transition-colors",
                  current.id === t.id ? "bg-gray-100 font-medium dark:bg-gray-850" : "text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-850",
                )}
              >
                <t.icon className="size-4" /> {t.label}
              </button>
            ))}
          </nav>
          <section className="min-w-0 flex-1 pb-10">
            <h2 className="mb-4 text-xl font-semibold">{current.label}</h2>
            {current.id === "users" && <UsersTab />}
            {current.id === "connections" && <ConnectionsTab />}
            {current.id === "general" && <GeneralTab />}
            {current.id === "cowork" && <CoworkTab />}
          </section>
        </div>
      </div>
    </div>
  );
}
