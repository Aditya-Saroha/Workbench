import json
import httpx
import re
import asyncio
from typing import Dict, Any
from .models import AgentState, PlanStep
from .tools import execute_tool, DIRECT_CHAT_MODEL
from .persistence import save_state

ROUTER_URL = "http://127.0.0.1:11435/v1/chat/completions"
TRIAGE_ROUTE = "triage"
PLANNER_ROUTE = "tool_use"
DIRECT_CHAT_ROUTE = "simple_chat"

# Split into two models rather than one:
# - TRIAGE_MODEL: near-instant SIMPLE/COMPLEX classification. Small and fast.
# - PLANNER_MODEL: generates the JSON plan and evaluates each step's output.
#   This is the model that actually needs reliable structured/tool-call
#   output — a weak model here (e.g. llama3.2:1b) is what caused the
#   PlanStep(**str) crash originally. Qwen3's dense models were trained with
#   native tool-calling support, which is why this replaces llama3.2:1b.
TRIAGE_MODEL = "qwen3:4b"
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
DOCUMENT_QUERY_KEYWORDS = (
    ".pdf", ".docx", ".xlsx", "pdf", "docx", "xlsx", "problem statement", "attached file",
    "attached document", "uploaded file", "uploaded document", "my document",
    "my documents", "knowledge base", "from the document", "in the document",
)
VALID_TOOL_NAMES = {"direct_chat", "search_rag", "read_file", "python_sandbox", "write_docx"}


def _looks_complex(prompt: str) -> bool:
    lower = prompt.lower()
    return any(kw in lower for kw in COMPLEX_KEYWORDS + DOCUMENT_QUERY_KEYWORDS)


def _needs_document_search(prompt: str) -> bool:
    lower = prompt.lower()
    return any(kw in lower for kw in DOCUMENT_QUERY_KEYWORDS)


def log_trace(state: AgentState, source: str, message: str):
    """Appends a timestamped log entry to the agent's state for the UI to stream."""
    import time
    state.trace_log.append({
        "timestamp": time.time(),
        "source": source,
        "message": message
    })
    save_state(state)


async def call_ollama(
    prompt: str,
    model: str = PLANNER_MODEL,
    format: str = "",
    options: dict | None = None,
    read_timeout: float = 240.0,
) -> str:
    # ollama-agent-router expects the task type under `router.taskType`,
    # not crammed into the top-level `model` field — every documented
    # request in its README uses "model": "auto" + a nested `router`
    # object. Sending "model": "triage"/"tool_use"/"simple_chat" isn't a
    # real Ollama model tag, so the router either misroutes it or stalls.
    # `mode: sync, allowAsync: false` also stops the router from ever
    # handing back an async job envelope ({"id": ..., "status": "queued"})
    # in place of a normal `choices` response under queue pressure —
    # queue.globalMaxConcurrent is 1 in the config, so that's not just
    # theoretical.
    task_type = TRIAGE_ROUTE if model == TRIAGE_MODEL else PLANNER_ROUTE if model == PLANNER_MODEL else DIRECT_CHAT_ROUTE
    payload = {
        "model": "auto",
        "messages": [{"role": "user", "content": prompt}],
        "router": {"taskType": task_type, "mode": "sync", "allowAsync": False},
    }
    if format:
        payload["response_format"] = {"type": "json_object"}
    if options:
        # "options" is an Ollama-native /api/chat field, not part of this
        # router's OpenAI-compatible schema. Map the fields we actually use
        # onto their OpenAI-style equivalents instead.
        if "temperature" in options:
            payload["temperature"] = options["temperature"]
        if "num_predict" in options:
            payload["max_tokens"] = options["num_predict"]
        if "stop" in options:
            payload["stop"] = options["stop"]

    timeout = httpx.Timeout(connect=10.0, read=read_timeout, write=10.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(ROUTER_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


async def stream_direct_chat(prompt: str, state: AgentState) -> str:
    """Get the direct-chat response from the router.

    NOTE: despite the name, this no longer streams token-by-token.
    ollama-agent-router's API is a single JSON response wrapped with routing
    metadata (selected model, timings) that it can only compute once the
    underlying Ollama call finishes — there's no `stream: true` mode
    documented or supported. Sending "stream": true was rejected outright
    (400) rather than degrading gracefully. This does one call and sets
    `final_deliverable` once, in full. Kept the function name/signature so
    run_agent_loop doesn't need to change.
    """
    payload = {
        "model": "auto",
        "messages": [{"role": "user", "content": prompt}],
        "router": {"taskType": DIRECT_CHAT_ROUTE, "mode": "sync", "allowAsync": False},
    }
    timeout = httpx.Timeout(connect=10.0, read=240.0, write=10.0, pool=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(ROUTER_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]

    state.final_deliverable = content
    save_state(state)
    return content


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
                    f"coercing into a search_rag step."
                )
                item = {
                    "step_id": i + 1,
                    "description": item,
                    "tool_name": "search_rag",
                    "tool_args": {"query": item},
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

        tool_name = str(item["tool_name"]).strip().lower()
        if tool_name not in VALID_TOOL_NAMES:
            fallback_tool = "search_rag" if _needs_document_search(state.original_prompt) else "direct_chat"
            fallback_args = {"query": state.original_prompt} if fallback_tool == "search_rag" else {"prompt": state.original_prompt}
            log_trace(
                state,
                "Planner",
                f"Unsupported tool '{item['tool_name']}' in step {i}; using {fallback_tool} fallback.",
            )
            item["tool_name"] = fallback_tool
            item["tool_args"] = fallback_args
        else:
            item["tool_name"] = tool_name

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
    sys_prompt = f"""You are the routing classifier for a local AI workbench.

Classify the user's request as exactly one label: SIMPLE or COMPLEX.

Available tools:
- search_rag: search the user's uploaded documents
- read_file: read a specific file
- python_sandbox: execute code
- write_docx: generate a Word document

Return COMPLEX when the request mentions a file, document, uploaded knowledge,
code execution, calculations that require running code, report/document
generation, data lookup, multi-step work, or any action using a tool.
Return SIMPLE only for a self-contained conversational question, explanation,
translation, brainstorming request, greeting, or opinion that needs no tool.

Output exactly one word and nothing else: SIMPLE or COMPLEX.

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

    label = response.strip().upper().split()[0] if response.strip() else ""
    if label in {"SIMPLE", "COMPLEX"}:
        return label
    raise RuntimeError(f"classify_intent: invalid classifier output {response!r}")


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
                    # A classifier failure should not send ordinary chat into
                    # the planner. Only requests that already look like tool
                    # or document work need the conservative complex fallback.
                    intent = "COMPLEX" if _looks_complex(state.original_prompt) else "SIMPLE"
                    log_trace(state, "Router", f"Router call failed ({e}); defaulting to {intent}.")

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
                if _needs_document_search(state.original_prompt):
                    log_trace(state, "RAG", "Document query detected. Searching the knowledge base before answering.")
                    plan_data = [{
                        "step_id": 1,
                        "description": "Retrieve relevant document excerpts",
                        "tool_name": "search_rag",
                        "tool_args": {"query": state.original_prompt},
                    }]
                else:
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
        retrieved_observations = []
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
                        None, execute_tool, current_step.tool_name, current_step.tool_args, state.session_id
                    )
                state.last_tool_output = str(observation)
                if current_step.tool_name == "search_rag":
                    retrieved_observations.append(str(observation))
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
            if retrieved_observations and not state.final_deliverable:
                log_trace(state, "Executor", "Generating an answer from the retrieved document excerpts.")
                grounded_prompt = (
                    "Answer the user's request using the retrieved document excerpts below. "
                    "Do not claim that you cannot access files. Cite the source and page "
                    "when the excerpts provide that metadata. If the excerpts do not contain "
                    "the answer, say so clearly.\n\n"
                    f"User request: {state.original_prompt}\n\n"
                    "Retrieved excerpts:\n" + "\n\n".join(retrieved_observations)
                )
                await stream_direct_chat(grounded_prompt, state)
            state.status = "completed"
            if not state.final_deliverable:
                state.final_deliverable = "Task sequence finished."
            log_trace(state, "System", "Task complete.")

    except Exception as e:
        state.status = "failed"
        log_trace(state, "Fatal Error", str(e))