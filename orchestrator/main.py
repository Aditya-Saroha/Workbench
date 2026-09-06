from fastapi import FastAPI, BackgroundTasks, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict

import httpx
import asyncio

from .models import AgentState, TaskRequest
from .agent import run_agent_loop, log_trace, TRIAGE_MODEL, PLANNER_MODEL
from .tools import DIRECT_CHAT_MODEL
from .persistence import initialize, load_states, list_sessions as persisted_sessions, save_state

app = FastAPI(title="MRPL Agentic Workbench API")

background_tasks: set[asyncio.Task] = set()

def spawn_agent_task(coro):
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return task

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
                    resp = await client.post(
                        "http://127.0.0.1:11435/v1/chat/completions",
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": ""}],
                            "stream": False,
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


@app.on_event("startup")
async def prewarm_model():
    # Fire-and-forget: don't let this block Uvicorn from accepting requests.
    # The agent loop already checks is_model_loaded() per-request and logs a
    # "cold-loading" message, so real requests degrade gracefully instead of
    # the whole API being unreachable while this retries in the background.
    spawn_agent_task(_prewarm_model())

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
    import time
    session_activity[request.session_id] = time.time()
    save_state(new_state)
    active_task_handles[new_state.task_id] = spawn_agent_task(run_agent_loop(new_state))
    return {"task_id": new_state.task_id, "status": new_state.status}

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
    log_trace(state, "System", "Human approval received. Resuming...")
    save_state(state)

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
        log_trace(state, "System", "Task cancelled by user.")
        save_state(state)
        return {"message": "Task cancelled."}

    state.status = "cancelled"
    log_trace(state, "System", "Task cancellation requested by user.")
    save_state(state)
    task = active_task_handles.get(task_id)
    if task and not task.done():
        task.cancel()

    return {"message": "Task cancelled."}


@app.get("/api/sessions")
async def list_sessions():
    import time
    persisted = persisted_sessions()
    sessions = {item["id"]: item["updated_at"] for item in persisted}
    sessions.update({session_id: updated_at for session_id, updated_at in session_activity.items()})
    for state in active_tasks.values():
        sessions.setdefault(state.session_id, time.time())
    if not sessions:
        sessions["default"] = time.time()
    return {
        "sessions": [
            {"id": session_id, "updated_at": updated_at}
            for session_id, updated_at in sorted(sessions.items(), key=lambda item: item[1], reverse=True)
        ]
    }