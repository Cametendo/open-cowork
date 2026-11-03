"""Workspace folders for Cowork sessions."""

from __future__ import annotations

import re
import secrets
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import CoworkSession, User


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return (slug[:max_len].rstrip("-")) or "task"


def new_scratch_folder(title: str) -> Path:
    """A fresh, human-readable folder under WORKSPACE_DIR, e.g. 2026-01-31-organize-receipts-3fa2."""
    root = get_settings().workspace_dir
    path = root / f"{date.today().isoformat()}-{slugify(title, 32)}-{secrets.token_hex(2)}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def is_inside(path: Path, root: Path) -> bool:
    path, root = path.resolve(), root.resolve()
    return path == root or root in path.parents


async def prepare_workspace(db: Session, session: CoworkSession, user: User) -> tuple[dict[str, str], dict[str, Any] | None]:
    """Get the workspace ready before a run.

    Returns extra environment variables for commands and, for repository
    workspaces, repo info for the system prompt.
    """
    Path(session.workspace_path).mkdir(parents=True, exist_ok=True)
    return {}, None
