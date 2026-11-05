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
        # Web search (off until an admin turns it on: queries leave this server)
        "web_search_enabled": False,
        "web_search_engine": "duckduckgo",
        "web_search_url": "",  # SearXNG base URL
        "web_search_result_count": 5,
        "web_allow_private_hosts": False,  # let fetch_url reach localhost / LAN addresses
    }

WEB_SEARCH_ENGINES = ("duckduckgo", "searxng", "brave", "tavily")
# Stored encrypted under this config key; never returned by the API
WEB_SEARCH_KEY = "web_search_api_key"


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
    "web_search_enabled": bool,
    "web_search_engine": str,
    "web_search_url": str,
    "web_search_result_count": int,
    "web_allow_private_hosts": bool,
}


def get_config(db: Session) -> dict[str, Any]:
    cfg = defaults()
    for entry in db.query(ConfigEntry).all():
        if entry.key in cfg:
            cfg[entry.key] = entry.value
    cfg["web_search_has_key"] = bool(db.get(ConfigEntry, WEB_SEARCH_KEY))
    return cfg


def _set_web_search_key(db: Session, value: Any) -> None:
    from .security import encrypt

    if not isinstance(value, str):
        raise ValueError("Invalid value for web_search_api_key")
    value = value.strip()
    entry = db.get(ConfigEntry, WEB_SEARCH_KEY)
    if not value:  # empty string clears the key
        if entry is not None:
            db.delete(entry)
    elif entry is None:
        db.add(ConfigEntry(key=WEB_SEARCH_KEY, value=encrypt(value)))
    else:
        entry.value = encrypt(value)


def update_config(db: Session, updates: dict[str, Any]) -> dict[str, Any]:
    updates = dict(updates)
    updates.pop("web_search_has_key", None)  # read-only, echoed back by the GET
    if WEB_SEARCH_KEY in updates:
        _set_web_search_key(db, updates.pop(WEB_SEARCH_KEY))
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
        if key == "web_search_engine" and value not in WEB_SEARCH_ENGINES:
            raise ValueError(f"web_search_engine must be one of: {', '.join(WEB_SEARCH_ENGINES)}")
        if key == "web_search_result_count" and not 1 <= value <= 10:
            raise ValueError("web_search_result_count must be between 1 and 10")
        if key == "web_search_url":
            value = value.strip().rstrip("/")
            if value and not value.startswith(("http://", "https://")):
                raise ValueError("The SearXNG URL must start with http:// or https://")
        if key == "webui_name":
            value = value.strip() or get_settings().app_name
        entry = db.get(ConfigEntry, key)
        if entry is None:
            db.add(ConfigEntry(key=key, value=value))
        else:
            entry.value = value
    db.commit()
    return get_config(db)
