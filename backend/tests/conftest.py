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
