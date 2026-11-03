"""A tiny fake LLM server speaking both the Ollama and OpenAI-compatible APIs.

Used by the test-suite and handy for UI development without a GPU:

    python tests/mock_llm.py --port 11555
    # then add an Ollama connection to http://localhost:11555
    # or an OpenAI connection to http://localhost:11555/v1

Behaviour:
- Without tools: streams "Echo: <last user message>".
- With tools: user messages may contain directives like
  ``[[tool:write_file {"path": "a.txt", "content": "hi"}]]``. The n-th directive is
  issued as a tool call after n-1 tool results; then a summary is returned.
  Without directives a small demo scenario runs (plan -> list -> write -> done).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
MODELS = ["mock-llama:latest", "mock-coder:7b"]
DIRECTIVE = re.compile(r"\[\[tool:(\w+)\s*(\{.*?\})?\]\]", re.S)


def _last_user_index(messages):
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            return i
    return -1


def _demo_calls(user_text: str):
    return [
        ("update_plan", {"items": [
            {"title": "Look around the workspace", "status": "in_progress"},
            {"title": "Write notes.md", "status": "pending"},
        ]}),
        ("list_files", {"path": "."}),
        ("write_file", {"path": "notes.md", "content": f"# Notes\n\nTask: {user_text.strip()[:200]}\n\n- Created by the mock model.\n"}),
        ("update_plan", {"items": [
            {"title": "Look around the workspace", "status": "completed"},
            {"title": "Write notes.md", "status": "completed"},
        ]}),
    ]


DEMO_ANSWER = """Think of a **vector database** as a library where books are shelved by *meaning* instead of by title.

### How it works
1. **Embed** — each document is turned into a vector (a list of numbers) by an embedding model.
2. **Index** — vectors are stored in a structure built for fast nearest-neighbour search (e.g. HNSW).
3. **Query** — your question is embedded too, and the closest vectors are returned.

```python
results = collection.query(query_texts=["how do I reset my password?"], n_results=3)
for doc in results["documents"][0]:
    print(doc)
```

| Traditional DB | Vector DB |
| --- | --- |
| Exact matches | Similar meaning |
| `WHERE title = ...` | nearest neighbours |

That's why they power *retrieval-augmented generation* (RAG): find the most relevant passages, then let the model answer with them."""


def decide(messages, has_tools: bool):
    """Return ("text", str) or ("tools", [(name, args)])."""
    idx = _last_user_index(messages)
    user_text = messages[idx].get("content") or "" if idx >= 0 else ""
    if isinstance(user_text, list):
        user_text = " ".join(p.get("text", "") for p in user_text if isinstance(p, dict))
    if not has_tools:
        if "title (3-6 words)" in user_text:
            return ("text", "Vector Databases Explained" if "vector database" in user_text else "Mock Conversation Title")
        if "vector database" in user_text.lower():
            return ("text", DEMO_ANSWER)
        return ("text", f"Echo: {user_text}")
    tool_results = sum(1 for m in messages[idx + 1 :] if m.get("role") == "tool")
    directives = [(m.group(1), json.loads(m.group(2) or "{}")) for m in DIRECTIVE.finditer(user_text)]
    calls = directives or _demo_calls(user_text)
    if tool_results < len(calls):
        return ("tools", [calls[tool_results]])
    return ("text", f"All done. I completed {len(calls)} step(s).")


def _chunks(text: str):
    words = re.findall(r"\S+\s*", text) or [text]
    for w in words:
        yield w


# ------------------------------------------------------------------ Ollama


@app.get("/api/tags")
async def tags():
    return {"models": [{"name": m, "model": m, "size": 123456789, "details": {"family": "mock", "parameter_size": "7B"}} for m in MODELS]}


@app.post("/api/chat")
async def ollama_chat(request: Request):
    body = await request.json()
    if body.get("model") not in MODELS:
        return JSONResponse({"error": f"model '{body.get('model')}' not found"}, status_code=404)
    kind, value = decide(body.get("messages", []), bool(body.get("tools")))

    async def gen():
        if kind == "text":
            for w in _chunks(value):
                yield json.dumps({"model": body["model"], "message": {"role": "assistant", "content": w}, "done": False}) + "\n"
                await asyncio.sleep(0.01)
        else:
            calls = [{"function": {"name": n, "arguments": a}} for n, a in value]
            yield json.dumps({"model": body["model"], "message": {"role": "assistant", "content": "", "tool_calls": calls}, "done": False}) + "\n"
        yield json.dumps({"model": body["model"], "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop", "eval_count": 10, "prompt_eval_count": 20, "total_duration": 1_000_000}) + "\n"

    if body.get("stream") is False:
        return {"message": {"role": "assistant", "content": value if kind == "text" else ""}, "done": True}
    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ------------------------------------------------------------------ OpenAI


@app.get("/v1/models")
async def models(request: Request):
    return {"object": "list", "data": [{"id": m, "object": "model", "owned_by": "mock"} for m in MODELS]}


@app.post("/v1/chat/completions")
async def completions(request: Request):
    body = await request.json()
    kind, value = decide(body.get("messages", []), bool(body.get("tools")))
    cid = "chatcmpl-" + uuid.uuid4().hex[:8]

    def chunk(delta, finish=None):
        return "data: " + json.dumps({"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": body.get("model"), "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}) + "\n\n"

    async def gen():
        yield chunk({"role": "assistant"})
        if kind == "text":
            for w in _chunks(value):
                yield chunk({"content": w})
                await asyncio.sleep(0.01)
            yield chunk({}, "stop")
        else:
            for i, (name, args) in enumerate(value):
                raw = json.dumps(args)
                half = len(raw) // 2
                yield chunk({"tool_calls": [{"index": i, "id": "call_" + uuid.uuid4().hex[:8], "type": "function", "function": {"name": name, "arguments": raw[:half]}}]})
                yield chunk({"tool_calls": [{"index": i, "function": {"arguments": raw[half:]}}]})
            yield chunk({}, "tool_calls")
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=11555)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port)
