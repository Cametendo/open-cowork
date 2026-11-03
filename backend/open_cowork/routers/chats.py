"""Regular chat conversations (the "Chat" tab).

Messages are persisted server-side, so a reply keeps being generated and saved
even if the browser tab is closed mid-stream.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..app_config import get_config
from ..db import SessionLocal, get_db, new_id, now
from ..deps import get_verified_user
from ..models import Chat, User
from ..providers import ProviderError, resolve_model
from ..sse import sse, sse_response

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chats", tags=["chats"])

DEFAULT_TITLE = "New Chat"


class CreateChatBody(BaseModel):
    title: str | None = None
    model: str | None = None
    params: dict[str, Any] | None = None


class UpdateChatBody(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    pinned: bool | None = None
    model: str | None = None
    params: dict[str, Any] | None = None


class SendBody(BaseModel):
    model: str
    content: str | None = None
    images: list[str] | None = None  # base64 (no data: prefix), for vision models
    regenerate: bool = False
    edit_message_id: str | None = None


def summary(chat: Chat) -> dict[str, Any]:
    return {
        "id": chat.id,
        "title": chat.title,
        "model": chat.model,
        "pinned": chat.pinned,
        "created_at": chat.created_at,
        "updated_at": chat.updated_at,
    }


def full(chat: Chat) -> dict[str, Any]:
    return {**summary(chat), "messages": chat.messages or [], "params": chat.params or {}}


def _get_chat(db: Session, chat_id: str, user: User) -> Chat:
    chat = db.get(Chat, chat_id)
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    return chat


@router.get("")
def list_chats(q: str | None = None, user: User = Depends(get_verified_user), db: Session = Depends(get_db)):
    query = db.query(Chat).filter(Chat.user_id == user.id)
    if q:
        query = query.filter(Chat.title.ilike(f"%{q}%"))
    return [summary(c) for c in query.order_by(Chat.updated_at.desc()).limit(500).all()]


@router.post("")
def create_chat(body: CreateChatBody, user: User = Depends(get_verified_user), db: Session = Depends(get_db)):
    chat = Chat(user_id=user.id, title=(body.title or DEFAULT_TITLE)[:512], model=body.model, params=body.params or {})
    db.add(chat)
    db.commit()
    return full(chat)


@router.get("/{chat_id}")
def get_chat(chat_id: str, user: User = Depends(get_verified_user), db: Session = Depends(get_db)):
    return full(_get_chat(db, chat_id, user))


@router.patch("/{chat_id}")
def update_chat(chat_id: str, body: UpdateChatBody, user: User = Depends(get_verified_user), db: Session = Depends(get_db)):
    chat = _get_chat(db, chat_id, user)
    if body.title is not None:
        chat.title = body.title.strip() or DEFAULT_TITLE
    if body.pinned is not None:
        chat.pinned = body.pinned
    if body.model is not None:
        chat.model = body.model
    if body.params is not None:
        chat.params = {k: v for k, v in body.params.items() if k in ("system", "temperature", "max_tokens", "num_ctx")}
    db.commit()
    return full(chat)


@router.delete("/{chat_id}")
def delete_chat(chat_id: str, user: User = Depends(get_verified_user), db: Session = Depends(get_db)):
    db.delete(_get_chat(db, chat_id, user))
    db.commit()
    return {"ok": True}


@router.delete("")
def delete_all_chats(user: User = Depends(get_verified_user), db: Session = Depends(get_db)):
    db.query(Chat).filter(Chat.user_id == user.id).delete()
    db.commit()
    return {"ok": True}


def _provider_messages(chat: Chat, user: User, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    params = chat.params or {}
    system = (params.get("system") or (user.settings or {}).get("system_prompt") or "").strip()
    out: list[dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in history:
        if m.get("role") not in ("user", "assistant"):
            continue
        if m.get("role") == "assistant" and m.get("error") and not m.get("content"):
            continue
        msg: dict[str, Any] = {"role": m["role"], "content": m.get("content") or ""}
        if m.get("images"):
            msg["images"] = m["images"]
        out.append(msg)
    return out


_THINK_RE = re.compile(r"<think>.*?(</think>|$)", re.S)


def _clean_title(text: str) -> str:
    text = _THINK_RE.sub("", text).strip().splitlines()[0] if text.strip() else ""
    text = text.strip().strip("\"'`*#").strip()
    text = re.sub(r"^(title:\s*)", "", text, flags=re.I)
    return text[:80]


async def _generate_title(provider, model: str, first_user: str, answer: str) -> str | None:
    prompt = (
        "Write a concise title (3-6 words) that summarizes this conversation. "
        "Reply with the title only — no quotes, no punctuation at the end.\n\n"
        f"User: {first_user[:1500]}\nAssistant: {answer[:1500]}"
    )
    try:
        text = await asyncio.wait_for(
            provider.complete(model, [{"role": "user", "content": prompt}], options={"temperature": 0.2, "max_tokens": 32}),
            timeout=30,
        )
    except Exception as e:  # noqa: BLE001
        log.info("Title generation failed: %s", e)
        return None
    return _clean_title(text) or None


@router.post("/{chat_id}/messages")
async def send_message(chat_id: str, body: SendBody, user: User = Depends(get_verified_user)):
    # Validate and prepare synchronously, before the stream starts
    with SessionLocal() as db:
        chat = _get_chat(db, chat_id, user)
        messages: list[dict[str, Any]] = list(chat.messages or [])

        if body.regenerate:
            while messages and messages[-1].get("role") == "assistant":
                messages.pop()
            if not messages:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to regenerate")
        elif body.edit_message_id:
            idx = next((i for i, m in enumerate(messages) if m.get("id") == body.edit_message_id), None)
            if idx is None or messages[idx].get("role") != "user":
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
            edited = {**messages[idx], "content": body.content or ""}
            messages = [*messages[:idx], edited]
        else:
            if not (body.content or "").strip() and not body.images:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message is empty")
            user_msg: dict[str, Any] = {"id": new_id(), "role": "user", "content": body.content or "", "created_at": now()}
            if body.images:
                user_msg["images"] = body.images
            messages.append(user_msg)

        try:
            provider, raw_model = await resolve_model(db, body.model)
        except ProviderError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, e.message) from e

        assistant: dict[str, Any] = {
            "id": new_id(),
            "role": "assistant",
            "content": "",
            "model": body.model,
            "created_at": now(),
        }
        provider_messages = _provider_messages(chat, user, messages)
        chat.messages = [*messages, assistant]
        chat.model = body.model
        chat.updated_at = now()
        db.commit()
        options = {k: v for k, v in (chat.params or {}).items() if k in ("temperature", "max_tokens", "num_ctx")}
        needs_title = chat.title == DEFAULT_TITLE and get_config(db)["enable_title_generation"]
        first_user = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")

    def persist(final: dict[str, Any]) -> None:
        with SessionLocal() as db2:
            c = db2.get(Chat, chat_id)
            if c is None:
                return
            msgs = list(c.messages or [])
            for i, m in enumerate(msgs):
                if m.get("id") == final["id"]:
                    msgs[i] = final
                    break
            c.messages = msgs
            c.updated_at = now()
            db2.commit()

    async def stream():
        content: list[str] = []
        reasoning: list[str] = []
        final = dict(assistant)
        yield sse({"type": "start", "message": assistant, "user_message": messages[-1]})
        try:
            async for ev in provider.stream_chat(raw_model, provider_messages, options=options):
                if ev["type"] == "content":
                    content.append(ev["text"])
                    yield sse({"type": "delta", "text": ev["text"]})
                elif ev["type"] == "reasoning":
                    reasoning.append(ev["text"])
                    yield sse({"type": "reasoning", "text": ev["text"]})
                elif ev["type"] == "done" and ev.get("usage"):
                    final["usage"] = ev["usage"]
            final["content"] = "".join(content)
            if reasoning:
                final["reasoning"] = "".join(reasoning)
            persist(final)
            yield sse({"type": "done", "message": final})
            if needs_title and final["content"]:
                title = await _generate_title(provider, raw_model, first_user, final["content"])
                if title:
                    with SessionLocal() as db3:
                        c = db3.get(Chat, chat_id)
                        if c is not None and c.title == DEFAULT_TITLE:
                            c.title = title
                            db3.commit()
                    yield sse({"type": "title", "title": title})
        except ProviderError as e:
            final.update(content="".join(content), error=e.message)
            if reasoning:
                final["reasoning"] = "".join(reasoning)
            persist(final)
            yield sse({"type": "error", "error": e.message, "message": final})
        except (asyncio.CancelledError, GeneratorExit):
            # Client disconnected / pressed stop: keep what we have
            final.update(content="".join(content), stopped=True)
            if reasoning:
                final["reasoning"] = "".join(reasoning)
            persist(final)
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("Chat completion failed")
            final.update(content="".join(content), error=str(e) or e.__class__.__name__)
            persist(final)
            yield sse({"type": "error", "error": final["error"], "message": final})

    return sse_response(stream())
