"""
embeddings.py — Generate embeddings locally using Sentence Transformers.

Uses all-MiniLM-L6-v2 by default:
    - 80 MB download (cached after first run)
    - 384-dimensional vectors
    - Runs on CPU or Apple MPS
    - Good quality-to-speed ratio for a local prototype

This module wraps model loading and encoding so the rest of the pipeline
never touches the model directly.
"""

import numpy as np
from sentence_transformers import SentenceTransformer
from config import EMBEDDING_MODEL

# ─── Module-level cache ──────────────────────────────────────────────
# The model is loaded once and reused for all subsequent calls within
# the same process. This avoids re-downloading / re-loading on every
# query.
_model = None


def _get_model() -> SentenceTransformer:
    """Load the embedding model (lazy, cached)."""
    global _model
    if _model is None:
        print(f"🔄 Loading embedding model: {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL)
        print(f"✅ Model loaded — dimension: {_model.get_embedding_dimension()}")
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Encode a list of strings into a 2-D numpy array of shape
    (len(texts), embedding_dim).

    The returned array has dtype float32 — this is what FAISS expects.
    """
    model = _get_model()
    embeddings = model.encode(
        texts,
        show_progress_bar=len(texts) > 50,  # progress bar for large batches
        convert_to_numpy=True,
    )
    return embeddings.astype(np.float32)


def embed_query(query: str) -> np.ndarray:
    """
    Encode a single query string into a 1-D numpy array of shape
    (embedding_dim,).
    """
    model = _get_model()
    embedding = model.encode(query, convert_to_numpy=True)
    return embedding.astype(np.float32)


def get_embedding_dimension() -> int:
    """Return the dimensionality of the embedding vectors (e.g. 384)."""
    model = _get_model()
    return model.get_embedding_dimension()


# ─── CLI smoke test ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("Running embeddings smoke test...\n")

    test_texts = [
        "Industrial equipment inspection procedure",
        "Chemical spill response guidelines",
        "Workplace safety training requirements",
    ]

    vectors = embed_texts(test_texts)
    print(f"\nEmbedded {len(test_texts)} texts")
    print(f"  Shape : {vectors.shape}")
    print(f"  Dtype : {vectors.dtype}")
    print(f"  Sample: {vectors[0][:5]}...")

    q_vec = embed_query("How do I handle a chemical spill?")
    print(f"\nQuery vector shape: {q_vec.shape}")
    print(f"  Sample: {q_vec[:5]}...")
