import os
import shutil
import asyncio
from typing import List

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag import ingest_documents, query_rag
from session import documents_dir, normalize_session_id

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
app.state.ingest_in_progress = {}
app.state.last_ingest_result = {}

# NOTE: assumes `rag` exposes a `delete_document(filename)` that drops the
# file's chunks from the index. If it doesn't exist yet, the endpoint below
# still removes the file from disk and reports that the index wasn't
# touched, rather than silently doing nothing or crashing.
try:
    from rag import delete_document as rag_delete_document
except ImportError as e:
    print(f"Warning: Could not import delete_document. Error: {e}")
    rag_delete_document = None


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


def _run_ingest(directory: str, session_id: str):
    """Runs in a worker thread via run_in_executor — keeps the blocking
    parse/chunk/embed work off the event loop."""
    app.state.ingest_in_progress[session_id] = True
    try:
        count = ingest_documents(directory, session_id=session_id)
        app.state.last_ingest_result[session_id] = {"chunks_indexed": count, "error": None}
    except Exception as e:
        app.state.last_ingest_result[session_id] = {"chunks_indexed": 0, "error": str(e)}
    finally:
        app.state.ingest_in_progress[session_id] = False


@app.post("/ingest")
async def ingest(files: List[UploadFile] = File(...), x_session_id: str = Header("default")):
    session_id = normalize_session_id(x_session_id)
    directory = documents_dir(session_id)
    os.makedirs(directory, exist_ok=True)

    saved = []
    SUPPORTED_EXTS = (".pdf", ".docx", ".xlsx")

    for f in files:
        if not f.filename.lower().endswith(SUPPORTED_EXTS):
            continue  # or raise HTTPException(400, f"Unsupported file type: {f.filename}")
        dest = os.path.join(directory, f.filename)
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(f.filename)

    if app.state.ingest_in_progress.get(session_id, False):
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
    app.state.ingest_in_progress[session_id] = True
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_ingest, directory, session_id)

    return {"files_saved": saved, "status": "ingesting"}


@app.get("/ingest/status")
def ingest_status(x_session_id: str = Header("default")):
    session_id = normalize_session_id(x_session_id)
    return {
        "in_progress": app.state.ingest_in_progress.get(session_id, False),
        "last_result": app.state.last_ingest_result.get(session_id),
    }


@app.post("/query")
def query(req: QueryRequest, x_session_id: str = Header("default")):
    return query_rag(req.query, top_k=req.top_k, session_id=normalize_session_id(x_session_id))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/documents")
def list_documents(x_session_id: str = Header("default")):
    directory = documents_dir(normalize_session_id(x_session_id))
    if not os.path.isdir(directory):
        return {"files": []}
    files = sorted(
        f for f in os.listdir(directory)
        if f.lower().endswith((".pdf", ".docx", ".xlsx"))
    )
    return {"files": files}


@app.delete("/documents/{filename}")
def delete_document(filename: str, x_session_id: str = Header("default")):
    # Path traversal guard: filename must be a bare name, not a path that
    # could escape DOCUMENTS_DIR (e.g. "../../etc/passwd").
    if filename != os.path.basename(filename) or filename in ("", ".", ".."):
        raise HTTPException(status_code=400, detail=f"Invalid filename: {filename}")

    session_id = normalize_session_id(x_session_id)
    dest = os.path.join(documents_dir(session_id), filename)
    index_error = None
    removed_chunks = 0
    if rag_delete_document:
        try:
            removed_chunks = rag_delete_document(filename, session_id=session_id)
        except Exception as e:
            # Don't let an index-side failure block removing the file the
            # user asked to remove — report it instead so the caller knows
            # the index may be stale until the next full re-ingest.
            index_error = str(e)
    else:
        index_error = "rag.delete_document is not available; index not updated — a re-ingest will be needed to fully drop this file's chunks."

    file_exists = os.path.isfile(dest)
    if not file_exists and removed_chunks == 0:
        raise HTTPException(
            status_code=404,
            detail=f"'{filename}' was not found on disk or in the retrieval index.",
        )

    if file_exists:
        os.remove(dest)

    return {
        "status": "ok",
        "filename": filename,
        "index_updated": index_error is None,
        "removed_chunks": removed_chunks,
        "detail": index_error,
    }