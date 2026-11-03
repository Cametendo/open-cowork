import os
import tempfile
from pathlib import Path

import pytest

# Isolate all runtime directories before the app is imported.
_TMP = Path(tempfile.mkdtemp(prefix="open-cowork-test-"))
os.environ.setdefault("DATA_DIR", str(_TMP / "data"))
os.environ.setdefault("REPO_DIR", str(_TMP / "repo"))
os.environ.setdefault("WORKSPACE_DIR", str(_TMP / "workspaces"))
os.environ.setdefault("FRONTEND_DIR", str(_TMP / "no-frontend"))
os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:9")  # nothing listening
os.environ.setdefault("ENABLE_SIGNUP", "true")


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from open_cowork.db import Base, engine, init_db
    from open_cowork.main import app

    Base.metadata.drop_all(engine)
    init_db()
    with TestClient(app) as c:
        yield c


def signup(client, email="admin@example.com", name="Admin", password="password123"):
    r = client.post("/api/auths/signup", json={"name": name, "email": email, "password": password})
    return r


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def mock_llm_url():
    """Run tests/mock_llm.py on a free port in a background thread."""
    import socket
    import threading
    import time

    import uvicorn

    from mock_llm import app as mock_app

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(mock_app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def admin_client_with_connection(client, mock_llm_url, kind="ollama"):
    """Sign up an admin and point a single connection at the mock LLM."""
    tok = signup(client).json()["token"]
    h = auth_headers(tok)
    for c in client.get("/api/admin/connections", headers=h).json():
        client.delete(f"/api/admin/connections/{c['id']}", headers=h)
    base = mock_llm_url if kind == "ollama" else mock_llm_url + "/v1"
    r = client.post("/api/admin/connections", json={"type": kind, "name": "Mock", "base_url": base}, headers=h)
    assert r.status_code == 200, r.text
    return h


def read_sse(response) -> list[dict]:
    import json

    events = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events
