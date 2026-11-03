import { useEffect, useState } from "react";
import { X } from "lucide-react";
import type { ChatParams } from "@/lib/types";
import { IconButton, Input, Label, Textarea } from "../ui";

export function ChatControls({
  params,
  onChange,
  onClose,
}: {
  params: ChatParams;
  onChange: (p: ChatParams) => void;
  onClose: () => void;
}) {
  const [local, setLocal] = useState<ChatParams>(params);
  useEffect(() => setLocal(params), [params]);

  const commit = (p: ChatParams) => {
    setLocal(p);
    onChange(p);
  };

  const num = (v: string) => (v === "" ? null : Number(v));

  return (
    <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-sm flex-col border-l border-gray-100 bg-white shadow-2xl animate-fade-in lg:relative lg:z-auto lg:w-80 lg:shadow-none dark:border-gray-850 dark:bg-gray-900">
      <div className="flex items-center justify-between px-4 py-3">
        <div className="font-medium">Chat controls</div>
        <IconButton label="Close" onClick={onClose}>
          <X className="size-4" />
        </IconButton>
      </div>
      <div className="flex-1 space-y-5 overflow-y-auto px-4 pb-6">
        <div>
          <Label hint="Overrides your default system prompt for this chat.">System prompt</Label>
          <Textarea
            rows={6}
            value={local.system ?? ""}
            placeholder="You are a helpful assistant."
            onChange={(e) => setLocal({ ...local, system: e.target.value })}
            onBlur={() => commit(local)}
          />
        </div>
        <div>
          <Label hint="Higher is more creative, lower more focused.">
            Temperature <span className="ml-1 text-gray-500">{local.temperature ?? "default"}</span>
          </Label>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={0}
              max={2}
              step={0.05}
              value={local.temperature ?? 0.8}
              onChange={(e) => setLocal({ ...local, temperature: Number(e.target.value) })}
              onMouseUp={() => commit(local)}
              onTouchEnd={() => commit(local)}
              onKeyUp={() => commit(local)}
              className="flex-1 accent-accent-600"
            />
            <button className="text-xs text-gray-500 hover:underline" onClick={() => commit({ ...local, temperature: null })}>
              Reset
            </button>
          </div>
        </div>
        <div>
          <Label hint="Maximum length of each reply.">Max tokens</Label>
          <Input
            type="number"
            min={1}
            placeholder="Default"
            value={local.max_tokens ?? ""}
            onChange={(e) => setLocal({ ...local, max_tokens: num(e.target.value) })}
            onBlur={() => commit(local)}
          />
        </div>
        <div>
          <Label hint="Ollama only: context window in tokens (num_ctx).">Context length</Label>
          <Input
            type="number"
            min={256}
            step={1024}
            placeholder="Model default"
            value={local.num_ctx ?? ""}
            onChange={(e) => setLocal({ ...local, num_ctx: num(e.target.value) })}
            onBlur={() => commit(local)}
          />
        </div>
      </div>
    </aside>
  );
}
