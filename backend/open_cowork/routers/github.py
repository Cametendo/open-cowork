"""GitHub connection, repository cloning and git operations."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..app_config import get_config
from ..config import get_settings
from ..cowork.workspaces import is_inside
from ..db import get_db, now
from ..deps import get_verified_user
from ..github import git
from ..github.client import GitHubClient, GitHubError
from ..github.repos import (
    author_for,
    clone_path,
    clone_url,
    full_name_from_remote,
    get_repo,
    parse_full_name,
    scan_local,
    serialize,
    user_token,
    verify_origin,
)
from ..github.sessions import repo_busy
from ..models import Repository, User
from ..security import encrypt

router = APIRouter(prefix="/api", tags=["github"])


def get_github_user(user: User = Depends(get_verified_user), db: Session = Depends(get_db)) -> User:
    if user.role != "admin" and not get_config(db)["github_enabled"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The GitHub integration is disabled by the administrator")
    return user


def _gh_error(e: GitHubError) -> HTTPException:
    code = e.status if e.status in (401, 403, 404, 422) else 502
    return HTTPException(code if code != 401 else 400, e.message)


def _git_error(e: git.GitError) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, e.message)


class TokenBody(BaseModel):
    token: str = Field(min_length=10, max_length=500)


class CloneBody(BaseModel):
    repo: str  # owner/name or URL
    branch: str | None = None


class CheckoutBody(BaseModel):
    branch: str
    create: bool = False


class CommitBody(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


class PullRequestBody(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    body: str = ""
    base: str | None = None
    draft: bool = False


# ----------------------------------------------------------------------------- account


@router.get("/github/status")
def github_status(user: User = Depends(get_github_user)):
    gh = user.github_profile or {}
    return {
        "connected": bool(user.github_token),
        "login": gh.get("login") if user.github_token else None,
        "name": gh.get("name") if user.github_token else None,
        "avatar_url": gh.get("avatar_url") if user.github_token else None,
        "html_url": gh.get("html_url") if user.github_token else None,
        "scopes": gh.get("scopes") if user.github_token else None,
        "repo_dir": str(get_settings().repo_dir),
    }


@router.put("/github/token")
async def set_token(body: TokenBody, user: User = Depends(get_github_user), db: Session = Depends(get_db)):
    token = body.token.strip()
    try:
        profile = await GitHubClient(token).user()
    except GitHubError as e:
        raise _gh_error(e) from e
    user.github_token = encrypt(token)
    user.github_profile = profile
    db.commit()
    return github_status(user)


@router.delete("/github/token")
def delete_token(user: User = Depends(get_github_user), db: Session = Depends(get_db)):
    user.github_token = None
    user.github_profile = None
    db.commit()
    return {"ok": True}


@router.get("/github/repos")
async def remote_repos(q: str | None = None, user: User = Depends(get_github_user), db: Session = Depends(get_db)):
    token = user_token(user)
    if not token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Connect your GitHub account first")
    try:
        items = await GitHubClient(token).repos(q)
    except GitHubError as e:
        raise _gh_error(e) from e
    local = {r.full_name: r.id for r in db.query(Repository).filter(Repository.user_id == user.id).all()}
    return [{**r, "local_id": local.get(r["full_name"])} for r in items]


# ----------------------------------------------------------------------------- local repos


@router.get("/repos")
async def list_repos(user: User = Depends(get_github_user), db: Session = Depends(get_db)):
    if user.role == "admin":
        scan_local(db, user)
        rows = db.query(Repository).order_by(Repository.created_at.desc()).all()
    else:
        rows = db.query(Repository).filter(Repository.user_id == user.id).order_by(Repository.created_at.desc()).all()
    out = []
    for r in rows:
        exists = (Path(r.path) / ".git").exists()
        branch = await git.current_branch(r.path) if exists else None
        out.append(serialize(r, {"exists": exists, "current_branch": branch, "busy": repo_busy(db, r.id)}))
    return out


@router.post("/repos/clone")
async def clone_repo(body: CloneBody, user: User = Depends(get_github_user), db: Session = Depends(get_db)):
    full_name = parse_full_name(body.repo)
    if body.branch and not git.valid_branch(body.branch):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid branch name")
    token = user_token(user)
    info = None
    try:
        info = await GitHubClient(token).repo(full_name)
        full_name = info["full_name"]
    except GitHubError as e:
        if e.status in (401, 403, 404) and not token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{full_name} was not found. For private repositories, connect GitHub first.") from e
        if e.status == 404:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{full_name} was not found or you don't have access") from e

    path = clone_path(db, full_name, user)
    existing = db.query(Repository).filter(Repository.path == str(path)).first()
    if existing:
        return serialize(existing, {"exists": True, "already_cloned": True})
    if path.exists() and any(path.iterdir()):
        if (path / ".git").exists() and full_name_from_remote(await git.remote_url(path)) == full_name:
            pass  # adopt the existing clone
        else:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{path} already exists and is not a clone of {full_name}")
    else:
        try:
            await git.clone(clone_url(full_name), path, token, body.branch)
        except git.GitError as e:
            shutil.rmtree(path, ignore_errors=True)
            raise _git_error(e) from e

    repo = Repository(
        user_id=user.id,
        full_name=full_name,
        path=str(path),
        default_branch=(info or {}).get("default_branch") or await git.current_branch(path) or "main",
        html_url=(info or {}).get("html_url") or f"{get_settings().github_url}/{full_name}",
        private=bool((info or {}).get("private")),
        source="github",
        last_pulled_at=now(),
    )
    db.add(repo)
    db.commit()
    return serialize(repo, {"exists": True, "current_branch": await git.current_branch(path)})


@router.delete("/repos/{repo_id}")
async def remove_repo(
    repo_id: str, delete_files: bool = False, user: User = Depends(get_github_user), db: Session = Depends(get_db)
):
    repo = db.get(Repository, repo_id)
    if repo is None or (repo.user_id != user.id and user.role != "admin"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    if repo_busy(db, repo.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "A task is running in this repository")
    path = Path(repo.path)
    root = get_settings().repo_dir
    if delete_files and is_inside(path, root) and path.resolve() != root.resolve():
        shutil.rmtree(path, ignore_errors=True)
    db.delete(repo)
    db.commit()
    return {"ok": True}


@router.get("/repos/{repo_id}/status")
async def repo_status(repo_id: str, user: User = Depends(get_github_user), db: Session = Depends(get_db)):
    repo = get_repo(db, repo_id, user)
    try:
        st = await git.status(repo.path)
    except git.GitError as e:
        raise _git_error(e) from e
    return {**st, "repo": serialize(repo), "busy": repo_busy(db, repo.id)}


@router.get("/repos/{repo_id}/changes")
async def repo_changes(repo_id: str, user: User = Depends(get_github_user), db: Session = Depends(get_db)):
    repo = get_repo(db, repo_id, user)
    try:
        return {"files": await git.changes(repo.path)}
    except git.GitError as e:
        raise _git_error(e) from e


@router.get("/repos/{repo_id}/branches")
async def repo_branches(repo_id: str, user: User = Depends(get_github_user), db: Session = Depends(get_db)):
    repo = get_repo(db, repo_id, user)
    return await git.branches(repo.path)


@router.post("/repos/{repo_id}/checkout")
async def repo_checkout(repo_id: str, body: CheckoutBody, user: User = Depends(get_github_user), db: Session = Depends(get_db)):
    repo = get_repo(db, repo_id, user)
    if repo_busy(db, repo.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "A task is running in this repository")
    try:
        async with git.repo_lock(repo.path):
            await git.checkout(repo.path, body.branch.strip(), create=body.create)
    except git.GitError as e:
        raise _git_error(e) from e
    return await git.status(repo.path)


@router.post("/repos/{repo_id}/pull")
async def repo_pull(repo_id: str, user: User = Depends(get_github_user), db: Session = Depends(get_db)):
    repo = get_repo(db, repo_id, user)
    if repo.source == "github":
        await verify_origin(repo)
    try:
        async with git.repo_lock(repo.path):
            msg = await git.pull(repo.path, user_token(user) if repo.source == "github" else None)
    except git.GitError as e:
        raise _git_error(e) from e
    repo.last_pulled_at = now()
    db.commit()
    return {"message": msg, "status": await git.status(repo.path)}


@router.post("/repos/{repo_id}/commit")
async def repo_commit(repo_id: str, body: CommitBody, user: User = Depends(get_github_user), db: Session = Depends(get_db)):
    repo = get_repo(db, repo_id, user)
    try:
        async with git.repo_lock(repo.path):
            sha = await git.commit_all(repo.path, body.message.strip(), author_for(user))
    except git.GitError as e:
        raise _git_error(e) from e
    return {"sha": sha, "status": await git.status(repo.path)}


@router.post("/repos/{repo_id}/push")
async def repo_push(repo_id: str, user: User = Depends(get_github_user), db: Session = Depends(get_db)):
    repo = get_repo(db, repo_id, user)
    token = user_token(user)
    if repo.source == "github":
        if not token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Connect your GitHub account to push")
        await verify_origin(repo)
    try:
        async with git.repo_lock(repo.path):
            out = await git.push(repo.path, token if repo.source == "github" else None)
    except git.GitError as e:
        raise _git_error(e) from e
    return {"message": out, "status": await git.status(repo.path)}


@router.get("/repos/{repo_id}/pull-request")
async def find_pull_request(repo_id: str, user: User = Depends(get_github_user), db: Session = Depends(get_db)):
    repo = get_repo(db, repo_id, user)
    token = user_token(user)
    branch = await git.current_branch(repo.path)
    if repo.source != "github" or not token or not branch:
        return {"pull_request": None}
    try:
        return {"pull_request": await GitHubClient(token).find_pull(repo.full_name, branch)}
    except GitHubError:
        return {"pull_request": None}


@router.post("/repos/{repo_id}/pull-request")
async def create_pull_request(
    repo_id: str, body: PullRequestBody, user: User = Depends(get_github_user), db: Session = Depends(get_db)
):
    repo = get_repo(db, repo_id, user)
    token = user_token(user)
    if repo.source != "github":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pull requests need a repository cloned from GitHub")
    if not token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Connect your GitHub account first")
    await verify_origin(repo)
    branch = await git.current_branch(repo.path)
    base = body.base or repo.default_branch
    if not branch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not on a branch")
    if branch == base:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"You're on the base branch '{base}'. Create a branch for your changes first.")
    try:
        async with git.repo_lock(repo.path):
            await git.push(repo.path, token)
    except git.GitError as e:
        raise _git_error(e) from e
    client = GitHubClient(token)
    try:
        pr = await client.create_pull(repo.full_name, title=body.title, body=body.body, head=branch, base=base, draft=body.draft)
    except GitHubError as e:
        if e.status == 422 and "already exists" in e.message:
            existing = await client.find_pull(repo.full_name, branch)
            if existing:
                return {"pull_request": existing, "existing": True}
        raise _gh_error(e) from e
    return {"pull_request": pr, "existing": False}
