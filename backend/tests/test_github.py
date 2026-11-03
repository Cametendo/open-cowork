import json
import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException

from conftest import admin_client_with_connection
from test_cowork import collect, directive


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture()
def local_repo(tmp_path):
    """REPO_DIR/acme/proj with an 'origin' bare remote."""
    from open_cowork.config import get_settings

    bare = tmp_path / "remote.git"
    git("init", "--bare", "-b", "main", str(bare), cwd=tmp_path)
    work = get_settings().repo_dir / "acme" / "proj"
    if work.exists():
        import shutil

        shutil.rmtree(work)
    work.parent.mkdir(parents=True, exist_ok=True)
    git("clone", str(bare), str(work), cwd=tmp_path)
    (work / "README.md").write_text("# proj\n")
    git("-c", "user.name=t", "-c", "user.email=t@e", "add", "-A", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@e", "commit", "-m", "init", cwd=work)
    git("push", "-u", "origin", "HEAD:main", cwd=work)
    yield work, bare


def test_parse_full_name():
    from open_cowork.github.repos import parse_full_name

    assert parse_full_name("octo/hello") == "octo/hello"
    assert parse_full_name("https://github.com/octo/hello.git") == "octo/hello"
    assert parse_full_name("git@github.com:octo/hello.git") == "octo/hello"
    for bad in ("hello", "../x/y", "a/b/c", "https://evil.com/a/b"):
        with pytest.raises(HTTPException):
            parse_full_name(bad)


def test_branch_names():
    from open_cowork.github.git import valid_branch

    assert valid_branch("cowork/fix-tests-1a2b")
    for bad in ("", "a..b", "-x", "a b", "x.lock", "/x", "x/", "a~1", "--upload-pack=evil"):
        assert not valid_branch(bad), bad


def test_repo_session_branch_commit_push(client, mock_llm_url, local_repo):
    work, bare = local_repo
    h = admin_client_with_connection(client, mock_llm_url, "openai")

    repos = client.get("/api/repos", headers=h).json()
    repo = next(r for r in repos if r["path"] == str(work))
    assert repo["source"] == "local" and repo["full_name"] == "acme/proj" and repo["current_branch"] == "main"

    prompt = "Add docs " + directive("write_file", path="docs/guide.md", content="guide\n")
    s = client.post(
        "/api/cowork/sessions",
        json={"prompt": prompt, "model": "mock-llama:latest", "approval_mode": "auto", "workspace": {"type": "repo", "repo_id": repo["id"]}},
        headers=h,
    ).json()
    assert s["workspace_type"] == "repo" and s["branch"].startswith("cowork/add-docs") and s["base_branch"] == "main"
    assert any(m["role"] == "event" and "Created branch" in m["content"] for m in s["messages"])
    evs = collect(client, h, s["id"])
    assert evs[-1]["status"] == "completed", evs[-1]
    assert (work / "docs" / "guide.md").exists()

    st = client.get(f"/api/repos/{repo['id']}/status", headers=h).json()
    assert st["branch"] == s["branch"] and not st["clean"]
    ch = client.get(f"/api/repos/{repo['id']}/changes", headers=h).json()["files"]
    assert ch[0]["path"].startswith("docs") and ch[0]["status"] == "?"

    # a second task can't start while... (run is finished, so it can) — checkout guard when dirty
    r = client.post(f"/api/repos/{repo['id']}/commit", json={"message": "Add guide"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"]["clean"]
    log = git("log", "-1", "--format=%an <%ae>|%s", cwd=work)
    assert log.strip() == "Admin <admin@example.com>|Add guide"
    assert client.post(f"/api/repos/{repo['id']}/commit", json={"message": "again"}, headers=h).status_code == 400

    r = client.post(f"/api/repos/{repo['id']}/push", headers=h)
    assert r.status_code == 200, r.text
    assert s["branch"] in git("branch", "--list", cwd=bare)

    # modify tracked file -> diff with numstat
    (work / "README.md").write_text("# proj\nmore\n")
    ch = client.get(f"/api/repos/{repo['id']}/changes", headers=h).json()["files"]
    assert ch[0]["path"] == "README.md" and ch[0]["added"] == 1 and "+more" in ch[0]["diff"]

    br = client.get(f"/api/repos/{repo['id']}/branches", headers=h).json()
    assert "main" in br["local"] and br["current"] == s["branch"]
    # checkout with a dirty tree that conflicts is refused by git? README modified exists on main too -> git keeps it
    r = client.post(f"/api/repos/{repo['id']}/checkout", json={"branch": "bad..name"}, headers=h)
    assert r.status_code == 400


def test_github_token_requires_valid(client, mock_llm_url, monkeypatch):
    h = admin_client_with_connection(client, mock_llm_url)
    from open_cowork.config import get_settings

    monkeypatch.setattr(get_settings(), "github_api_url", "http://127.0.0.1:9")
    r = client.put("/api/github/token", json={"token": "ghp_" + "x" * 30}, headers=h)
    assert r.status_code == 502
    st = client.get("/api/github/status", headers=h).json()
    assert st["connected"] is False
    assert client.get("/api/github/repos", headers=h).status_code == 400
