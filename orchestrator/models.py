from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import uuid

class PlanStep(BaseModel):
    step_id: int
    description: str
    tool_name: str
    tool_args: Dict[str, Any]
    status: str = Field(default="pending") # pending, running, success, failed, human_approval
    result: Optional[str] = None

class AgentState(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_prompt: str
    plan: List[PlanStep] = []
    current_step_index: int = 0
    trace_log: List[Dict[str, Any]] = [] 
    final_deliverable: Optional[str] = None
    status: str = Field(default="initializing") # initializing, planning, executing, paused, completed, failed

class TaskRequest(BaseModel):
    prompt: str