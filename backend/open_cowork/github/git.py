"""Async wrappers around the git CLI.

Hardening: repository hooks, fsmonitor and credential helpers are disabled for
every command the *server* runs (the agent may have written to .git/), the
environment is scrubbed of server secrets, and the GitHub token is passed via
GIT_CONFIG_* variables scoped to the GitHub host, so it is never written to
.git/config and never sent to any other host.
"""

from __future__ import annotations

import asyncio
import base64
import difflib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..cowork.tools import _ENV_ALLOW

SAFE_CONFIG = [
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.fsmonitor=false",
    "-c", "credential.helper=",
    "-c", "protocol.ext.allow=never",
    "-c", "color.ui=false",
]
BRANCH_RE = re.compile(r"^(?!/|-|.*\.\.|.*//|.*@\{|.*\.lock$|.*[\s~^:?*\[\\])[\w./-]{1,200}(?<![./])$")
MAX_FILE_DIFF = 60_000

_locks: dict[str, asyncio.Lock] = {}


def repo_lock(path: str | Path) -> asyncio.Lock:
    key = str(Path(path).resolve())
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


class GitError(Exception):
    def __init__(self, message: str, output: str = ""):
        super().__init__(message)
        self.message = message
        self.output = output


def _env(token: str | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOW or k.startswith("LC_")}
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "LC_ALL": "C.UTF-8", "GIT_ASKPASS": "true"})
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": f"http.{get_settings().github_url}/.extraheader",
                "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
            }
        )
    if extra:
        env.update(extra)
    return env


def _redact(text: str, token: str | None) -> str:
    if token:
        text = text.replace(token, "***")
    return re.sub(r"(https?://)[^/@\s]+@", r"\1***@", text)


async def run_git(
    args: list[str],
    cwd: str | Path | None,
    *,
    token: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 120,
    check: bool = True,
) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *SAFE_CONFIG,
        *args,
        cwd=str(cwd) if cwd else None,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=_env(token, env),
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise GitError(f"git {args[0]} timed out after {int(timeout)}s") from e
    text = _redact(out.decode("utf-8", errors="replace"), token)
    if check and proc.returncode != 0:
        lines = [ln for ln in text.strip().splitlines() if ln.strip()]
        msg = next((ln for ln in reversed(lines) if ln.startswith(("fatal:", "error:"))), lines[-1] if lines else "")
        raise GitError(msg.replace("fatal: ", "").replace("error: ", "") or f"git {args[0]} failed", text)
    return proc.returncode or 0, text


def valid_branch(name: str) -> bool:
    return bool(BRANCH_RE.match(name or ""))


# --------------------------------------------------------------------------- queries


async def current_branch(path: str | Path) -> str | None:
    code, out = await run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], path, check=False)
    return out.strip() if code == 0 else None


async def has_commits(path: str | Path) -> bool:
    code, _ = await run_git(["rev-parse", "--verify", "--quiet", "HEAD"], path, check=False)
    return code == 0


async def remote_url(path: str | Path, remote: str = "origin") -> str | None:
    code, out = await run_git(["remote", "get-url", remote], path, check=False)
    return out.strip() if code == 0 else None


@dataclass
class FileStatus:
    path: str
    status: str  # M, A, D, R, C, U, ?
    staged: bool
    orig_path: str | None = None


async def status(path: str | Path) -> dict[str, Any]:
    _, out = await run_git(["status", "--porcelain=v1", "-b", "-z"], path)
    entries = out.split("\0")
    branch, upstream, ahead, behind = None, None, 0, 0
    files: list[dict[str, Any]] = []
    i = 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if not e:
            continue
        if e.startswith("## "):
            head = e[3:]
            for prefix in ("No commits yet on ", "Initial commit on "):
                if head.startswith(prefix):
                    head = head[len(prefix) :]
            info = ""
            if " [" in head and head.endswith("]"):
                head, info = head.split(" [", 1)
            name, _, up = head.partition("...")
            branch = None if name.startswith("HEAD") else name.strip()
            upstream = up.strip() or None
            a = re.search(r"ahead (\d+)", info)
            b = re.search(r"behind (\d+)", info)
            ahead, behind = int(a.group(1)) if a else 0, int(b.group(1)) if b else 0
            continue
        xy, file_path = e[:2], e[3:]
        orig = None
        if xy[0] in "RC":
            orig = entries[i] if i < len(entries) else None
            i += 1
        if xy == "??":
            code = "?"
        elif "U" in xy or xy in ("AA", "DD"):
            code = "U"
        else:
            code = (xy[0] if xy[0] != " " else xy[1]).strip() or "M"
        files.append(
            {
                "path": file_path,
                "status": code,
                "staged": xy[0] not in (" ", "?"),
                "orig_path": orig,
            }
        )
    return {
        "branch": branch or await current_branch(path),
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "files": files,
        "clean": not files,
    }


async def changes(path: str | Path, limit: int = 150) -> list[dict[str, Any]]:
    """Per-file unified diffs of the working tree against HEAD (untracked files included)."""
    st = await status(path)
    root = Path(path)
    head = await has_commits(path)
    numstat: dict[str, tuple[int, int]] = {}
    if head:
        _, out = await run_git(["diff", "HEAD", "--numstat", "-z", "--no-renames"], path, check=False)
        for rec in out.split("\0"):
            parts = rec.split("\t")
            if len(parts) == 3:
                a, d, p = parts
                numstat[p] = (int(a) if a.isdigit() else 0, int(d) if d.isdigit() else 0)

    result: list[dict[str, Any]] = []
    for f in st["files"][:limit]:
        p = f["path"]
        item: dict[str, Any] = {**f, "added": 0, "removed": 0, "diff": "", "binary": False}
        if f["status"] == "?":
            fp = root / p
            if fp.is_dir():
                item["diff"] = ""
                item["note"] = "untracked folder"
            elif fp.is_file():
                data = fp.read_bytes()[:MAX_FILE_DIFF + 1]
                if b"\0" in data[:8192]:
                    item["binary"] = True
                else:
                    text = data.decode("utf-8", errors="replace")
                    lines = list(difflib.unified_diff([], text.splitlines(keepends=True), "/dev/null", f"b/{p}"))
                    item["diff"] = "".join(ln if ln.endswith("\n") else ln + "\n" for ln in lines)
                    item["added"] = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        elif head:
            _, diff = await run_git(["diff", "HEAD", "--no-ext-diff", "--no-renames", "--", p], path, check=False)
            if "Binary files" in diff[:500] and "@@" not in diff:
                item["binary"] = True
            item["diff"] = diff
            item["added"], item["removed"] = numstat.get(p, (0, 0))
        else:
            _, diff = await run_git(["diff", "--cached", "--no-ext-diff", "--", p], path, check=False)
            item["diff"] = diff
        if len(item["diff"]) > MAX_FILE_DIFF:
            item["diff"] = item["diff"][:MAX_FILE_DIFF] + "\n… diff truncated …\n"
            item["truncated"] = True
        result.append(item)
    return result


async def branches(path: str | Path) -> dict[str, Any]:
    _, local = await run_git(["for-each-ref", "--format=%(refname:short)", "refs/heads"], path)
    _, remote = await run_git(["for-each-ref", "--format=%(refname:short)", "refs/remotes"], path)
    remotes = [b for b in remote.split() if not b.endswith("/HEAD")]
    return {"current": await current_branch(path), "local": local.split(), "remote": remotes}


# --------------------------------------------------------------------------- mutations


async def clone(url: str, dest: Path, token: str | None, branch: str | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone", "--quiet"]
    if branch:
        args += ["--branch", branch]
    args += [url, str(dest)]
    await run_git(args, dest.parent, token=token, timeout=900)


async def checkout(path: str | Path, branch: str, create: bool = False, start_point: str | None = None) -> None:
    if not valid_branch(branch):
        raise GitError(f"'{branch}' is not a valid branch name")
    if create:
        args = ["checkout", "-b", branch] + ([start_point] if start_point else [])
        await run_git(args, path)
        return
    code, _ = await run_git(["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], path, check=False)
    if code == 0:
        await run_git(["checkout", branch], path)
        return
    code, _ = await run_git(["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"], path, check=False)
    if code == 0:
        await run_git(["checkout", "-b", branch, "--track", f"origin/{branch}"], path)
        return
    raise GitError(f"Branch '{branch}' does not exist")


async def commit_all(path: str | Path, message: str, author: dict[str, str]) -> str:
    if not message.strip():
        raise GitError("Commit message is required")
    await run_git(["add", "-A"], path)
    code, _ = await run_git(["diff", "--cached", "--quiet"], path, check=False)
    if code == 0:
        raise GitError("Nothing to commit")
    await run_git(["commit", "--no-verify", "-m", message], path, env=author)
    _, sha = await run_git(["rev-parse", "HEAD"], path)
    return sha.strip()


async def pull(path: str | Path, token: str | None) -> str:
    branch = await current_branch(path)
    if not branch:
        raise GitError("Not on a branch (detached HEAD)")
    await run_git(["fetch", "--prune", "origin"], path, token=token, timeout=300)
    code, _ = await run_git(["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"], path, check=False)
    if code != 0:
        return f"Fetched. Branch '{branch}' has no remote counterpart yet."
    _, out = await run_git(["merge", "--ff-only", f"origin/{branch}"], path)
    return out.strip() or "Up to date"


async def push(path: str | Path, token: str | None) -> str:
    branch = await current_branch(path)
    if not branch:
        raise GitError("Not on a branch (detached HEAD)")
    _, out = await run_git(["push", "--set-upstream", "origin", f"HEAD:refs/heads/{branch}"], path, token=token, timeout=300)
    return out.strip()


def author_env(name: str, email: str) -> dict[str, str]:
    return {
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
    }
