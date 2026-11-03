import pytest

from conftest import admin_client_with_connection, auth_headers, read_sse, signup


def test_seeded_ollama_connection(client):
    h = auth_headers(signup(client).json()["token"])
    conns = client.get("/api/admin/connections", headers=h).json()
    assert any(c["type"] == "ollama" for c in conns)


@pytest.mark.parametrize("kind", ["ollama", "openai"])
def test_models_and_chat_stream(client, mock_llm_url, kind):
    h = admin_client_with_connection(client, mock_llm_url, kind)
    models = client.get("/api/models?refresh=true", headers=h).json()["data"]
    ids = [m["id"] for m in models]
    assert "mock-llama:latest" in ids
    assert models[0]["provider"] == kind

    chat = client.post("/api/chats", json={}, headers=h).json()
    with client.stream("POST", f"/api/chats/{chat['id']}/messages", json={"model": "mock-llama:latest", "content": "hello there"}, headers=h) as r:
        assert r.status_code == 200
        events = read_sse(r)
    types = [e["type"] for e in events]
    assert types[0] == "start" and "done" in types
    text = "".join(e["text"] for e in events if e["type"] == "delta")
    assert text == "Echo: hello there"
    assert any(e["type"] == "title" and e["title"] == "Mock Conversation Title" for e in events)

    saved = client.get(f"/api/chats/{chat['id']}", headers=h).json()
    assert saved["title"] == "Mock Conversation Title"
    assert [m["role"] for m in saved["messages"]] == ["user", "assistant"]
    assert saved["messages"][1]["content"] == "Echo: hello there"

    # regenerate replaces the assistant message
    with client.stream("POST", f"/api/chats/{chat['id']}/messages", json={"model": "mock-llama:latest", "regenerate": True}, headers=h) as r:
        read_sse(r)
    saved = client.get(f"/api/chats/{chat['id']}", headers=h).json()
    assert len(saved["messages"]) == 2

    # editing the user message truncates and re-answers
    uid = saved["messages"][0]["id"]
    with client.stream("POST", f"/api/chats/{chat['id']}/messages", json={"model": "mock-llama:latest", "content": "edited", "edit_message_id": uid}, headers=h) as r:
        read_sse(r)
    saved = client.get(f"/api/chats/{chat['id']}", headers=h).json()
    assert saved["messages"][0]["content"] == "edited"
    assert saved["messages"][1]["content"] == "Echo: edited"


def test_unknown_model_and_isolation(client, mock_llm_url):
    h = admin_client_with_connection(client, mock_llm_url)
    chat = client.post("/api/chats", json={}, headers=h).json()
    r = client.post(f"/api/chats/{chat['id']}/messages", json={"model": "nope", "content": "x"}, headers=h)
    assert r.status_code == 400

    client.put("/api/admin/config", json={"default_user_role": "user"}, headers=h)
    other = auth_headers(signup(client, email="o@example.com").json()["token"])
    assert client.get(f"/api/chats/{chat['id']}", headers=other).status_code == 404
    assert client.get("/api/chats", headers=other).json() == []


def test_connection_verify_and_prefix(client, mock_llm_url):
    h = admin_client_with_connection(client, mock_llm_url, "openai")
    r = client.post("/api/admin/connections/verify", json={"type": "openai", "base_url": mock_llm_url + "/v1"}, headers=h)
    assert r.status_code == 200 and "mock-coder:7b" in r.json()["models"]
    bad = client.post("/api/admin/connections/verify", json={"type": "ollama", "base_url": "http://127.0.0.1:9"}, headers=h)
    assert bad.status_code == 400

    client.post("/api/admin/connections", json={"type": "ollama", "name": "Second", "base_url": mock_llm_url, "prefix_id": "box2", "model_ids": ["mock-coder:7b"]}, headers=h)
    ids = [m["id"] for m in client.get("/api/models?refresh=true", headers=h).json()["data"]]
    assert "box2.mock-coder:7b" in ids and "box2.mock-llama:latest" not in ids
