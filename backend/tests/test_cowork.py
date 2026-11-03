import json
from pathlib import Path

from conftest import admin_client_with_connection, auth_headers


def collect(client, h, sid, after=-1, stop_on=("run_end",)):
    events = []
    with client.stream("GET", f"/api/cowork/sessions/{sid}/stream?after={after}", headers=h) as r:
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            events.append(ev)
            if ev["type"] in stop_on:
                break
    return events


def directive(name, **args):
    return f"[[tool:{name} {json.dumps(args)}]]"


def test_cowork_auto_run_writes_files(client, mock_llm_url):
    h = admin_client_with_connection(client, mock_llm_url, "openai")
    prompt = "Make a file " + directive("write_file", path="hello.txt", content="hi there\n") + directive("read_file", path="hello.txt")
    s = client.post("/api/cowork/sessions", json={"prompt": prompt, "model": "mock-llama:latest", "approval_mode": "auto"}, headers=h).json()
    assert s["workspace_type"] == "scratch" and Path(s["workspace_path"]).is_dir()

    events = collect(client, h, s["id"])
    types = [e["type"] for e in events]
    assert types[0] == "run_start" and types[1] == "user_message" and types[-1] == "run_end"
    assert events[-1]["status"] == "completed"
    results = [e["message"] for e in events if e["type"] == "tool_result"]
    assert [r["name"] for r in results] == ["write_file", "read_file"]
    assert results[1]["content"].startswith("hi there")
    assert (Path(s["workspace_path"]) / "hello.txt").read_text() == "hi there\n"

    full = client.get(f"/api/cowork/sessions/{s['id']}", headers=h).json()
    roles = [m["role"] for m in full["messages"]]
    # while the finished run is still buffered, messages exclude it (it is replayed from events)
    assert roles == [] or roles == ["user", "assistant", "tool", "assistant", "tool", "assistant"]

    # file browser endpoints
    listing = client.get(f"/api/cowork/sessions/{s['id']}/files", headers=h).json()
    assert any(e["name"] == "hello.txt" for e in listing["entries"])
    f = client.get(f"/api/cowork/sessions/{s['id']}/file", params={"path": "hello.txt"}, headers=h).json()
    assert f["content"] == "hi there\n"
    assert client.get(f"/api/cowork/sessions/{s['id']}/file", params={"path": "../x"}, headers=h).status_code == 400


def test_cowork_approval_flow_and_follow_up(client, mock_llm_url):
    h = admin_client_with_connection(client, mock_llm_url)
    prompt = directive("run_command", command="echo approved-run > out.txt") + directive("write_file", path="b.txt", content="b")
    s = client.post("/api/cowork/sessions", json={"prompt": prompt, "model": "mock-llama:latest", "approval_mode": "ask"}, headers=h).json()
    sid = s["id"]

    ev = collect(client, h, sid, stop_on=("approval_required",))
    req = ev[-1]
    assert req["type"] == "approval_required"
    # reconnecting replays from the start and nothing ran yet
    assert not (Path(s["workspace_path"]) / "out.txt").exists()

    assert client.post(f"/api/cowork/sessions/{sid}/approve", json={"tool_call_id": req["tool_call_id"], "approved": True}, headers=h).status_code == 200
    ev2 = collect(client, h, sid, after=req["seq"], stop_on=("approval_required",))
    assert any(e["type"] == "tool_output" or e["type"] == "tool_result" for e in ev2)
    req2 = ev2[-1]
    # deny the second action
    client.post(f"/api/cowork/sessions/{sid}/approve", json={"tool_call_id": req2["tool_call_id"], "approved": False}, headers=h)
    ev3 = collect(client, h, sid, after=req2["seq"])
    denied = [e for e in ev3 if e["type"] == "tool_result"][0]["message"]
    assert denied["is_error"] and denied["meta"]["denied"]
    assert (Path(s["workspace_path"]) / "out.txt").read_text().strip() == "approved-run"
    assert not (Path(s["workspace_path"]) / "b.txt").exists()

    # follow-up message starts a new run (no tools directive -> demo scenario writes notes.md)
    r = client.post(f"/api/cowork/sessions/{sid}/messages", json={"content": "now take notes"}, headers=h).json()
    assert r["queued"] is False
    client.patch(f"/api/cowork/sessions/{sid}", json={"approval_mode": "auto"}, headers=h)  # 409 while running is fine too
    evs = collect(client, h, sid, stop_on=("approval_required", "run_end"))
    if evs[-1]["type"] == "approval_required":
        client.post(f"/api/cowork/sessions/{sid}/approve", json={"tool_call_id": evs[-1]["tool_call_id"], "approved": True, "always": True}, headers=h)
        evs = collect(client, h, sid, after=evs[-1]["seq"])
    assert evs[-1]["type"] == "run_end" and evs[-1]["status"] == "completed"
    assert any(e["type"] == "plan" for e in evs)
    assert (Path(s["workspace_path"]) / "notes.md").exists()


def test_cowork_cancel(client, mock_llm_url):
    h = admin_client_with_connection(client, mock_llm_url)
    prompt = directive("run_command", command="sleep 20")
    s = client.post("/api/cowork/sessions", json={"prompt": prompt, "model": "mock-llama:latest", "approval_mode": "auto"}, headers=h).json()
    collect(client, h, s["id"], stop_on=("tool_start",))
    assert client.post(f"/api/cowork/sessions/{s['id']}/cancel", headers=h).json()["cancelled"] is True
    evs = collect(client, h, s["id"])
    assert evs[-1]["type"] == "run_end" and evs[-1]["status"] == "cancelled"


def test_cowork_disabled_for_users(client, mock_llm_url):
    h = admin_client_with_connection(client, mock_llm_url)
    client.put("/api/admin/config", json={"cowork_enabled": False, "default_user_role": "user"}, headers=h)
    from conftest import signup

    uh = auth_headers(signup(client, email="u@example.com").json()["token"])
    assert client.get("/api/cowork/sessions", headers=uh).status_code == 403
    assert client.get("/api/cowork/sessions", headers=h).status_code == 200


def test_upload_and_download(client, mock_llm_url):
    h = admin_client_with_connection(client, mock_llm_url)
    s = client.post(
        "/api/cowork/sessions",
        json={"prompt": directive("list_files"), "model": "mock-llama:latest", "approval_mode": "auto"},
        headers=h,
    ).json()
    collect(client, h, s["id"])
    r = client.post(
        f"/api/cowork/sessions/{s['id']}/upload",
        files=[("files", ("data.csv", b"a,b\n1,2\n", "text/csv"))],
        data={"path": "inputs"},
        headers=h,
    )
    assert r.status_code == 200 and r.json()["saved"] == ["inputs/data.csv"]
    assert client.get(f"/api/cowork/sessions/{s['id']}/download", params={"path": "inputs/data.csv"}, headers=h).content == b"a,b\n1,2\n"
    bad = client.post(
        f"/api/cowork/sessions/{s['id']}/upload",
        files=[("files", ("..", b"x", "text/plain"))],
        data={"path": "inputs"},
        headers=h,
    )
    assert bad.status_code == 400
    outside = client.post(
        f"/api/cowork/sessions/{s['id']}/upload",
        files=[("files", ("x.txt", b"x", "text/plain"))],
        data={"path": "../.."},
        headers=h,
    )
    assert outside.status_code == 400
