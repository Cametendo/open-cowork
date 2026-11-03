"""Aggregates models across all enabled connections and resolves model ids."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ConfigEntry, Connection
from ..security import decrypt, encrypt
from .base import ConnectionInfo, Provider, ProviderError
from .ollama import OllamaProvider
from .openai import OpenAIProvider

log = logging.getLogger(__name__)

_CACHE_TTL = 30.0
_cache: dict[str, Any] = {"at": 0.0, "models": [], "index": {}}
_lock = asyncio.Lock()


def connection_info(conn: Connection) -> ConnectionInfo:
    return ConnectionInfo(
        id=conn.id,
        type=conn.type,
        name=conn.name,
        base_url=conn.base_url,
        api_key=decrypt(conn.api_key),
        prefix_id=conn.prefix_id or None,
        model_ids=list(conn.model_ids or []),
    )


def make_provider(info: ConnectionInfo) -> Provider:
    if info.type == "ollama":
        return OllamaProvider(info)
    if info.type == "openai":
        return OpenAIProvider(info)
    raise ProviderError(f"Unknown connection type: {info.type}")


def invalidate_cache() -> None:
    _cache["at"] = 0.0


async def _fetch(info: ConnectionInfo) -> tuple[ConnectionInfo, list, str | None]:
    try:
        models = await asyncio.wait_for(make_provider(info).list_models(), timeout=12)
        return info, models, None
    except (ProviderError, asyncio.TimeoutError, Exception) as e:  # noqa: BLE001
        msg = getattr(e, "message", None) or str(e) or e.__class__.__name__
        log.warning("Could not list models for %s (%s): %s", info.name, info.base_url, msg)
        return info, [], msg


async def get_models(db: Session, force: bool = False) -> list[dict[str, Any]]:
    async with _lock:
        if not force and time.monotonic() - _cache["at"] < _CACHE_TTL:
            return _cache["models"]
        conns = [connection_info(c) for c in db.query(Connection).filter(Connection.enabled.is_(True)).all()]
        results = await asyncio.gather(*(_fetch(c) for c in conns))
        models: list[dict[str, Any]] = []
        index: dict[str, tuple[ConnectionInfo, str]] = {}
        for info, items, _err in results:
            allow = set(info.model_ids)
            for m in items:
                if allow and m.id not in allow:
                    continue
                mid = f"{info.prefix_id}.{m.id}" if info.prefix_id else m.id
                if mid in index:
                    continue
                index[mid] = (info, m.id)
                models.append(
                    {
                        "id": mid,
                        "name": m.name if not info.prefix_id else f"{info.prefix_id}.{m.name}",
                        "provider": info.type,
                        "connection_id": info.id,
                        "connection_name": info.name,
                        "details": m.details,
                    }
                )
        _cache.update(at=time.monotonic(), models=models, index=index)
        return models


async def resolve_model(db: Session, model_id: str) -> tuple[Provider, str]:
    """Return (provider, raw model id) for a model id from get_models()."""
    await get_models(db)
    hit = _cache["index"].get(model_id)
    if hit is None:
        await get_models(db, force=True)
        hit = _cache["index"].get(model_id)
    if hit is None:
        raise ProviderError(f"Model '{model_id}' is not available. Check the connection in Admin › Connections.", 404)
    info, raw = hit
    return make_provider(info), raw


def seed_connections(db: Session) -> None:
    """Create initial connections from env vars on first boot."""
    if db.get(ConfigEntry, "connections_seeded"):
        return
    s = get_settings()
    if db.query(Connection).count() == 0:
        db.add(
            Connection(
                type="ollama",
                name="Ollama",
                base_url=s.seed_ollama_base_url.rstrip("/"),
                enabled=s.seed_enable_ollama,
            )
        )
        if s.seed_openai_base_url or s.seed_openai_api_key:
            base = s.seed_openai_base_url or "https://api.openai.com/v1"
            db.add(
                Connection(
                    type="openai",
                    name="OpenAI" if "api.openai.com" in base else "OpenAI-compatible",
                    base_url=base.rstrip("/"),
                    api_key=encrypt(s.seed_openai_api_key),
                    enabled=s.seed_enable_openai,
                )
            )
    db.add(ConfigEntry(key="connections_seeded", value=True))
    db.commit()
