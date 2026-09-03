"""
vector_store.py — Build, save, load, and search a FAISS vector index.

FAISS (Facebook AI Similarity Search) stores the embedding vectors and
lets us find the most similar chunks to a query in milliseconds.

We use IndexFlatIP (inner-product / cosine similarity on normalized
vectors) — the simplest FAISS index. It does a brute-force search which
is plenty fast for thousands of chunks on a laptop. For millions of
chunks you'd switch to an approximate index like IndexIVFFlat, but
that's unnecessary for this prototype.

The index is saved alongside a JSON metadata file that maps each FAISS
row number back to the original chunk dict (text, source, page).
"""

import json
import os
import numpy as np
import faiss
from config import DATA_DIR, TOP_K, RERANKING_ENABLED
from embeddings import embed_texts, embed_query, get_embedding_dimension

# ─── File paths ───────────────────────────────────────────────────────
INDEX_PATH = os.path.join(DATA_DIR, "faiss.index")
META_PATH = os.path.join(DATA_DIR, "chunks_meta.json")


# ─── Build & Save ─────────────────────────────────────────────────────

def build_index(chunks: list[dict]) -> faiss.Index:
    """
    Given a list of chunk dicts (each with a "text" key), embed them
    all and build a FAISS index.

    Steps:
        1. Extract the text from each chunk.
        2. Embed all texts in one batch.
        3. L2-normalize the vectors (so inner-product = cosine similarity).
        4. Add them to a FAISS IndexFlatIP.
        5. Save the index and metadata to disk.

    Returns the FAISS index object.
    """
    texts = [c["text"] for c in chunks]
    print(f"🔢 Embedding {len(texts)} chunks...")
    vectors = embed_texts(texts)

    # Normalize so inner-product search = cosine similarity
    faiss.normalize_L2(vectors)

    dim = vectors.shape[1]
    index = faiss.IndexFlatIP(dim)  # inner-product index
    index.add(vectors)

    print(f"✅ FAISS index built: {index.ntotal} vectors, {dim} dimensions")

    # Save index
    faiss.write_index(index, INDEX_PATH)
    print(f"💾 Index saved to {INDEX_PATH}")

    # Save metadata (everything except "text" is small; we save full chunks
    # so retrieval can return source, page, AND text without re-reading PDFs)
    with open(META_PATH, "w") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    print(f"💾 Metadata saved to {META_PATH}")

    # Build BM25 index for hybrid retrieval (if reranking is enabled)
    if RERANKING_ENABLED:
        from reranker import build_bm25, invalidate_cache
        build_bm25(chunks)
        invalidate_cache()  # clear any stale in-memory cache

    return index


# ─── Load ─────────────────────────────────────────────────────────────

def load_index() -> tuple[faiss.Index, list[dict]]:
    """
    Load a previously saved FAISS index and its chunk metadata from disk.

    Returns (index, chunks_meta).
    """
    if not os.path.exists(INDEX_PATH):
        raise FileNotFoundError(
            f"No FAISS index found at {INDEX_PATH}. Run build_index() first."
        )
    if not os.path.exists(META_PATH):
        raise FileNotFoundError(
            f"No metadata found at {META_PATH}. Run build_index() first."
        )

    index = faiss.read_index(INDEX_PATH)
    with open(META_PATH, "r") as f:
        chunks_meta = json.load(f)

    print(f"📂 Loaded FAISS index: {index.ntotal} vectors")
    print(f"📂 Loaded metadata: {len(chunks_meta)} chunks")
    return index, chunks_meta


# ─── Search ───────────────────────────────────────────────────────────

def search(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    Embed a query, search the FAISS index, and return the top-k most
    similar chunks with their similarity scores.

    Returns a list of dicts:
        [
            {
                "text": "chunk text...",
                "source": "file.pdf",
                "page": 3,
                "score": 0.8123
            },
            ...
        ]
    """
    index, chunks_meta = load_index()

    # Embed and normalize the query
    q_vec = embed_query(query).reshape(1, -1)
    faiss.normalize_L2(q_vec)

    # Search
    scores, indices = index.search(q_vec, min(top_k, index.ntotal))

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue  # FAISS returns -1 for unfilled slots
        chunk = chunks_meta[idx].copy()
        chunk["score"] = float(score)
        results.append(chunk)

    return results


# ─── CLI entry-point ──────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Build the index from chunks.json, then run a test query.

    Usage:
        python vector_store.py
    """
    # Load chunks from Phase 1
    chunks_path = os.path.join(DATA_DIR, "chunks.json")
    with open(chunks_path, "r") as f:
        chunks = json.load(f)

    # Build and save
    index = build_index(chunks)

    # Test search
    print("\n── Test search ──")
    query = "What safety equipment is required for chemical handling?"
    print(f"Query: {query}\n")

    results = search(query, top_k=3)
    for i, r in enumerate(results, 1):
        print(f"  Result {i} (score={r['score']:.4f}):")
        print(f"    Source: {r['source']} page {r['page']}")
        print(f"    Text:   {r['text'][:100]}...")
        print()
