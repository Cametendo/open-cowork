import { useState } from "react";
import { AlertTriangle, Check, Copy, Pencil, RefreshCw } from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import { cn, copyText } from "@/lib/utils";
import { AssistantContent } from "../Markdown";
import { Button, Logo } from "../ui";

function ActionButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      title={label}
      aria-label={label}
      onClick={onClick}
      className="rounded-lg p-1.5 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-gray-850 dark:hover:text-gray-100"
    >
      {children}
    </button>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <ActionButton
      label="Copy"
      onClick={async () => {
        await copyText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
    >
      {done ? <Check className="size-4" /> : <Copy className="size-4" />}
    </ActionButton>
  );
}

function UserMessage({
  message,
  onEdit,
  disabled,
}: {
  message: ChatMessage;
  onEdit: (content: string) => void;
  disabled?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.content);
  if (editing) {
    return (
      <div className="ml-auto w-full max-w-[85%] rounded-3xl bg-gray-50 p-3 dark:bg-gray-850">
        <textarea
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="min-h-20 w-full resize-y bg-transparent px-1 text-[15px] outline-none"
        />
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant="primary"
            disabled={!draft.trim()}
            onClick={() => {
              setEditing(false);
              onEdit(draft.trim());
            }}
          >
            Save & send
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className="group flex flex-col items-end">
      {message.images && message.images.length > 0 && (
        <div className="mb-2 flex flex-wrap justify-end gap-2">
          {message.images.map((img, i) => (
            <img key={i} src={`data:image/*;base64,${img}`} alt="" className="max-h-48 rounded-2xl object-cover" />
          ))}
        </div>
      )}
      {message.content && (
        <div className="max-w-[85%] rounded-3xl bg-gray-50 px-4 py-2.5 text-[15px] whitespace-pre-wrap dark:bg-gray-850">
          {message.content}
        </div>
      )}
      <div className="mt-1 flex opacity-0 transition-opacity group-hover:opacity-100">
        {!disabled && (
          <ActionButton label="Edit" onClick={() => setEditing(true)}>
            <Pencil className="size-4" />
          </ActionButton>
        )}
        <CopyButton text={message.content} />
      </div>
    </div>
  );
}

function AssistantMessage({
  message,
  streaming,
  isLast,
  onRegenerate,
}: {
  message: ChatMessage;
  streaming: boolean;
  isLast: boolean;
  onRegenerate: () => void;
}) {
  const empty = !message.content && !message.reasoning;
  return (
    <div className="group flex gap-3">
      <Logo className="mt-0.5 size-7 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="mb-1 text-sm font-medium text-gray-500">{message.model}</div>
        {streaming && empty ? (
          <div className="flex h-7 items-center gap-1">
            <span className="size-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
            <span className="size-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
            <span className="size-2 animate-bounce rounded-full bg-gray-400" />
          </div>
        ) : (
          <div className={cn(streaming && "streaming")}>
            <AssistantContent content={message.content} reasoning={message.reasoning} streaming={streaming} />
          </div>
        )}
        {message.error && (
          <div className="mt-2 flex items-start gap-2 rounded-2xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <div className="min-w-0 break-words">{message.error}</div>
          </div>
        )}
        {message.stopped && !message.error && <div className="mt-1 text-xs text-gray-500">Stopped</div>}
        {!streaming && (
          <div className={cn("mt-1 flex items-center opacity-0 transition-opacity group-hover:opacity-100", isLast && "opacity-100")}>
            <CopyButton text={message.content} />
            {isLast && (
              <ActionButton label="Regenerate" onClick={onRegenerate}>
                <RefreshCw className="size-4" />
              </ActionButton>
            )}
            {message.usage?.completion_tokens != null && (
              <span className="ml-2 text-xs text-gray-400">
                {message.usage.completion_tokens} tokens
                {message.usage.total_duration_ms
                  ? ` · ${((message.usage.completion_tokens ?? 0) / (message.usage.total_duration_ms / 1000)).toFixed(1)} tok/s`
                  : ""}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function Messages({
  messages,
  streaming,
  onRegenerate,
  onEdit,
}: {
  messages: ChatMessage[];
  streaming: boolean;
  onRegenerate: () => void;
  onEdit: (id: string, content: string) => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
      {messages.map((m, i) =>
        m.role === "user" ? (
          <UserMessage key={m.id} message={m} disabled={streaming} onEdit={(c) => onEdit(m.id, c)} />
        ) : (
          <AssistantMessage
            key={m.id}
            message={m}
            streaming={streaming && i === messages.length - 1}
            isLast={i === messages.length - 1}
            onRegenerate={onRegenerate}
          />
        ),
      )}
    </div>
  );
}
