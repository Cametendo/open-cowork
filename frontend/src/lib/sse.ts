import { authHeaders, errorFrom } from "./api";

/**
 * POST/GET a server-sent-events endpoint with fetch (so we can send the auth
 * header) and call onEvent for every `data:` JSON payload.
 */
export async function streamSSE<T = any>(
  path: string,
  opts: { method?: "GET" | "POST"; body?: unknown; signal?: AbortSignal },
  onEvent: (ev: T) => void,
): Promise<void> {
  const res = await fetch(path, {
    method: opts.method ?? "GET",
    headers: { ...authHeaders(true), Accept: "text/event-stream" },
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    signal: opts.signal,
  });
  if (!res.ok) throw await errorFrom(res);
  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const data = block
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trimStart())
        .join("\n");
      if (!data) continue;
      try {
        onEvent(JSON.parse(data) as T);
      } catch {
        /* ignore malformed event */
      }
    }
  }
}
