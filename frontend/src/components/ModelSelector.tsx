import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { Check, ChevronDown, RefreshCw, Search, Settings2 } from "lucide-react";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";
import { cn } from "@/lib/utils";
import { Spinner } from "./ui";

function ProviderDot({ provider }: { provider: string }) {
  return (
    <span
      className={cn(
        "rounded-md px-1.5 py-0.5 text-[10px] font-semibold tracking-wide uppercase",
        provider === "ollama"
          ? "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
          : "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
      )}
    >
      {provider === "ollama" ? "Ollama" : "API"}
    </span>
  );
}

export function ModelSelector({
  value,
  onChange,
  align = "left",
  compact,
}: {
  value: string | null;
  onChange: (id: string) => void;
  align?: "left" | "right";
  compact?: boolean;
}) {
  const { models, modelsLoaded, loadModels } = useApp();
  const isAdmin = useAuth((s) => s.user?.role === "admin");
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return models.filter((m) => m.id.toLowerCase().includes(q) || m.connection_name.toLowerCase().includes(q));
  }, [models, query]);

  const current = models.find((m) => m.id === value);
  const missing = value && modelsLoaded && !current;

  return (
    <div className="relative min-w-0" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex max-w-full items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-left font-medium transition-colors hover:bg-gray-100 dark:hover:bg-gray-850",
          compact ? "text-sm" : "text-lg",
        )}
      >
        <span className={cn("truncate", missing && "text-amber-600 dark:text-amber-400", !value && "text-gray-500")}>
          {value ?? "Select a model"}
        </span>
        <ChevronDown className="size-4 shrink-0 text-gray-500" />
      </button>
      {open && (
        <div
          className={cn(
            "absolute top-full z-40 mt-1 w-[min(26rem,calc(100vw-2rem))] rounded-2xl border border-gray-100 bg-white shadow-2xl animate-fade-in dark:border-gray-800 dark:bg-gray-850",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          <div className="flex items-center gap-2 border-b border-gray-100 px-3 py-2 dark:border-gray-800">
            <Search className="size-4 text-gray-400" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search models"
              className="w-full bg-transparent py-1 text-sm outline-none placeholder:text-gray-400"
            />
            <button
              title="Refresh models"
              onClick={async () => {
                setRefreshing(true);
                await loadModels(true);
                setRefreshing(false);
              }}
              className="rounded-lg p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              {refreshing ? <Spinner className="size-3.5" /> : <RefreshCw className="size-3.5" />}
            </button>
          </div>
          <div className="max-h-80 overflow-y-auto p-1">
            {!modelsLoaded && (
              <div className="flex justify-center p-4">
                <Spinner />
              </div>
            )}
            {modelsLoaded && filtered.length === 0 && (
              <div className="px-3 py-6 text-center text-sm text-gray-500">
                {models.length === 0 ? (
                  <>
                    No models available.
                    <br />
                    {isAdmin ? "Check that Ollama is running or add a connection." : "Ask an admin to add a connection."}
                  </>
                ) : (
                  "No models match your search."
                )}
              </div>
            )}
            {filtered.map((m) => (
              <button
                key={m.id}
                onClick={() => {
                  onChange(m.id);
                  setOpen(false);
                  setQuery("");
                }}
                className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{m.name}</div>
                  <div className="truncate text-xs text-gray-500">
                    {m.connection_name}
                    {typeof m.details?.parameter_size === "string" && ` · ${m.details.parameter_size}`}
                  </div>
                </div>
                <ProviderDot provider={m.provider} />
                {m.id === value && <Check className="size-4 shrink-0" />}
              </button>
            ))}
          </div>
          {isAdmin && (
            <Link
              to="/admin/connections"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 border-t border-gray-100 px-4 py-2.5 text-xs text-gray-500 hover:text-gray-900 dark:border-gray-800 dark:hover:text-gray-100"
            >
              <Settings2 className="size-3.5" /> Manage connections
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
