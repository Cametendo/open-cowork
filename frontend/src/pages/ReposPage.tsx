import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { ArrowDownToLine, Bot, FolderGit2, Github, Globe, Lock, MoreHorizontal, Search, Star, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { GitHubStatus, LocalRepo, RemoteRepo } from "@/lib/types";
import { timeAgo } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import { GitHubConnect } from "@/components/SettingsModal";
import { Badge, Button, ConfirmDialog, Input, Menu, MenuItem, Spinner } from "@/components/ui";
import { TopBar } from "./ChatPage";

export function ReposPage() {
  const navigate = useNavigate();
  const config = useAuth((s) => s.config);
  const isAdmin = useAuth((s) => s.user?.role === "admin");
  const [gh, setGh] = useState<GitHubStatus | null>(null);
  const [local, setLocal] = useState<LocalRepo[] | null>(null);
  const [remote, setRemote] = useState<RemoteRepo[] | null>(null);
  const [query, setQuery] = useState("");
  const [manual, setManual] = useState("");
  const [cloning, setCloning] = useState<string | null>(null);
  const [removing, setRemoving] = useState<LocalRepo | null>(null);
  const [deleteFiles, setDeleteFiles] = useState(false);
  const enabled = isAdmin || config?.features.github;

  const loadLocal = () => api.repos().then(setLocal).catch((e) => toast.error(e.message));
  useEffect(() => {
    if (!enabled) return;
    api.githubStatus().then(setGh).catch(() => {});
    loadLocal();
  }, [enabled]);

  useEffect(() => {
    if (!gh?.connected) return;
    setRemote(null);
    const t = setTimeout(() => api.githubRepos(query || undefined).then(setRemote).catch((e) => toast.error(e.message)), query ? 350 : 0);
    return () => clearTimeout(t);
  }, [gh?.connected, query]);

  const clone = async (name: string) => {
    setCloning(name);
    try {
      const r = await api.cloneRepo(name);
      toast.success(`Cloned ${r.full_name} into ${r.path}`);
      await loadLocal();
      if (gh?.connected) setRemote((list) => list?.map((x) => (x.full_name === r.full_name ? { ...x, local_id: r.id } : x)) ?? null);
      setManual("");
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setCloning(null);
    }
  };

  if (!enabled) {
    return (
      <div className="flex h-full flex-1 flex-col">
        <TopBar />
        <div className="flex flex-1 items-center justify-center text-gray-500">The GitHub integration is disabled.</div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      <TopBar>
        <div className="px-2 text-lg font-medium">Repositories</div>
      </TopBar>
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl space-y-8 px-4 pt-2 pb-16">
          <p className="text-sm text-gray-500">
            Repositories are cloned into <code className="rounded bg-gray-100 px-1.5 py-0.5 text-[12px] dark:bg-gray-850">{gh?.repo_dir ?? "…"}</code> so
            you can find them easily on disk. Each Cowork task pulls the latest changes first and works on its own branch.
          </p>

          {/* Local */}
          <section>
            <h2 className="mb-3 text-sm font-medium">On this machine</h2>
            {!local ? (
              <Spinner />
            ) : local.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-gray-200 p-6 text-center text-sm text-gray-500 dark:border-gray-800">
                No repositories yet. Clone one below{isAdmin ? ", or put a git repository in the folder above" : ""}.
              </div>
            ) : (
              <div className="space-y-2">
                {local.map((r) => (
                  <div key={r.id} className="flex items-center gap-3 rounded-2xl border border-gray-100 p-3 dark:border-gray-850">
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gray-100 dark:bg-gray-850">
                      <FolderGit2 className="size-5 text-gray-500" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-medium">{r.full_name}</span>
                        {r.source === "local" && <Badge className="bg-gray-100 text-gray-600 dark:bg-gray-850 dark:text-gray-300">local</Badge>}
                        {r.private && <Lock className="size-3 text-gray-400" />}
                        {r.busy && <Badge className="bg-accent-500/10 text-accent-700 dark:text-accent-300">task running</Badge>}
                      </div>
                      <div className="truncate font-mono text-[11px] text-gray-500">
                        {r.path} · {r.exists === false ? "missing" : (r.current_branch ?? "?")}
                      </div>
                    </div>
                    <Button size="sm" variant="primary" onClick={() => navigate(`/cowork?repo=${r.id}`)}>
                      <Bot className="size-3.5" /> New task
                    </Button>
                    <Menu
                      align="right"
                      trigger={(_, toggle) => (
                        <button onClick={toggle} className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-850">
                          <MoreHorizontal className="size-4" />
                        </button>
                      )}
                    >
                      {(close) => (
                        <>
                          <MenuItem
                            icon={<ArrowDownToLine className="size-4" />}
                            onClick={async () => {
                              close();
                              try {
                                const res = await api.repoPull(r.id);
                                toast.success(res.message || "Up to date");
                                loadLocal();
                              } catch (e: any) {
                                toast.error(e.message);
                              }
                            }}
                          >
                            Pull latest
                          </MenuItem>
                          {r.html_url && (
                            <MenuItem
                              icon={<Github className="size-4" />}
                              onClick={() => {
                                close();
                                window.open(r.html_url!, "_blank");
                              }}
                            >
                              Open on GitHub
                            </MenuItem>
                          )}
                          <MenuItem
                            danger
                            icon={<Trash2 className="size-4" />}
                            onClick={() => {
                              close();
                              setRemoving(r);
                            }}
                          >
                            Remove
                          </MenuItem>
                        </>
                      )}
                    </Menu>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Clone */}
          <section>
            <h2 className="mb-3 text-sm font-medium">Clone from GitHub</h2>
            <form
              className="mb-4 flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (manual.trim()) clone(manual.trim());
              }}
            >
              <Input value={manual} onChange={(e) => setManual(e.target.value)} placeholder="owner/repo or https://github.com/owner/repo" />
              <Button type="submit" variant="primary" loading={!!cloning && cloning === manual.trim()} disabled={!manual.trim()}>
                Clone
              </Button>
            </form>

            {gh && !gh.connected && (
              <div className="rounded-2xl border border-gray-100 p-4 dark:border-gray-850">
                <div className="mb-3 flex items-center gap-2 font-medium">
                  <Github className="size-5" /> Connect GitHub
                </div>
                <GitHubConnect onChange={setGh} />
              </div>
            )}

            {gh?.connected && (
              <div className="rounded-2xl border border-gray-100 dark:border-gray-850">
                <div className="flex items-center gap-2 border-b border-gray-100 px-3 dark:border-gray-850">
                  <Search className="size-4 text-gray-400" />
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={`Search ${gh.login}'s repositories`}
                    className="w-full bg-transparent py-2.5 text-sm outline-none"
                  />
                </div>
                <div className="max-h-[28rem] overflow-y-auto">
                  {!remote ? (
                    <div className="flex justify-center p-6">
                      <Spinner className="text-gray-400" />
                    </div>
                  ) : remote.length === 0 ? (
                    <div className="p-6 text-center text-sm text-gray-500">No repositories found</div>
                  ) : (
                    remote.map((r) => (
                      <div key={r.full_name} className="flex items-center gap-3 border-b border-gray-100 px-3 py-2.5 last:border-0 dark:border-gray-850">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            {r.private ? <Lock className="size-3.5 text-gray-400" /> : <Globe className="size-3.5 text-gray-400" />}
                            <span className="truncate text-sm font-medium">{r.full_name}</span>
                          </div>
                          {r.description && <div className="truncate text-xs text-gray-500">{r.description}</div>}
                          <div className="mt-0.5 flex gap-3 text-[11px] text-gray-400">
                            {r.language && <span>{r.language}</span>}
                            {r.stargazers_count > 0 && (
                              <span className="flex items-center gap-0.5">
                                <Star className="size-3" />
                                {r.stargazers_count}
                              </span>
                            )}
                            {r.pushed_at && <span>updated {timeAgo(Date.parse(r.pushed_at) / 1000)}</span>}
                          </div>
                        </div>
                        {r.local_id ? (
                          <Button size="sm" variant="secondary" onClick={() => navigate(`/cowork?repo=${r.local_id}`)}>
                            <Bot className="size-3.5" /> New task
                          </Button>
                        ) : (
                          <Button size="sm" variant="secondary" loading={cloning === r.full_name} disabled={!!cloning} onClick={() => clone(r.full_name)}>
                            Clone
                          </Button>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </section>
        </div>
      </div>

      <ConfirmDialog
        open={!!removing}
        title="Remove repository?"
        confirmLabel="Remove"
        danger
        message={<>Remove <strong>{removing?.full_name}</strong> from {config?.name}.</>}
        onClose={() => {
          setRemoving(null);
          setDeleteFiles(false);
        }}
        onConfirm={async () => {
          try {
            await api.removeRepo(removing!.id, deleteFiles);
            loadLocal();
          } catch (e: any) {
            toast.error(e.message);
          }
        }}
      >
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={deleteFiles} onChange={(e) => setDeleteFiles(e.target.checked)} />
          Also delete the folder <code className="text-xs">{removing?.path}</code>
        </label>
      </ConfirmDialog>
    </div>
  );
}
