"""
reranker.py — BM25 lexical search + cross-encoder reranking for hybrid retrieval.

This module adds two capabilities to the existing FAISS-based dense retrieval:

1. BM25 Lexical Search:
   A token-overlap-based retrieval that captures exact keyword matches
   the dense bi-encoder may miss (e.g. "cylinder lubricant" vs "cylinder oil").

2. Cross-Encoder Reranking:
   A lightweight cross-encoder that scores (query, passage) pairs jointly
   with full attention, producing more accurate relevance scores than
   the bi-encoder used for initial retrieval.

Both components run entirely locally — no external API calls.

Architecture:
    FAISS results (top N) ──┐
                             ├──→ RRF Fusion ──→ Cross-Encoder Rerank ──→ Top K
    BM25 results  (top N) ──┘
"""

import json
import os
import pickle
import re

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from config import (
    RERANKER_MODEL,
    CANDIDATE_POOL_SIZE,
    BM25_WEIGHT,
    DENSE_WEIGHT,
    RERANKING_ENABLED,
)
from session import data_dir

# ─── File paths ───────────────────────────────────────────────────────
def _bm25_path():
    os.makedirs(data_dir(), exist_ok=True)
    return os.path.join(data_dir(), "bm25.pkl")

# ─── Module-level cache ──────────────────────────────────────────────
_cross_encoder = None
_bm25_index = None
_bm25_meta = None


# ─── Tokenisation ────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """
    Simple whitespace + punctuation tokeniser.
    Lowercase, split on non-alphanumeric characters, filter short tokens.
    """
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 1]


# ─── BM25 Index ──────────────────────────────────────────────────────

def build_bm25(chunks: list[dict]) -> None:
    """
    Build a BM25 index from the same chunks used for FAISS.
    Saves the index and associated metadata to disk.
    """
    tokenized_corpus = [_tokenize(c["text"]) for c in chunks]
    bm25 = BM25Okapi(tokenized_corpus)

    with open(_bm25_path(), "wb") as f:
        pickle.dump({"bm25": bm25, "chunks": chunks}, f)

    print(f"💾 BM25 index saved to {_bm25_path()}")


def _load_bm25() -> tuple[BM25Okapi, list[dict]]:
    """Load the BM25 index from disk (cached in memory after first load)."""
    global _bm25_index, _bm25_meta

    if _bm25_index is not None:
        return _bm25_index, _bm25_meta

    bm25_path = _bm25_path()
    if not os.path.exists(bm25_path):
        raise FileNotFoundError(
            f"No BM25 index found at {bm25_path}. Run build_bm25() first."
        )

    with open(bm25_path, "rb") as f:
        data = pickle.load(f)

    _bm25_index = data["bm25"]
    _bm25_meta = data["chunks"]
    return _bm25_index, _bm25_meta


def bm25_search(query: str, top_k: int) -> list[dict]:
    """
    Search the BM25 index for the top-k chunks matching the query.

    Returns a list of dicts with keys: text, source, page, score, _idx.
    """
    bm25, chunks = _load_bm25()
    tokenized_query = _tokenize(query)
    scores = bm25.get_scores(tokenized_query)

    # Get top-k indices by BM25 score
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        chunk = chunks[idx].copy()
        chunk["score"] = float(scores[idx])
        chunk["_idx"] = int(idx)
        results.append(chunk)

    return results


# ─── Reciprocal Rank Fusion ──────────────────────────────────────────

def reciprocal_rank_fusion(
    dense_results: list[dict],
    bm25_results: list[dict],
    k_dense: int = DENSE_WEIGHT,
    k_bm25: int = BM25_WEIGHT,
) -> list[dict]:
    """
    Combine dense (FAISS) and lexical (BM25) results using Reciprocal
    Rank Fusion (RRF).

    RRF score for document d = sum over systems S of:
        1 / (k_S + rank_S(d))

    This avoids the need to calibrate scores between the two systems.
    """
    # Build a map of chunk identity → accumulated RRF score + chunk data.
    # We use (source, page, text[:50]) as a dedup key.
    fused = {}

    for rank, r in enumerate(dense_results):
        key = (r["source"], r["page"], r["text"][:50])
        if key not in fused:
            fused[key] = {
                "text": r["text"],
                "source": r["source"],
                "page": r["page"],
                "chunk_index": r.get("chunk_index"),
                "rrf_score": 0.0,
                "dense_score": r["score"],
                "bm25_score": 0.0,
            }
        fused[key]["rrf_score"] += 1.0 / (k_dense + rank + 1)
        fused[key]["dense_score"] = r["score"]

    for rank, r in enumerate(bm25_results):
        key = (r["source"], r["page"], r["text"][:50])
        if key not in fused:
            fused[key] = {
                "text": r["text"],
                "source": r["source"],
                "page": r["page"],
                "chunk_index": r.get("chunk_index"),
                "rrf_score": 0.0,
                "dense_score": 0.0,
                "bm25_score": 0.0,
            }
        fused[key]["rrf_score"] += 1.0 / (k_bm25 + rank + 1)
        fused[key]["bm25_score"] = r["score"]

    # Sort by RRF score descending
    sorted_results = sorted(fused.values(), key=lambda x: x["rrf_score"], reverse=True)

    return sorted_results


# ─── Cross-Encoder Reranking ─────────────────────────────────────────

def _get_cross_encoder() -> CrossEncoder:
    """Load the cross-encoder model (lazy, cached)."""
    global _cross_encoder
    if _cross_encoder is None:
        print(f"🔄 Loading cross-encoder: {RERANKER_MODEL}")
        _cross_encoder = CrossEncoder(RERANKER_MODEL)
        print(f"✅ Cross-encoder loaded")
    return _cross_encoder


def rerank(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    """
    Rerank candidate chunks using the cross-encoder.

    Takes the fused candidate list (from RRF) and produces final
    relevance scores by encoding each (query, passage) pair jointly.

    Returns the top-k results sorted by cross-encoder score descending.
    """
    if not candidates:
        return []

    cross_encoder = _get_cross_encoder()

    # Build (query, passage) pairs
    pairs = [(query, c["text"]) for c in candidates]

    # Score all pairs
    ce_scores = cross_encoder.predict(pairs)

    # Normalize scores to [0, 1] via sigmoid to preserve Phase 3 test compatibility
    import math
    def sigmoid(x):
        # Clip to prevent math range error
        x = max(min(x, 100), -100)
        return 1 / (1 + math.exp(-x))

    # Attach scores and sort
    for i, c in enumerate(candidates):
        c["score"] = sigmoid(float(ce_scores[i]))

    # Sort by cross-encoder score descending
    ranked = sorted(candidates, key=lambda x: x["score"], reverse=True)

    # Return top-k, keeping only the public fields
    results = []
    for c in ranked[:top_k]:
        results.append({
            "text": c["text"],
            "source": c["source"],
            "page": c["page"],
            "score": round(c["score"], 4),
            "chunk_index": c.get("chunk_index"),
        })

    return results


# ─── Hybrid Search (full pipeline) ───────────────────────────────────

def hybrid_search(query: str, top_k: int, dense_results: list[dict]) -> list[dict]:
    """
    Full two-stage hybrid retrieval pipeline:
        1. Combine dense_results (from FAISS) with BM25 results via RRF
        2. Rerank the fused candidates using the cross-encoder
        3. Return top-k results

    Parameters:
        query:          The user's search query
        top_k:          Number of final results to return
        dense_results:  Pre-computed FAISS results (passed in by retrieve.py)

    Returns:
        List of dicts with keys: text, source, page, score
    """
    # Stage 1: BM25 search
    # Fetch as many candidates from BM25 as we did from dense search
    pool_size = len(dense_results)
    bm25_results = bm25_search(query, top_k=pool_size)

    # Stage 1b: Fuse dense + BM25 via RRF
    fused = reciprocal_rank_fusion(dense_results, bm25_results)

    # Stage 2: Rerank fused candidates with cross-encoder
    final = rerank(query, fused, top_k=top_k)

    return final


def invalidate_cache():
    """
    Clear the in-memory BM25 cache. Called after re-ingestion so
    stale data is not served.
    """
    global _bm25_index, _bm25_meta
    _bm25_index = None
    _bm25_meta = None
