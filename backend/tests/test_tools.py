import asyncio
import os

import pytest

from open_cowork.cowork.tools import ToolError, Workspace, execute_tool, update_plan


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def main():\n    print('hi')\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("x")
    return Workspace(root=tmp_path, command_timeout=5)


def run(coro):
    return asyncio.run(coro)


def test_path_confinement(ws, tmp_path):
    with pytest.raises(ToolError):
        ws.resolve("../outside.txt")
    with pytest.raises(ToolError):
        ws.resolve("/etc/passwd")
    assert ws.resolve(str(tmp_path / "src")) == tmp_path / "src"
    # symlink escaping the workspace is rejected
    os.symlink("/etc", tmp_path / "evil")
    with pytest.raises(ToolError):
        ws.resolve("evil/passwd")
    r = run(execute_tool(ws, "read_file", {"path": "../../etc/passwd"}))
    assert r.is_error and "outside the workspace" in r.content


def test_list_read_write_edit(ws, tmp_path):
    r = run(execute_tool(ws, "list_files", {}))
    assert "src/" in r.content and "app.py" in r.content and "junk.js" not in r.content

    r = run(execute_tool(ws, "write_file", {"path": "docs/readme.md", "content": "hello\nworld\n"}))
    assert not r.is_error and r.meta["created"] and (tmp_path / "docs" / "readme.md").read_text() == "hello\nworld\n"
    assert r.meta["added"] == 2

    r = run(execute_tool(ws, "edit_file", {"path": "docs/readme.md", "old_string": "world", "new_string": "there"}))
    assert not r.is_error and "-world" in r.meta["diff"] and "+there" in r.meta["diff"]

    r = run(execute_tool(ws, "edit_file", {"path": "docs/readme.md", "old_string": "nope", "new_string": "x"}))
    assert r.is_error and "not found" in r.content

    (tmp_path / "dup.txt").write_text("a a a")
    r = run(execute_tool(ws, "edit_file", {"path": "dup.txt", "old_string": "a", "new_string": "b"}))
    assert r.is_error and "3 times" in r.content
    r = run(execute_tool(ws, "edit_file", {"path": "dup.txt", "old_string": "a", "new_string": "b", "replace_all": True}))
    assert not r.is_error and (tmp_path / "dup.txt").read_text() == "b b b"

    r = run(execute_tool(ws, "read_file", {"path": "src/app.py", "offset": 2, "limit": 1}))
    assert r.content.startswith("    print('hi')") and "lines 2-2 of 2" in r.content


def test_search(ws):
    r = run(execute_tool(ws, "search_files", {"pattern": r"print\(", "glob": "*.py"}))
    assert "src/app.py:2:" in r.content
    # ignored folders are skipped unless searched explicitly
    r = run(execute_tool(ws, "search_files", {"pattern": "^x$"}))
    assert "No matches" in r.content
    r = run(execute_tool(ws, "search_files", {"pattern": "^x$", "path": "node_modules"}))
    assert "junk.js:1" in r.content


def test_run_command_and_env(ws, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("WEBUI_SECRET_KEY", "server-secret")
    r = run(execute_tool(ws, "run_command", {"command": "echo $OPENAI_API_KEY$WEBUI_SECRET_KEY; pwd; exit 3"}))
    assert "sk-secret" not in r.content and "server-secret" not in r.content
    assert str(ws.root) in r.content and r.meta["exit_code"] == 3 and r.is_error

    out = []
    r = run(execute_tool(ws, "run_command", {"command": "echo one; echo two"}, on_output=out.append))
    assert "".join(out).split() == ["one", "two"] and not r.is_error

    r = run(execute_tool(ws, "run_command", {"command": "sleep 30", "timeout": 1}))
    assert r.meta["timed_out"] and r.is_error


def test_shell_disabled(tmp_path):
    ws = Workspace(root=tmp_path, allow_shell=False)
    r = run(execute_tool(ws, "run_command", {"command": "ls"}))
    assert r.is_error and "disabled" in r.content


def test_bad_args_and_unknown_tool(ws):
    assert run(execute_tool(ws, "nope", {})).is_error
    assert run(execute_tool(ws, "read_file", {})).is_error
    assert run(execute_tool(ws, "read_file", {"__raw__": "{bad"})).is_error


def test_update_plan_normalizes(ws):
    r = update_plan(ws, [{"step": "A", "status": "done"}, "B", {"title": "C", "status": "Doing"}])
    assert [p["status"] for p in r.meta["plan"]] == ["completed", "pending", "in_progress"]
