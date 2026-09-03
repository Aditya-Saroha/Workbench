"""
verify_phase2.py — Thorough verification of Phase 2: embeddings + FAISS.

Tests:
  1.  Embedding model loads and returns correct dimensionality
  2.  embed_texts() returns correct shape and dtype
  3.  embed_query() returns correct shape and dtype
  4.  Embeddings are deterministic (same input → same output)
  5.  Semantically similar texts have higher similarity than dissimilar ones
  6.  FAISS index builds from chunks without errors
  7.  Index file and metadata file are saved to disk
  8.  FAISS index vector count matches chunk count
  9.  Metadata count matches FAISS index count
  10. load_index() recovers the same index from disk
  11. search() returns results with required fields
  12. search() returns results in descending score order
  13. search() returns semantically relevant results for known queries
  14. search() with top_k parameter is respected
  15. Scores are valid cosine similarities (in [-1, 1])

Run:
    python verify_phase2.py
"""

import json
import os
import sys
import numpy as np

# Must import before faiss to avoid torch/MKL conflicts on some systems
from config import DATA_DIR, TOP_K, EMBEDDING_MODEL
from embeddings import embed_texts, embed_query, get_embedding_dimension
from vector_store import (
    build_index, load_index, search,
    INDEX_PATH, META_PATH,
)

PASS = 0
FAIL = 0


def report(test_name: str, passed: bool, detail: str = ""):
    global PASS, FAIL
    status = "✅ PASS" if passed else "❌ FAIL"
    if passed:
        PASS += 1
    else:
        FAIL += 1
    print(f"  {status}: {test_name}")
    if detail:
        for line in detail.strip().split("\n"):
            print(f"         {line}")


def divider(title: str):
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 1: Embedding model and basic encoding
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 1: Embedding model basics")

print(f"  Model: {EMBEDDING_MODEL}")

dim = get_embedding_dimension()
report("Model loads and returns embedding dimension", dim > 0, f"Dimension: {dim}")
report("Dimension is 384 (expected for all-MiniLM-L6-v2)", dim == 384)

# Batch embedding
test_texts = [
    "Industrial equipment inspection procedure",
    "Chemical spill response guidelines",
    "Workplace safety training requirements",
]
vectors = embed_texts(test_texts)

report(
    "embed_texts() returns correct shape",
    vectors.shape == (3, 384),
    f"Shape: {vectors.shape}",
)
report(
    "embed_texts() returns float32",
    vectors.dtype == np.float32,
    f"Dtype: {vectors.dtype}",
)

# Single query embedding
q_vec = embed_query("How to inspect equipment?")
report(
    "embed_query() returns correct shape",
    q_vec.shape == (384,),
    f"Shape: {q_vec.shape}",
)
report(
    "embed_query() returns float32",
    q_vec.dtype == np.float32,
    f"Dtype: {q_vec.dtype}",
)


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 2: Embedding quality checks
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 2: Embedding quality")

# Determinism — encoding the same text twice should give identical vectors
vec_a = embed_texts(["Safety inspection checklist"])
vec_b = embed_texts(["Safety inspection checklist"])
report(
    "Embeddings are deterministic (same input → same output)",
    np.allclose(vec_a, vec_b, atol=1e-6),
)

# Semantic similarity — similar texts should score higher than dissimilar
similar_pair = embed_texts([
    "How to handle a chemical spill",
    "Chemical spill response procedure",
])
dissimilar_pair = embed_texts([
    "How to handle a chemical spill",
    "Recipe for chocolate cake",
])

# Cosine similarity (normalize then dot product)
def cosine_sim(a, b):
    a_n = a / np.linalg.norm(a)
    b_n = b / np.linalg.norm(b)
    return float(np.dot(a_n, b_n))

sim_score = cosine_sim(similar_pair[0], similar_pair[1])
dissim_score = cosine_sim(dissimilar_pair[0], dissimilar_pair[1])

report(
    "Semantically similar texts have higher cosine similarity",
    sim_score > dissim_score,
    f"Similar pair: {sim_score:.4f}, Dissimilar pair: {dissim_score:.4f}",
)


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 3: FAISS index build
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 3: FAISS index build")

chunks_path = os.path.join(DATA_DIR, "chunks.json")
with open(chunks_path, "r") as f:
    chunks = json.load(f)

print(f"  Loaded {len(chunks)} chunks from chunks.json")

index = build_index(chunks)

report(
    "build_index() completes without error",
    True,
)
report(
    "FAISS index vector count matches chunk count",
    index.ntotal == len(chunks),
    f"Index: {index.ntotal}, Chunks: {len(chunks)}",
)


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 4: Persistence (save/load)
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 4: Index persistence")

report(
    f"Index file exists on disk",
    os.path.exists(INDEX_PATH),
    f"Path: {INDEX_PATH}, Size: {os.path.getsize(INDEX_PATH)} bytes",
)
report(
    f"Metadata file exists on disk",
    os.path.exists(META_PATH),
    f"Path: {META_PATH}, Size: {os.path.getsize(META_PATH)} bytes",
)

# Load from disk
loaded_index, loaded_meta = load_index()

report(
    "Loaded index has same vector count as original",
    loaded_index.ntotal == index.ntotal,
    f"Original: {index.ntotal}, Loaded: {loaded_index.ntotal}",
)
report(
    "Loaded metadata count matches index count",
    len(loaded_meta) == loaded_index.ntotal,
    f"Metadata: {len(loaded_meta)}, Index: {loaded_index.ntotal}",
)


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 5: Search correctness
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 5: Search correctness")

# Query about inspection (should match sample_inspection_sop.pdf)
results_inspection = search("What is the inspection procedure for industrial equipment?", top_k=3)

report(
    "search() returns results",
    len(results_inspection) > 0,
    f"Got {len(results_inspection)} results",
)

# Check required fields
required_fields = {"text", "source", "page", "score"}
first_result = results_inspection[0] if results_inspection else {}
result_fields = set(first_result.keys())
report(
    "Results contain required fields (text, source, page, score)",
    required_fields.issubset(result_fields),
    f"Fields: {result_fields}",
)

# Scores in descending order
scores = [r["score"] for r in results_inspection]
report(
    "Results are in descending score order",
    all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)),
    f"Scores: {[f'{s:.4f}' for s in scores]}",
)

# Scores are valid cosine similarities
report(
    "All scores are valid cosine similarities (in [-1, 1])",
    all(-1.0 <= s <= 1.0 + 1e-6 for s in scores),
    f"Score range: [{min(scores):.4f}, {max(scores):.4f}]",
)

# Top result should be from the inspection SOP
report(
    "Inspection query → top result is from sample_inspection_sop.pdf",
    results_inspection[0]["source"] == "sample_inspection_sop.pdf",
    f"Top source: {results_inspection[0]['source']}",
)

# Query about chemical safety (should match safety_manual.pdf)
results_safety = search("What PPE is required for chemical handling?", top_k=3)
report(
    "Chemical safety query → top result is from safety_manual.pdf",
    results_safety[0]["source"] == "safety_manual.pdf",
    f"Top source: {results_safety[0]['source']}",
)

# top_k is respected
results_2 = search("safety", top_k=2)
report(
    "top_k=2 returns at most 2 results",
    len(results_2) <= 2,
    f"Got {len(results_2)} results",
)

results_all = search("safety", top_k=100)
report(
    "top_k > total chunks is clamped to total chunks",
    len(results_all) == len(chunks),
    f"Got {len(results_all)} results (total chunks: {len(chunks)})",
)


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 6: Print search results for manual inspection
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 6: Search results (manual inspection)")

test_queries = [
    "What is the inspection procedure for industrial equipment?",
    "What PPE is required for chemical handling?",
    "How should a major chemical spill be handled?",
]

for query in test_queries:
    print(f"\n  Query: \"{query}\"")
    results = search(query, top_k=3)
    for i, r in enumerate(results, 1):
        print(f"    Result {i} (score={r['score']:.4f}) — {r['source']} p.{r['page']}")
        print(f"      {r['text'][:120]}...")


# ─────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────
divider("VERIFICATION SUMMARY")
total = PASS + FAIL
print(f"  Passed: {PASS}/{total}")
print(f"  Failed: {FAIL}/{total}")

if FAIL > 0:
    print("\n  ⚠️  Some tests failed. Review the output above for details.")
    sys.exit(1)
else:
    print("\n  🎉 All Phase 2 tests passed! Embeddings + FAISS verified.")
    sys.exit(0)
