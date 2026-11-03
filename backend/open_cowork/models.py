from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, new_id, now


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    # "admin" | "user" | "pending"
    role: Mapped[str] = mapped_column(String(16), default="pending")
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # GitHub personal access token, encrypted at rest (see security.encrypt)
    github_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    last_active_at: Mapped[int] = mapped_column(Integer, default=now)

    def public(self) -> dict[str, Any]:
        gh = self.github_profile or {}
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
            "github_login": gh.get("login") if self.github_token else None,
        }


class ConfigEntry(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[int] = mapped_column(Integer, default=now, onupdate=now)


class Connection(Base):
    """A model provider endpoint: an Ollama server or an OpenAI-compatible API."""

    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # "ollama" | "openai"
    type: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(255))
    base_url: Mapped[str] = mapped_column(String(1024))
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Optional prefix to keep model ids unique across connections ("work.gpt-4o")
    prefix_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Optional allow-list of model ids. Empty means "all models".
    model_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(512), default="New Chat")
    model: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # [{id, role, content, model?, reasoning?, error?, created_at}]
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # {system?, temperature?, max_tokens?, num_ctx?}
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    updated_at: Mapped[int] = mapped_column(Integer, default=now, index=True)


class Repository(Base):
    """A git repository cloned into REPO_DIR."""

    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str] = mapped_column(String(512))
    path: Mapped[str] = mapped_column(String(2048), unique=True)
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    html_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    private: Mapped[bool] = mapped_column(Boolean, default=False)
    # "github" (cloned through the integration) | "local" (found on disk)
    source: Mapped[str] = mapped_column(String(16), default="github")
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    last_pulled_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CoworkSession(Base):
    """An agentic Cowork task: a conversation bound to a workspace folder."""

    __tablename__ = "cowork_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(512), default="New task")
    model: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # "scratch" | "repo"
    workspace_type: Mapped[str] = mapped_column(String(16), default="scratch")
    workspace_path: Mapped[str] = mapped_column(String(2048))
    repo_id: Mapped[str | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True
    )
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # "ask" (approve edits & commands) | "auto"
    approval_mode: Mapped[str] = mapped_column(String(16), default="ask")
    # OpenAI-style message list (user / assistant+tool_calls / tool)
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    plan: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # "idle" | "running" | "error"
    status: Mapped[str] = mapped_column(String(16), default="idle")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    updated_at: Mapped[int] = mapped_column(Integer, default=now, index=True)
