from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict

from .models import AgentState, TaskRequest
from .agent import run_agent_loop, log_trace

app = FastAPI(title="MRPL Agentic Workbench API")

# Enable CORS for the client_ui (React/Vue/etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict to localhost:3000 etc.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory state store for the hackathon (use Redis/SQLite for production)
active_tasks: Dict[str, AgentState] = {}

@app.post("/api/task")
async def create_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """Initializes a new agent task and starts the loop in the background."""
    new_state = AgentState(original_prompt=request.prompt)
    active_tasks[new_state.task_id] = new_state
    
    # Run the loop in the background so the endpoint returns immediately
    background_tasks.add_task(run_agent_loop, new_state)
    
    return {"task_id": new_state.task_id, "status": new_state.status}

@app.get("/api/agent/{task_id}/trace")
async def get_task_trace(task_id: str):
    """Frontend polls this endpoint to update the UI trace and status."""
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    state = active_tasks[task_id]
    return {
        "status": state.status,
        "current_step": state.current_step_index,
        "plan": [step.dict() for step in state.plan],
        "trace": state.trace_log,
        "final_deliverable": state.final_deliverable
    }

@app.post("/api/agent/{task_id}/resume")
async def resume_task(task_id: str, background_tasks: BackgroundTasks):
    """Resumes a paused task (e.g., after human approval)."""
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
        
    state = active_tasks[task_id]
    
    if state.status != "paused":
        raise HTTPException(status_code=400, detail="Task is not paused.")
        
    # Mark the paused step as successful
    current_step = state.plan[state.current_step_index]
    current_step.status = "success"
    log_trace(state, "System", "Human approval received. Resuming...")
    state.current_step_index += 1
    
    # Resume the loop
    background_tasks.add_task(run_agent_loop, state)
    
    return {"message": "Task resumed."}