import { useState } from "react";
import { AlertTriangle, Check, ChevronDown, Copy, Globe, Pencil, RefreshCw } from "lucide-react";
import type { ChatMessage, WebSource } from "@/lib/types";
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

function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Turn [1] citations into links to the matching source. */
function linkCitations(content: string, sources?: WebSource[]) {
  if (!sources?.length) return content;
  return content.replace(/\[(\d{1,2})\](?!\()/g, (m, n) => {
    const src = sources[Number(n) - 1];
    return src ? `[${n}](${src.url})` : m;
  });
}

function SearchSummary({ message, streaming }: { message: ChatMessage; streaming: boolean }) {
  const [open, setOpen] = useState(false);
  if (!message.search_query) return null;
  const sources = message.sources;
  const searching = streaming && sources === undefined;
  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={!sources?.length}
        className="flex max-w-full items-center gap-1.5 text-sm text-gray-500 enabled:hover:text-gray-800 dark:enabled:hover:text-gray-200"
      >
        <Globe className="size-4 shrink-0" />
        <span className={cn("truncate", searching && "shimmer")}>
          {searching
            ? `Searching the web for “${message.search_query}”…`
            : message.search_error
              ? "Web search failed"
              : sources?.length
                ? `Searched the web · ${sources.length} source${sources.length === 1 ? "" : "s"}`
                : "Searched the web · no results"}
        </span>
        {!!sources?.length && <ChevronDown className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-180")} />}
      </button>
      {message.search_error && <div className="mt-1 ml-5.5 text-xs text-amber-600 dark:text-amber-400">{message.search_error}</div>}
      {open && !!sources?.length && (
        <ol className="mt-2 space-y-1.5 border-l-2 border-gray-200 pl-3 dark:border-gray-800">
          {sources.map((s, i) => (
            <li key={s.url + i} className="text-sm">
              <a href={s.url} target="_blank" rel="noreferrer noopener" className="font-medium text-accent-600 hover:underline dark:text-accent-400">
                [{i + 1}] {s.title || hostOf(s.url)}
              </a>
              <div className="truncate text-xs text-gray-500">{hostOf(s.url)}</div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function SourceChips({ sources }: { sources: WebSource[] }) {
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {sources.map((s, i) => (
        <a
          key={s.url + i}
          href={s.url}
          target="_blank"
          rel="noreferrer noopener"
          title={s.title}
          className="flex max-w-56 items-center gap-1.5 rounded-full border border-gray-200 px-2.5 py-1 text-xs text-gray-600 transition-colors hover:bg-gray-50 dark:border-gray-800 dark:text-gray-400 dark:hover:bg-gray-850"
        >
          <span className="font-medium text-gray-900 dark:text-gray-100">{i + 1}</span>
          <span className="truncate">{hostOf(s.url)}</span>
        </a>
      ))}
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
        <SearchSummary message={message} streaming={streaming} />
        {streaming && empty && !(message.search_query && message.sources === undefined) ? (
          <div className="flex h-7 items-center gap-1">
            <span className="size-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
            <span className="size-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
            <span className="size-2 animate-bounce rounded-full bg-gray-400" />
          </div>
        ) : (
          <div className={cn(streaming && "streaming")}>
            <AssistantContent content={linkCitations(message.content, message.sources)} reasoning={message.reasoning} streaming={streaming} />
          </div>
        )}
        {!streaming && !!message.sources?.length && <SourceChips sources={message.sources} />}
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
