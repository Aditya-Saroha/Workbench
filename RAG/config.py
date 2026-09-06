"""
config.py — Central configuration for the RAG pipeline.

All tuneable parameters live here so you never have to hunt through
multiple files to change a setting.
"""

import os
from session import data_dir, documents_dir

# ─── Paths ───────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCUMENTS_DIR = documents_dir()
DATA_DIR = data_dir()

# ─── Chunking ────────────────────────────────────────────────────────
# Target number of characters per chunk.
# ~500 chars ≈ ~100 tokens — small enough for a lightweight embedding
# model, large enough to carry meaningful context.
CHUNK_SIZE = 500

# Overlap between consecutive chunks (in characters).
# Overlap prevents important sentences from being split across chunks.
CHUNK_OVERLAP = 100

# ─── Embeddings (will be used in Phase 2) ────────────────────────────
# A small, high-quality model that runs comfortably on CPU / Apple MPS.
# all-MiniLM-L6-v2: 80 MB, 384-dim vectors, excellent quality/speed ratio.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ─── Context Expansion ─────────────────────────────────────────────────
CONTEXT_EXPANSION_ENABLED = True
CONTEXT_EXPANSION_CHUNKS = 2     # Number of neighboring chunks to fetch (e.g. 2 means up to 2 before and 2 after)
MAX_CONTEXT_CHARS = 4000         # Hard bound for the size of any single expanded context block
MIN_RELEVANCE_SCORE = 0.3        # Minimum score required to keep a chunk after reranking

# ─── OCR Quality Gate ────────────────────────────────────────────────
OCR_MIN_ALPHA_RATIO = 0.4        # Trigger OCR if alphabetic chars are < 40% of non-whitespace
OCR_MIN_AVG_WORD_LEN = 2.5       # Trigger OCR if average word length is suspiciously short

# ─── Retrieval (will be used in Phase 2) ─────────────────────────────
TOP_K = 5  # number of chunks to retrieve per query

# ─── Hybrid Retrieval / Reranking ────────────────────────────────────
# When enabled, retrieval uses a two-stage pipeline:
#   Stage 1: FAISS dense + BM25 lexical search fused via RRF
#   Stage 2: Cross-encoder reranking of the fused candidate pool
RERANKING_ENABLED = True
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"  # ~80 MB, local
CANDIDATE_POOL_SIZE = 20  # number of candidates to fetch before reranking
BM25_WEIGHT = 60   # RRF constant for BM25 rank contribution
DENSE_WEIGHT = 60  # RRF constant for dense rank contribution

# ─── Ensure directories exist ────────────────────────────────────────
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
