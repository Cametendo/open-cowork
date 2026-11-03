"""The Cowork tab: agentic tasks that work inside a workspace folder."""

from __future__ import annotations

import asyncio
import mimetypes
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..app_config import get_config
from ..config import get_settings
from ..cowork.runner import manager
from ..cowork.tools import IGNORED_DIRS, ToolError, Workspace
from ..cowork.workspaces import is_inside, new_scratch_folder
from ..db import get_db, now
from ..deps import get_verified_user
from ..models import CoworkSession, Repository, User
from ..sse import sse, sse_response

router = APIRouter(prefix="/api/cowork", tags=["cowork"])

MAX_PREVIEW_BYTES = 1_000_000


def get_cowork_user(user: User = Depends(get_verified_user), db: Session = Depends(get_db)) -> User:
    if user.role != "admin" and not get_config(db)["cowork_enabled"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cowork is disabled by the administrator")
    return user


class WorkspaceSpec(BaseModel):
    type: str = "scratch"  # "scratch" | "repo"
    repo_id: str | None = None
    create_branch: bool = True
    branch: str | None = None


class CreateSessionBody(BaseModel):
    prompt: str = Field(min_length=1)
    model: str
    approval_mode: str = "ask"
    title: str | None = None
    workspace: WorkspaceSpec = WorkspaceSpec()


class UpdateSessionBody(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    model: str | None = None
    approval_mode: str | None = None


class MessageBody(BaseModel):
    content: str = Field(min_length=1)
    model: str | None = None


class ApprovalBody(BaseModel):
    tool_call_id: str
    approved: bool
    always: bool = False


def _repo_name(db: Session, s: CoworkSession) -> str | None:
    if not s.repo_id:
        return None
    repo = db.get(Repository, s.repo_id)
    return repo.full_name if repo else None


def summary(db: Session, s: CoworkSession) -> dict[str, Any]:
    return {
        "id": s.id,
        "title": s.title,
        "model": s.model,
        "status": "running" if manager.active(s.id) else ("error" if s.status == "error" else "idle"),
        "workspace_type": s.workspace_type,
        "workspace_path": s.workspace_path,
        "repo_id": s.repo_id,
        "repo_name": _repo_name(db, s),
        "branch": s.branch,
        "base_branch": s.base_branch,
        "approval_mode": s.approval_mode,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


def full(db: Session, s: CoworkSession) -> dict[str, Any]:
    run = manager.get(s.id)
    messages = list(s.messages or [])
    run_info = None
    if run is not None:
        # The live run is replayed from its event stream; send only what came before it.
        messages = messages[: run.start_index]
        run_info = {"id": run.id, "done": run.done}
    return {
        **summary(db, s),
        "messages": messages,
        "plan": s.plan or [],
        "last_error": s.last_error,
        "run": run_info,
    }


def get_session(db: Session, session_id: str, user: User) -> CoworkSession:
    s = db.get(CoworkSession, session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return s


def workspace_of(s: CoworkSession) -> Workspace:
    root = Path(s.workspace_path)
    if not root.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The workspace folder no longer exists")
    return Workspace(root=root)


def _resolve(ws: Workspace, path: str | None) -> Path:
    try:
        return ws.resolve(path)
    except ToolError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.get("/sessions")
def list_sessions(user: User = Depends(get_cowork_user), db: Session = Depends(get_db)):
    rows = (
        db.query(CoworkSession)
        .filter(CoworkSession.user_id == user.id)
        .order_by(CoworkSession.updated_at.desc())
        .limit(300)
        .all()
    )
    return [summary(db, s) for s in rows]


@router.post("/sessions")
async def create_session(body: CreateSessionBody, user: User = Depends(get_cowork_user), db: Session = Depends(get_db)):
    if body.approval_mode not in ("ask", "auto"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "approval_mode must be 'ask' or 'auto'")
    title = (body.title or body.prompt.strip().splitlines()[0])[:80]
    s = CoworkSession(user_id=user.id, title=title, model=body.model, approval_mode=body.approval_mode)

    if body.workspace.type == "scratch":
        s.workspace_type = "scratch"
        s.workspace_path = str(new_scratch_folder(title))
    elif body.workspace.type == "repo":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Repository workspaces are not available yet")
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown workspace type")

    db.add(s)
    db.commit()
    manager.start(s.id, user.id, body.prompt)
    return full(db, s)


@router.get("/sessions/{session_id}")
def read_session(session_id: str, user: User = Depends(get_cowork_user), db: Session = Depends(get_db)):
    return full(db, get_session(db, session_id, user))


@router.patch("/sessions/{session_id}")
def update_session(
    session_id: str, body: UpdateSessionBody, user: User = Depends(get_cowork_user), db: Session = Depends(get_db)
):
    s = get_session(db, session_id, user)
    if body.title is not None:
        s.title = body.title.strip() or s.title
    if body.model is not None:
        s.model = body.model
    if body.approval_mode is not None:
        if body.approval_mode not in ("ask", "auto"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "approval_mode must be 'ask' or 'auto'")
        if manager.active(s.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "Can't change approval mode while a task is running")
        s.approval_mode = body.approval_mode
    s.updated_at = now()
    db.commit()
    return summary(db, s)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    delete_files: bool = False,
    user: User = Depends(get_cowork_user),
    db: Session = Depends(get_db),
):
    s = get_session(db, session_id, user)
    await manager.cancel(s.id)
    path = Path(s.workspace_path)
    if delete_files and s.workspace_type == "scratch" and is_inside(path, get_settings().workspace_dir):
        if path.resolve() != get_settings().workspace_dir.resolve():
            shutil.rmtree(path, ignore_errors=True)
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str, body: MessageBody, user: User = Depends(get_cowork_user), db: Session = Depends(get_db)
):
    s = get_session(db, session_id, user)
    if manager.active(s.id):
        msg = manager.add_input(s.id, body.content)
        return {"queued": True, "message": msg}
    if body.model and body.model != s.model:
        s.model = body.model
        db.commit()
    run = manager.start(s.id, user.id, body.content)
    return {"queued": False, "run": {"id": run.id, "done": False}}


@router.get("/sessions/{session_id}/stream")
async def stream(session_id: str, after: int = -1, user: User = Depends(get_cowork_user), db: Session = Depends(get_db)):
    get_session(db, session_id, user)
    db.close()
    run = manager.get(session_id)

    async def gen():
        if run is None:
            yield sse({"type": "idle"})
            return
        agen = run.subscribe(after)
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(agen.__anext__(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                except StopAsyncIteration:
                    return
                yield sse(ev)
        finally:
            await agen.aclose()

    return sse_response(gen())


@router.post("/sessions/{session_id}/cancel")
async def cancel(session_id: str, user: User = Depends(get_cowork_user), db: Session = Depends(get_db)):
    get_session(db, session_id, user)
    return {"cancelled": await manager.cancel(session_id)}


@router.post("/sessions/{session_id}/approve")
async def approve(session_id: str, body: ApprovalBody, user: User = Depends(get_cowork_user), db: Session = Depends(get_db)):
    get_session(db, session_id, user)
    if not manager.resolve_approval(session_id, body.tool_call_id, body.approved, body.always):
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for approval")
    return {"ok": True}


# ----------------------------------------------------------------------------- files


@router.get("/sessions/{session_id}/files")
def list_dir(session_id: str, path: str = ".", user: User = Depends(get_cowork_user), db: Session = Depends(get_db)):
    ws = workspace_of(get_session(db, session_id, user))
    target = _resolve(ws, path)
    if not target.is_dir():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a directory")
    entries = []
    for e in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if e.name == ".git":
            continue
        try:
            st = e.stat()
        except OSError:
            continue
        entries.append(
            {
                "name": e.name,
                "path": ws.rel(e),
                "type": "dir" if e.is_dir() else "file",
                "size": st.st_size if e.is_file() else None,
                "modified": int(st.st_mtime),
                "ignored": e.is_dir() and e.name in IGNORED_DIRS,
            }
        )
    return {"path": ws.rel(target), "root": str(ws.root), "entries": entries}


@router.get("/sessions/{session_id}/file")
def read_file(session_id: str, path: str, user: User = Depends(get_cowork_user), db: Session = Depends(get_db)):
    ws = workspace_of(get_session(db, session_id, user))
    target = _resolve(ws, path)
    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    size = target.stat().st_size
    mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    with target.open("rb") as f:
        head = f.read(MAX_PREVIEW_BYTES)
    binary = b"\0" in head[:8192]
    return {
        "path": ws.rel(target),
        "size": size,
        "mime": mime,
        "binary": binary,
        "truncated": size > MAX_PREVIEW_BYTES,
        "content": None if binary else head.decode("utf-8", errors="replace"),
    }


@router.get("/sessions/{session_id}/download")
def download(session_id: str, path: str, user: User = Depends(get_cowork_user), db: Session = Depends(get_db)):
    ws = workspace_of(get_session(db, session_id, user))
    target = _resolve(ws, path)
    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return FileResponse(target, filename=target.name)


@router.post("/sessions/{session_id}/upload")
async def upload(
    session_id: str,
    files: list[UploadFile] = File(...),
    path: str = Form("."),
    user: User = Depends(get_cowork_user),
    db: Session = Depends(get_db),
):
    ws = workspace_of(get_session(db, session_id, user))
    folder = _resolve(ws, path)
    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        name = Path(f.filename or "upload").name
        dest = _resolve(ws, str((folder / name).relative_to(ws.root)))
        with dest.open("wb") as out:
            while chunk := await f.read(1024 * 1024):
                out.write(chunk)
        saved.append(ws.rel(dest))
    return {"saved": saved}
