import { useCallback, useEffect, useState } from "react";
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  ChevronRight,
  ExternalLink,
  GitBranch,
  GitCommitHorizontal,
  GitPullRequest,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { GitFile, GitStatus, PullRequest } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button, IconButton, Input, Label, Modal, Spinner, Textarea, Toggle } from "../ui";
import { DiffStat, DiffView } from "./DiffView";

const STATUS_STYLE: Record<string, string> = {
  M: "text-amber-600 dark:text-amber-400",
  A: "text-emerald-600 dark:text-emerald-400",
  "?": "text-emerald-600 dark:text-emerald-400",
  D: "text-red-600 dark:text-red-400",
  R: "text-sky-600 dark:text-sky-400",
  U: "text-red-600 dark:text-red-400",
};

function FileRow({ f }: { f: GitFile }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-gray-100 last:border-0 dark:border-gray-850">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] hover:bg-gray-50 dark:hover:bg-gray-850">
        <ChevronRight className={cn("size-3.5 shrink-0 text-gray-400 transition-transform", open && "rotate-90")} />
        <span className={cn("w-3 shrink-0 font-mono text-[11px] font-bold", STATUS_STYLE[f.status])}>{f.status === "?" ? "U" : f.status}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-[12px]" title={f.path}>
          {f.path}
        </span>
        <DiffStat added={f.added} removed={f.removed} />
      </button>
      {open && (
        <div className="max-h-96 overflow-auto border-t border-gray-100 bg-gray-50/50 dark:border-gray-850 dark:bg-gray-950/50">
          {f.binary ? (
            <div className="px-3 py-2 text-xs text-gray-500">Binary file</div>
          ) : f.note ? (
            <div className="px-3 py-2 text-xs text-gray-500">{f.note}</div>
          ) : (
            <DiffView diff={f.diff ?? ""} className="py-1" />
          )}
        </div>
      )}
    </div>
  );
}

function PullRequestModal({
  repoId,
  defaultTitle,
  base,
  onClose,
  onCreated,
}: {
  repoId: string;
  defaultTitle: string;
  base: string;
  onClose: () => void;
  onCreated: (pr: PullRequest) => void;
}) {
  const [title, setTitle] = useState(defaultTitle);
  const [body, setBody] = useState("");
  const [baseBranch, setBase] = useState(base);
  const [draft, setDraft] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <Modal open onClose={onClose} title="Open a pull request">
      <form
        className="space-y-3 px-5 pb-5"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const r = await api.createPullRequest(repoId, { title, body, base: baseBranch, draft });
            onCreated(r.pull_request);
            toast.success(r.existing ? `Pull request #${r.pull_request.number} already exists` : `Opened pull request #${r.pull_request.number}`);
            onClose();
          } catch (err: any) {
            toast.error(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div>
          <Label>Title</Label>
          <Input required value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <Label>Description</Label>
          <Textarea rows={6} value={body} onChange={(e) => setBody(e.target.value)} placeholder="What changed and why" />
        </div>
        <div className="flex items-end gap-4">
          <div className="flex-1">
            <Label>Base branch</Label>
            <Input value={baseBranch} onChange={(e) => setBase(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 pb-2 text-sm">
            <Toggle checked={draft} onChange={setDraft} /> Draft
          </label>
        </div>
        <p className="text-xs text-gray-500">Your branch is pushed to GitHub first.</p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={busy}>
            <GitPullRequest className="size-4" /> Create pull request
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function GitPanel({
  repoId,
  taskTitle,
  baseBranch,
  version,
  running,
}: {
  repoId: string;
  taskTitle: string;
  baseBranch: string | null;
  version: number;
  running: boolean;
}) {
  const [status, setStatus] = useState<(GitStatus & { repo?: any }) | null>(null);
  const [files, setFiles] = useState<GitFile[]>([]);
  const [pr, setPr] = useState<PullRequest | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [prOpen, setPrOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [st, ch] = await Promise.all([api.repoStatus(repoId), api.repoChanges(repoId)]);
      setStatus(st);
      setFiles(ch.files);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, [repoId]);

  useEffect(() => {
    load();
  }, [load, version]);
  useEffect(() => {
    api.repoPullRequest(repoId).then((r) => setPr(r.pull_request)).catch(() => {});
  }, [repoId, status?.branch]);

  const act = async (name: string, fn: () => Promise<any>, ok?: string) => {
    setBusy(name);
    try {
      await fn();
      if (ok) toast.success(ok);
      await load();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(null);
    }
  };

  if (error) return <div className="p-4 text-sm text-red-500">{error}</div>;
  if (!status) return <div className="flex justify-center p-6"><Spinner className="text-gray-400" /></div>;

  const repo = status.repo;
  const isGitHub = repo?.source === "github";
  const base = baseBranch || repo?.default_branch || "main";
  const onBase = status.branch === base;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-2 border-b border-gray-100 p-3 dark:border-gray-850">
        <div className="flex items-center gap-2">
          <GitBranch className="size-4 shrink-0 text-gray-500" />
          <span className="min-w-0 flex-1 truncate font-mono text-[13px] font-medium" title={status.branch ?? ""}>
            {status.branch ?? "detached HEAD"}
          </span>
          <IconButton label="Refresh" onClick={load}>
            <RefreshCw className="size-4" />
          </IconButton>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
          {status.upstream ? <span>↔ {status.upstream}</span> : <span>Not pushed yet</span>}
          {status.ahead > 0 && <span>{status.ahead} ahead</span>}
          {status.behind > 0 && <span>{status.behind} behind</span>}
          {!onBase && <span>base: {base}</span>}
        </div>
        {pr && (
          <a
            href={pr.html_url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 rounded-xl bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 hover:bg-emerald-500/15 dark:text-emerald-300"
          >
            <GitPullRequest className="size-4" />
            <span className="min-w-0 flex-1 truncate">
              #{pr.number} {pr.title}
            </span>
            <ExternalLink className="size-3.5" />
          </a>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex items-center justify-between px-3 pt-3 pb-1.5 text-xs font-medium text-gray-500">
          <span>{files.length ? `${files.length} changed file${files.length > 1 ? "s" : ""}` : "No uncommitted changes"}</span>
        </div>
        {files.length > 0 && (
          <div className="mx-3 overflow-hidden rounded-xl border border-gray-100 dark:border-gray-850">
            {files.map((f) => (
              <FileRow key={f.path} f={f} />
            ))}
          </div>
        )}
      </div>

      <div className="space-y-2 border-t border-gray-100 p-3 dark:border-gray-850">
        {files.length > 0 && (
          <>
            <Textarea rows={2} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Commit message" className="resize-none" />
            <Button
              variant="primary"
              className="w-full"
              disabled={!message.trim() || running}
              loading={busy === "commit"}
              onClick={() =>
                act(
                  "commit",
                  async () => {
                    await api.repoCommit(repoId, message.trim());
                    setMessage("");
                  },
                  "Committed",
                )
              }
            >
              <GitCommitHorizontal className="size-4" /> Commit all changes
            </Button>
          </>
        )}
        <div className="grid grid-cols-2 gap-2">
          <Button variant="secondary" loading={busy === "pull"} onClick={() => act("pull", () => api.repoPull(repoId), "Up to date")}>
            <ArrowDownToLine className="size-4" /> Pull
          </Button>
          <Button
            variant="secondary"
            loading={busy === "push"}
            disabled={!status.branch || (!!status.upstream && status.ahead === 0)}
            onClick={() => act("push", () => api.repoPush(repoId), "Pushed")}
          >
            <ArrowUpFromLine className="size-4" /> Push
          </Button>
        </div>
        {isGitHub && !pr && !onBase && (
          <Button variant="accent" className="w-full" onClick={() => setPrOpen(true)}>
            <GitPullRequest className="size-4" /> Create pull request
          </Button>
        )}
        {running && <p className="text-center text-[11px] text-gray-500">Cowork is working — commit when it's done.</p>}
      </div>

      {prOpen && (
        <PullRequestModal repoId={repoId} defaultTitle={taskTitle} base={base} onClose={() => setPrOpen(false)} onCreated={setPr} />
      )}
    </div>
  );
}
