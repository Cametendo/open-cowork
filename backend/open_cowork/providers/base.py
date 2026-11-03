"""Provider abstraction shared by Ollama and OpenAI-compatible backends.

Internally, conversations use an OpenAI-like message shape:

    {"role": "system" | "user" | "assistant", "content": str}
    {"role": "assistant", "content": str, "tool_calls": [{"id", "name", "arguments": dict}]}
    {"role": "tool", "tool_call_id": str, "name": str, "content": str}

Each provider converts these to its wire format and normalises its stream into
plain dict events:

    {"type": "content",    "text": str}
    {"type": "reasoning",  "text": str}
    {"type": "tool_calls", "tool_calls": [{"id", "name", "arguments": dict}]}
    {"type": "done",       "finish_reason": str | None, "usage": dict | None}
"""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=60.0, pool=10.0)


class ProviderError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class ConnectionInfo:
    id: str
    type: str  # "ollama" | "openai"
    name: str
    base_url: str
    api_key: str | None = None
    prefix_id: str | None = None
    model_ids: list[str] = field(default_factory=list)


@dataclass
class ModelInfo:
    id: str  # raw id as understood by the provider
    name: str
    details: dict[str, Any] = field(default_factory=dict)


def new_tool_call_id() -> str:
    return "call_" + uuid.uuid4().hex[:24]


def parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {"__raw__": raw}
        return value if isinstance(value, dict) else {"value": value}
    return {"value": raw}


async def error_from_response(resp: httpx.Response) -> ProviderError:
    try:
        body = (await resp.aread()).decode(errors="replace")
    except Exception:  # pragma: no cover - network edge
        body = ""
    message = body.strip() or resp.reason_phrase
    try:
        data = json.loads(body)
        err = data.get("error", data) if isinstance(data, dict) else data
        if isinstance(err, dict):
            message = err.get("message") or err.get("detail") or json.dumps(err)
        elif isinstance(err, str):
            message = err
    except (json.JSONDecodeError, AttributeError):
        pass
    return ProviderError(f"{resp.status_code}: {message}"[:2000], status=resp.status_code)


class Provider(ABC):
    def __init__(self, conn: ConnectionInfo, client: httpx.AsyncClient | None = None):
        self.conn = conn
        self.base_url = conn.base_url.rstrip("/")
        self._client = client

    def headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.conn.api_key:
            h["Authorization"] = f"Bearer {self.conn.api_key}"
        return h

    def client(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)

    async def _close(self, client: httpx.AsyncClient) -> None:
        if client is not self._client:
            await client.aclose()

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]: ...

    @abstractmethod
    def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]: ...

    async def complete(self, model: str, messages: list[dict[str, Any]], options: dict[str, Any] | None = None) -> str:
        """Non-streaming convenience wrapper (used for title generation)."""
        out: list[str] = []
        async for ev in self.stream_chat(model, messages, options=options):
            if ev["type"] == "content":
                out.append(ev["text"])
        return "".join(out)
