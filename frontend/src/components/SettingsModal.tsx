import { useEffect, useState } from "react";
import { Bot, Github, Info, Monitor, Moon, Settings, Sun, User as UserIcon } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { GitHubStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";
import { ModelSelector } from "./ModelSelector";
import { Avatar, Button, Input, Label, Modal, Select, Spinner, Textarea } from "./ui";

const TABS = [
  { id: "general", label: "General", icon: Settings },
  { id: "cowork", label: "Cowork", icon: Bot },
  { id: "github", label: "GitHub", icon: Github },
  { id: "account", label: "Account", icon: UserIcon },
  { id: "about", label: "About", icon: Info },
];

function General() {
  const { theme, setTheme, user, saveSettings } = useAuth();
  const [system, setSystem] = useState(user?.settings?.system_prompt ?? "");
  const [model, setModel] = useState<string | null>(user?.settings?.default_model ?? null);
  return (
    <div className="space-y-6">
      <div>
        <Label>Theme</Label>
        <div className="grid grid-cols-3 gap-2">
          {(
            [
              ["system", "System", Monitor],
              ["light", "Light", Sun],
              ["dark", "Dark", Moon],
            ] as const
          ).map(([v, l, Icon]) => (
            <button
              key={v}
              onClick={() => {
                setTheme(v);
                saveSettings({ theme: v }).catch(() => {});
              }}
              className={cn(
                "flex items-center justify-center gap-2 rounded-xl border px-3 py-2 text-sm transition-colors",
                theme === v
                  ? "border-gray-900 bg-gray-50 dark:border-gray-100 dark:bg-gray-850"
                  : "border-gray-200 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-850",
              )}
            >
              <Icon className="size-4" /> {l}
            </button>
          ))}
        </div>
      </div>
      <div>
        <Label hint="Used for new chats when available.">Default model</Label>
        <div className="rounded-xl border border-gray-200 dark:border-gray-800">
          <ModelSelector
            compact
            value={model}
            onChange={(m) => {
              setModel(m);
              saveSettings({ default_model: m }).then(() => toast.success("Default model saved"));
            }}
          />
        </div>
      </div>
      <div>
        <Label hint="Sent at the start of every chat (unless a chat overrides it).">System prompt</Label>
        <Textarea rows={5} value={system} onChange={(e) => setSystem(e.target.value)} placeholder="e.g. Answer concisely. I'm a software engineer." />
        <div className="mt-2 flex justify-end">
          <Button size="sm" variant="primary" onClick={() => saveSettings({ system_prompt: system }).then(() => toast.success("Saved"))}>
            Save
          </Button>
        </div>
      </div>
    </div>
  );
}

function Cowork() {
  const { user, saveSettings } = useAuth();
  const [instructions, setInstructions] = useState(user?.settings?.cowork_instructions ?? "");
  const [mode, setMode] = useState(user?.settings?.cowork_approval_mode ?? "ask");
  const [model, setModel] = useState<string | null>(user?.settings?.cowork_default_model ?? null);
  return (
    <div className="space-y-6">
      <div>
        <Label hint="Cowork needs a model that supports tool calling (e.g. qwen3, llama3.1, gpt-oss).">Default Cowork model</Label>
        <div className="rounded-xl border border-gray-200 dark:border-gray-800">
          <ModelSelector
            compact
            value={model}
            onChange={(m) => {
              setModel(m);
              saveSettings({ cowork_default_model: m }).then(() => toast.success("Saved"));
            }}
          />
        </div>
      </div>
      <div>
        <Label hint="Whether new tasks ask before editing files or running commands.">Default approval mode</Label>
        <Select
          value={mode}
          onChange={(e) => {
            const v = e.target.value as "ask" | "auto";
            setMode(v);
            saveSettings({ cowork_approval_mode: v }).then(() => toast.success("Saved"));
          }}
        >
          <option value="ask">Ask before edits and commands</option>
          <option value="auto">Run automatically</option>
        </Select>
      </div>
      <div>
        <Label hint="Added to every Cowork task — your preferences, conventions, context about you.">Custom instructions</Label>
        <Textarea
          rows={6}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          placeholder="e.g. Use TypeScript and pnpm. Write tests for new code. Keep commit messages short."
        />
        <div className="mt-2 flex justify-end">
          <Button size="sm" variant="primary" onClick={() => saveSettings({ cowork_instructions: instructions }).then(() => toast.success("Saved"))}>
            Save
          </Button>
        </div>
      </div>
    </div>
  );
}

export function GitHubConnect({ onChange }: { onChange?: (s: GitHubStatus) => void }) {
  const [status, setStatus] = useState<GitHubStatus | null>(null);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const config = useAuth((s) => s.config);
  const isAdmin = useAuth((s) => s.user?.role === "admin");

  useEffect(() => {
    api.githubStatus().then(setStatus).catch(() => {});
  }, []);

  if (!isAdmin && config && !config.features.github) {
    return <div className="text-sm text-gray-500">The GitHub integration is disabled by your administrator.</div>;
  }
  if (!status) return <Spinner />;

  if (status.connected) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3 rounded-2xl border border-gray-200 p-3 dark:border-gray-800">
          <Avatar name={status.login ?? "?"} src={status.avatar_url} className="size-10" />
          <div className="min-w-0 flex-1">
            <div className="font-medium">{status.name || status.login}</div>
            <a href={status.html_url ?? "#"} target="_blank" rel="noreferrer" className="text-sm text-gray-500 hover:underline">
              @{status.login}
            </a>
          </div>
          <Button
            variant="ghost"
            onClick={async () => {
              await api.githubDisconnect();
              const s = await api.githubStatus();
              setStatus(s);
              onChange?.(s);
            }}
          >
            Disconnect
          </Button>
        </div>
        <p className="text-xs text-gray-500">
          Repositories are cloned into <code className="rounded bg-gray-100 px-1 dark:bg-gray-800">{status.repo_dir}</code>.
          {status.scopes != null && <> Token scopes: {status.scopes || "fine-grained"}.</>}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600 dark:text-gray-400">
        Connect GitHub with a personal access token to clone private repositories, push branches and open pull requests.
        Create a{" "}
        <a
          className="text-accent-600 hover:underline dark:text-accent-400"
          href="https://github.com/settings/tokens/new?scopes=repo&description=Open%20Cowork"
          target="_blank"
          rel="noreferrer"
        >
          classic token with the <code>repo</code> scope
        </a>{" "}
        or a fine-grained token with <em>Contents</em> and <em>Pull requests</em> read & write access.
      </p>
      <form
        className="flex gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const s = await api.githubConnect(token.trim());
            setStatus(s);
            setToken("");
            onChange?.(s);
            toast.success(`Connected as @${s.login}`);
          } catch (err: any) {
            toast.error(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Input type="password" placeholder="ghp_… or github_pat_…" value={token} onChange={(e) => setToken(e.target.value)} />
        <Button type="submit" variant="primary" loading={busy} disabled={token.trim().length < 10}>
          Connect
        </Button>
      </form>
      <p className="text-xs text-gray-500">The token is stored encrypted on this server and only used for your requests.</p>
    </div>
  );
}

function Account() {
  const { user, setUser } = useAuth();
  const [name, setName] = useState(user?.name ?? "");
  const [pw, setPw] = useState({ current: "", next: "" });
  return (
    <div className="space-y-6">
      <div>
        <Label>Name</Label>
        <div className="flex gap-2">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
          <Button
            variant="primary"
            disabled={!name.trim() || name === user?.name}
            onClick={async () => {
              try {
                const u = await api.updateProfile(name.trim());
                setUser(u);
                toast.success("Profile updated");
              } catch (e: any) {
                toast.error(e.message);
              }
            }}
          >
            Save
          </Button>
        </div>
      </div>
      <div>
        <Label>Email</Label>
        <Input value={user?.email ?? ""} disabled />
      </div>
      <form
        className="space-y-2"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api.updatePassword(pw.current, pw.next);
            setPw({ current: "", next: "" });
            toast.success("Password changed");
          } catch (err: any) {
            toast.error(err.message);
          }
        }}
      >
        <Label>Change password</Label>
        <Input type="password" placeholder="Current password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} autoComplete="current-password" />
        <Input type="password" placeholder="New password (8+ characters)" minLength={8} value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} autoComplete="new-password" />
        <div className="flex justify-end">
          <Button type="submit" size="sm" variant="primary" disabled={!pw.current || pw.next.length < 8}>
            Update password
          </Button>
        </div>
      </form>
    </div>
  );
}

function About() {
  const config = useAuth((s) => s.config);
  return (
    <div className="space-y-3 text-sm text-gray-600 dark:text-gray-400">
      <div className="text-base font-medium text-gray-900 dark:text-gray-100">
        {config?.name} <span className="text-gray-500">v{config?.version}</span>
      </div>
      <p>
        A self-hosted workspace for local and OpenAI-compatible models: chat in the <strong>Chat</strong> tab, or hand off
        multi-step work to an agent in the <strong>Cowork</strong> tab, which can read and edit files, run commands and work
        inside your GitHub repositories.
      </p>
      <p>Licensed under the MIT license.</p>
    </div>
  );
}

export function SettingsModal() {
  const { settingsOpen, settingsTab, closeSettings, openSettings } = useApp();
  return (
    <Modal open={settingsOpen} onClose={closeSettings} title="Settings" wide>
      <div className="flex max-h-[75vh] flex-col sm:flex-row">
        <nav className="flex shrink-0 gap-1 overflow-x-auto px-4 pb-3 sm:w-44 sm:flex-col sm:px-3">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => openSettings(t.id)}
              className={cn(
                "flex items-center gap-2 rounded-xl px-3 py-2 text-left text-sm whitespace-nowrap transition-colors",
                settingsTab === t.id ? "bg-gray-100 font-medium dark:bg-gray-850" : "text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-850",
              )}
            >
              <t.icon className="size-4" /> {t.label}
            </button>
          ))}
        </nav>
        <div className="min-h-[24rem] flex-1 overflow-y-auto px-5 pb-6">
          {settingsTab === "general" && <General />}
          {settingsTab === "cowork" && <Cowork />}
          {settingsTab === "github" && <GitHubConnect />}
          {settingsTab === "account" && <Account />}
          {settingsTab === "about" && <About />}
        </div>
      </div>
    </Modal>
  );
}
