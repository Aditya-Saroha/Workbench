# Local RAG Pipeline — SIH Project

A lightweight, completely local RAG (Retrieval-Augmented Generation) component for the Sovereign On-Premise Agentic AI Workbench.

**Everything runs locally. No data ever leaves your machine.**

---

## Project File Tree

```
rag/
├── documents/                ← Drop your PDFs here
│   ├── safety_manual.pdf          (sample)
│   └── sample_inspection_sop.pdf  (sample)
├── data/                     ← Generated at runtime
│   ├── chunks.json                Raw chunks from ingestion
│   ├── chunks_meta.json           Chunk metadata for FAISS rows
│   └── faiss.index                FAISS vector index
│
│── PRODUCTION CODE ──────────────────────────────────────
├── config.py                 Central configuration (paths, model, chunk params)
├── ingest.py                 PDF text extraction + chunking
├── embeddings.py             Local embedding generation (all-MiniLM-L6-v2)
├── vector_store.py           FAISS index build, save, load, search
├── retrieve.py               Query → structured JSON formatting
├── rag.py                    Top-level public API + CLI
├── requirements.txt          Python dependencies
│
│── TEST / VERIFICATION ──────────────────────────────────
├── create_sample_pdf.py      Generates sample_inspection_sop.pdf (3 pages)
├── create_sample_pdf_2.py    Generates safety_manual.pdf (2 pages)
├── verify_phase1.py          Tests for PDF extraction + chunking
├── verify_phase2.py          Tests for embeddings + FAISS
├── verify_phase3.py          Tests for end-to-end query → JSON pipeline
│
└── README.md
```

### Production code (6 files, 636 lines total)

| File | Lines | Role |
|------|------:|------|
| `config.py` | 35 | All tuneable parameters in one place |
| `ingest.py` | 161 | PDF → pages → overlapping chunks with source/page metadata |
| `embeddings.py` | 86 | Sentence-Transformers model loading + batch/single encoding |
| `vector_store.py` | 162 | FAISS IndexFlatIP — build, persist, load, cosine search |
| `retrieve.py` | 82 | Format search results into the router-compatible JSON schema |
| `rag.py` | 110 | Public API entry-point (`ingest_documents`, `query_rag`) + CLI |

### Test / verification files (5 files)

| File | Purpose |
|------|---------|
| `create_sample_pdf.py` | Generate a 3-page industrial inspection SOP test PDF |
| `create_sample_pdf_2.py` | Generate a 2-page chemical safety manual test PDF |
| `verify_phase1.py` | 10 tests — JSON validity, chunk fields, page ranges, overlap |
| `verify_phase2.py` | 22 tests — embedding shape/dtype, determinism, FAISS build, search |
| `verify_phase3.py` | 21 tests — end-to-end structure, types, ordering, relevance, CLI |

---

## Quick Start

```bash
cd rag/
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Generate sample test PDFs (or place your own PDFs in documents/)
python create_sample_pdf.py
python create_sample_pdf_2.py

# Ingest + build index + query — all in one
python rag.py --ingest --query "What PPE is required for chemical handling?"
```

---

## Configuration

Edit `config.py` to change:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CHUNK_SIZE` | `500` | Characters per chunk |
| `CHUNK_OVERLAP` | `50` | Overlap between consecutive chunks |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-Transformers model name |
| `TOP_K` | `5` | Default chunks returned per query |

---

## How It Works

```
documents/*.pdf
       │
       ▼
 ┌─────────────┐
 │  ingest.py   │  PyMuPDF extracts text page-by-page,
 │              │  then splits into ~500-char overlapping chunks.
 └──────┬───────┘  Each chunk carries {text, source, page}.
        │
        ▼
 ┌──────────────┐
 │ embeddings.py │  all-MiniLM-L6-v2 encodes each chunk
 │              │  into a 384-dim float32 vector.
 └──────┬───────┘
        │
        ▼
 ┌────────────────┐
 │ vector_store.py │  L2-normalise vectors, add to FAISS
 │                │  IndexFlatIP, save index + metadata to disk.
 └──────┬─────────┘
        │
        ▼
 ┌──────────────┐
 │  retrieve.py  │  Embed query → FAISS search → format into
 │              │  structured {query, context, sources} dict.
 └──────┬───────┘
        │
        ▼
 ┌──────────────┐
 │    rag.py     │  Public API: ingest_documents() / query_rag()
 └──────────────┘  ← Your teammate's router calls this
```

---

## RAG → Router Integration Contract

This section defines the exact interface between this RAG component and the Ollama-based model router.

### Python API

```python
from rag import ingest_documents, query_rag
```

#### `ingest_documents(directory="documents/") → int`

Scans the directory for PDFs, extracts text, chunks it, generates embeddings, and builds the FAISS index. Call once at startup or whenever documents change.

Returns the number of chunks indexed.

```python
chunk_count = ingest_documents()           # uses default documents/ folder
chunk_count = ingest_documents("/path/to/pdfs")  # custom folder
```

#### `query_rag(query: str, top_k: int = 5) → dict`

Accepts a natural-language query, searches the FAISS index, and returns a structured dict. Does **not** call any LLM — the router is responsible for prompt construction and model selection.

```python
result = query_rag("What PPE is required for chemical handling?")
result = query_rag("How to handle a spill?", top_k=3)
```

### CLI

```bash
# Ingest documents
python rag.py --ingest

# Query (prints JSON to stdout)
python rag.py --query "What PPE is required?" --top-k 3

# Both
python rag.py --ingest --query "What PPE is required?"
```

### Output JSON Schema

`query_rag()` returns a Python dict with this exact structure:

```json
{
  "query": "user's original question",
  "context": [
    {
      "text": "the relevant chunk of text from the document",
      "source": "filename.pdf",
      "page": 2,
      "score": 0.7226
    }
  ],
  "sources": [
    {
      "source": "filename.pdf",
      "page": 2
    }
  ]
}
```

#### Field definitions

| Field | Type | Description |
|-------|------|-------------|
| `query` | `str` | The original query string, echoed back |
| `context` | `list[dict]` | Relevant chunks, ordered by descending `score` |
| `context[].text` | `str` | The chunk text (≤ `CHUNK_SIZE` characters) |
| `context[].source` | `str` | Source PDF filename |
| `context[].page` | `int` | 1-indexed page number within the source PDF |
| `context[].score` | `float` | Cosine similarity score in the range [−1, 1] |
| `sources` | `list[dict]` | Deduplicated `(source, page)` pairs from `context`, preserving retrieval order |
| `sources[].source` | `str` | Source PDF filename |
| `sources[].page` | `int` | 1-indexed page number |

#### Guarantees

- `context` contains at most `top_k` entries (clamped to total indexed chunks).
- `context` is sorted by `score` descending (most relevant first).
- `sources` contains no duplicate `(source, page)` pairs.
- Every `(source, page)` in `sources` appears in at least one `context` entry.
- `score` values are cosine similarities (L2-normalised inner product). Higher = more relevant.
- The output is JSON-serialisable via `json.dumps()`.

### Example: Router prompt construction

The router can use the RAG output to build an Ollama prompt like this:

```python
import json
from rag import query_rag

result = query_rag(user_question, top_k=5)

# Build the context block for the LLM prompt
context_block = ""
for i, chunk in enumerate(result["context"], 1):
    context_block += f"[{i}] (Source: {chunk['source']}, Page {chunk['page']})\n"
    context_block += f"{chunk['text']}\n\n"

# Build the citation list
citations = ", ".join(
    f"{s['source']} p.{s['page']}" for s in result["sources"]
)

# Construct the final prompt for Ollama
prompt = f"""Answer the following question using ONLY the provided context.
Cite sources where applicable.

Context:
{context_block}

Sources: {citations}

Question: {result['query']}

Answer:"""

# Send `prompt` to Ollama via the router
```

---

## Roadmap

- [x] Phase 1: PDF extraction + chunking
- [x] Phase 2: Local embeddings (all-MiniLM-L6-v2) + FAISS vector search
- [x] Phase 3: Structured JSON retrieval API
- [ ] Phase 4: DOCX / scanned PDF (OCR) support
- [ ] Phase 5: Agent integration hooks
