import { useMemo, useState } from "react";
import { FileDiff, FolderOpen, GitBranch, ListChecks, X } from "lucide-react";
import type { CoworkMessage } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { LiveSession } from "@/store/cowork";
import { IconButton } from "../ui";
import { DiffStat } from "./DiffView";
import { FileBrowser } from "./FileBrowser";
import { GitPanel } from "./GitPanel";
import { PlanList, PlanProgress } from "./PlanList";

type Tab = "progress" | "files" | "git";

function touchedFiles(messages: CoworkMessage[]) {
  const map = new Map<string, { path: string; added: number; removed: number; created: boolean }>();
  for (const m of messages) {
    if (m.role !== "tool" || m.is_error || !m.meta?.path || !["write_file", "edit_file"].includes(m.name ?? "")) continue;
    const prev = map.get(m.meta.path) ?? { path: m.meta.path, added: 0, removed: 0, created: false };
    prev.added += m.meta.added ?? 0;
    prev.removed += m.meta.removed ?? 0;
    prev.created ||= !!m.meta.created;
    map.set(m.meta.path, prev);
  }
  return [...map.values()];
}

export function WorkspacePanel({ live, onClose, version }: { live: LiveSession; onClose: () => void; version: number }) {
  const s = live.session;
  const isRepo = s.workspace_type === "repo" && !!s.repo_id;
  const [tab, setTab] = useState<Tab>("progress");
  const files = useMemo(() => touchedFiles(live.messages), [live.messages]);
  const commands = live.messages.filter((m) => m.role === "tool" && m.name === "run_command").length;

  const tabs: { id: Tab; label: string; icon: typeof ListChecks }[] = [
    { id: "progress", label: "Progress", icon: ListChecks },
    { id: "files", label: "Files", icon: FolderOpen },
    ...(isRepo ? [{ id: "git" as Tab, label: "Git", icon: GitBranch }] : []),
  ];

  return (
    <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-gray-100 bg-white shadow-2xl animate-fade-in xl:relative xl:z-auto xl:w-[400px] xl:max-w-none xl:shadow-none dark:border-gray-850 dark:bg-gray-900">
      <div className="flex items-center gap-1 px-2 py-2">
        <div className="flex flex-1 gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors",
                tab === t.id ? "bg-gray-100 font-medium dark:bg-gray-850" : "text-gray-500 hover:text-gray-900 dark:hover:text-gray-100",
              )}
            >
              <t.icon className="size-4" /> {t.label}
            </button>
          ))}
        </div>
        <IconButton label="Close panel" onClick={onClose}>
          <X className="size-4" />
        </IconButton>
      </div>

      <div className="min-h-0 flex-1 border-t border-gray-100 dark:border-gray-850">
        {tab === "progress" && (
          <div className="h-full space-y-6 overflow-y-auto p-4">
            <section>
              <div className="mb-2 text-xs font-medium tracking-wide text-gray-500 uppercase">Plan</div>
              {live.plan.length ? (
                <div className="space-y-3">
                  <PlanProgress plan={live.plan} />
                  <PlanList plan={live.plan} />
                </div>
              ) : (
                <p className="text-sm text-gray-500">{live.running ? "No plan yet — Cowork creates one for multi-step tasks." : "No plan for this task."}</p>
              )}
            </section>
            <section>
              <div className="mb-2 text-xs font-medium tracking-wide text-gray-500 uppercase">Changed files</div>
              {files.length ? (
                <ul className="space-y-1">
                  {files.map((f) => (
                    <li key={f.path} className="flex items-center gap-2 text-sm">
                      <FileDiff className="size-4 shrink-0 text-gray-400" />
                      <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]">{f.path}</span>
                      {f.created && <span className="text-[11px] text-emerald-600">new</span>}
                      <DiffStat added={f.added} removed={f.removed} />
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-gray-500">No files changed yet.</p>
              )}
            </section>
            <section>
              <div className="mb-2 text-xs font-medium tracking-wide text-gray-500 uppercase">Workspace</div>
              <div className="space-y-1 text-sm">
                {s.repo_name && (
                  <div className="flex gap-2">
                    <span className="w-16 shrink-0 text-gray-500">Repo</span>
                    <span className="truncate">{s.repo_name}</span>
                  </div>
                )}
                {s.branch && (
                  <div className="flex gap-2">
                    <span className="w-16 shrink-0 text-gray-500">Branch</span>
                    <span className="truncate font-mono text-[12.5px]">{s.branch}</span>
                  </div>
                )}
                <div className="flex gap-2">
                  <span className="w-16 shrink-0 text-gray-500">Folder</span>
                  <span className="font-mono text-[12px] break-all">{s.workspace_path}</span>
                </div>
                <div className="flex gap-2">
                  <span className="w-16 shrink-0 text-gray-500">Activity</span>
                  <span>
                    {files.length} file{files.length === 1 ? "" : "s"} changed · {commands} command{commands === 1 ? "" : "s"} run
                  </span>
                </div>
              </div>
            </section>
          </div>
        )}
        {tab === "files" && <FileBrowser sessionId={s.id} root={s.workspace_path} version={version} />}
        {tab === "git" && isRepo && (
          <GitPanel repoId={s.repo_id!} taskTitle={s.title} baseBranch={s.base_branch} version={version} running={live.running} />
        )}
      </div>
    </aside>
  );
}
