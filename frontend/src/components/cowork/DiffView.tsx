import { cn } from "@/lib/utils";

export function DiffView({ diff, className }: { diff: string; className?: string }) {
  if (!diff.trim()) return <div className="px-3 py-2 text-xs text-gray-500">No textual changes</div>;
  const lines = diff.replace(/\n$/, "").split("\n");
  return (
    <div className={cn("overflow-x-auto font-mono text-[12px] leading-[1.6]", className)}>
      {lines.map((line, i) => {
        if (line.startsWith("diff --git") || line.startsWith("index ") || line.startsWith("new file mode") || line.startsWith("deleted file mode"))
          return null;
        const kind = line.startsWith("+++") || line.startsWith("---")
          ? "file"
          : line.startsWith("@@")
            ? "hunk"
            : line.startsWith("+")
              ? "add"
              : line.startsWith("-")
                ? "del"
                : "ctx";
        return (
          <div
            key={i}
            className={cn(
              "px-3 whitespace-pre",
              kind === "add" && "bg-emerald-500/10 text-emerald-800 dark:text-emerald-300",
              kind === "del" && "bg-red-500/10 text-red-800 dark:text-red-300",
              kind === "hunk" && "bg-accent-500/5 text-accent-700 dark:text-accent-300",
              kind === "file" && "text-gray-500",
              kind === "ctx" && "text-gray-700 dark:text-gray-300",
            )}
          >
            {line || " "}
          </div>
        );
      })}
    </div>
  );
}

export function DiffStat({ added, removed }: { added?: number; removed?: number }) {
  if (!added && !removed) return null;
  return (
    <span className="font-mono text-[11px]">
      {!!added && <span className="text-emerald-600 dark:text-emerald-400">+{added}</span>}
      {!!added && !!removed && " "}
      {!!removed && <span className="text-red-600 dark:text-red-400">−{removed}</span>}
    </span>
  );
}
