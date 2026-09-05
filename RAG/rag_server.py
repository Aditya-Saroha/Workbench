import os
import shutil
import asyncio
from typing import List

from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag import ingest_documents, query_rag
from config import DOCUMENTS_DIR

app = FastAPI(title="MRPL RAG Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tracks whether an ingestion job is currently running, so callers (or the
# orchestrator, if you wire it up) can tell "still indexing" apart from
# "something is stuck".
app.state.ingest_in_progress = False
app.state.last_ingest_result = None


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


def _run_ingest(directory: str):
    """Runs in a worker thread via run_in_executor — keeps the blocking
    parse/chunk/embed work off the event loop."""
    app.state.ingest_in_progress = True
    try:
        count = ingest_documents(directory)
        app.state.last_ingest_result = {"chunks_indexed": count, "error": None}
    except Exception as e:
        app.state.last_ingest_result = {"chunks_indexed": 0, "error": str(e)}
    finally:
        app.state.ingest_in_progress = False


@app.post("/ingest")
async def ingest(files: List[UploadFile] = File(...)):
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)

    saved = []
    SUPPORTED_EXTS = (".pdf", ".docx", ".xlsx")

    for f in files:
        if not f.filename.lower().endswith(SUPPORTED_EXTS):
            continue  # or raise HTTPException(400, f"Unsupported file type: {f.filename}")
        dest = os.path.join(DOCUMENTS_DIR, f.filename)
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(f.filename)

    if app.state.ingest_in_progress:
        # Don't stack a second ingestion run on top of one still in flight —
        # that would only make Ollama contention worse. Files are already
        # saved to disk, so a follow-up ingest call will pick them up.
        return {
            "files_saved": saved,
            "status": "queued",
            "detail": "An ingestion job is already running; files were saved and will be picked up next run.",
        }

    # Offload the blocking parse/chunk/embed pipeline to a worker thread so
    # this route (and this service's event loop) stays responsive, and so
    # the HTTP response returns immediately instead of holding the
    # connection open for the full ingestion duration.
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_ingest, DOCUMENTS_DIR)

    return {"files_saved": saved, "status": "ingesting"}


@app.get("/ingest/status")
def ingest_status():
    return {
        "in_progress": app.state.ingest_in_progress,
        "last_result": app.state.last_ingest_result,
    }


@app.post("/query")
def query(req: QueryRequest):
    return query_rag(req.query, top_k=req.top_k)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/documents")
def list_documents():
    if not os.path.isdir(DOCUMENTS_DIR):
        return {"files": []}
    files = sorted(
        f for f in os.listdir(DOCUMENTS_DIR)
        if f.lower().endswith((".pdf", ".docx", ".xlsx"))
    )
    return {"files": files}