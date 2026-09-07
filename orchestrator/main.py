from fastapi import FastAPI, BackgroundTasks, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Optional

import httpx
import asyncio
import re
import time
import uuid

from .models import AgentState, TaskRequest
from .agent import run_agent_loop, log_trace, TRIAGE_MODEL, PLANNER_MODEL, TRIAGE_ROUTE, PLANNER_ROUTE, DIRECT_CHAT_ROUTE
from .tools import DIRECT_CHAT_MODEL, close_sandbox_session, reap_idle_sandbox_sessions
from .persistence import (
    initialize,
    load_states,
    list_sessions as persisted_sessions,
    save_state,
    create_session,
    rename_session,
    get_session_title,
    delete_session,
    DEFAULT_TITLE,
)

app = FastAPI(title="MRPL Agentic Workbench API")

background_tasks: set[asyncio.Task] = set()

def spawn_agent_task(coro):
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return task

async def _save_state_async(state: AgentState) -> None:
    """Runs the blocking SQLite write off the event loop (same helper as agent.py)."""
    await asyncio.get_event_loop().run_in_executor(None, save_state, state)

async def _prewarm_model():
    app.state.model_ready = False
    # Prewarm every model actually hit by the request path, not a single
    # hardcoded name. classify_intent always uses TRIAGE_MODEL; the SIMPLE
    # fast-path uses DIRECT_CHAT_MODEL; the planner/critic use PLANNER_MODEL.
    models_to_warm = [TRIAGE_MODEL, DIRECT_CHAT_MODEL, PLANNER_MODEL]
    print(f"Pre-warming Ollama models into memory: {models_to_warm}")

    timeout = httpx.Timeout(connect=5.0, read=120.0, write=5.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for model in models_to_warm:
            for attempt in range(30):  # retry for up to ~2.5 min per model if Ollama isn't up yet
                try:
                    task_type = (
                        TRIAGE_ROUTE if model == TRIAGE_MODEL
                        else PLANNER_ROUTE if model == PLANNER_MODEL
                        else DIRECT_CHAT_ROUTE
                    )
                    resp = await client.post(
                        "http://127.0.0.1:11435/v1/chat/completions",
                        json={
                            # ollama-agent-router expects "auto" + a nested
                            # router.taskType, not the task type as "model"
                            # itself — see agent.py's call_ollama for the
                            # same fix and why.
                            "model": "auto",
                            "messages": [{"role": "user", "content": "ping"}],
                            "router": {"taskType": task_type, "mode": "sync", "allowAsync": False},
                        },
                    )
                    resp.raise_for_status()
                    print(f"Model pre-warmed: {model}")
                    break
                except Exception as e:
                    print(f"Ollama not ready for {model} yet ({e}), retrying in 5s...")
                    await asyncio.sleep(5)
            else:
                print(f"Warning: could not confirm {model} is ready after retries.")

    app.state.model_ready = True


async def _reap_sandboxes_loop():
    while True:
        await asyncio.sleep(120)
        if reap_idle_sandbox_sessions:
            await asyncio.get_event_loop().run_in_executor(None, reap_idle_sandbox_sessions)


@app.on_event("startup")
async def prewarm_model():
    # Fire-and-forget: don't let this block Uvicorn from accepting requests.
    # The agent loop already checks is_model_loaded() per-request and logs a
    # "cold-loading" message, so real requests degrade gracefully instead of
    # the whole API being unreachable while this retries in the background.
    spawn_agent_task(_prewarm_model())
    spawn_agent_task(_reap_sandboxes_loop())


def _autoname_title(prompt: str) -> str:
    """Derive a chat title from its first message.

    Deliberately a plain string operation instead of another model round
    trip — this workbench already runs the router/planner/critic entirely
    on a CPU-only local box, so titling shouldn't add another cold-load or
    queue wait just to pick a name.
    """
    cleaned = re.sub(r"\s+", " ", prompt).strip()
    if not cleaned:
        return DEFAULT_TITLE
    words = cleaned.split(" ")
    title = " ".join(words[:8])
    if len(title) > 48:
        title = title[:48].rstrip()
    if len(words) > 8 or len(cleaned) > 48:
        title += "…"
    return title[0].upper() + title[1:]

# Enable CORS for the client_ui (React/Vue/etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to localhost:3000 etc.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active handles remain in memory; task state is durable in SQLite.
initialize()
active_tasks: Dict[str, AgentState] = {state.task_id: state for state in load_states()}
active_task_handles: Dict[str, asyncio.Task] = {}
session_activity: Dict[str, float] = {}

@app.post("/api/agent/task")
async def create_task(request: TaskRequest):
    new_state = AgentState(original_prompt=request.prompt, session_id=request.session_id)
    active_tasks[new_state.task_id] = new_state
    session_activity[request.session_id] = time.time()

    # Autoname: the first message in a chat still titled "New chat" (or not
    # registered at all yet) names it, same idea as chat titles elsewhere.
    current_title = await asyncio.get_event_loop().run_in_executor(
        None, get_session_title, request.session_id
    )
    new_title = _autoname_title(request.prompt)
    if current_title is None:
        await asyncio.get_event_loop().run_in_executor(None, create_session, request.session_id, new_title)
    elif current_title == DEFAULT_TITLE:
        await asyncio.get_event_loop().run_in_executor(None, rename_session, request.session_id, new_title)

    await _save_state_async(new_state)
    active_task_handles[new_state.task_id] = spawn_agent_task(run_agent_loop(new_state))
    return {"task_id": new_state.task_id, "status": new_state.status}


class SessionCreateResponse(BaseModel):
    id: str
    title: str
    updated_at: float


class SessionRenameRequest(BaseModel):
    title: str


@app.post("/api/sessions", response_model=SessionCreateResponse)
async def create_new_session():
    """Registers a fresh chat, defaulting to 'New chat', immediately in
    SQLite — not just in the frontend's React state — so it's still there
    after a refresh even before the first message is sent."""
    session_id = f"session-{uuid.uuid4()}"
    timestamp = time.time()
    await asyncio.get_event_loop().run_in_executor(None, create_session, session_id, DEFAULT_TITLE)
    return {"id": session_id, "title": DEFAULT_TITLE, "updated_at": timestamp}


@app.patch("/api/sessions/{session_id}")
async def update_session(session_id: str, body: SessionRenameRequest):
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    await asyncio.get_event_loop().run_in_executor(None, rename_session, session_id, title[:80])
    return {"id": session_id, "title": title[:80]}


@app.delete("/api/sessions/{session_id}")
async def remove_session(session_id: str):
    await asyncio.get_event_loop().run_in_executor(None, delete_session, session_id)
    if close_sandbox_session:
        await asyncio.get_event_loop().run_in_executor(None, close_sandbox_session, session_id)
    session_activity.pop(session_id, None)

    orphaned_task_ids = [task_id for task_id, state in active_tasks.items() if state.session_id == session_id]
    for task_id in orphaned_task_ids:
        active_tasks.pop(task_id, None)
        handle = active_task_handles.pop(task_id, None)
        if handle and not handle.done():
            handle.cancel()

    return {"status": "deleted", "id": session_id}

@app.get("/api/agent/{task_id}/trace")
async def get_task_trace(task_id: str, x_session_id: str = Header("default")):
    """Frontend polls this endpoint to update the UI trace and status."""
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    state = active_tasks[task_id]
    if state.session_id != x_session_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "status": state.status,
        "current_step": state.current_step_index,
        "plan": [step.dict() for step in state.plan],
        "trace": state.trace_log,
        "final_deliverable": state.final_deliverable,
        "last_tool_output": state.last_tool_output,
        "session_id": state.session_id,
        # Distinct from "status": lets the UI show "warming up qwen3:8b,
        # first response may take ~2 min" instead of a generic spinner
        # that looks identical to a hang. None once nothing is cold-loading.
        "warming_model": state.warming_model,
    }

@app.post("/api/agent/{task_id}/resume")
async def resume_task(task_id: str, x_session_id: str = Header("default")):
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    state = active_tasks[task_id]
    if state.session_id != x_session_id:
        raise HTTPException(status_code=404, detail="Task not found")
    if state.status != "paused":
        raise HTTPException(status_code=400, detail="Task is not paused.")

    # Mark the paused step as approved WITHOUT advancing past it or faking
    # success. run_agent_loop's pause check ("write_docx and not
    # human_approved") will then let this exact step fall through and
    # actually call execute_tool this time, instead of the step being
    # skipped entirely.
    current_step = state.plan[state.current_step_index]
    current_step.human_approved = True
    await log_trace(state, "System", "Human approval received. Resuming...")
    await _save_state_async(state)

    active_task_handles[task_id] = spawn_agent_task(run_agent_loop(state))
    return {"message": "Task resumed."}


@app.post("/api/agent/{task_id}/cancel")
async def cancel_task(task_id: str, x_session_id: str = Header("default")):
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    state = active_tasks[task_id]
    if state.session_id != x_session_id:
        raise HTTPException(status_code=404, detail="Task not found")
    if state.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=400, detail=f"Task is already {state.status}.")
    if state.status == "paused":
        state.status = "cancelled"
        await log_trace(state, "System", "Task cancelled by user.")
        await _save_state_async(state)
        return {"message": "Task cancelled."}

    state.status = "cancelled"
    await log_trace(state, "System", "Task cancellation requested by user.")
    await _save_state_async(state)
    task = active_task_handles.get(task_id)
    if task and not task.done():
        task.cancel()

    return {"message": "Task cancelled."}


@app.get("/api/sessions")
async def list_sessions():
    persisted = await asyncio.get_event_loop().run_in_executor(None, persisted_sessions)
    sessions: Dict[str, Dict[str, object]] = {
        item["id"]: {"updated_at": item["updated_at"], "title": item["title"]} for item in persisted
    }
    for session_id, updated_at in session_activity.items():
        sessions.setdefault(session_id, {"title": DEFAULT_TITLE, "updated_at": updated_at})
        sessions[session_id]["updated_at"] = max(sessions[session_id]["updated_at"], updated_at)
    for state in active_tasks.values():
        sessions.setdefault(state.session_id, {"title": DEFAULT_TITLE, "updated_at": time.time()})
    if not sessions:
        sessions["default"] = {"title": DEFAULT_TITLE, "updated_at": time.time()}

    return {
        "sessions": [
            {"id": session_id, "title": info["title"], "updated_at": info["updated_at"]}
            for session_id, info in sorted(sessions.items(), key=lambda item: item[1]["updated_at"], reverse=True)
        ]
    }