# Drop this file into your `rag/` folder (alongside rag.py) and run it with:
#   pip install fastapi uvicorn
#   uvicorn rag_server:app --port 8000
#
# This exposes your existing query_rag() / ingest_documents() functions
# over HTTP so the Next.js UI (or your future agent loop) can call them
# the same way it calls the router — no direct Python imports needed
# outside this process.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag import ingest_documents, query_rag

app = FastAPI(title="MRPL RAG Service")

# Next.js dev server runs on :3000; loosen this once you know your
# deployment origin(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class IngestRequest(BaseModel):
    directory: str = "documents/"


@app.post("/ingest")
def ingest(req: IngestRequest):
    count = ingest_documents(req.directory)
    return {"chunks_indexed": count}


@app.post("/query")
def query(req: QueryRequest):
    return query_rag(req.query, top_k=req.top_k)


@app.get("/health")
def health():
    return {"status": "ok"}
