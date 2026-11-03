"""Shared helpers for locally cloned repositories."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Repository, User
from ..security import decrypt
from . import git

GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def user_token(user: User) -> str | None:
    return decrypt(user.github_token)


def author_for(user: User) -> dict[str, str]:
    gh = user.github_profile or {}
    if user.github_token and gh.get("login"):
        name = gh.get("name") or gh["login"]
        email = gh.get("email") or f"{gh.get('id')}+{gh['login']}@users.noreply.github.com"
    else:
        name, email = user.name, user.email
    return git.author_env(name, email)


def parse_full_name(value: str) -> str:
    """Accept 'owner/repo', 'https://github.com/owner/repo(.git)' or 'git@github.com:owner/repo.git'."""
    v = value.strip()
    base = get_settings().github_url
    host = re.sub(r"^https?://", "", base)
    v = re.sub(rf"^(https?://)?(www\.)?{re.escape(host)}/", "", v)
    v = re.sub(rf"^git@{re.escape(host)}:", "", v)
    v = v.removesuffix("/").removesuffix(".git")
    if not GITHUB_NAME_RE.match(v) or ".." in v:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Use the form owner/repo or a GitHub URL")
    return v


def full_name_from_remote(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return parse_full_name(url)
    except HTTPException:
        return None


def clone_url(full_name: str) -> str:
    return f"{get_settings().github_url}/{full_name}.git"


def clone_path(db: Session, full_name: str, user: User) -> Path:
    """REPO_DIR/<owner>/<repo>; suffixed with the user's name if another user already owns that folder."""
    owner, name = full_name.split("/", 1)
    root = get_settings().repo_dir
    path = root / owner / name
    existing = db.query(Repository).filter(Repository.path == str(path)).first()
    if existing and existing.user_id != user.id:
        slug = re.sub(r"[^a-z0-9]+", "-", user.name.lower()).strip("-") or user.id[:8]
        path = root / owner / f"{name}-{slug}"
    return path


def get_repo(db: Session, repo_id: str, user: User) -> Repository:
    repo = db.get(Repository, repo_id)
    if repo is None or (repo.user_id != user.id and user.role != "admin"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    if not (Path(repo.path) / ".git").exists():
        raise HTTPException(status.HTTP_410_GONE, f"The folder {repo.path} is missing or no longer a git repository")
    return repo


async def verify_origin(repo: Repository) -> None:
    """Refuse to send the token anywhere but the repository we cloned."""
    if repo.source != "github":
        return
    url = await git.remote_url(repo.path)
    if full_name_from_remote(url) != repo.full_name:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"The 'origin' remote ({url}) doesn't match {repo.full_name}; refusing to use your GitHub token.",
        )


def scan_local(db: Session, admin: User) -> None:
    """Register git repositories that were placed in REPO_DIR by hand (depth 1 or 2)."""
    root = get_settings().repo_dir
    known = {r.path for r in db.query(Repository).all()}
    candidates: list[Path] = []
    for first in sorted(root.iterdir()) if root.exists() else []:
        if not first.is_dir() or first.name.startswith("."):
            continue
        if (first / ".git").exists():
            candidates.append(first)
            continue
        for second in sorted(first.iterdir()):
            if second.is_dir() and (second / ".git").exists():
                candidates.append(second)
    added = False
    for path in candidates:
        if str(path) in known:
            continue
        rel = path.relative_to(root).as_posix()
        db.add(Repository(user_id=admin.id, full_name=rel, path=str(path), source="local", default_branch="main"))
        added = True
    if added:
        db.commit()


def serialize(repo: Repository, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": repo.id,
        "full_name": repo.full_name,
        "path": repo.path,
        "default_branch": repo.default_branch,
        "html_url": repo.html_url,
        "private": repo.private,
        "source": repo.source,
        "user_id": repo.user_id,
        "created_at": repo.created_at,
        "last_pulled_at": repo.last_pulled_at,
        **(extra or {}),
    }
