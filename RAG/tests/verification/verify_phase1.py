import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
"""
verify_phase1.py — Thorough verification of the Phase 1 ingestion pipeline.

Tests:
  1. data/chunks.json is valid JSON
  2. Correct number of chunks
  3. Every chunk has non-empty text, source, page fields
  4. Page numbers are valid for each source PDF
  5. Print complete chunks for manual inspection
  6. Verify chunk_size and chunk_overlap are actually applied
  7. Multi-document ingestion (two different PDFs)

Run:
    python verify_phase1.py
"""

import json
import os
import sys
import pymupdf
from config import DOCUMENTS_DIR, DATA_DIR, CHUNK_SIZE, CHUNK_OVERLAP
from ingest import ingest_pdfs, extract_text_from_pdf, chunk_text

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
# TEST 1: Re-run ingestion with both PDFs and save chunks.json
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 1: Re-run ingestion with all PDFs")

chunks = ingest_pdfs(DOCUMENTS_DIR)

# Save fresh chunks.json
chunks_path = os.path.join(DATA_DIR, "chunks.json")
with open(chunks_path, "w") as f:
    json.dump(chunks, f, indent=2, ensure_ascii=False)
print(f"\n💾 Saved {len(chunks)} chunks to {chunks_path}")


# ─────────────────────────────────────────────────────────────────────
# TEST 2: Validate chunks.json is valid JSON
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 2: Validate chunks.json")

try:
    with open(chunks_path, "r") as f:
        loaded_chunks = json.load(f)
    report("chunks.json is valid JSON", True)
    report(
        "Loaded chunk count matches in-memory count",
        len(loaded_chunks) == len(chunks),
        f"In-memory: {len(chunks)}, On-disk: {len(loaded_chunks)}",
    )
except json.JSONDecodeError as e:
    report("chunks.json is valid JSON", False, str(e))
    loaded_chunks = []

print(f"\n  Total chunks: {len(loaded_chunks)}")


# ─────────────────────────────────────────────────────────────────────
# TEST 3: Every chunk has required non-empty fields
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 3: Chunk field validation")

required_fields = ["text", "source", "page"]
missing_fields = []
empty_fields = []

for i, chunk in enumerate(loaded_chunks):
    for field in required_fields:
        if field not in chunk:
            missing_fields.append(f"Chunk {i}: missing '{field}'")
        elif field == "page":
            pg = chunk[field]
            if not isinstance(pg, int) or (pg < 1 and pg != -1):
                empty_fields.append(f"Chunk {i}: 'page' is not a positive int or -1 (got {pg!r})")
        elif not isinstance(chunk[field], str) or not chunk[field].strip():
            empty_fields.append(f"Chunk {i}: '{field}' is empty or not a string")

report(
    "All chunks have required fields (text, source, page)",
    len(missing_fields) == 0,
    "\n".join(missing_fields[:5]) if missing_fields else "",
)
report(
    "All fields are non-empty and correctly typed",
    len(empty_fields) == 0,
    "\n".join(empty_fields[:5]) if empty_fields else "",
)


# ─────────────────────────────────────────────────────────────────────
# TEST 4: Metadata validation (Source and Page)
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 4: Metadata validation")

# Build a map of source -> max page count from actual PDFs
pdf_page_counts = {}
all_supported_files = []
for file in os.listdir(DOCUMENTS_DIR):
    if file.lower().endswith((".pdf", ".docx", ".xlsx")):
        all_supported_files.append(file)
        if file.lower().endswith(".pdf"):
            pdf_path = os.path.join(DOCUMENTS_DIR, file)
            doc = pymupdf.open(pdf_path)
            pdf_page_counts[file] = len(doc)
            doc.close()

print(f"  PDF page counts: {pdf_page_counts}")

invalid_pages = []
unknown_sources = []
for i, chunk in enumerate(loaded_chunks):
    src = chunk["source"]
    pg = chunk["page"]
    
    if src not in all_supported_files:
        unknown_sources.append(f"Chunk {i}: source '{src}' not found in supported documents/")
    elif src.lower().endswith(".pdf"):
        if src not in pdf_page_counts:
            unknown_sources.append(f"Chunk {i}: PDF source '{src}' not in pdf_page_counts")
        elif pg < 1 or pg > pdf_page_counts[src]:
            invalid_pages.append(
                f"Chunk {i}: page {pg} out of range [1, {pdf_page_counts[src]}] for '{src}'"
            )
    elif src.lower().endswith(".docx"):
        if pg != -1:
            invalid_pages.append(f"Chunk {i}: expected page=-1 for DOCX '{src}', got {pg}")
    elif src.lower().endswith(".xlsx"):
        if pg != -1:
            invalid_pages.append(f"Chunk {i}: expected page=-1 for XLSX '{src}', got {pg}")
        if "sheet" not in chunk:
            invalid_pages.append(f"Chunk {i}: expected 'sheet' key in metadata for XLSX '{src}'")

report(
    "All chunk sources match actual documents",
    len(unknown_sources) == 0,
    "\n".join(unknown_sources[:5]) if unknown_sources else "",
)
report(
    "All page numbers are within valid range for their source format",
    len(invalid_pages) == 0,
    "\n".join(invalid_pages[:5]) if invalid_pages else "",
)

# Check that we have chunks from multiple sources
unique_sources = set(c["source"] for c in loaded_chunks)
report(
    f"Chunks come from multiple documents ({len(unique_sources)} sources)",
    len(unique_sources) >= 2,
    f"Sources: {unique_sources}",
)


# ─────────────────────────────────────────────────────────────────────
# TEST 5: Print complete chunks for manual inspection
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 5: Complete chunk contents (for manual inspection)")

# Print first chunk, a middle chunk, and last chunk from EACH source
for source in sorted(unique_sources):
    source_chunks = [c for c in loaded_chunks if c["source"] == source]
    print(f"\n  ── Source: {source} ({len(source_chunks)} chunks) ──")

    indices_to_show = [0]
    if len(source_chunks) > 2:
        indices_to_show.append(len(source_chunks) // 2)
    if len(source_chunks) > 1:
        indices_to_show.append(len(source_chunks) - 1)

    for idx in indices_to_show:
        c = source_chunks[idx]
        print(f"\n  Chunk {idx + 1}/{len(source_chunks)} | page={c['page']} | {len(c['text'])} chars")
        print(f"  ┌{'─' * 58}┐")
        # Print full text, wrapped
        for line in c["text"].split("\n"):
            print(f"  │ {line}")
        print(f"  └{'─' * 58}┘")


# ─────────────────────────────────────────────────────────────────────
# TEST 6: Verify chunk_size and chunk_overlap are actually applied
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 6: Chunk size and overlap verification")

print(f"  Configured CHUNK_SIZE:    {CHUNK_SIZE}")
print(f"  Configured CHUNK_OVERLAP: {CHUNK_OVERLAP}")

# Check chunk sizes
sizes = [len(c["text"]) for c in loaded_chunks]
max_size = max(sizes)
min_size = min(sizes)
avg_size = sum(sizes) / len(sizes)

print(f"\n  Actual chunk sizes:")
print(f"    Min:  {min_size} chars")
print(f"    Max:  {max_size} chars")
print(f"    Avg:  {avg_size:.0f} chars")

# No chunk should exceed CHUNK_SIZE (after stripping)
oversized = [i for i, s in enumerate(sizes) if s > CHUNK_SIZE]
report(
    f"No chunk exceeds CHUNK_SIZE ({CHUNK_SIZE})",
    len(oversized) == 0,
    f"Oversized chunk indices: {oversized}" if oversized else "",
)

# Verify overlap by checking that consecutive same-page chunks share text
divider("TEST GROUP 6b: Overlap verification between consecutive same-page chunks")

overlap_verified = 0
overlap_failed = 0
overlap_details = []

for source in sorted(unique_sources):
    source_chunks = [c for c in loaded_chunks if c["source"] == source]
    for pg in sorted(set(c["page"] for c in source_chunks)):
        page_chunks = [c for c in source_chunks if c["page"] == pg]
        if len(page_chunks) < 2:
            continue
        for j in range(len(page_chunks) - 1):
            chunk_a = page_chunks[j]["text"]
            chunk_b = page_chunks[j + 1]["text"]
            # The last CHUNK_OVERLAP chars of chunk_a should appear at
            # the start of chunk_b (approximately, since we strip)
            overlap_len = min(CHUNK_OVERLAP, len(chunk_b))
            tail_a = chunk_a[-overlap_len:].strip()
            # Check if tail of chunk_a appears somewhere near the start of chunk_b
            if tail_a and tail_a in chunk_b[:overlap_len + 50]:
                overlap_verified += 1
            else:
                # Try a shorter overlap match (stripping can shift things)
                shorter_overlap = max(10, overlap_len - 10)
                shorter_tail = chunk_a[-shorter_overlap:].strip()
                if shorter_tail and shorter_tail in chunk_b[:overlap_len + 80]:
                    overlap_verified += 1
                else:
                    overlap_failed += 1
                    overlap_details.append(
                        f"  {source} page {pg}, chunks {j+1}→{j+2}:\n"
                        f"    tail_a = ...{repr(chunk_a[-60:])}\n"
                        f"    head_b = {repr(chunk_b[:60])}..."
                    )

total_overlap_checks = overlap_verified + overlap_failed
if total_overlap_checks > 0:
    report(
        f"Consecutive same-page chunks share overlapping text ({overlap_verified}/{total_overlap_checks})",
        overlap_failed == 0,
        "\n".join(overlap_details[:3]) if overlap_details else "",
    )
else:
    print("  (No consecutive same-page chunk pairs to check)")


# ─────────────────────────────────────────────────────────────────────
# TEST 7: Verify the raw extraction matches actual PDF content
# ─────────────────────────────────────────────────────────────────────
divider("TEST GROUP 7: Raw extraction vs. PDF content spot-check")

# Pick the first PDF, extract page 1 raw, verify our chunk text is a subset
pdf_sources = [s for s in sorted(unique_sources) if s.lower().endswith(".pdf")]
if pdf_sources:
    first_pdf = pdf_sources[0]
    pdf_path = os.path.join(DOCUMENTS_DIR, first_pdf)
    raw_pages = extract_text_from_pdf(pdf_path)

    if raw_pages:
        page1_text = raw_pages[0]["text"]
        page1_chunks = [c for c in loaded_chunks if c["source"] == first_pdf and c["page"] == 1]

        all_chunk_text_in_raw = all(
            c["text"].replace("\n", " ")[:80] in page1_text.replace("\n", " ")
            for c in page1_chunks
        )
        report(
            f"All page-1 chunks from '{first_pdf}' are substrings of raw extracted text",
            all_chunk_text_in_raw,
        )
        print(f"\n  Raw page 1 length: {len(page1_text)} chars")
        print(f"  Chunks from page 1: {len(page1_chunks)}")
else:
    print("  (No PDF sources to check)")


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
    print("\n  🎉 All tests passed! Phase 1 is verified and ready.")
    sys.exit(0)
