"""Cowork sessions that work inside a cloned repository, each on its own branch."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..cowork.runner import manager
from ..cowork.workspaces import slugify
from ..db import now
from ..models import CoworkSession, Repository, User
from . import git
from .repos import get_repo, user_token, verify_origin

log = logging.getLogger(__name__)


def repo_busy(db: Session, repo_id: str, exclude_session: str | None = None) -> bool:
    ids = [
        sid
        for (sid,) in db.query(CoworkSession.id).filter(CoworkSession.repo_id == repo_id).all()
        if sid != exclude_session
    ]
    return any(manager.active(sid) for sid in ids)


async def setup_repo_session(db: Session, s: CoworkSession, user: User, spec: Any) -> list[str]:
    """Pull the latest base branch and create a fresh working branch for the task.

    Returns human-readable notes about what happened (shown in the UI).
    """
    if not spec.repo_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "repo_id is required")
    repo = get_repo(db, spec.repo_id, user)
    if repo_busy(db, repo.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Another task is already running in this repository")
    notes: list[str] = []
    path = repo.path
    try:
        async with git.repo_lock(path):
            st = await git.status(path)
            base = spec.branch or st["branch"] or repo.default_branch
            if st["clean"]:
                if base != st["branch"]:
                    await git.checkout(path, base)
                if repo.source == "github":
                    try:
                        await verify_origin(repo)
                        msg = await git.pull(path, user_token(user))
                        repo.last_pulled_at = now()
                        notes.append(f"Pulled latest '{base}': {msg.splitlines()[-1] if msg else 'up to date'}")
                    except (git.GitError, HTTPException) as e:
                        detail = e.message if isinstance(e, git.GitError) else e.detail
                        notes.append(f"Could not pull '{base}': {detail}")
            else:
                notes.append(f"Working tree has uncommitted changes on '{st['branch']}'; they carry over to the task branch.")
                base = st["branch"] or base
            branch = st["branch"]
            if spec.create_branch:
                branch = f"cowork/{slugify(s.title, 32)}-{secrets.token_hex(2)}"
                await git.checkout(path, branch, create=True)
                notes.append(f"Created branch '{branch}' from '{base}'")
    except git.GitError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Git: {e.message}") from e

    s.workspace_type = "repo"
    s.workspace_path = path
    s.repo_id = repo.id
    s.branch = branch
    s.base_branch = base
    return notes


async def prepare_repo_workspace(db: Session, s: CoworkSession, user: User) -> dict[str, Any] | None:
    """Before each run: make sure the task's branch is checked out."""
    repo = db.get(Repository, s.repo_id) if s.repo_id else None
    if repo is None:
        return None
    if repo_busy(db, repo.id, exclude_session=s.id):
        raise LookupError("Another task is running in this repository. Wait for it to finish or stop it first.")
    if s.branch:
        async with git.repo_lock(repo.path):
            current = await git.current_branch(repo.path)
            if current != s.branch:
                st = await git.status(repo.path)
                if not st["clean"]:
                    raise LookupError(
                        f"The repository has uncommitted changes on '{current}'. Commit or discard them in the Git "
                        f"panel so this task can switch back to its branch '{s.branch}'."
                    )
                try:
                    await git.checkout(repo.path, s.branch)
                except git.GitError:
                    await git.checkout(repo.path, s.branch, create=True)
    return {"full_name": repo.full_name, "branch": s.branch or await git.current_branch(repo.path), "base_branch": s.base_branch}
