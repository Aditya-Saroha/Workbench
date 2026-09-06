"""
rag.py — Top-level API for the local RAG pipeline.

This is the single entry-point that another component (e.g. the Ollama-
based model router) should import and call.

Usage from Python:

    from rag import query_rag, ingest_documents

    # One-time: ingest PDFs and build the vector index
    ingest_documents()

    # Per query: retrieve relevant context
    result = query_rag("What PPE is required for chemical handling?")
    # result is a dict with keys: query, context, sources

Usage from the command line:

    # Ingest
    python rag.py --ingest

    # Query
    python rag.py --query "What PPE is required for chemical handling?"

    # Both
    python rag.py --ingest --query "How to handle a spill?"
"""

import json
from config import TOP_K, DOCUMENTS_DIR
from ingest import ingest_pdfs
from vector_store import build_index, clear_index, load_index
from reranker import invalidate_cache
from retrieve import retrieve


# ─── Public API ───────────────────────────────────────────────────────

def ingest_documents(directory: str = DOCUMENTS_DIR) -> int:
    """
    Ingest all PDFs from `directory`, embed them, and build the FAISS
    index.  Call this once (or whenever documents change).

    Returns the number of chunks indexed.
    """
    chunks = ingest_pdfs(directory)
    if not chunks:
        print("⚠️  No chunks produced. Check that PDFs exist in the documents/ folder.")
        return 0
    build_index(chunks)
    return len(chunks)


def query_rag(query: str, top_k: int = TOP_K) -> dict:
    """
    Retrieve the most relevant chunks for a natural-language query.

    Returns a dict:
        {
            "query": "...",
            "context": [ { "text", "source", "page", "score" }, ... ],
            "sources": [ { "source", "page" }, ... ]
        }

    The router can use `context` entries to build an LLM prompt and
    `sources` for citations.
    """
    return retrieve(query, top_k=top_k)


def delete_document(filename: str) -> int:
    """Remove one source document and all of its chunks from every index.

    The source file is deleted by ``rag_server``. This function only updates
    persisted retrieval data, using the exact stored basename as identity.
    Returns the number of removed chunks.
    """
    try:
        _, chunks = load_index()
    except FileNotFoundError:
        return 0

    remaining = [chunk for chunk in chunks if chunk.get("source") != filename]
    removed = len(chunks) - len(remaining)
    if removed == 0:
        return 0

    if remaining:
        build_index(remaining)
    else:
        clear_index()

    invalidate_cache()
    return removed


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Local RAG pipeline — ingest documents and/or query them."
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Ingest PDFs from the documents/ folder and rebuild the FAISS index.",
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=None,
        help="Natural-language query to retrieve relevant context for.",
    )
    parser.add_argument(
        "--top-k", "-k",
        type=int,
        default=TOP_K,
        help=f"Number of chunks to retrieve (default: {TOP_K}).",
    )

    args = parser.parse_args()

    if not args.ingest and args.query is None:
        parser.print_help()
        raise SystemExit(1)

    if args.ingest:
        count = ingest_documents()
        print(f"\n{'─' * 40}")
        print(f"Ingestion complete: {count} chunks indexed.\n")

    if args.query:
        result = query_rag(args.query, top_k=args.top_k)
        print(json.dumps(result, indent=2, ensure_ascii=False))
