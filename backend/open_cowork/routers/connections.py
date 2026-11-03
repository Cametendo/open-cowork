"""Admin management of Ollama / OpenAI-compatible connections, and the model list."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_admin_user, get_verified_user
from ..models import Connection, User
from ..providers import ProviderError, get_models, invalidate_cache, make_provider
from ..providers.base import ConnectionInfo
from ..providers.registry import connection_info
from ..security import encrypt

router = APIRouter(prefix="/api", tags=["models"])

TYPES = ("ollama", "openai")


class ConnectionBody(BaseModel):
    type: str
    name: str = Field(min_length=1, max_length=255)
    base_url: str = Field(min_length=1, max_length=1024)
    api_key: str | None = None
    enabled: bool = True
    prefix_id: str | None = None
    model_ids: list[str] = []


class ConnectionPatch(BaseModel):
    name: str | None = None
    base_url: str | None = None
    # None = unchanged, "" = clear
    api_key: str | None = None
    enabled: bool | None = None
    prefix_id: str | None = None
    model_ids: list[str] | None = None


class VerifyBody(BaseModel):
    type: str
    base_url: str
    api_key: str | None = None
    # When verifying an existing connection without retyping its key
    connection_id: str | None = None


def serialize(c: Connection) -> dict:
    return {
        "id": c.id,
        "type": c.type,
        "name": c.name,
        "base_url": c.base_url,
        "has_api_key": bool(c.api_key),
        "enabled": c.enabled,
        "prefix_id": c.prefix_id,
        "model_ids": c.model_ids or [],
        "created_at": c.created_at,
    }


def _clean_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Base URL must start with http:// or https://")
    return url


@router.get("/models")
async def list_models(refresh: bool = False, _: User = Depends(get_verified_user), db: Session = Depends(get_db)):
    return {"data": await get_models(db, force=refresh)}


@router.get("/admin/connections")
def list_connections(_: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    return [serialize(c) for c in db.query(Connection).order_by(Connection.created_at.asc()).all()]


@router.post("/admin/connections")
def create_connection(body: ConnectionBody, _: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    if body.type not in TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "type must be 'ollama' or 'openai'")
    conn = Connection(
        type=body.type,
        name=body.name.strip(),
        base_url=_clean_url(body.base_url),
        api_key=encrypt(body.api_key.strip()) if body.api_key else None,
        enabled=body.enabled,
        prefix_id=(body.prefix_id or "").strip() or None,
        model_ids=[m.strip() for m in body.model_ids if m.strip()],
    )
    db.add(conn)
    db.commit()
    invalidate_cache()
    return serialize(conn)


@router.patch("/admin/connections/{conn_id}")
def update_connection(
    conn_id: str, body: ConnectionPatch, _: User = Depends(get_admin_user), db: Session = Depends(get_db)
):
    conn = db.get(Connection, conn_id)
    if conn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    if body.name is not None:
        conn.name = body.name.strip() or conn.name
    if body.base_url is not None:
        conn.base_url = _clean_url(body.base_url)
    if body.api_key is not None:
        conn.api_key = encrypt(body.api_key.strip()) if body.api_key.strip() else None
    if body.enabled is not None:
        conn.enabled = body.enabled
    if body.prefix_id is not None:
        conn.prefix_id = body.prefix_id.strip() or None
    if body.model_ids is not None:
        conn.model_ids = [m.strip() for m in body.model_ids if m.strip()]
    db.commit()
    invalidate_cache()
    return serialize(conn)


@router.delete("/admin/connections/{conn_id}")
def delete_connection(conn_id: str, _: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    conn = db.get(Connection, conn_id)
    if conn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    db.delete(conn)
    db.commit()
    invalidate_cache()
    return {"ok": True}


@router.post("/admin/connections/verify")
async def verify_connection(body: VerifyBody, _: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    if body.type not in TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "type must be 'ollama' or 'openai'")
    api_key = body.api_key
    if not api_key and body.connection_id:
        existing = db.get(Connection, body.connection_id)
        if existing:
            api_key = connection_info(existing).api_key
    info = ConnectionInfo(id="verify", type=body.type, name="verify", base_url=_clean_url(body.base_url), api_key=api_key)
    try:
        models = await make_provider(info).list_models()
    except ProviderError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, e.message) from e
    return {"ok": True, "models": [m.id for m in models]}
