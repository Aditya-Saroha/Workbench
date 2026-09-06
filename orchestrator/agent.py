import json
import httpx
import re
import asyncio
from typing import Dict, Any
from .models import AgentState, PlanStep
from .tools import execute_tool, DIRECT_CHAT_MODEL

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# Split into two models rather than one:
# - TRIAGE_MODEL: near-instant SIMPLE/COMPLEX classification. Small and fast.
# - PLANNER_MODEL: generates the JSON plan and evaluates each step's output.
#   This is the model that actually needs reliable structured/tool-call
#   output — a weak model here (e.g. llama3.2:1b) is what caused the
#   PlanStep(**str) crash originally. Qwen3's dense models were trained with
#   native tool-calling support, which is why this replaces llama3.2:1b.
TRIAGE_MODEL = "qwen3:0.6b"
PLANNER_MODEL = "qwen3:8b"

# TRIAGE_MODEL is fast but unreliable on short, imperative requests that
# name a tool directly — e.g. "run echo hello in sandbox" got classified
# SIMPLE, so direct_chat answered *about* running the command instead of
# python_sandbox actually running it. Anything that clearly names one of
# the four real tools skips the LLM guess entirely and goes straight to
# the planner. This is deliberately a plain substring check, not a model
# call — it should be true more often on a false positive (an unnecessary
# planner run) than a false negative (silently answering instead of using
# a tool).
COMPLEX_KEYWORDS = (
    "sandbox", "python_sandbox", "run this code", "run the code",
    "execute this code", "execute the code", "run a script", "run script",
    "write_docx", "write a docx", "generate a docx", "generate a doc",
    "generate a report", "generate a word document",
    "search_rag", "search my documents", "search the documents",
    "search the knowledge base", "search my knowledge base",
    "read_file", "read the file", "read this file", "read the document",
)


def _looks_complex(prompt: str) -> bool:
    lower = prompt.lower()
    return any(kw in lower for kw in COMPLEX_KEYWORDS)


def log_trace(state: AgentState, source: str, message: str):
    """Appends a timestamped log entry to the agent's state for the UI to stream."""
    import time
    state.trace_log.append({
        "timestamp": time.time(),
        "source": source,
        "message": message
    })


async def call_ollama(
    prompt: str,
    model: str = PLANNER_MODEL,
    format: str = "",
    options: dict | None = None,
    read_timeout: float = 240.0,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "3m",  # matches router config; avoid two models resident at once on 16GB
    }
    if format:
        payload["format"] = format
    if options:
        payload["options"] = options

    timeout = httpx.Timeout(connect=10.0, read=read_timeout, write=10.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        return response.json()["response"]


async def stream_direct_chat(prompt: str, state: AgentState) -> str:
    """Stream direct-chat tokens into the task state as Ollama produces them.

    The frontend already reads ``final_deliverable`` from the trace endpoint.
    Updating that field for every received Ollama chunk lets the existing task
    UI render the answer while it is being generated instead of waiting for
    the complete response.
    """
    payload = {
        "model": DIRECT_CHAT_MODEL,
        "prompt": prompt,
        "stream": True,
        "keep_alive": "3m",
    }
    timeout = httpx.Timeout(connect=10.0, read=240.0, write=10.0, pool=10.0)
    accumulated = ""

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", OLLAMA_URL, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue

                chunk = json.loads(line)
                token = chunk.get("response", "")
                if token:
                    accumulated += token
                    state.final_deliverable = accumulated

                if chunk.get("done"):
                    break

    return accumulated


def extract_json_from_llm(text: str) -> list:
    """
    Safely extract a JSON array from LLM output, ignoring markdown fences.
    Handles the common failure modes of wrapping the array in an object
    (e.g. {"plan": [...]}) or returning a single object instead of a list.
    """
    try:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
        else:
            parsed = json.loads(text)
    except json.JSONDecodeError:
        return []

    if isinstance(parsed, dict):
        for key in ("plan", "steps", "actions"):
            if isinstance(parsed.get(key), list):
                return parsed[key]
        return [parsed]
    if isinstance(parsed, list):
        return parsed
    return []


def normalize_plan_steps(raw_steps: list, state: AgentState) -> list[dict]:
    """
    Guarantees every item handed to PlanStep(**item) is actually a dict.
    Kept as a safety net even with a tool-calling-capable planner model.
    """
    normalized = []
    for i, item in enumerate(raw_steps):
        if isinstance(item, str):
            try:
                parsed = json.loads(item)
            except json.JSONDecodeError:
                parsed = None

            if isinstance(parsed, dict):
                item = parsed
            else:
                log_trace(
                    state, "Planner",
                    f"Step {i} came back as a bare string, not an object; "
                    f"coercing into a direct_chat fallback step."
                )
                item = {
                    "step_id": i + 1,
                    "description": item,
                    "tool_name": "direct_chat",
                    "tool_args": {"prompt": item},
                }

        if not isinstance(item, dict):
            log_trace(state, "Planner", f"Dropping unparseable step {i}: {item!r}")
            continue

        item.setdefault("step_id", i + 1)
        item.setdefault("description", item.get("tool_name", "unknown step"))
        item.setdefault("tool_args", {})
        if "tool_name" not in item:
            log_trace(state, "Planner", f"Dropping step {i} with no tool_name: {item!r}")
            continue

        normalized.append(item)

    return normalized


async def generate_plan(prompt: str) -> list:
    sys_prompt = f"""You are an industrial AI planner. Break the user's request into a sequential JSON array of steps.
Available tools: [search_rag, read_file, python_sandbox, write_docx].
User Request: {prompt}
Respond with ONLY a top-level JSON array, exactly like this, with no wrapping object and no stringified elements:
[{{"step_id": 1, "description": "...", "tool_name": "...", "tool_args": {{}}}}]"""

    raw_response = await call_ollama(sys_prompt, model=PLANNER_MODEL, format="json")
    return extract_json_from_llm(raw_response)


async def evaluate_step(step: PlanStep, observation: str) -> Dict[str, Any]:
    sys_prompt = f"""You are an AI QA agent. Evaluate if the tool's output successfully accomplished the step.
Step Goal: {step.description}
Tool Output: {observation}
Reply strictly in JSON: {{"passed": true/false, "reason": "..."}}"""

    raw_response = await call_ollama(sys_prompt, model=PLANNER_MODEL, format="json")
    try:
        match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(raw_response)
    except Exception:
        return {"passed": True, "reason": "Failed to parse critic response, assuming success."}


async def classify_intent(prompt: str) -> str:
    """Classifies if a prompt needs the complex agent loop or just a fast response.

    Only called for prompts that _looks_complex() didn't already resolve —
    i.e. requests that don't name a tool outright, where SIMPLE vs COMPLEX
    is a genuine judgment call (multi-step reasoning, ambiguous phrasing).
    """
    sys_prompt = f"""You are a strict routing classifier for an agent that has these tools:
- search_rag: search the user's uploaded documents
- read_file: read a specific file
- python_sandbox: execute code
- write_docx: generate a Word document

Output exactly one word — SIMPLE or COMPLEX — with no punctuation or explanation.

COMPLEX: the request needs any of the tools above, or needs multiple steps to finish.
SIMPLE: a greeting, opinion, or question answerable directly from general knowledge —
no file, document, code execution, or generation involved.

Examples:
"hi" -> SIMPLE
"what's the capital of France?" -> SIMPLE
"can you check yesterday's numbers and email me a summary?" -> COMPLEX
"what do you think about pineapple on pizza?" -> SIMPLE
"pull up last quarter's report and pull out the revenue figure" -> COMPLEX

User: {prompt}
Classification:"""

    try:
        response = await call_ollama(
            sys_prompt,
            model=TRIAGE_MODEL,
            options={"num_predict": 8, "temperature": 0, "stop": ["\n"]},
            read_timeout=20.0,
        )
    except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.ConnectError) as e:
        raise RuntimeError(f"classify_intent: router call failed ({e})") from e

    return "COMPLEX" if "COMPLEX" in response.upper() else "SIMPLE"


async def is_model_loaded(model: str = PLANNER_MODEL) -> bool:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get("http://127.0.0.1:11434/api/ps")
            resp.raise_for_status()
            return any(m["name"] == model for m in resp.json().get("models", []))
        except Exception:
            return False


async def run_agent_loop(state: AgentState):
    try:
        state.status = "planning"

        if not state.plan:
            if _looks_complex(state.original_prompt):
                # Skips the TRIAGE_MODEL call entirely — the request already
                # names a tool, so there's nothing genuinely ambiguous to
                # classify.
                log_trace(
                    state, "Router",
                    "Request names a specific tool (sandbox, file, RAG, or docx) — routing straight to the planner."
                )
                intent = "COMPLEX"
            else:
                if not await is_model_loaded(TRIAGE_MODEL):
                    log_trace(state, "System", f"{TRIAGE_MODEL} not resident in memory — cold-loading now.")
                else:
                    log_trace(state, "System", "Routing request...")

                try:
                    intent = await classify_intent(state.original_prompt)
                except RuntimeError as e:
                    log_trace(state, "Router", f"Router call failed ({e}); defaulting to SIMPLE.")
                    intent = "SIMPLE"

            if intent == "SIMPLE":
                log_trace(state, "Router", "Classified as simple conversational task. Bypassing planner.")
                # This path's actual model call is direct_chat -> DIRECT_CHAT_MODEL,
                # not the planner model, so check/report on that one.
                if not await is_model_loaded(DIRECT_CHAT_MODEL):
                    log_trace(
                        state, "System",
                        f"{DIRECT_CHAT_MODEL} not resident in memory — cold-loading now, typically <2 min."
                    )
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
                if not await is_model_loaded(PLANNER_MODEL):
                    log_trace(
                        state, "System",
                        f"{PLANNER_MODEL} not resident in memory — cold-loading now, typically <2 min."
                    )
                plan_data = await generate_plan(state.original_prompt)
                plan_data = normalize_plan_steps(plan_data, state)

                if not plan_data:
                    log_trace(
                        state, "Planner",
                        "No valid steps could be parsed from the planner output; failing task."
                    )
                    state.status = "failed"
                    return

                state.plan = [PlanStep(**step) for step in plan_data]
                log_trace(state, "Planner", f"Generated {len(state.plan)} steps.")

        state.status = "executing"

        # 2. EXECUTION LOOP
        while state.current_step_index < len(state.plan):
            current_step = state.plan[state.current_step_index]
            current_step.status = "running"

            log_trace(state, "Executor", f"Executing step {current_step.step_id}: {current_step.description}")

            # Only pause the FIRST time we reach a write_docx step. If a human
            # has already approved it (human_approved=True, set by /resume),
            # fall through and actually execute it instead of pausing again.
            if current_step.tool_name == "write_docx" and not current_step.human_approved:
                current_step.status = "human_approval"
                state.status = "paused"
                log_trace(state, "System", "Paused for human review.")
                return

            try:
                if current_step.tool_name == "direct_chat":
                    # Keep this call async so each Ollama token can update the
                    # state immediately. The UI receives those partial updates
                    # through the trace endpoint while the task is executing.
                    observation = await stream_direct_chat(
                        current_step.tool_args.get("prompt", state.original_prompt), state
                    )
                else:
                    observation = await asyncio.get_event_loop().run_in_executor(
                        None, execute_tool, current_step.tool_name, current_step.tool_args
                    )
                log_trace(
                    state, "Tool Output",
                    str(observation)[:200] + "..." if len(str(observation)) > 200 else str(observation)
                )

                if current_step.tool_name == "direct_chat":
                    current_step.status = "success"
                    current_step.result = observation
                    state.final_deliverable = observation
                    state.current_step_index += 1
                    continue

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
            if not state.final_deliverable:
                state.final_deliverable = "Task sequence finished."
            log_trace(state, "System", "Task complete.")

    except Exception as e:
        state.status = "failed"
        log_trace(state, "Fatal Error", str(e))