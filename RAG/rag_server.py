import os
import shutil
from typing import List

from fastapi import FastAPI, UploadFile, File
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


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

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

    count = ingest_documents(DOCUMENTS_DIR)
    return {"files_saved": saved, "chunks_indexed": count}


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