import { useEffect, useRef, useState } from "react";
import {
  Ban,
  Check,
  ChevronRight,
  FilePen,
  FilePlus2,
  FileText,
  FolderTree,
  ListChecks,
  Search,
  ShieldQuestion,
  SquareTerminal,
  Wrench,
  X,
} from "lucide-react";
import type { CoworkMessage, PlanItem, ToolCall } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button, Spinner } from "../ui";
import { DiffStat, DiffView } from "./DiffView";
import { PlanList } from "./PlanList";

const ICONS: Record<string, typeof Wrench> = {
  list_files: FolderTree,
  read_file: FileText,
  write_file: FilePlus2,
  edit_file: FilePen,
  search_files: Search,
  run_command: SquareTerminal,
  update_plan: ListChecks,
};

function str(v: unknown) {
  return typeof v === "string" ? v : v == null ? "" : JSON.stringify(v);
}

export function describe(tc: ToolCall, result?: CoworkMessage): { verb: string; target: string } {
  const a = tc.arguments || {};
  switch (tc.name) {
    case "list_files":
      return { verb: "Listed", target: str(a.path) || "." };
    case "read_file":
      return { verb: "Read", target: str(a.path) };
    case "write_file":
      return { verb: result?.meta?.created === false ? "Rewrote" : "Created", target: str(a.path) };
    case "edit_file":
      return { verb: "Edited", target: str(a.path) };
    case "search_files":
      return { verb: "Searched", target: `/${str(a.pattern)}/${a.glob ? ` in ${str(a.glob)}` : ""}` };
    case "run_command":
      return { verb: "Ran", target: str(a.command) };
    case "update_plan":
      return { verb: "Updated plan", target: "" };
    default:
      return { verb: tc.name, target: JSON.stringify(a).slice(0, 80) };
  }
}

function approvalVerb(name: string) {
  return ({ write_file: "Create", edit_file: "Edit", run_command: "Run" } as Record<string, string>)[name] ?? name;
}

function pendingVerb(name: string) {
  return (
    {
      list_files: "Listing",
      read_file: "Reading",
      write_file: "Writing",
      edit_file: "Editing",
      search_files: "Searching",
      run_command: "Running",
      update_plan: "Updating plan",
    }[name] ?? "Running"
  );
}

function LiveOutput({ text }: { text: string }) {
  const ref = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [text]);
  return (
    <pre ref={ref} className="max-h-60 overflow-auto bg-gray-950 px-3 py-2 font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-gray-200">
      {text || " "}
    </pre>
  );
}

export function ToolStep({
  call,
  result,
  waitingApproval,
  active,
  liveOutput,
  onApprove,
  interrupted,
}: {
  call: ToolCall;
  result?: CoworkMessage;
  waitingApproval: boolean;
  active: boolean;
  liveOutput?: string;
  onApprove: (approved: boolean, always?: boolean) => void;
  interrupted?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const Icon = ICONS[call.name] ?? Wrench;
  const { verb, target } = describe(call, result);
  const denied = !!result?.meta?.denied;
  const failed = !!result?.is_error && !denied;
  const running = !result && (active || (!waitingApproval && !interrupted));

  if (call.name === "update_plan" && result && !result.is_error) {
    const plan = (result.meta?.plan ?? []) as PlanItem[];
    return (
      <div className="rounded-2xl border border-gray-100 px-3 py-2.5 dark:border-gray-850">
        <div className="mb-1.5 flex items-center gap-2 text-xs font-medium text-gray-500">
          <ListChecks className="size-3.5" /> Plan · {plan.filter((p) => p.status === "completed").length}/{plan.length}
        </div>
        <PlanList plan={plan} compact animate={!interrupted} />
      </div>
    );
  }

  const exitCode = result?.meta?.exit_code;
  const diff: string | undefined = result?.meta?.diff;
  const showLive = !result && call.name === "run_command" && (active || liveOutput);

  return (
    <div
      className={cn(
        "overflow-hidden rounded-2xl border transition-colors",
        waitingApproval ? "border-accent-500/50 bg-accent-500/5" : "border-gray-100 dark:border-gray-850",
      )}
    >
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm">
        <span
          className={cn(
            "flex size-6 shrink-0 items-center justify-center rounded-lg",
            failed ? "bg-red-500/10 text-red-600 dark:text-red-400" : "bg-gray-100 text-gray-600 dark:bg-gray-850 dark:text-gray-300",
          )}
        >
          <Icon className="size-3.5" />
        </span>
        <span className={cn("shrink-0 font-medium", running && "shimmer")}>{result ? verb : waitingApproval ? approvalVerb(call.name) : pendingVerb(call.name)}</span>
        <span className={cn("min-w-0 truncate text-gray-600 dark:text-gray-400", call.name === "run_command" && "font-mono text-[12.5px]")}>
          {target}
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-2 pl-2">
          <DiffStat added={result?.meta?.added} removed={result?.meta?.removed} />
          {typeof exitCode === "number" && exitCode !== 0 && (
            <span className="rounded-md bg-red-500/10 px-1.5 py-0.5 font-mono text-[11px] text-red-600 dark:text-red-400">exit {exitCode}</span>
          )}
          {result?.meta?.timed_out && <span className="text-[11px] text-red-500">timed out</span>}
          {running && <Spinner className="size-3.5 text-gray-400" />}
          {waitingApproval && <ShieldQuestion className="size-4 text-accent-600 dark:text-accent-400" />}
          {result && !result.is_error && <Check className="size-4 text-emerald-600 dark:text-emerald-400" />}
          {failed && <X className="size-4 text-red-500" />}
          {denied && <Ban className="size-4 text-gray-400" />}
          {!result && interrupted && !waitingApproval && <Ban className="size-4 text-gray-400" />}
          <ChevronRight className={cn("size-4 text-gray-400 transition-transform", open && "rotate-90")} />
        </span>
      </button>

      {waitingApproval && (
        <div className="border-t border-accent-500/20 px-3 py-3">
          <div className="mb-2 text-sm">
            {call.name === "run_command" ? "Allow Cowork to run this command?" : `Allow Cowork to ${call.name === "write_file" ? "write" : "edit"} this file?`}
          </div>
          {call.name === "run_command" ? (
            <pre className="mb-3 overflow-x-auto rounded-xl bg-gray-950 px-3 py-2 font-mono text-[12.5px] text-gray-100">{str(call.arguments.command)}</pre>
          ) : call.name === "write_file" ? (
            <pre className="mb-3 max-h-56 overflow-auto rounded-xl bg-gray-950 px-3 py-2 font-mono text-[12px] text-gray-100">{str(call.arguments.content)}</pre>
          ) : (
            <div className="mb-3 overflow-hidden rounded-xl border border-gray-200 dark:border-gray-800">
              <DiffView
                diff={
                  str(call.arguments.old_string)
                    .split("\n")
                    .map((l) => `-${l}`)
                    .join("\n") +
                  "\n" +
                  str(call.arguments.new_string)
                    .split("\n")
                    .map((l) => `+${l}`)
                    .join("\n")
                }
              />
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="primary" onClick={() => onApprove(true)}>
              Allow
            </Button>
            <Button size="sm" variant="secondary" onClick={() => onApprove(true, true)}>
              Allow all for this task
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onApprove(false)}>
              Deny
            </Button>
          </div>
        </div>
      )}

      {showLive && !open && <LiveOutput text={liveOutput ?? ""} />}

      {open && (
        <div className="border-t border-gray-100 dark:border-gray-850">
          {diff ? (
            <DiffView diff={diff} className="max-h-96 py-1" />
          ) : call.name === "run_command" && !result ? (
            <LiveOutput text={liveOutput ?? ""} />
          ) : (
            <>
              {call.name !== "run_command" && (
                <pre className="overflow-x-auto bg-gray-50 px-3 py-2 font-mono text-[11.5px] text-gray-600 dark:bg-gray-950 dark:text-gray-400">
                  {JSON.stringify(call.arguments, null, 2)}
                </pre>
              )}
              {result && (
                <pre
                  className={cn(
                    "max-h-96 overflow-auto px-3 py-2 font-mono text-[12px] leading-relaxed whitespace-pre-wrap",
                    call.name === "run_command" ? "bg-gray-950 text-gray-200" : "text-gray-700 dark:text-gray-300",
                  )}
                >
                  {result.content}
                </pre>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
