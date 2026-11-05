from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..app_config import get_config
from ..models import ConfigEntry
from ..security import decrypt

SECRET_KEY_NAME = "web_search_api_key"


@dataclass
class WebSettings:
    enabled: bool = False
    engine: str = "duckduckgo"
    url: str = ""  # SearXNG base URL
    api_key: str | None = None
    result_count: int = 5
    allow_private_hosts: bool = False


def load_web_settings(db: Session) -> WebSettings:
    cfg = get_config(db)
    entry = db.get(ConfigEntry, SECRET_KEY_NAME)
    return WebSettings(
        enabled=bool(cfg["web_search_enabled"]),
        engine=cfg["web_search_engine"],
        url=cfg["web_search_url"],
        api_key=decrypt(entry.value) if entry and entry.value else None,
        result_count=int(cfg["web_search_result_count"]),
        allow_private_hosts=bool(cfg["web_allow_private_hosts"]),
    )
