import json
import httpx
import re
from typing import Dict, Any
from .models import AgentState, PlanStep
from .tools import execute_tool

OLLAMA_URL = "http://localhost:11434/api/generate"
PLANNER_MODEL = "llama3.2:1b" # Change to your chosen router model

def log_trace(state: AgentState, source: str, message: str):
    """Appends a timestamped log entry to the agent's state for the UI to stream."""
    import time
    state.trace_log.append({
        "timestamp": time.time(),
        "source": source,
        "message": message
    })

async def call_ollama(prompt: str, model: str = PLANNER_MODEL, format: str = "") -> str:
    """Helper to query the local Ollama instance."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    if format:
        payload["format"] = format
        
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        return response.json()["response"]

def extract_json_from_llm(text: str) -> list:
    """Safely extract JSON array from LLM output, ignoring markdown fences."""
    try:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(text)
    except json.JSONDecodeError:
        return []

async def generate_plan(prompt: str) -> list:
    sys_prompt = f"""You are an industrial AI planner. Break the user's request into a sequential JSON array of steps. 
Available tools: [search_rag, read_file, python_sandbox, write_docx].
User Request: {prompt}
Format exactly like this: [{{"step_id": 1, "description": "...", "tool_name": "...", "tool_args": {{}}}}]"""
    
    raw_response = await call_ollama(sys_prompt, format="json")
    return extract_json_from_llm(raw_response)

async def evaluate_step(step: PlanStep, observation: str) -> Dict[str, Any]:
    sys_prompt = f"""You are an AI QA agent. Evaluate if the tool's output successfully accomplished the step.
Step Goal: {step.description}
Tool Output: {observation}
Reply strictly in JSON: {{"passed": true/false, "reason": "..."}}"""
    
    raw_response = await call_ollama(sys_prompt, format="json")
    try:
        match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(raw_response)
    except:
        return {"passed": True, "reason": "Failed to parse critic response, assuming success."}

async def classify_intent(prompt: str) -> str:
    """Classifies if a prompt needs the complex agent loop or just a fast response."""
    sys_prompt = f"""You are a routing system. Read the user's prompt and output exactly one word:
'SIMPLE' if it's a greeting, basic question, or request that doesn't need file reading/writing.
'COMPLEX' if it requires multiple steps, file operations, RAG search, or coding.

User: {prompt}
Classification:"""
    
    # We don't force JSON here, just a quick text completion
    response = await call_ollama(sys_prompt, model=PLANNER_MODEL)
    return "COMPLEX" if "COMPLEX" in response.upper() else "SIMPLE"

async def run_agent_loop(state: AgentState):
    try:
        state.status = "planning"
        log_trace(state, "System", "Routing request...")
        
        # 1. SMART ROUTING & PLANNING
        if not state.plan:
            intent = await classify_intent(state.original_prompt)
            
            if intent == "SIMPLE":
                log_trace(state, "Router", "Classified as simple conversational task. Bypassing planner.")
                state.plan = [
                    PlanStep(
                        step_id=1, 
                        description="Direct model response", 
                        tool_name="direct_chat", 
                        tool_args={"prompt": state.original_prompt}
                    )
                ]
            else:
                log_trace(state, "Router", "Classified as complex task. Engaging planner.")
                plan_data = await generate_plan(state.original_prompt)
                state.plan = [PlanStep(**step) for step in plan_data]
                log_trace(state, "Planner", f"Generated {len(state.plan)} steps.")
        
        state.status = "executing"
        
        # 2. EXECUTION LOOP
        while state.current_step_index < len(state.plan):
            current_step = state.plan[state.current_step_index]
            current_step.status = "running"
            
            log_trace(state, "Executor", f"Executing step {current_step.step_id}: {current_step.description}")
            
            if current_step.tool_name == "write_docx":
                current_step.status = "human_approval"
                state.status = "paused"
                log_trace(state, "System", "Paused for human review.")
                return 
                
            try:
                observation = execute_tool(current_step.tool_name, current_step.tool_args)
                log_trace(state, "Tool Output", str(observation)[:200] + "..." if len(str(observation)) > 200 else str(observation))
                
                # Fast-path bypasses the Critic to save time
                if current_step.tool_name == "direct_chat":
                    current_step.status = "success"
                    current_step.result = observation
                    state.final_deliverable = observation
                    state.current_step_index += 1
                    continue

                # 3. CRITIC STAGE (Only for complex tasks)
                critic_verdict = await evaluate_step(current_step, observation)
                
                if critic_verdict.get("passed", False):
                    current_step.status = "success"
                    current_step.result = observation
                    log_trace(state, "Critic", "Step succeeded.")
                    state.current_step_index += 1
                else:
                    current_step.status = "failed"
                    reason = critic_verdict.get('reason', 'Unknown failure')
                    log_trace(state, "Critic", f"Step failed: {reason}. Halting.")
                    state.status = "failed"
                    return
                    
            except Exception as e:
                current_step.status = "failed"
                state.status = "failed"
                log_trace(state, "System Error", str(e))
                return
                
        if state.current_step_index >= len(state.plan):
            state.status = "completed"
            # If the fast path was used, the deliverable is already set
            if not state.final_deliverable:
                state.final_deliverable = "Task sequence finished."
            log_trace(state, "System", "Task complete.")
            
    except Exception as e:
        state.status = "failed"
        log_trace(state, "Fatal Error", str(e))