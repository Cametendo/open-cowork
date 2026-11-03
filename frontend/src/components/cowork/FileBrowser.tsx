import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ChevronRight, Download, File, Folder, FolderOpen, RefreshCw, Upload } from "lucide-react";
import { toast } from "sonner";
import { api, authHeaders } from "@/lib/api";
import type { FileEntry } from "@/lib/types";
import { cn, formatBytes, languageFor } from "@/lib/utils";
import { Markdown } from "../Markdown";
import { IconButton, Spinner } from "../ui";

function Tree({
  sessionId,
  path,
  depth,
  onOpen,
  selected,
  version,
}: {
  sessionId: string;
  path: string;
  depth: number;
  onOpen: (p: string) => void;
  selected: string | null;
  version: number;
}) {
  const [entries, setEntries] = useState<FileEntry[] | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .coworkFiles(sessionId, path)
      .then((r) => {
        setEntries(r.entries);
        setError(null);
      })
      .catch((e) => setError(e.message));
  }, [sessionId, path, version]);

  if (error) return <div className="px-3 py-2 text-xs text-red-500">{error}</div>;
  if (!entries) return <div className="px-3 py-1" style={{ paddingLeft: 12 + depth * 14 }}><Spinner className="size-3.5 text-gray-400" /></div>;
  if (entries.length === 0 && depth === 0) return <div className="px-3 py-6 text-center text-xs text-gray-500">The workspace is empty</div>;

  return (
    <div>
      {entries.map((e) => (
        <div key={e.path}>
          <button
            onClick={() => (e.type === "dir" ? setOpen((o) => ({ ...o, [e.path]: !o[e.path] })) : onOpen(e.path))}
            className={cn(
              "flex w-full items-center gap-1.5 rounded-lg py-1 pr-2 text-left text-[13px] hover:bg-gray-100 dark:hover:bg-gray-850",
              selected === e.path && "bg-gray-100 dark:bg-gray-850",
              e.ignored && "opacity-50",
            )}
            style={{ paddingLeft: 8 + depth * 14 }}
          >
            {e.type === "dir" ? (
              <>
                <ChevronRight className={cn("size-3.5 shrink-0 text-gray-400 transition-transform", open[e.path] && "rotate-90")} />
                {open[e.path] ? <FolderOpen className="size-4 shrink-0 text-accent-500" /> : <Folder className="size-4 shrink-0 text-accent-500" />}
              </>
            ) : (
              <>
                <span className="w-3.5 shrink-0" />
                <File className="size-4 shrink-0 text-gray-400" />
              </>
            )}
            <span className="truncate">{e.name}</span>
            {e.type === "file" && <span className="ml-auto shrink-0 pl-2 text-[11px] text-gray-400">{formatBytes(e.size)}</span>}
          </button>
          {e.type === "dir" && open[e.path] && (
            <Tree sessionId={sessionId} path={e.path} depth={depth + 1} onOpen={onOpen} selected={selected} version={version} />
          )}
        </div>
      ))}
    </div>
  );
}

function Preview({ sessionId, path, onBack, version }: { sessionId: string; path: string; onBack: () => void; version: number }) {
  const [file, setFile] = useState<Awaited<ReturnType<typeof api.coworkFile>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rendered, setRendered] = useState(true);
  useEffect(() => {
    setFile(null);
    api.coworkFile(sessionId, path).then(setFile).catch((e) => setError(e.message));
  }, [sessionId, path, version]);

  const lang = languageFor(path);
  const isMarkdown = lang === "markdown";
  const isImage = file?.mime.startsWith("image/");

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1 border-b border-gray-100 px-2 py-1.5 dark:border-gray-850">
        <IconButton label="Back to files" onClick={onBack}>
          <ArrowLeft className="size-4" />
        </IconButton>
        <div className="min-w-0 flex-1 truncate font-mono text-xs text-gray-600 dark:text-gray-400" title={path}>
          {path}
        </div>
        {isMarkdown && (
          <button onClick={() => setRendered((v) => !v)} className="rounded-lg px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-850">
            {rendered ? "Source" : "Preview"}
          </button>
        )}
        <IconButton label="Download" onClick={() => api.coworkDownload(sessionId, path).catch((e) => toast.error(e.message))}>
          <Download className="size-4" />
        </IconButton>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {error && <div className="p-3 text-sm text-red-500">{error}</div>}
        {!file && !error && (
          <div className="flex justify-center p-6">
            <Spinner className="text-gray-400" />
          </div>
        )}
        {file &&
          (file.binary ? (
            isImage ? (
              <ImagePreview sessionId={sessionId} path={path} />
            ) : (
              <div className="p-6 text-center text-sm text-gray-500">Binary file ({formatBytes(file.size)}). Download it to open.</div>
            )
          ) : isMarkdown && rendered ? (
            <div className="p-4">
              <Markdown content={file.content ?? ""} />
            </div>
          ) : (file.content?.length ?? 0) > 150_000 ? (
            <pre className="p-3 font-mono text-[12px] whitespace-pre">{file.content}</pre>
          ) : (
            <HighlightedCode code={file.content ?? ""} language={lang} />
          ))}
        {file?.truncated && <div className="p-3 text-xs text-gray-500">Preview truncated — download the file to see all of it.</div>}
      </div>
    </div>
  );
}

function HighlightedCode({ code, language }: { code: string; language: string }) {
  // Reuse the markdown pipeline (rehype-highlight) to colourise the file
  const fence = "`".repeat((code.match(/`+/g) ?? []).reduce((m, s) => Math.max(m, s.length + 1), 3));
  return (
    <div className="[&_.not-prose]:my-0 [&_.not-prose]:rounded-none [&_.not-prose]:border-0">
      <Markdown content={`${fence}${language}\n${code}\n${fence}`} />
    </div>
  );
}

function ImagePreview({ sessionId, path }: { sessionId: string; path: string }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let revoke: string | null = null;
    fetch(`/api/cowork/sessions/${sessionId}/download?path=${encodeURIComponent(path)}`, { headers: authHeaders(false) })
      .then((r) => r.blob())
      .then((b) => {
        revoke = URL.createObjectURL(b);
        setUrl(revoke);
      })
      .catch(() => {});
    return () => {
      if (revoke) URL.revokeObjectURL(revoke);
    };
  }, [sessionId, path]);
  return url ? <img src={url} alt={path} className="mx-auto max-w-full p-4" /> : <Spinner />;
}

export function FileBrowser({ sessionId, root, version }: { sessionId: string; root: string; version: number }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [localVersion, setLocalVersion] = useState(0);
  const [uploading, setUploading] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const v = version + localVersion;
  const refresh = useCallback(() => setLocalVersion((x) => x + 1), []);

  if (selected) return <Preview sessionId={sessionId} path={selected} onBack={() => setSelected(null)} version={v} />;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1 border-b border-gray-100 px-3 py-1.5 dark:border-gray-850">
        <div className="min-w-0 flex-1 truncate font-mono text-[11px] text-gray-500" title={root}>
          {root}
        </div>
        <input
          ref={input}
          type="file"
          multiple
          hidden
          onChange={async (e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (!files.length) return;
            setUploading(true);
            try {
              const r = await api.coworkUpload(sessionId, files);
              toast.success(`Uploaded ${r.saved.length} file${r.saved.length > 1 ? "s" : ""}`);
              refresh();
            } catch (err: any) {
              toast.error(err.message);
            } finally {
              setUploading(false);
            }
          }}
        />
        <IconButton label="Upload files to the workspace" onClick={() => input.current?.click()}>
          {uploading ? <Spinner className="size-4" /> : <Upload className="size-4" />}
        </IconButton>
        <IconButton label="Refresh" onClick={refresh}>
          <RefreshCw className="size-4" />
        </IconButton>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
        <Tree sessionId={sessionId} path="." depth={0} onOpen={setSelected} selected={selected} version={v} />
      </div>
    </div>
  );
}
