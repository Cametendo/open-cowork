"""Runtime configuration persisted in the database and editable by admins."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .config import get_settings
from .models import ConfigEntry

ROLES = ("admin", "user", "pending")


def defaults() -> dict[str, Any]:
    s = get_settings()
    return {
        "webui_name": s.app_name,
        "enable_signup": s.seed_enable_signup,
        "default_user_role": s.seed_default_user_role
        if s.seed_default_user_role in ("user", "pending")
        else "pending",
        # Chat
        "enable_title_generation": True,
        # Cowork
        "cowork_enabled": True,  # for non-admin users; admins always have access
        "cowork_allow_shell": s.seed_cowork_allow_shell,
        "cowork_command_timeout": 120,
        "cowork_max_steps": 40,
        # num_ctx sent to Ollama for Cowork runs (agents need room for tool output)
        "cowork_ollama_num_ctx": 16384,
        # GitHub integration
        "github_enabled": True,
    }


# Allowed value types for validation of admin updates
_TYPES: dict[str, type] = {
    "webui_name": str,
    "enable_signup": bool,
    "default_user_role": str,
    "enable_title_generation": bool,
    "cowork_enabled": bool,
    "cowork_allow_shell": bool,
    "cowork_command_timeout": int,
    "cowork_max_steps": int,
    "cowork_ollama_num_ctx": int,
    "github_enabled": bool,
}


def get_config(db: Session) -> dict[str, Any]:
    cfg = defaults()
    for entry in db.query(ConfigEntry).all():
        if entry.key in cfg:
            cfg[entry.key] = entry.value
    return cfg


def update_config(db: Session, updates: dict[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        expected = _TYPES.get(key)
        if expected is None:
            raise ValueError(f"Unknown setting: {key}")
        if expected is int and isinstance(value, bool):
            raise ValueError(f"Invalid value for {key}")
        if not isinstance(value, expected):
            raise ValueError(f"Invalid value for {key}")
        if key == "default_user_role" and value not in ("user", "pending"):
            raise ValueError("default_user_role must be 'user' or 'pending'")
        if key in {"cowork_command_timeout", "cowork_max_steps"} and value < 1:
            raise ValueError(f"{key} must be positive")
        if key == "cowork_ollama_num_ctx" and value < 0:
            raise ValueError(f"{key} must be >= 0")
        if key == "webui_name":
            value = value.strip() or get_settings().app_name
        entry = db.get(ConfigEntry, key)
        if entry is None:
            db.add(ConfigEntry(key=key, value=value))
        else:
            entry.value = value
    db.commit()
    return get_config(db)
