# LIAMA AI Workbench

LIAMA AI Workbench is a local, multi-service AI application for document-grounded chat, agentic task execution, local model routing, and isolated Python execution.

## Components

- `client_ui`: Next.js frontend for chat, uploads, document search, task progress, and model status.
- `orchestrator`: FastAPI agent service for intent classification, planning, tool execution, critic evaluation, and human approval.
- `RAG`: FastAPI document ingestion and retrieval service using embeddings, FAISS, BM25, and cross-encoder reranking.
- `ollama-agent-router.yaml`: Configuration for the local Ollama model router.
- `sandbox`: Docker-isolated Python execution tool.
- `start.ps1` / `start.sh`: Development startup scripts.

The intended deployment is local: the UI, APIs, indexes, models, and sandbox are run on the developer machine.

The orchestrator persists task states and session activity in SQLite at
`data/workbench.sqlite3`. Model requests from the orchestrator go through the
agent router at `127.0.0.1:11435`; the router remains the only component that
talks to Ollama at `127.0.0.1:11434`.

Each browser workspace has a session ID stored in browser local storage. The
session ID is forwarded through the Next.js proxy to the orchestrator and RAG
service, so tasks, uploads, indexes, and document lists are isolated by
session.

---

## 1. High-Level Architecture

```text
                                      User
                                       │
                                       ▼
                         ┌──────────────────────────┐
                         │       client_ui          │
                         │ Next.js + React frontend │
                         └────────────┬─────────────┘
                                      │ same-origin /api proxies
              ┌───────────────────────┼────────────────────────┐
              ▼                       ▼                        ▼
   ┌──────────────────┐    ┌──────────────────┐     ┌──────────────────┐
   │ Agent proxy      │    │ RAG proxy        │     │ Chat/status proxy│
   └────────┬─────────┘    └────────┬─────────┘     └────────┬─────────┘
            ▼                       ▼                        ▼
   ┌──────────────────┐    ┌──────────────────┐     ┌──────────────────┐
   │ orchestrator     │    │ RAG service      │     │ Agent router     │
   │ FastAPI :8001    │    │ FastAPI :8000    │     │ :11435           │
   └──────┬─────┬─────┘    └──────────────────┘     └────────┬─────────┘
          │     │                                             ▼
          │     └──────────────────────────────┐    ┌──────────────────┐
          ▼                                    ▼    │ Ollama daemon    │
   ┌──────────────┐                    ┌──────────┐ │ :11434           │
   │ Docker       │                    │ RAG API  │ └──────────────────┘
   │ sandbox      │                    │ imported │
   └──────────────┘                    └──────────┘
```

### Important runtime distinction

There are two local model paths:

1. **UI chat/status:** `client_ui` proxies to the agent router at `127.0.0.1:11435`; the router connects to Ollama at `127.0.0.1:11434`.
2. **Agent tasks:** `orchestrator` calls Ollama directly at `127.0.0.1:11434` for triage, planning, evaluation, and direct chat. Its RAG and sandbox tools are imported in-process.

The orchestrator routes triage, planning, critic, and direct-chat requests
through the agent router's OpenAI-compatible `/v1/chat/completions` endpoint.

| Component | Runtime | Default port | Responsibility |
|---|---|---:|---|
| `client_ui` | Next.js | usually `3000` | User interface and service proxies |
| `orchestrator` | FastAPI/Uvicorn | `8001` | Agent lifecycle and tool execution |
| `RAG` | FastAPI/Uvicorn | `8000` | Ingestion, indexing, and retrieval |
| Agent router | `ollama-agent-router` | `11435` | Model routing, queueing, and status |
| Ollama | Local daemon | `11434` | Model inference |
| `sandbox` | Docker | none | Isolated Python execution |

---

## 2. Client UI

`client_ui` is a Next.js 14 application using React 18, TypeScript, Tailwind CSS, IBM Plex fonts, and Lucide icons.

### Main layout

`app/page.tsx` renders three panels:

```text
┌────────────────┬──────────────────────────────┬──────────────────┐
│ StatusRail     │ ChatPanel                    │ ContextPanel     │
│ Router status  │ Prompt, uploads, agent trace │ Documents/search │
│ Model list     │ Plan, approval, final output │ Retrieved chunks │
└────────────────┴──────────────────────────────┴──────────────────┘
```

### Status rail

`components/status-rail.tsx` polls `/api/status` every eight seconds and shows router availability, configured models, model purposes, and local compute information. The status route queries:

```text
GET http://127.0.0.1:11435/v1/router/models
GET http://127.0.0.1:11435/v1/router/gpu
```

The router URL is configurable through `ROUTER_URL`.

The left rail also lists known workbench sessions and provides a new-session
control. Switching sessions changes the active session ID and refreshes the
chat history, document list, and RAG context for that workspace.

### Chat panel

`components/chat-panel.tsx` supports:

- Natural-language task submission.
- Multiple `.pdf`, `.docx`, and `.xlsx` uploads.
- Knowledge-base listing and deletion.
- Document-list reconciliation every five seconds and on window focus.
- Agent plan visualization.
- Trace polling every 250 milliseconds while a task is active.
- Human approval for paused `write_docx` steps.
- Final deliverable display.
- Stop button for active agent queries.
- Mock terminal output for complete tool and sandbox results.

For simple conversational tasks, the output is streamed progressively. The
orchestrator requests Ollama's NDJSON response stream, appends each received
token to `AgentState.final_deliverable`, and exposes the partial value through
the existing trace endpoint. `ChatPanel` polls that endpoint every 250 ms, so
the answer appears while the model is generating instead of after the complete
response arrives. Complex tool steps continue to report progress through the
same trace mechanism.

Chat flow:

```text
User prompt
   │
   ├── files → POST /api/rag/ingest → RAG /ingest
   │
        └── text  → search RAG → POST /api/agent/task → orchestrator
                                      │
                                      ▼
                              task_id returned
                                      │
                                      ▼
                         poll /api/agent/{id}/trace
                                      │
                                      ├── partial `final_deliverable` updates
                                      ▼
                        render plan, trace, terminal output, status, result
```

### Context panel

`components/context-panel.tsx` lists documents, sends direct RAG searches, renders retrieved text with source/page metadata, and deletes documents. It refreshes the authoritative list every five seconds and on window focus, so entries removed externally do not remain visible. A stale row is also removed locally when deletion returns `404`.

### Next.js proxy routes

The browser uses same-origin routes; the Next.js server forwards requests to local backend services.

| UI route | Target | Purpose |
|---|---|---|
| `POST /api/chat` | Router `/v1/chat/completions` | Routed chat |
| `GET /api/status` | Router model/GPU endpoints | Router status |
| `POST /api/rag` | RAG `/query` | Search documents |
| `POST /api/rag/ingest` | RAG `/ingest` | Upload and index files |
| `GET /api/documents` | RAG `/documents` | List files |
| `DELETE /api/documents/{filename}` | RAG delete endpoint | Remove file/index data |
| `POST /api/agent/task` | Orchestrator task endpoint | Start agent task |
| `GET /api/agent/{taskID}/trace` | Orchestrator trace endpoint | Poll task |
| `POST /api/agent/{taskID}/resume` | Orchestrator resume endpoint | Approve task |
| `POST /api/agent/{taskID}/cancel` | Orchestrator cancel endpoint | Stop active task |
| `GET /api/rag/ingest/status` | RAG `/ingest/status` | Wait for indexing |

Environment overrides:

```text
ROUTER_URL=http://127.0.0.1:11435
RAG_URL=http://127.0.0.1:8000
RAG_SERVICE_URL=http://127.0.0.1:8000
ORCHESTRATOR_URL=http://127.0.0.1:8001
```

---

## 3. Orchestrator

The orchestrator is implemented in `orchestrator/main.py` and exposes:

```text
POST /api/agent/task
GET  /api/agent/{task_id}/trace
POST /api/agent/{task_id}/resume
POST /api/agent/{task_id}/cancel
```

### Task lifecycle

```text
initializing → planning → executing → completed
                              │
                              ├──────────────► failed
                              ├──────────────► cancelled
                              │
                              └── write_docx → paused → approval → executing
```

`AgentState`, `PlanStep`, and `TaskRequest` are defined in `models.py`. Active
handles remain in memory, while task snapshots and session activity are stored
in SQLite. Completed and paused task records survive an orchestrator restart;
currently running asyncio handles must still be resumed or recreated by the
application after a process restart.

### Intent routing

`agent.py` first checks `_looks_complex()` for explicit terms such as `sandbox`, `search_rag`, `read_file`, and `write_docx`.

If no explicit tool keyword is found, `qwen3:4b` classifies the prompt as `SIMPLE` or `COMPLEX`:

```text
SIMPLE  → one direct_chat step using qwen3:4b
COMPLEX → qwen3:8b generates a JSON tool plan
```

Available planner tools:

```text
search_rag
read_file
python_sandbox
write_docx
```

Planner output is parsed, normalized, and converted into Pydantic `PlanStep` objects. Invalid output is rejected or converted into a safe fallback rather than being trusted blindly.

### Execution and critic loop

```text
Generate plan
      │
      ▼
Execute current tool
      │
      ▼
Capture observation
      │
      ▼
qwen3:8b evaluates observation
      │
      ├── passed → next step
      └── failed → task failed
```

Ollama is called directly at `http://127.0.0.1:11434/api/generate`. The orchestrator pre-warms `qwen3:4b` for triage/direct chat and `qwen3:8b` for planning and critique in a background startup task.

### Direct-chat streaming

The `direct_chat` fast path uses Ollama with `stream: true`. Ollama returns
newline-delimited JSON objects containing response fragments. The orchestrator
reads those fragments asynchronously and updates `AgentState.final_deliverable`
after each non-empty fragment:

```text
Ollama NDJSON stream
        │
        ▼
stream_direct_chat()
        │ append token
        ▼
AgentState.final_deliverable
        │
        ▼
GET /api/agent/{task_id}/trace
        │ poll every 250 ms
        ▼
ChatPanel renders partial answer
```

This is application-level streaming over the existing polling endpoint. The
browser does not hold an open streaming connection; it receives progressively
updated task snapshots. Planner, critic, and tool calls remain non-streaming.

### Human approval

The first unapproved `write_docx` step changes the task to `paused`. The UI displays an approval button. `/resume` sets `human_approved=True` on the current step and reruns the loop so that the step executes instead of being skipped. The stop button calls `/cancel`, marks the task `cancelled`, and cancels the active asyncio task, including an in-flight streamed Ollama response.

### Tool dispatcher

`orchestrator/tools.py` validates arguments and dispatches as follows:

| Tool | Current implementation |
|---|---|
| `direct_chat` | Calls Ollama with `qwen3:4b` |
| `search_rag` | Imports and calls `RAG/rag.py::query_rag` |
| `python_sandbox` | Calls `sandbox.executor.run_sandboxed` |
| `read_file` | Reads an allowed workspace/session document with a 500KB cap |
| `write_docx` | Creates a session-scoped DOCX under `RAG/sessions/<session-id>/outputs/` |

The RAG and sandbox calls are in-process Python calls, not HTTP calls.

### Document-grounded agent requests

Requests mentioning PDFs, attached/uploaded documents, problem statements, or the knowledge base are routed deterministically to `search_rag`. Retrieved excerpts are then supplied to a final streaming answer prompt. If the planner returns a malformed bare string, it is treated as a RAG query rather than as a direct-chat prompt about a filename.

The UI waits for `/ingest/status` to report that indexing is complete before starting a task that follows an upload.

---

## 4. RAG Service

The RAG service lives in `RAG/` and is started from that directory:

```powershell
python -m uvicorn rag_server:app --port 8000
```

It is both a FastAPI service and an importable Python pipeline used by the orchestrator.

### Session-specific storage

RAG data is stored below `RAG/sessions/` instead of one global document/index
directory:

```text
RAG/sessions/
├── session-.../
│   ├── documents/
│   └── data/
│       ├── faiss.index
│       ├── chunks_meta.json
│       └── bm25.pkl
└── another-session-/
```

The session ID is received through the `X-Session-ID` header. Ingestion
status, document listing, querying, and deletion all resolve paths within the
active session. Orchestrator task traces, resume, and cancellation also verify
that the task belongs to the requesting session.

### Endpoints

```text
POST /ingest
GET  /ingest/status
POST /query
GET  /health
GET  /documents
DELETE /documents/{filename}
```

### Supported documents

- `.pdf`: PyMuPDF extraction.
- `.docx`: `python-docx` paragraph/table extraction.
- `.xlsx`: pandas worksheet/row extraction.

PDFs with very little extracted text attempt an optional `ocrmac` fallback. If `ocrmac` is unavailable, ingestion continues without OCR. `Pillow` is used for image conversion in that path.

### Ingestion flow

```text
Multipart upload
      │
      ▼
Save supported files to RAG/sessions/<session-id>/documents/
      │
      ▼
Background ingestion worker
      │
      ▼
Extract logical pages/sheets
      │
      ▼
500-character chunks with 100-character overlap
      │
      ▼
Sentence-transformer embeddings
      │
      ├── FAISS index + metadata
      └── BM25 index when reranking is enabled
```

The upload endpoint returns while indexing continues. The UI polls `/ingest/status` before submitting a follow-up task. A second upload during ingestion saves the files and reports `queued` rather than starting a concurrent indexing job.

### Extraction and chunking

PDF records contain `text`, `source`, and one-based `page`. DOCX and XLSX records use page `-1`; XLSX records also retain the sheet name. Chunking is character-based, not heading-aware:

```text
chunk 1: characters 0–499
chunk 2: characters 400–899
chunk 3: characters 800–1299
```

Every chunk retains source/page metadata.

### Embeddings and FAISS

`embeddings.py` lazily loads and caches `all-MiniLM-L6-v2`. `vector_store.py` embeds all chunks, L2-normalizes vectors, stores them in FAISS `IndexFlatIP`, and saves matching metadata.

Artifacts:

```text
RAG/sessions/<session-id>/data/faiss.index
RAG/sessions/<session-id>/data/chunks_meta.json
RAG/sessions/<session-id>/data/bm25.pkl
```

The FAISS row number matches the corresponding entry in `chunks_meta.json`.

### Hybrid retrieval

Reranking is enabled in `RAG/config.py`:

```text
embedding model: all-MiniLM-L6-v2
candidate pool: 20
final top_k: 5
reranker: cross-encoder/ms-marco-MiniLM-L-6-v2
```

The retrieval pipeline is:

```text
Query
  │
  ├── embedding → FAISS dense candidates
  └── tokens    → BM25 lexical candidates
                       │
                       ▼
                Reciprocal Rank Fusion
                       │
                       ▼
                CrossEncoder reranking
                       │
                       ▼
                    top-k results
```

BM25 uses lowercased alphanumeric tokens. Reciprocal Rank Fusion combines dense and lexical rankings. The cross-encoder scores `(query, passage)` pairs and returns the final ranking.

RAG returns:

```json
{
  "query": "user question",
  "context": [
    {"text": "retrieved passage", "source": "manual.pdf", "page": 3, "score": 0.8123}
  ],
  "sources": [
    {"source": "manual.pdf", "page": 3}
  ]
}
```

RAG retrieves and formats context; it does not generate the final answer.

### Document deletion and stale data

Deleting a document removes its source file when present and removes every matching chunk from the FAISS metadata, FAISS index, and BM25 index. The remaining chunks are re-embedded and the indexes are rebuilt. Deleting the final document removes the persisted index artifacts. If a source file is already missing but indexed chunks remain, deletion still purges those chunks. The endpoint returns `removed_chunks`.

---

## 5. Ollama Agent Router

`ollama-agent-router.yaml` configures a router at `127.0.0.1:11435`, backed by Ollama at `127.0.0.1:11434`.

### Configured models

| Model | Purpose |
|---|---|
| `qwen3:0.6b` | Legacy low-cost fallback model |
| `qwen3:4b` | Simple chat and summarization |
| `qwen2.5-coder:7b` | Code generation, review, and fixes |
| `qwen3:8b` | Tool use, agentic reasoning, and large context |

### Routes

```text
triage            → qwen3:4b
simple_chat       → qwen3:4b
summarize         → qwen3:4b
code_generate     → qwen2.5-coder:7b
code_review       → qwen2.5-coder:7b
code_fix          → qwen2.5-coder:7b
agentic_reasoning → qwen3:8b
large_context     → qwen3:8b
tool_use          → qwen3:8b
unknown           → qwen3:0.6b
```

### Queue/resource configuration

```text
global concurrent jobs: 1
maximum queued jobs:    50
per-user queued jobs:   10
job attempts:           2
result TTL:             86400 seconds
model keep-alive:       3 minutes
request timeout:        300000 ms
```

The configuration contains Apple Silicon unified-memory assumptions and disables dedicated GPU monitoring. Review these values for Windows/NVIDIA deployments.

---

## 6. Sandbox

The sandbox prevents LLM-generated Python from executing inside the orchestrator process.

```text
Agent plan
   │
   ▼
execute_tool("python_sandbox", {"code": "..."})
   │
   ▼
run_sandboxed(code)
   │
   ▼
docker run mrpl-sandbox:latest
   │
   ├── code through stdin → python3 -
   ├── stdout/stderr captured
   └── formatted result returned to the agent critic
```

Each run uses a fresh container with:

```text
--network none
--cap-drop ALL
--security-opt no-new-privileges
--memory 256m
--memory-swap 256m
--cpus 1.0
--pids-limit 64
--rm
```

Additional controls:

- Non-root UID `1000`.
- No host filesystem mounts.
- No intentional API keys/project paths in the container environment.
- Ten-second wall-clock timeout.
- stdout and stderr capped at 1 MB each.
- Missing image is auto-built.
- Docker-unavailable execution never falls back to the host.

Build manually:

```powershell
docker build -t mrpl-sandbox:latest sandbox/
```

This is container-level isolation, not a complete hypervisor boundary. The detailed sandbox README documents limitations and further hardening options such as seccomp, read-only filesystems, gVisor, and image pinning.

---

## 7. End-to-End Flows

### Document upload

```text
User attaches PDF/DOCX/XLSX
        │
        ▼
client_ui POST /api/rag/ingest
        │
        ▼
Next.js proxy → RAG /ingest
        │
        ▼
RAG stores file and starts background ingestion
        │
        ▼
Extract → chunk → embed → FAISS/BM25
        │
        ▼
UI refreshes document list
```

### Direct document search

```text
User enters query
        │
        ▼
client_ui POST /api/rag
        │
        ▼
RAG /query
        │
        ▼
FAISS + BM25 + RRF + cross-encoder
        │
        ▼
ContextPanel renders passages and sources
```

### Agent task

```text
User enters task
        │
        ▼
client_ui POST /api/agent/task
        │
        ▼
Orchestrator creates AgentState
        │
        ├── explicit tool keyword → COMPLEX
        └── otherwise qwen3:4b triage
                         │
                         ▼
                  SIMPLE or COMPLEX
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
   qwen3:4b direct chat          qwen3:8b plan
                                        │
                                        ▼
                              execute tools sequentially
                                        │
                                        ▼
                              critic evaluates each step
                                        │
                         completed / failed / paused
```

### RAG-backed agent task

```text
Planner creates search_rag step
        │
        ▼
tools.py calls RAG/rag.py::query_rag
        │
        ▼
Retrieved excerpts become tool observation
        │
        ▼
Critic evaluates the step
```

### Sandboxed code task

```text
Planner creates python_sandbox step
        │
        ▼
tools.py validates code
        │
        ▼
Docker container executes code with restrictions
        │
        ▼
Capped output returns to the critic
```

---

## 8. Startup and Development

### Windows

`start.ps1` opens four PowerShell windows:

```text
client_ui     → npm run dev
orchestrator  → .venv\Scripts\python.exe -m uvicorn orchestrator.main:app --port 8001 --reload
RAG service   → .venv\Scripts\python.exe -m uvicorn rag_server:app --port 8000
router        → ollama-agent-router serve --config ollama-agent-router.yaml
```

Run from the project root:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\start.ps1
```

Individual commands:

```powershell
Set-Location client_ui
npm install
npm run dev

# From project root
.\.venv\Scripts\python.exe -m uvicorn orchestrator.main:app --port 8001 --reload

Set-Location RAG
..\.venv\Scripts\python.exe -m uvicorn rag_server:app --port 8000

Set-Location ..
ollama-agent-router serve --config .\ollama-agent-router.yaml
```

The RAG service must run with `RAG` as its working directory because its modules use local imports.

### macOS/Linux

`start.sh` launches the same services using macOS `Terminal.app` and `osascript`. It is not a native Windows script; use `start.ps1` on Windows.

### Dependencies

Python dependencies are listed in `requirements.txt`:

```text
pymupdf>=1.24.0
sentence-transformers>=3.0.0
faiss-cpu>=1.8.0
rank-bm25>=0.2.2
uvicorn
fastapi
python-docx
python-multipart
pandas
pillow
```

Install with:

```powershell
python -m pip install -r requirements.txt
```

Frontend dependencies are managed by `client_ui/package.json` and `package-lock.json`.

---

## 9. Project Structure

```text
SIH_AI_Workbench/
├── client_ui/
│   ├── app/
│   │   ├── api/                         # Next.js backend proxy routes
│   │   ├── layout.tsx
│   │   └── page.tsx                     # Application shell
│   ├── components/
│   │   ├── chat-panel.tsx               # Chat, uploads, task trace
│   │   ├── context-panel.tsx            # RAG search and documents
│   │   ├── status-rail.tsx              # Router/model status
│   │   └── ui/                          # UI primitives
│   ├── lib/api.ts                        # Typed client helpers
│   ├── lib/session.ts                    # Browser session identity
│   └── package.json
├── orchestrator/
│   ├── main.py                           # FastAPI endpoints
│   ├── agent.py                          # Triage/planning/execution loop
│   ├── models.py                         # Pydantic state models
│   └── tools.py                          # Tool dispatcher
├── RAG/
│   ├── rag_server.py                     # FastAPI endpoints
│   ├── rag.py                            # Importable RAG API and CLI
│   ├── ingest.py                         # Extraction and chunking
│   ├── embeddings.py                     # Embedding wrapper
│   ├── vector_store.py                   # FAISS persistence/search
│   ├── retrieve.py                       # Retrieval response formatter
│   ├── reranker.py                       # BM25, RRF, cross-encoder
│   ├── config.py                         # RAG settings
│   ├── session.py                         # Session-scoped paths
│   └── sessions/                         # Per-session documents/indexes/outputs
├── sandbox/
│   ├── executor.py                       # Docker execution boundary
│   ├── Dockerfile                        # Sandbox image
│   └── README.md                         # Security documentation
├── tests/
├── ollama-agent-router.yaml              # Router/model/queue config
├── requirements.txt
├── start.ps1
├── start.sh
├── mac_setup.sh
└── ollama_install.sh
```

---

## 10. Persistence and Limitations

### Persistent data

- Session-specific uploaded files: `RAG/sessions/<session-id>/documents/`.
- Session-specific FAISS vectors: `RAG/sessions/<session-id>/data/faiss.index`.
- Session-specific chunk metadata: `RAG/sessions/<session-id>/data/chunks_meta.json`.
- Session-specific BM25 index: `RAG/sessions/<session-id>/data/bm25.pkl`.
- Session-specific generated DOCX files: `RAG/sessions/<session-id>/outputs/`.
- Durable orchestrator database: `data/workbench.sqlite3`.

### In-memory data

- Orchestrator tasks and traces.
- Browser session selection and session list are currently process/browser scoped.
- Cached embedding model.
- Cached cross-encoder.
- Cached BM25 index.
- Background task references.

### Current limitations

- `read_file` is intentionally restricted to the workspace and uploaded session documents.
- The UI document list is reconciled against the RAG service rather than treated as permanent client state.
- There is no authentication, authorization, or durable task queue.
- The RAG service is local and rebuild-oriented.
- OCR depends on optional `ocrmac` availability.
- Router GPU settings contain Apple Silicon assumptions.
- CORS and local service security are development-oriented.

### Validation

Backend compilation:

```powershell
\.venv\Scripts\python.exe -m py_compile orchestrator/*.py RAG/*.py
```

Frontend production build:

```powershell
Set-Location client_ui
npm run build
```

---

## Summary

```text
User
  → Next.js client UI
  → proxy route
  → orchestrator for agent tasks
  → local Ollama models for triage/planning/critique
  → RAG for document context
  → Docker sandbox for generated Python
  → router for UI chat and model status
  → traceable result in the UI
```

The UI is the user-facing layer, the orchestrator coordinates multi-step work, RAG supplies grounded document context, the router selects local models for routed requests, Ollama performs inference, and the sandbox isolates generated code execution.
