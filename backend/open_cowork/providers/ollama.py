"""Ollama native API (/api/tags, /api/chat)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .base import ModelInfo, Provider, ProviderError, error_from_response, new_tool_call_id, parse_arguments


def to_ollama_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": m.get("content") or ""}
            if m.get("tool_calls"):
                msg["tool_calls"] = [
                    {"function": {"name": tc["name"], "arguments": tc.get("arguments") or {}}}
                    for tc in m["tool_calls"]
                ]
            out.append(msg)
        elif role == "tool":
            out.append({"role": "tool", "content": m.get("content") or "", "tool_name": m.get("name", "")})
        else:
            msg = {"role": role, "content": m.get("content") or ""}
            if m.get("images"):
                msg["images"] = m["images"]
            out.append(msg)
    return out


class OllamaProvider(Provider):
    async def list_models(self) -> list[ModelInfo]:
        client = self.client()
        try:
            resp = await client.get(f"{self.base_url}/api/tags", headers=self.headers(), timeout=10.0)
            if resp.status_code >= 400:
                raise await error_from_response(resp)
            data = resp.json()
        except httpx.HTTPError as e:
            raise ProviderError(f"Could not reach Ollama at {self.base_url}: {e}") from e
        finally:
            await self._close(client)
        models = []
        for m in data.get("models", []):
            mid = m.get("model") or m.get("name")
            if not mid:
                continue
            details = dict(m.get("details") or {})
            if m.get("size"):
                details["size"] = m["size"]
            models.append(ModelInfo(id=mid, name=m.get("name") or mid, details=details))
        return models

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        options = dict(options or {})
        payload: dict[str, Any] = {
            "model": model,
            "messages": to_ollama_messages(messages),
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        ollama_opts: dict[str, Any] = {}
        if options.get("temperature") is not None:
            ollama_opts["temperature"] = options["temperature"]
        if options.get("max_tokens"):
            ollama_opts["num_predict"] = options["max_tokens"]
        if options.get("num_ctx"):
            ollama_opts["num_ctx"] = options["num_ctx"]
        if ollama_opts:
            payload["options"] = ollama_opts
        if options.get("keep_alive") is not None:
            payload["keep_alive"] = options["keep_alive"]

        tool_calls: list[dict[str, Any]] = []
        client = self.client()
        try:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload, headers=self.headers()) as resp:
                if resp.status_code >= 400:
                    raise await error_from_response(resp)
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        raise ProviderError(str(chunk["error"]))
                    msg = chunk.get("message") or {}
                    if msg.get("thinking"):
                        yield {"type": "reasoning", "text": msg["thinking"]}
                    if msg.get("content"):
                        yield {"type": "content", "text": msg["content"]}
                    for tc in msg.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        tool_calls.append(
                            {
                                "id": tc.get("id") or new_tool_call_id(),
                                "name": fn.get("name", ""),
                                "arguments": parse_arguments(fn.get("arguments")),
                            }
                        )
                    if chunk.get("done"):
                        if tool_calls:
                            yield {"type": "tool_calls", "tool_calls": tool_calls}
                        usage = None
                        if "eval_count" in chunk or "prompt_eval_count" in chunk:
                            usage = {
                                "prompt_tokens": chunk.get("prompt_eval_count"),
                                "completion_tokens": chunk.get("eval_count"),
                                "total_duration_ms": int((chunk.get("total_duration") or 0) / 1e6),
                            }
                        yield {"type": "done", "finish_reason": chunk.get("done_reason"), "usage": usage}
                        return
        except httpx.HTTPError as e:
            raise ProviderError(f"Ollama request failed: {e}") from e
        finally:
            await self._close(client)
        # Stream ended without a done marker
        if tool_calls:
            yield {"type": "tool_calls", "tool_calls": tool_calls}
        yield {"type": "done", "finish_reason": None, "usage": None}
