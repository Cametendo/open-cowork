"""Minimal GitHub REST client (personal access token auth)."""

from __future__ import annotations

from typing import Any

import httpx

from ..config import get_settings


class GitHubError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


class GitHubClient:
    def __init__(self, token: str | None):
        self.token = token
        self.api = get_settings().github_api_url

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "open-cowork"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.request(method, f"{self.api}{path}", headers=self._headers(), **kwargs)
            except httpx.HTTPError as e:
                raise GitHubError(f"Could not reach GitHub: {e}") from e
        if resp.status_code >= 400:
            try:
                data = resp.json()
                msg = data.get("message", resp.text)
                errors = data.get("errors")
                if errors and isinstance(errors, list):
                    details = "; ".join(e.get("message", "") if isinstance(e, dict) else str(e) for e in errors)
                    msg = f"{msg}: {details}" if details else msg
            except ValueError:
                msg = resp.text
            if resp.status_code == 401:
                msg = "GitHub rejected the token (401). Reconnect GitHub in Settings."
            raise GitHubError(msg or f"GitHub error {resp.status_code}", resp.status_code)
        return resp

    async def user(self) -> dict[str, Any]:
        resp = await self.request("GET", "/user")
        data = resp.json()
        return {
            "id": data.get("id"),
            "login": data.get("login"),
            "name": data.get("name"),
            "email": data.get("email"),
            "avatar_url": data.get("avatar_url"),
            "html_url": data.get("html_url"),
            "scopes": resp.headers.get("x-oauth-scopes"),
        }

    async def repos(self, query: str | None = None) -> list[dict[str, Any]]:
        params = {"per_page": 100, "sort": "pushed", "affiliation": "owner,collaborator,organization_member"}
        resp = await self.request("GET", "/user/repos", params=params)
        items = [_repo(r) for r in resp.json()]
        if query:
            q = query.lower().strip()
            items = [r for r in items if q in r["full_name"].lower() or q in (r["description"] or "").lower()]
            if "/" in q and not any(r["full_name"].lower() == q for r in items):
                try:
                    items.insert(0, await self.repo(q))
                except GitHubError:
                    pass
        return items

    async def repo(self, full_name: str) -> dict[str, Any]:
        return _repo((await self.request("GET", f"/repos/{full_name}")).json())

    async def find_pull(self, full_name: str, branch: str) -> dict[str, Any] | None:
        owner = full_name.split("/")[0]
        resp = await self.request("GET", f"/repos/{full_name}/pulls", params={"head": f"{owner}:{branch}", "state": "open"})
        pulls = resp.json()
        return _pull(pulls[0]) if pulls else None

    async def create_pull(self, full_name: str, *, title: str, body: str, head: str, base: str, draft: bool) -> dict[str, Any]:
        resp = await self.request(
            "POST",
            f"/repos/{full_name}/pulls",
            json={"title": title, "body": body, "head": head, "base": base, "draft": draft},
        )
        return _pull(resp.json())


def _repo(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "full_name": r.get("full_name"),
        "name": r.get("name"),
        "owner": (r.get("owner") or {}).get("login"),
        "description": r.get("description"),
        "private": r.get("private", False),
        "default_branch": r.get("default_branch") or "main",
        "html_url": r.get("html_url"),
        "clone_url": r.get("clone_url"),
        "pushed_at": r.get("pushed_at"),
        "language": r.get("language"),
        "stargazers_count": r.get("stargazers_count", 0),
    }


def _pull(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": p.get("number"),
        "title": p.get("title"),
        "html_url": p.get("html_url"),
        "state": p.get("state"),
        "draft": p.get("draft", False),
        "head": (p.get("head") or {}).get("ref"),
        "base": (p.get("base") or {}).get("ref"),
    }
