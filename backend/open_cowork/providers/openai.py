"""OpenAI-compatible Chat Completions API (OpenAI, vLLM, LM Studio, llama.cpp,
LiteLLM, OpenRouter, Groq, Ollama's /v1, ...)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .base import ModelInfo, Provider, ProviderError, error_from_response, new_tool_call_id, parse_arguments

# Non-chat model families hidden when talking to api.openai.com
_OPENAI_NON_CHAT = ("babbage", "dall-e", "davinci", "embedding", "tts", "whisper", "moderation", "transcribe", "image", "realtime", "audio", "search")


def to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": m.get("content") or ""}
            if m.get("tool_calls"):
                msg["content"] = m.get("content") or None
                msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc.get("arguments") or {})},
                    }
                    for tc in m["tool_calls"]
                ]
            out.append(msg)
        elif role == "tool":
            out.append({"role": "tool", "tool_call_id": m.get("tool_call_id"), "content": m.get("content") or ""})
        else:
            out.append({"role": role, "content": m.get("content") or ""})
    return out


class OpenAIProvider(Provider):
    async def list_models(self) -> list[ModelInfo]:
        client = self.client()
        try:
            resp = await client.get(f"{self.base_url}/models", headers=self.headers(), timeout=15.0)
            if resp.status_code >= 400:
                raise await error_from_response(resp)
            data = resp.json()
        except httpx.HTTPError as e:
            raise ProviderError(f"Could not reach {self.base_url}: {e}") from e
        except ValueError as e:
            raise ProviderError(f"Unexpected response from {self.base_url}/models") from e
        finally:
            await self._close(client)

        items = data.get("data", data) if isinstance(data, dict) else data
        is_openai = "api.openai.com" in self.base_url
        models = []
        for m in items or []:
            mid = m.get("id") if isinstance(m, dict) else None
            if not mid:
                continue
            if is_openai and any(x in mid for x in _OPENAI_NON_CHAT):
                continue
            details = {k: m[k] for k in ("owned_by", "context_length") if isinstance(m, dict) and k in m}
            models.append(ModelInfo(id=mid, name=(m.get("name") or mid), details=details))
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
            "messages": to_openai_messages(messages),
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        if options.get("temperature") is not None:
            payload["temperature"] = options["temperature"]
        if options.get("max_tokens"):
            payload["max_tokens"] = options["max_tokens"]

        # index -> {"id", "name", "arguments": str}
        partial: dict[int, dict[str, str]] = {}
        finish_reason = None
        usage = None
        client = self.client()
        try:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions", json=payload, headers=self.headers()
            ) as resp:
                if resp.status_code >= 400:
                    raise await error_from_response(resp)
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":") or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        err = chunk["error"]
                        raise ProviderError(err.get("message", str(err)) if isinstance(err, dict) else str(err))
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or choice.get("message") or {}
                        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                        if reasoning and isinstance(reasoning, str):
                            yield {"type": "reasoning", "text": reasoning}
                        if delta.get("content"):
                            yield {"type": "content", "text": delta["content"]}
                        for tc in delta.get("tool_calls") or []:
                            idx = tc.get("index", len(partial))
                            slot = partial.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                            if tc.get("id"):
                                slot["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                slot["name"] += fn["name"]
                            if fn.get("arguments"):
                                args = fn["arguments"]
                                slot["arguments"] += args if isinstance(args, str) else json.dumps(args)
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
        except httpx.HTTPError as e:
            raise ProviderError(f"Request to {self.base_url} failed: {e}") from e
        finally:
            await self._close(client)

        if partial:
            yield {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "id": slot["id"] or new_tool_call_id(),
                        "name": slot["name"],
                        "arguments": parse_arguments(slot["arguments"]),
                    }
                    for _, slot in sorted(partial.items())
                ],
            }
        yield {"type": "done", "finish_reason": finish_reason, "usage": usage}
