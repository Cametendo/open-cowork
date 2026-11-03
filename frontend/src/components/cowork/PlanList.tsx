import { Check, Circle, CircleDot, Loader2 } from "lucide-react";
import type { PlanItem } from "@/lib/types";
import { cn } from "@/lib/utils";

export function PlanList({ plan, compact, animate = true }: { plan: PlanItem[]; compact?: boolean; animate?: boolean }) {
  return (
    <ol className={cn("space-y-1", compact ? "text-[13px]" : "text-sm")}>
      {plan.map((item, i) => (
        <li key={i} className="flex items-start gap-2">
          <span className="mt-0.5 shrink-0">
            {item.status === "completed" ? (
              <span className="flex size-4 items-center justify-center rounded-full bg-emerald-500 text-white">
                <Check className="size-3" strokeWidth={3} />
              </span>
            ) : item.status === "in_progress" ? (
              animate ? (
                <Loader2 className="size-4 animate-spin text-accent-500" />
              ) : (
                <CircleDot className="size-4 text-accent-500" />
              )
            ) : (
              <Circle className="size-4 text-gray-300 dark:text-gray-700" />
            )}
          </span>
          <span
            className={cn(
              item.status === "completed" && "text-gray-500 line-through decoration-gray-300 dark:decoration-gray-700",
              item.status === "in_progress" && "font-medium",
            )}
          >
            {item.title}
          </span>
        </li>
      ))}
    </ol>
  );
}

export function PlanProgress({ plan }: { plan: PlanItem[] }) {
  const done = plan.filter((p) => p.status === "completed").length;
  const pct = plan.length ? Math.round((done / plan.length) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-850">
        <div className="h-full rounded-full bg-accent-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500">
        {done}/{plan.length}
      </span>
    </div>
  );
}
