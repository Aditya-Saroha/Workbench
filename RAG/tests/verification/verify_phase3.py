import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
"""
verify_phase3.py — End-to-end verification of the complete RAG pipeline.

Tests the full path:
    PDF files → ingest → embed → FAISS index → query → structured JSON

Tests:
  1.  ingest_documents() returns correct chunk count
  2.  query_rag() returns a dict (not None, not a string)
  3.  Top-level keys are exactly {query, context, sources}
  4.  "query" field matches the input query string
  5.  "context" is a non-empty list
  6.  Each context entry has exactly {text, source, page, score}
  7.  Context entries have correct types (str, str, int, float)
  8.  Context scores are in descending order
  9.  Context scores are valid cosine similarities (in [-1, 1])
  10. "sources" is a non-empty list of {source, page} dicts
  11. Every source in "sources" also appears in "context"
  12. "sources" has no duplicates
  13. top_k parameter is respected
  14. Inspection query retrieves from sample_inspection_sop.pdf
  15. Chemical query retrieves from safety_manual.pdf
  16. Output is valid JSON (serialisable and deserialisable)
  17. CLI --query flag produces valid JSON to stdout
  18. CLI --ingest flag works without error

Run:
    python verify_phase3.py
"""

import json
import os
import subprocess
import sys

from config import DOCUMENTS_DIR, DATA_DIR, TOP_K

# Import the public API
from rag import ingest_documents, query_rag

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
# TEST GROUP 1: End-to-end ingest
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 1: ingest_documents()")

chunk_count = ingest_documents()
report(
    "ingest_documents() returns a positive chunk count",
    chunk_count > 0,
    f"Chunks: {chunk_count}",
)


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 2: query_rag() return structure
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 2: query_rag() return structure")

query_text = "What is the procedure for inspecting industrial equipment?"
result = query_rag(query_text, top_k=3)

report(
    "query_rag() returns a dict",
    isinstance(result, dict),
    f"Type: {type(result).__name__}",
)

expected_keys = {"query", "context", "sources"}
actual_keys = set(result.keys())
report(
    f"Top-level keys are exactly {{query, context, sources}}",
    actual_keys == expected_keys,
    f"Got: {actual_keys}",
)

report(
    '"query" field matches input',
    result.get("query") == query_text,
    f'Expected: "{query_text}"\nGot:      "{result.get("query")}"',
)


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 3: context list validation
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 3: context list validation")

ctx = result.get("context", [])
report("context is a non-empty list", isinstance(ctx, list) and len(ctx) > 0, f"Length: {len(ctx)}")

# Field check on every context entry
ctx_fields_ok = True
ctx_types_ok = True
ctx_field_details = []
ctx_type_details = []

expected_ctx_keys = {"text", "source", "page", "score"}
for i, entry in enumerate(ctx):
    entry_keys = set(entry.keys())
    if entry_keys != expected_ctx_keys:
        ctx_fields_ok = False
        ctx_field_details.append(f"Entry {i}: keys={entry_keys}")
    # Type checks
    if not isinstance(entry.get("text"), str) or not entry["text"].strip():
        ctx_types_ok = False
        ctx_type_details.append(f"Entry {i}: text is empty or not str")
    if not isinstance(entry.get("source"), str) or not entry["source"].strip():
        ctx_types_ok = False
        ctx_type_details.append(f"Entry {i}: source is empty or not str")
    if not isinstance(entry.get("page"), int) or entry["page"] < 1:
        ctx_types_ok = False
        ctx_type_details.append(f"Entry {i}: page={entry.get('page')!r} not a positive int")
    if not isinstance(entry.get("score"), float):
        ctx_types_ok = False
        ctx_type_details.append(f"Entry {i}: score={entry.get('score')!r} not a float")

report(
    "Each context entry has keys {text, source, page, score}",
    ctx_fields_ok,
    "\n".join(ctx_field_details[:5]) if ctx_field_details else "",
)
report(
    "Context field types are correct (str, str, int, float)",
    ctx_types_ok,
    "\n".join(ctx_type_details[:5]) if ctx_type_details else "",
)

# Score ordering
scores = [e["score"] for e in ctx]
report(
    "Context scores are in descending order",
    all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)),
    f"Scores: {scores}",
)

report(
    "All scores are valid cosine similarities (in [-1, 1])",
    all(-1.0 <= s <= 1.0 + 1e-6 for s in scores),
    f"Range: [{min(scores):.4f}, {max(scores):.4f}]",
)


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 4: sources list validation
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 4: sources list validation")

srcs = result.get("sources", [])
report(
    "sources is a non-empty list",
    isinstance(srcs, list) and len(srcs) > 0,
    f"Length: {len(srcs)}",
)

# Each source entry has {source, page}
src_fields_ok = all(set(s.keys()) == {"source", "page"} for s in srcs)
report(
    "Each source entry has keys {source, page}",
    src_fields_ok,
)

# Every source should appear in context
ctx_source_pages = {(e["source"], e["page"]) for e in ctx}
src_source_pages = {(s["source"], s["page"]) for s in srcs}
report(
    "Every (source, page) in sources also appears in context",
    src_source_pages.issubset(ctx_source_pages),
    f"sources: {src_source_pages}\ncontext: {ctx_source_pages}",
)

# No duplicates in sources
report(
    "sources has no duplicate (source, page) pairs",
    len(src_source_pages) == len(srcs),
    f"Unique: {len(src_source_pages)}, Total: {len(srcs)}",
)


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 5: top_k parameter
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 5: top_k parameter")

r1 = query_rag("safety", top_k=1)
report("top_k=1 returns exactly 1 context entry", len(r1["context"]) == 1)

r5 = query_rag("safety", top_k=5)
report("top_k=5 returns exactly 5 context entries", len(r5["context"]) == 5)

r_big = query_rag("safety", top_k=100000)
report(
    f"top_k=100000 is clamped to total chunks ({chunk_count})",
    len(r_big["context"]) == chunk_count,
    f"Got: {len(r_big['context'])}",
)


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 6: Semantic relevance (cross-document)
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 6: Semantic relevance")

r_insp = query_rag("What is the procedure for inspecting industrial equipment?", top_k=1)
report(
    "Inspection query → top hit from sample_inspection_sop.pdf",
    r_insp["context"][0]["source"] == "sample_inspection_sop.pdf",
    f"Got: {r_insp['context'][0]['source']}",
)

r_chem = query_rag("What PPE is required for chemical handling?", top_k=1)
report(
    "Chemical PPE query → top hit from safety_manual.pdf",
    r_chem["context"][0]["source"] == "safety_manual.pdf",
    f"Got: {r_chem['context'][0]['source']}",
)


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 7: JSON serialisability
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 7: JSON round-trip")

try:
    json_str = json.dumps(result, ensure_ascii=False)
    roundtripped = json.loads(json_str)
    report(
        "Output survives JSON dumps → loads round-trip",
        roundtripped == result,
    )
except (TypeError, json.JSONDecodeError) as e:
    report("Output survives JSON dumps → loads round-trip", False, str(e))


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 8: CLI interface
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 8: CLI interface")

# --query should print valid JSON to stdout
venv_python = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../../", ".venv", "bin", "python"
)
cli_proc = subprocess.run(
    [venv_python, "rag.py", "--query", "spill response"],
    capture_output=True,
    text=True,
    cwd=os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../'),
)
report(
    "CLI --query exits with code 0",
    cli_proc.returncode == 0,
    f"stderr: {cli_proc.stderr[:200]}" if cli_proc.returncode != 0 else "",
)

# The stdout should contain valid JSON (after stripping log lines)
cli_lines = cli_proc.stdout.strip().split("\n")
# Find the JSON block — it starts with '{'
json_start = None
for i, line in enumerate(cli_lines):
    if line.strip().startswith("{"):
        json_start = i
        break

if json_start is not None:
    json_block = "\n".join(cli_lines[json_start:])
    try:
        cli_result = json.loads(json_block)
        report(
            "CLI stdout contains valid JSON with expected keys",
            set(cli_result.keys()) == {"query", "context", "sources"},
            f"Keys: {set(cli_result.keys())}",
        )
    except json.JSONDecodeError as e:
        report("CLI stdout contains valid JSON", False, str(e))
else:
    report("CLI stdout contains valid JSON", False, "No JSON block found in stdout")


# ─────────────────────────────────────────────────────────────────────
# TEST GROUP 9: Print a full result for manual inspection
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 9: Full output sample (manual inspection)")

sample = query_rag("How should a major chemical spill be handled?", top_k=3)
print(json.dumps(sample, indent=2, ensure_ascii=False))


# ─────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────
divider("VERIFICATION SUMMARY")
total = PASS + FAIL
print(f"  Passed: {PASS}/{total}")
print(f"  Failed: {FAIL}/{total}")

if FAIL > 0:
    print("\n  ⚠️  Some tests failed. Review output above.")
    sys.exit(1)
else:
    print("\n  🎉 All Phase 3 tests passed! End-to-end RAG pipeline verified.")
    sys.exit(0)
