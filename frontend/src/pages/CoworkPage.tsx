import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Route, Routes, useNavigate, useParams, useSearchParams } from "react-router";
import {
  BarChart3,
  Bot,
  Check,
  ChevronDown,
  FileText,
  FolderGit2,
  FolderPlus,
  GitBranch,
  Hammer,
  PanelRight,
  Plus,
  ShieldCheck,
  Sparkles,
  TestTube2,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { LocalRepo } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";
import { useCowork } from "@/store/cowork";
import { MessageInput } from "@/components/MessageInput";
import { ModelSelector } from "@/components/ModelSelector";
import { Transcript } from "@/components/cowork/Transcript";
import { WorkspacePanel } from "@/components/cowork/WorkspacePanel";
import { PlanProgress } from "@/components/cowork/PlanList";
import { IconButton, Menu, MenuItem, Spinner } from "@/components/ui";
import { TopBar } from "./ChatPage";
import { ReposPage } from "./ReposPage";

const EXAMPLES = [
  { icon: FileText, title: "Write a README", prompt: "Read through this project and write a clear README.md with setup and usage instructions." },
  { icon: TestTube2, title: "Fix failing tests", prompt: "Run the test suite, find out why tests fail, fix the problems and re-run until everything passes." },
  { icon: Hammer, title: "Build a small app", prompt: "Build a single-page pomodoro timer in index.html with a clean, modern design and no external dependencies." },
  { icon: BarChart3, title: "Analyze data", prompt: "Look at the CSV files in the workspace, summarize what's in them and write the key findings to report.md." },
];

function useCoworkModel() {
  const user = useAuth((s) => s.user);
  const { models, modelsLoaded } = useApp();
  const [model, setModel] = useState<string | null>(null);
  useEffect(() => {
    if (!modelsLoaded || model) return;
    const ids = models.map((m) => m.id);
    let last: string | null = null;
    try {
      last = localStorage.getItem("last_cowork_model");
    } catch {
      /* ignore */
    }
    const candidates = [user?.settings?.cowork_default_model, last, user?.settings?.default_model];
    setModel(candidates.find((c) => c && ids.includes(c)) ?? ids[0] ?? null);
  }, [modelsLoaded, models, user, model]);
  const choose = (m: string) => {
    setModel(m);
    try {
      localStorage.setItem("last_cowork_model", m);
    } catch {
      /* ignore */
    }
  };
  return [model, choose] as const;
}

function Chip({ children, className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className={cn(
        "flex max-w-full items-center gap-1.5 rounded-full border border-gray-200 px-2.5 py-1 text-[13px] text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-800 dark:text-gray-300 dark:hover:bg-gray-800",
        className,
      )}
    >
      {children}
    </button>
  );
}

function ApprovalChip({ mode, onChange, disabled }: { mode: "ask" | "auto"; onChange: (m: "ask" | "auto") => void; disabled?: boolean }) {
  return (
    <Menu
      side="top"
      trigger={(_, toggle) => (
        <Chip onClick={toggle} disabled={disabled} title="Approval mode">
          {mode === "ask" ? <ShieldCheck className="size-3.5" /> : <Zap className="size-3.5 text-amber-500" />}
          {mode === "ask" ? "Ask first" : "Auto"}
          <ChevronDown className="size-3 text-gray-400" />
        </Chip>
      )}
    >
      {(close) => (
        <div className="w-72">
          {(
            [
              ["ask", "Ask before acting", "Approve each file edit and command", ShieldCheck],
              ["auto", "Run automatically", "Edits and commands run without asking", Zap],
            ] as const
          ).map(([v, title, desc, Icon]) => (
            <button
              key={v}
              onClick={() => {
                onChange(v);
                close();
              }}
              className="flex w-full items-start gap-2.5 rounded-xl px-3 py-2 text-left hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <Icon className="mt-0.5 size-4 shrink-0" />
              <div className="flex-1">
                <div className="text-sm font-medium">{title}</div>
                <div className="text-xs text-gray-500">{desc}</div>
              </div>
              {mode === v && <Check className="size-4" />}
            </button>
          ))}
        </div>
      )}
    </Menu>
  );
}

// ---------------------------------------------------------------- New task

function NewTask() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const user = useAuth((s) => s.user);
  const config = useAuth((s) => s.config);
  const upsertSession = useApp((s) => s.upsertSession);
  const initLive = useCowork((s) => s.init);
  const [model, setModel] = useCoworkModel();
  const [mode, setMode] = useState<"ask" | "auto">(user?.settings?.cowork_approval_mode ?? "ask");
  const [repos, setRepos] = useState<LocalRepo[]>([]);
  const [repoId, setRepoId] = useState<string | null>(params.get("repo"));
  const [newBranch, setNewBranch] = useState(true);
  const [busy, setBusy] = useState(false);
  const githubEnabled = user?.role === "admin" || config?.features.github;

  useEffect(() => {
    if (githubEnabled) api.repos().then(setRepos).catch(() => {});
  }, [githubEnabled]);

  const repo = repos.find((r) => r.id === repoId) ?? null;

  const start = async (prompt: string) => {
    if (!model) return toast.error("Select a model first");
    setBusy(true);
    try {
      if ("Notification" in window && Notification.permission === "default") Notification.requestPermission().catch(() => {});
      const s = await api.createCoworkSession({
        prompt,
        model,
        approval_mode: mode,
        workspace: repo ? { type: "repo", repo_id: repo.id, create_branch: newBranch } : { type: "scratch" },
      });
      initLive(s);
      upsertSession(s);
      navigate(`/cowork/${s.id}`);
    } catch (e: any) {
      toast.error(e.message);
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      <TopBar>
        <ModelSelector value={model} onChange={setModel} />
      </TopBar>
      <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-4 pb-16">
        <div className="w-full max-w-3xl">
          <div className="mb-8 text-center">
            <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-500 to-fuchsia-500 text-white shadow-lg shadow-accent-500/20">
              <Bot className="size-6" />
            </div>
            <h1 className="text-3xl font-medium">What should we work on?</h1>
            <p className="mx-auto mt-2 max-w-lg text-gray-500">
              Cowork plans the task, then reads and edits files and runs commands in a workspace folder. Watch every step, or let it run.
            </p>
          </div>

          <MessageInput
            large
            autoFocus
            disabled={busy || !model}
            busy={busy}
            placeholder={repo ? `Describe a task for ${repo.full_name}…` : "Describe a task…"}
            onSend={(text) => start(text)}
            toolbar={
              <>
                <Menu
                  side="top"
                  className="w-80"
                  trigger={(_, toggle) => (
                    <Chip onClick={toggle}>
                      {repo ? <FolderGit2 className="size-3.5" /> : <FolderPlus className="size-3.5" />}
                      <span className="truncate">{repo ? repo.full_name : "New folder"}</span>
                      <ChevronDown className="size-3 text-gray-400" />
                    </Chip>
                  )}
                >
                  {(close) => (
                    <>
                      <MenuItem
                        icon={<FolderPlus className="size-4" />}
                        onClick={() => {
                          setRepoId(null);
                          close();
                        }}
                      >
                        <div className="flex-1">
                          <div>New scratch folder</div>
                          <div className="text-xs text-gray-500">An empty workspace for this task</div>
                        </div>
                        {!repo && <Check className="size-4" />}
                      </MenuItem>
                      {repos.length > 0 && <div className="px-3 pt-2 pb-1 text-[11px] font-medium text-gray-500 uppercase">Repositories</div>}
                      <div className="max-h-64 overflow-y-auto">
                        {repos.map((r) => (
                          <MenuItem
                            key={r.id}
                            icon={<FolderGit2 className="size-4" />}
                            onClick={() => {
                              setRepoId(r.id);
                              close();
                            }}
                          >
                            <div className="min-w-0 flex-1">
                              <div className="truncate">{r.full_name}</div>
                              <div className="truncate text-xs text-gray-500">{r.current_branch ?? r.default_branch}</div>
                            </div>
                            {r.id === repoId && <Check className="size-4" />}
                          </MenuItem>
                        ))}
                      </div>
                      {githubEnabled && (
                        <MenuItem
                          icon={<Plus className="size-4" />}
                          onClick={() => {
                            close();
                            navigate("/cowork/repos");
                          }}
                        >
                          Clone a repository…
                        </MenuItem>
                      )}
                    </>
                  )}
                </Menu>
                {repo && (
                  <Chip onClick={() => setNewBranch((v) => !v)} title="Work on a new branch">
                    <GitBranch className="size-3.5" />
                    {newBranch ? "New branch" : (repo.current_branch ?? "current branch")}
                  </Chip>
                )}
                <ApprovalChip mode={mode} onChange={setMode} />
              </>
            }
          />
          {repo && (
            <p className="mt-2 px-2 text-xs text-gray-500">
              {newBranch
                ? `Pulls the latest ${repo.current_branch ?? repo.default_branch} and creates a cowork/… branch in ${repo.path}.`
                : `Works directly on ${repo.current_branch ?? "the current branch"} in ${repo.path}.`}
            </p>
          )}

          <div className="mt-6 grid gap-2 sm:grid-cols-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex.title}
                disabled={busy || !model}
                onClick={() => start(ex.prompt)}
                className="flex items-start gap-3 rounded-2xl border border-gray-100 p-3 text-left transition-colors hover:bg-gray-50 disabled:opacity-50 dark:border-gray-850 dark:hover:bg-gray-850"
              >
                <ex.icon className="mt-0.5 size-4 shrink-0 text-gray-500" />
                <div>
                  <div className="text-sm font-medium">{ex.title}</div>
                  <div className="mt-0.5 line-clamp-2 text-xs text-gray-500">{ex.prompt}</div>
                </div>
              </button>
            ))}
          </div>
          <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-xs text-gray-400">
            <Sparkles className="size-3.5" /> Works best with models that support tool calling, like qwen3, llama3.1 or gpt-oss.
          </p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Session

function SessionView() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const live = useCowork((s) => s.live[id]);
  const { open, send, cancel, approve, patchSession } = useCowork();
  const upsertSession = useApp((s) => s.upsertSession);
  const [panel, setPanel] = useState(() => window.innerWidth >= 1280);
  const [model, setModel] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);

  useEffect(() => {
    open(id).catch((e) => {
      toast.error(e.message);
      navigate("/cowork");
    });
  }, [id, open, navigate]);

  useEffect(() => {
    if (live?.session.model) setModel(live.session.model);
  }, [live?.session.model]);

  // Keep the newest step in view
  const lastMsg = live?.messages[live.messages.length - 1];
  const sig = `${live?.messages.length}-${lastMsg?.content?.length}-${live?.approvals.length}-${Object.values(live?.toolOutput ?? {}).join("").length}`;
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && atBottom) el.scrollTop = el.scrollHeight;
  }, [sig, atBottom]);

  // Refresh files / git after every tool result
  const version = useMemo(() => (live ? live.messages.filter((m) => m.role === "tool").length + (live.running ? 0 : 1000) : 0), [live]);

  if (!live) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Spinner className="size-6 text-gray-400" />
      </div>
    );
  }
  const s = live.session;

  const setMode = async (m: "ask" | "auto") => {
    try {
      await api.updateCoworkSession(id, { approval_mode: m });
      patchSession(id, { approval_mode: m });
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  return (
    <div className="flex h-full min-w-0 flex-1">
      <div className="flex h-full min-w-0 flex-1 flex-col">
        <TopBar
          right={
            <IconButton label="Workspace panel" onClick={() => setPanel((v) => !v)} className={cn(panel && "bg-gray-100 dark:bg-gray-850")}>
              <PanelRight className="size-[18px]" />
            </IconButton>
          }
        >
          <div className="flex min-w-0 items-center gap-2 px-2">
            <div className="min-w-0">
              <div className="truncate font-medium">{s.title}</div>
              <div className="flex items-center gap-1.5 truncate text-xs text-gray-500">
                {s.workspace_type === "repo" ? <FolderGit2 className="size-3 shrink-0" /> : <FolderPlus className="size-3 shrink-0" />}
                <span className="truncate">{s.repo_name ?? s.workspace_path.split("/").pop()}</span>
                {s.branch && (
                  <>
                    <GitBranch className="ml-1 size-3 shrink-0" />
                    <span className="truncate font-mono">{s.branch}</span>
                  </>
                )}
              </div>
            </div>
            {live.running && (
              <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-accent-500/10 px-2 py-0.5 text-xs text-accent-700 dark:text-accent-300">
                <span className="size-1.5 animate-pulse rounded-full bg-accent-500" /> Running
              </span>
            )}
          </div>
        </TopBar>

        {live.plan.length > 0 && live.running && (
          <div className="mx-auto w-full max-w-3xl px-4">
            <PlanProgress plan={live.plan} />
          </div>
        )}

        <div
          ref={scrollRef}
          onScroll={() => {
            const el = scrollRef.current!;
            setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 120);
          }}
          className="flex-1 overflow-y-auto"
        >
          <Transcript live={live} onApprove={(tc, ok, always) => {
            approve(id, tc, ok, always);
            if (always) patchSession(id, { approval_mode: "auto" });
          }} />
        </div>

        <div className="mx-auto w-full max-w-3xl px-4 pb-4">
          <MessageInput
            busy={live.running}
            sendWhileBusy
            onStop={() => cancel(id)}
            onSend={(text) => {
              setAtBottom(true);
              send(id, text, model ?? undefined);
              upsertSession({ id, updated_at: Date.now() / 1000 });
            }}
            placeholder={live.running ? "Steer Cowork — it reads your message after the current step" : "Reply or give Cowork a follow-up task"}
            toolbar={
              <>
                <div className="max-w-56">
                  <ModelSelector compact value={model} onChange={setModel} />
                </div>
                <ApprovalChip mode={s.approval_mode} onChange={setMode} disabled={live.running} />
              </>
            }
          />
        </div>
      </div>
      {panel && <WorkspacePanel live={live} onClose={() => setPanel(false)} version={version} />}
    </div>
  );
}

export function CoworkRoutes() {
  return (
    <Routes>
      <Route index element={<NewTask />} />
      <Route path="repos" element={<ReposPage />} />
      <Route path=":id" element={<SessionView />} />
    </Routes>
  );
}

