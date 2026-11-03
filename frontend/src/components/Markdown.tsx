import { memo, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Brain, Check, ChevronDown, Copy } from "lucide-react";
import { cn, copyText, splitThinking } from "@/lib/utils";

function textOf(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (typeof node === "object" && "props" in (node as any)) return textOf((node as any).props.children);
  return "";
}

export function CodeBlock({ language, code, children }: { language?: string; code: string; children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="not-prose my-3 overflow-hidden rounded-2xl border border-gray-200 bg-gray-950 dark:border-gray-800">
      <div className="flex items-center justify-between bg-gray-900 px-4 py-1.5 text-xs text-gray-400">
        <span className="font-mono">{language || "text"}</span>
        <button
          onClick={async () => {
            await copyText(code);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
          className="flex items-center gap-1 rounded-md px-1.5 py-0.5 hover:bg-gray-800 hover:text-gray-100"
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 text-[13px] leading-relaxed text-gray-100">
        <code className={language ? `hljs language-${language}` : "hljs"}>{children ?? code}</code>
      </pre>
    </div>
  );
}

const components = {
  pre: ({ children }: { children?: ReactNode }) => <>{children}</>,
  code: ({ className, children, ...rest }: { className?: string; children?: ReactNode; node?: any }) => {
    const match = /language-([\w+#-]+)/.exec(className || "");
    const raw = textOf(children);
    const isBlock = !!match || raw.includes("\n");
    if (!isBlock) return <code className={className}>{children}</code>;
    void rest;
    return (
      <CodeBlock language={match?.[1]} code={raw.replace(/\n$/, "")}>
        {children}
      </CodeBlock>
    );
  },
  a: ({ href, children }: { href?: string; children?: ReactNode }) => (
    <a href={href} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  ),
  table: ({ children }: { children?: ReactNode }) => (
    <div className="not-prose my-3 overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800">
      <table className="w-full text-sm [&_td]:border-t [&_td]:border-gray-200 [&_td]:px-3 [&_td]:py-2 [&_th]:bg-gray-50 [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-medium dark:[&_td]:border-gray-800 dark:[&_th]:bg-gray-850">
        {children}
      </table>
    </div>
  ),
};

export const Markdown = memo(function Markdown({ content, className }: { content: string; className?: string }) {
  return (
    <div className={cn("markdown", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: false, ignoreMissing: true }]]}
        components={components as any}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});

export function Thinking({ text, active }: { text: string; active?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 dark:hover:text-gray-200"
      >
        <Brain className="size-4" />
        <span className={cn(active && "shimmer")}>{active ? "Thinking…" : "Thought process"}</span>
        <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-2 border-l-2 border-gray-200 pl-3 text-sm whitespace-pre-wrap text-gray-500 dark:border-gray-800">
          {text}
        </div>
      )}
    </div>
  );
}

/** Assistant content with reasoning (explicit field or inline <think> tags) split out. */
export function AssistantContent({
  content,
  reasoning,
  streaming,
}: {
  content: string;
  reasoning?: string;
  streaming?: boolean;
}) {
  const split = splitThinking(content);
  const thinking = [reasoning, split.thinking].filter(Boolean).join("\n\n");
  const thinkingActive = !!streaming && (split.open || (!!reasoning && !split.answer));
  return (
    <>
      {thinking && <Thinking text={thinking} active={thinkingActive} />}
      {split.answer && <Markdown content={split.answer} />}
    </>
  );
}
