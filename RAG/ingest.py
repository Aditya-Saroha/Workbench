"""
ingest.py — Document ingestion: text extraction and chunking.

Pipeline:
    PDF files  →  per-page text extraction (PyMuPDF)  →  character-level chunking

Each chunk is a dict:
    {
        "text":   "chunk content ...",
        "source": "filename.pdf",
        "page":   3            # 1-indexed page number
    }

This module is intentionally simple. It handles plain-text PDFs today;
scanned/OCR PDFs and DOCX support can be added later by writing new
extract_* helpers and registering them here.
"""

import os
import pymupdf  # PyMuPDF — imported as pymupdf (modern API)
from config import DOCUMENTS_DIR, CHUNK_SIZE, CHUNK_OVERLAP


# ─── Text Extraction ─────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """
    Extract text from every page of a PDF.

    Returns a list of dicts, one per page:
        [{"text": "...", "source": "file.pdf", "page": 1}, ...]
    """
    filename = os.path.basename(pdf_path)
    pages = []

    doc = pymupdf.open(pdf_path)
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")  # plain UTF-8 text
        if text.strip():  # skip blank pages
            pages.append({
                "text": text,
                "source": filename,
                "page": page_num,
            })
    doc.close()

    return pages


# ─── Chunking ─────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    source: str,
    page: int,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    """
    Split a block of text into overlapping chunks of roughly `chunk_size`
    characters.  Each chunk inherits the source filename and page number.

    Strategy (simple sliding window):
        1. Start at position 0.
        2. Take `chunk_size` characters.
        3. Advance by `chunk_size - chunk_overlap`.
        4. Repeat until the text is exhausted.

    This is the simplest chunking approach that still avoids cutting
    sentences in half most of the time (thanks to the overlap).
    """
    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size
        chunk_text_slice = text[start:end]

        # Only keep chunks that have meaningful content
        if chunk_text_slice.strip():
            chunks.append({
                "text": chunk_text_slice.strip(),
                "source": source,
                "page": page,
            })

        # Advance the window
        start += chunk_size - chunk_overlap

    return chunks


# ─── Ingest all PDFs ──────────────────────────────────────────────────

def ingest_pdfs(directory: str = DOCUMENTS_DIR) -> list[dict]:
    """
    Scan `directory` for PDF files, extract text, chunk it, and return
    the full list of chunks.

    This is the main entry-point for Phase 1.
    """
    all_chunks = []

    pdf_files = sorted(
        f for f in os.listdir(directory) if f.lower().endswith(".pdf")
    )

    if not pdf_files:
        print(f"⚠️  No PDF files found in {directory}")
        return all_chunks

    for pdf_file in pdf_files:
        pdf_path = os.path.join(directory, pdf_file)
        print(f"📄 Processing: {pdf_file}")

        pages = extract_text_from_pdf(pdf_path)
        print(f"   → {len(pages)} page(s) with text")

        for page_info in pages:
            page_chunks = chunk_text(
                text=page_info["text"],
                source=page_info["source"],
                page=page_info["page"],
            )
            all_chunks.extend(page_chunks)

        print(f"   → {sum(1 for c in all_chunks if c['source'] == pdf_file)} chunk(s) created")

    print(f"\n✅ Total chunks across all documents: {len(all_chunks)}")
    return all_chunks


# ─── CLI entry-point ──────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Run directly to test ingestion:
        python ingest.py

    Place PDF files in the documents/ folder first.
    """
    import json

    chunks = ingest_pdfs()

    if chunks:
        # Show first 3 chunks as a preview
        print("\n── Preview of first 3 chunks ──")
        for i, chunk in enumerate(chunks[:3]):
            print(f"\nChunk {i + 1}:")
            print(f"  Source : {chunk['source']}")
            print(f"  Page   : {chunk['page']}")
            print(f"  Length : {len(chunk['text'])} chars")
            print(f"  Text   : {chunk['text'][:120]}...")

        # Save all chunks to data/ for inspection
        out_path = os.path.join("data", "chunks.json")
        with open(out_path, "w") as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)
        print(f"\n💾 All chunks saved to {out_path}")
