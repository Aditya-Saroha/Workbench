"""
retrieve.py — Query the FAISS index and return structured results.

This module bridges vector_store.search() (which returns raw scored
chunks) and the clean JSON interface that the model router expects.

When hybrid retrieval is enabled (RERANKING_ENABLED=True), it uses
a two-stage pipeline:
  Stage 1: FAISS dense + BM25 lexical search, fused via RRF
  Stage 2: Cross-encoder reranking of the fused candidate pool

When disabled, it falls back to the original single-stage FAISS search.

It does NOT call an LLM or generate summaries — that is the router's
job.  This module only retrieves and formats.
"""

from vector_store import search
from config import TOP_K, RERANKING_ENABLED, CANDIDATE_POOL_SIZE


def retrieve(query: str, top_k: int = TOP_K) -> dict:
    """
    Accept a natural-language query, search the vector store, and return
    a structured dict ready for JSON serialisation.

    Returns:
        {
            "query": "user's question",
            "context": [
                {
                    "text": "relevant chunk ...",
                    "source": "inspection_sop.pdf",
                    "page": 14,
                    "score": 0.81
                },
                ...
            ],
            "sources": [
                {"source": "inspection_sop.pdf", "page": 14},
                ...
            ]
        }

    Design notes:
        - `context` contains the full chunk text + metadata + score,
          ordered by descending relevance.
        - `sources` is a deduplicated list of (source, page) pairs for
          quick citation without reading every chunk.
        - The router can iterate `context` to build its LLM prompt and
          use `sources` for the citation footer.
    """
    if RERANKING_ENABLED:
        # Two-stage hybrid retrieval
        from reranker import hybrid_search

        # Stage 1a: Get a larger candidate pool from FAISS
        pool_size = max(CANDIDATE_POOL_SIZE, top_k)
        dense_results = search(query, top_k=pool_size)

        # Stages 1b + 2: BM25 fusion + cross-encoder reranking
        results = hybrid_search(query, top_k=top_k, dense_results=dense_results)
    else:
        # Original single-stage FAISS retrieval
        raw_results = search(query, top_k=top_k)
        results = [
            {
                "text": r["text"],
                "source": r["source"],
                "page": r["page"],
                "score": round(r["score"], 4),
            }
            for r in raw_results
        ]

    context = results

    # Deduplicated sources, preserving retrieval order
    seen = set()
    sources = []
    for r in results:
        key = (r["source"], r["page"])
        if key not in seen:
            seen.add(key)
            sources.append({"source": r["source"], "page": r["page"]})

    return {
        "query": query,
        "context": context,
        "sources": sources,
    }


# ─── CLI entry-point ──────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    query = "What safety equipment is needed for inspections?"
    print(f"Query: {query}\n")
    result = retrieve(query, top_k=3)
    print(json.dumps(result, indent=2, ensure_ascii=False))
