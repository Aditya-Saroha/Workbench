# MRPL AI Workbench — UI

Minimalist operator-console UI for the router + RAG components. Three panels:
system status (left), task interaction (center), retrieved knowledge-base
context (right).

## Run it

```
npm install
npm run dev
```

Opens at http://localhost:3000. Two backend services this UI expects to be
running alongside it:

**1. The router** (port 11435) — from your `SIH_AI_Workbench` folder:
```
ollama-agent-router serve --config ollama-agent-router.yaml
```

**2. The RAG service** (port 8000) — this doesn't exist yet as an HTTP
service; `rag_server.py` in this folder wraps your existing `rag.py` with
FastAPI. Copy it into your `rag/` folder and run:
```
pip install fastapi uvicorn
uvicorn rag_server:app --port 8000
```

If either service isn't running, the UI stays usable and shows a clear
"unreachable" state rather than crashing — check the left rail for router
status, and the right panel will show a plain-language error if RAG queries
fail.

## What's real vs. stubbed

- **Left rail model list** comes live from the router's own
  `/v1/router/models` and `/v1/router/gpu` endpoints — not hardcoded.
- **Chat panel** calls the router's actual `/v1/chat/completions` and shows
  the real `router` object (task type, selected model, decision reason,
  latency) under each response.
- **Context panel** calls your friend's real RAG pipeline once
  `rag_server.py` is running.
- Nothing here calls out to the internet — both proxy routes only ever talk
  to `127.0.0.1`.

## Next integration point

The agent loop (when you build it) should follow the same pattern as this
UI: call the router over HTTP for model selection, call the RAG service over
HTTP for retrieval, and treat both as tools rather than importing anything
directly. Keeping that consistent is what let this UI get built without
needing to know anything about how either backend works internally.
