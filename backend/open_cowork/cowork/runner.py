"""The Cowork agent loop.

Each run executes as a background asyncio task, independent of any HTTP request.
Events are buffered per run so a browser can (re)attach at any point and replay
the run from the start; persisted messages always hold everything *before* the
current run (``RunState.start_index``), so replaying never duplicates anything.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..app_config import get_config
from ..db import SessionLocal, new_id, now
from ..models import CoworkSession, User
from ..providers import ProviderError, resolve_model
from .prompts import build_system_prompt
from .tools import NEEDS_APPROVAL, ToolResult, Workspace, execute_tool, tool_specs
from .workspaces import prepare_workspace

log = logging.getLogger(__name__)

KEEP_FINISHED_RUN_SECONDS = 120
_FULL_TOOL_RESULTS = 8  # most recent tool results sent to the model in full


class RunState:
    def __init__(self, session_id: str, start_index: int) -> None:
        self.id = new_id()
        self.session_id = session_id
        self.start_index = start_index
        self.events: list[dict[str, Any]] = []
        self.seq = 0
        self.queues: set[asyncio.Queue] = set()
        self.approvals: dict[str, asyncio.Future] = {}
        self.pending_inputs: list[dict[str, Any]] = []
        self.task: asyncio.Task | None = None
        self.done = False

    def emit(self, type_: str, **data: Any) -> dict[str, Any]:
        ev = {"seq": self.seq, "type": type_, **data}
        self.seq += 1
        self.events.append(ev)
        for q in list(self.queues):
            q.put_nowait(ev)
        return ev

    def compact(self, kind: str, key: str, value: str) -> None:
        """Drop streaming fragments once the final value is known (keeps replay small)."""
        self.events = [e for e in self.events if not (e["type"] == kind and e.get(key) == value)]

    async def subscribe(self, after: int = -1):
        q: asyncio.Queue = asyncio.Queue()
        backlog = [e for e in self.events if e["seq"] > after]
        finished = self.done
        self.queues.add(q)
        try:
            for ev in backlog:
                yield ev
            if finished:
                return
            last = backlog[-1]["seq"] if backlog else after
            while True:
                ev = await q.get()
                if ev["seq"] <= last:
                    continue
                yield ev
                if ev["type"] == "run_end":
                    return
        finally:
            self.queues.discard(q)


def _for_model(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shorten older tool outputs so long runs fit in small context windows."""
    tool_idx = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    old = set(tool_idx[:-_FULL_TOOL_RESULTS])
    out = []
    for i, m in enumerate(messages):
        if m.get("role") not in ("user", "assistant", "tool"):
            continue
        if m.get("notice"):
            continue
        if i in old and len(m.get("content") or "") > 1500:
            m = {**m, "content": m["content"][:1500] + "\n… [older output truncated]"}
        out.append(m)
    return out


def _close_dangling(messages: list[dict[str, Any]], reason: str) -> list[dict[str, Any]]:
    """Every assistant tool call must be followed by a tool result."""
    answered = {m.get("tool_call_id") for m in messages if m.get("role") == "tool"}
    for m in reversed(messages):
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                if tc["id"] not in answered:
                    messages.append(
                        {
                            "id": new_id(),
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": tc["name"],
                            "content": reason,
                            "is_error": True,
                            "created_at": now(),
                        }
                    )
            break
    return messages


def _save(session_id: str, **fields: Any) -> None:
    with SessionLocal() as db:
        s = db.get(CoworkSession, session_id)
        if s is None:
            return
        for k, v in fields.items():
            setattr(s, k, v)
        s.updated_at = now()
        db.commit()


class CoworkManager:
    def __init__(self) -> None:
        self.runs: dict[str, RunState] = {}

    # ------------------------------------------------------------------ public API

    def get(self, session_id: str) -> RunState | None:
        return self.runs.get(session_id)

    def active(self, session_id: str) -> RunState | None:
        run = self.runs.get(session_id)
        return run if run and not run.done else None

    def start(self, session_id: str, user_id: str, content: str) -> RunState:
        if self.active(session_id):
            raise RuntimeError("A run is already in progress")
        with SessionLocal() as db:
            s = db.get(CoworkSession, session_id)
            if s is None:
                raise LookupError("Session not found")
            messages = list(s.messages or [])
            first_run = not any(m.get("role") == "assistant" for m in messages)
            run = RunState(session_id, start_index=len(messages))
            user_msg = {"id": new_id(), "role": "user", "content": content, "created_at": now()}
            s.messages = [*messages, user_msg]
            s.status = "running"
            s.last_error = None
            s.updated_at = now()
            db.commit()
        self.runs[session_id] = run
        run.emit("run_start", run_id=run.id)
        run.emit("user_message", message=user_msg)
        run.task = asyncio.create_task(self._run(run, session_id, user_id, first_run))
        return run

    def add_input(self, session_id: str, content: str) -> dict[str, Any]:
        run = self.active(session_id)
        if run is None:
            raise LookupError("No active run")
        msg = {"id": new_id(), "role": "user", "content": content, "created_at": now()}
        run.pending_inputs.append(msg)
        run.emit("input_queued", message=msg)
        return msg

    def resolve_approval(self, session_id: str, tool_call_id: str, approved: bool, always: bool = False) -> bool:
        run = self.active(session_id)
        fut = run.approvals.get(tool_call_id) if run else None
        if fut is None or fut.done():
            return False
        fut.set_result({"approved": approved, "always": always})
        return True

    async def cancel(self, session_id: str) -> bool:
        run = self.active(session_id)
        if run is None or run.task is None:
            return False
        run.task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(run.task), timeout=10)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):  # noqa: BLE001
            pass
        return True

    async def shutdown(self) -> None:
        for sid in list(self.runs):
            await self.cancel(sid)

    # ------------------------------------------------------------------ the loop

    async def _run(self, run: RunState, session_id: str, user_id: str, first_run: bool) -> None:
        messages: list[dict[str, Any]] = []
        status, error, end_status = "idle", None, "completed"
        partial: dict[str, Any] | None = None
        try:
            with SessionLocal() as db:
                s = db.get(CoworkSession, session_id)
                user = db.get(User, user_id)
                if s is None or user is None:
                    raise LookupError("Session not found")
                cfg = get_config(db)
                messages = list(s.messages or [])
                if not s.model:
                    raise ProviderError("No model selected for this task. Pick a model and try again.")
                provider, raw_model = await resolve_model(db, s.model)
                extra_env, repo_info = await prepare_workspace(db, s, user)
                approval_mode = s.approval_mode
                settings = user.settings or {}
                system_prompt = build_system_prompt(
                    app_name=cfg["webui_name"],
                    workspace=s.workspace_path,
                    allow_shell=cfg["cowork_allow_shell"],
                    user_name=user.name,
                    repo=repo_info,
                    instructions=settings.get("cowork_instructions"),
                )
                model_id = s.model
                provider_type = provider.conn.type

            ws = Workspace(
                root=s.workspace_path,
                allow_shell=bool(cfg["cowork_allow_shell"]),
                command_timeout=int(cfg["cowork_command_timeout"]),
                extra_env=extra_env,
            )
            ws.root.mkdir(parents=True, exist_ok=True)
            tools = tool_specs(ws.allow_shell)
            options: dict[str, Any] = {}
            if provider_type == "ollama" and cfg["cowork_ollama_num_ctx"]:
                options["num_ctx"] = int(cfg["cowork_ollama_num_ctx"])

            max_steps = int(cfg["cowork_max_steps"])
            for step in range(max_steps):
                if run.pending_inputs:
                    for msg in run.pending_inputs:
                        messages.append(msg)
                        run.emit("user_message", message=msg)
                    run.pending_inputs.clear()
                    _save(session_id, messages=messages)

                msg_id = new_id()
                partial = {"id": msg_id, "role": "assistant", "content": "", "model": model_id, "created_at": now()}
                run.emit("assistant_start", id=msg_id, model=model_id)
                content: list[str] = []
                reasoning: list[str] = []
                tool_calls: list[dict[str, Any]] = []
                usage = None
                async for ev in provider.stream_chat(
                    raw_model,
                    [{"role": "system", "content": system_prompt}, *_for_model(messages)],
                    tools=tools,
                    options=options,
                ):
                    if ev["type"] == "content":
                        content.append(ev["text"])
                        partial["content"] += ev["text"]
                        run.emit("delta", id=msg_id, text=ev["text"])
                    elif ev["type"] == "reasoning":
                        reasoning.append(ev["text"])
                        run.emit("reasoning", id=msg_id, text=ev["text"])
                    elif ev["type"] == "tool_calls":
                        tool_calls = [tc for tc in ev["tool_calls"] if tc.get("name")]
                    elif ev["type"] == "done":
                        usage = ev.get("usage")

                assistant: dict[str, Any] = {**partial, "content": "".join(content)}
                if reasoning:
                    assistant["reasoning"] = "".join(reasoning)
                if tool_calls:
                    assistant["tool_calls"] = tool_calls
                if usage:
                    assistant["usage"] = usage
                partial = None
                messages.append(assistant)
                _save(session_id, messages=messages)
                run.emit("assistant_end", message=assistant)
                run.compact("delta", "id", msg_id)
                run.compact("reasoning", "id", msg_id)

                if not tool_calls:
                    if run.pending_inputs:
                        continue
                    break

                for tc in tool_calls:
                    result = await self._execute(run, session_id, ws, tc, approval_mode)
                    if result.meta.get("approval_mode"):
                        approval_mode = result.meta.pop("approval_mode")
                    tool_msg = {
                        "id": new_id(),
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": tc["name"],
                        "content": result.content,
                        "is_error": result.is_error,
                        "meta": result.meta,
                        "created_at": now(),
                    }
                    messages.append(tool_msg)
                    fields: dict[str, Any] = {"messages": messages}
                    if tc["name"] == "update_plan" and not result.is_error:
                        fields["plan"] = result.meta["plan"]
                        run.emit("plan", plan=result.meta["plan"])
                    _save(session_id, **fields)
                    run.emit("tool_result", message=tool_msg)
                    run.compact("tool_output", "tool_call_id", tc["id"])
            else:
                notice = {
                    "id": new_id(),
                    "role": "assistant",
                    "content": f"I reached the step limit for one run ({max_steps} steps). Send a message to let me continue.",
                    "notice": True,
                    "created_at": now(),
                }
                messages.append(notice)
                run.emit("assistant_end", message=notice)
        except asyncio.CancelledError:
            end_status = "cancelled"
        except ProviderError as e:
            status, end_status = "error", "error"
            error = e.message
            if "does not support tools" in error or "tool" in error.lower() and e.status == 400:
                error += (
                    "\n\nCowork needs a model with tool calling support "
                    "(for Ollama e.g. qwen3, llama3.1, mistral-nemo, gpt-oss)."
                )
        except LookupError as e:
            status, end_status, error = "error", "error", str(e)
        except Exception as e:  # noqa: BLE001
            log.exception("Cowork run failed")
            status, end_status = "error", "error"
            error = f"{e.__class__.__name__}: {e}"
        finally:
            if partial and (partial.get("content") or "").strip():
                messages.append({**partial, "stopped": True})
                run.emit("assistant_end", message={**partial, "stopped": True})
            messages = _close_dangling(messages, "Cancelled by the user." if end_status == "cancelled" else "Not executed.")
            if messages:
                _save(session_id, messages=messages, status=status, last_error=error)
            else:
                _save(session_id, status=status, last_error=error)
            run.done = True
            run.emit("run_end", status=end_status, error=error)
            asyncio.get_running_loop().call_later(KEEP_FINISHED_RUN_SECONDS, self._forget, session_id, run.id)
        if first_run and end_status == "completed":
            asyncio.create_task(self._maybe_title(session_id))

    async def _execute(
        self, run: RunState, session_id: str, ws: Workspace, tc: dict[str, Any], approval_mode: str
    ) -> ToolResult:
        new_mode = None
        if approval_mode == "ask" and tc["name"] in NEEDS_APPROVAL:
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            run.approvals[tc["id"]] = fut
            run.emit("approval_required", tool_call_id=tc["id"])
            try:
                decision = await fut
            finally:
                run.approvals.pop(tc["id"], None)
            run.emit("approval_resolved", tool_call_id=tc["id"], approved=decision["approved"])
            if decision["approved"] and decision.get("always"):
                new_mode = "auto"
                _save(session_id, approval_mode="auto")
                run.emit("session_update", approval_mode="auto")
            if not decision["approved"]:
                return ToolResult(
                    "The user declined this action. Don't retry it; ask what they'd prefer or take another approach.",
                    is_error=True,
                    meta={"denied": True},
                )
        run.emit("tool_start", tool_call_id=tc["id"])
        result = await execute_tool(
            ws, tc["name"], tc.get("arguments") or {}, on_output=lambda t: run.emit("tool_output", tool_call_id=tc["id"], text=t)
        )
        if new_mode:
            result.meta["approval_mode"] = new_mode
        return result

    async def _maybe_title(self, session_id: str) -> None:
        from ..routers.chats import _generate_title

        try:
            with SessionLocal() as db:
                s = db.get(CoworkSession, session_id)
                if s is None or not s.model:
                    return
                msgs = s.messages or []
                first = next((m.get("content", "") for m in msgs if m.get("role") == "user"), "")
                last = next((m.get("content", "") for m in reversed(msgs) if m.get("role") == "assistant" and m.get("content")), "")
                if not get_config(db)["enable_title_generation"]:
                    return
                provider, raw = await resolve_model(db, s.model)
                original = s.title
            title = await _generate_title(provider, raw, first, last)
            if title:
                with SessionLocal() as db:
                    s = db.get(CoworkSession, session_id)
                    if s is not None and s.title == original:
                        s.title = title
                        db.commit()
        except Exception as e:  # noqa: BLE001
            log.info("Cowork title generation failed: %s", e)

    def _forget(self, session_id: str, run_id: str) -> None:
        run = self.runs.get(session_id)
        if run and run.id == run_id and run.done:
            del self.runs[session_id]


manager = CoworkManager()
