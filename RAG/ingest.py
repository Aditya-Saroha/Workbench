"""
ingest.py — Document ingestion: text extraction and chunking.

Pipeline:
    Documents  →  extraction (PDF, DOCX, XLSX, OCR)  →  character-level chunking

Each chunk is a dict:
    {
        "text":   "chunk content ...",
        "source": "filename.ext",
        "page":   3            # 1-indexed page number, or -1 for docx/xlsx
    }
"""

import os
import pymupdf  # PyMuPDF
import docx
import pandas as pd
from PIL import Image
import io
from config import DOCUMENTS_DIR, CHUNK_SIZE, CHUNK_OVERLAP


# ─── Text Extraction ─────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """
    Extract text from every page of a PDF. Uses ocrmac as fallback for scanned PDFs.
    """
    filename = os.path.basename(pdf_path)
    pages = []

    doc = pymupdf.open(pdf_path)
    
    total_text_len = 0
    for page in doc:
        total_text_len += len(page.get_text("text").strip())
        
    use_ocr = False
    if len(doc) > 0 and (total_text_len / len(doc)) < 50:
        use_ocr = True
        print(f"   [OCR Fallback] Insufficient text detected for {filename}. Using OCR.")
        try:
            from ocrmac import ocrmac
        except ImportError:
            print("   ⚠️ ocrmac not found. Proceeding without OCR.")
            use_ocr = False

    for page_num, page in enumerate(doc, start=1):
        if use_ocr:
            from ocrmac import ocrmac
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
            img_bytes = pix.tobytes("png")
            pil_img = Image.open(io.BytesIO(img_bytes))
            annotations = ocrmac.OCR(pil_img).recognize()
            # ocrmac returns (text, confidence, bbox)
            text = "\n".join([annot[0] for annot in annotations])
        else:
            text = page.get_text("text")  # plain UTF-8 text
            
        if text.strip():  # skip blank pages
            pages.append({
                "text": text.strip(),
                "source": filename,
                "page": page_num,
            })
    doc.close()
    return pages


def extract_text_from_docx(docx_path: str) -> list[dict]:
    """
    Extract text from a DOCX file, parsing paragraphs and tables.
    """
    filename = os.path.basename(docx_path)
    pages = []
    
    try:
        doc = docx.Document(docx_path)
        full_text = []
        
        # We iterate over the body elements to preserve order of paragraphs and tables
        for element in doc.element.body:
            if element.tag.endswith('p'):
                p = docx.text.paragraph.Paragraph(element, doc)
                if p.text.strip():
                    full_text.append(p.text.strip())
            elif element.tag.endswith('tbl'):
                t = docx.table.Table(element, doc)
                table_text = []
                headers = []
                for i, row in enumerate(t.rows):
                    row_text = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
                    if i == 0:
                        headers = row_text
                    else:
                        mapped = []
                        for h, v in zip(headers, row_text):
                            if v:
                                if h:
                                    mapped.append(f"{h}: {v}")
                                else:
                                    mapped.append(v)
                        if mapped:
                            table_text.append(" - " + ", ".join(mapped))
                if table_text:
                    full_text.append("\n".join(table_text))
                    
        text = "\n\n".join(full_text)
        if text.strip():
            pages.append({
                "text": text.strip(),
                "source": filename,
                "page": -1, # No reliable page numbers in docx
            })
    except Exception as e:
        print(f"   ⚠️ Error parsing {filename}: {e}")
        
    return pages


def extract_text_from_xlsx(xlsx_path: str) -> list[dict]:
    """
    Extract text from an XLSX file, converting each sheet to a text representation.
    """
    filename = os.path.basename(xlsx_path)
    pages = []
    
    try:
        excel_file = pd.ExcelFile(xlsx_path)
        for sheet_name in excel_file.sheet_names:
            df = excel_file.parse(sheet_name).dropna(how='all')
            if df.empty:
                continue
                
            sheet_lines = [f"--- Sheet: {sheet_name} ---"]
            cols = [str(c) for c in df.columns]
            
            for _, row in df.iterrows():
                row_vals = []
                for col_name, val in zip(cols, row.values):
                    if pd.notna(val) and str(val).strip():
                        if "Unnamed:" not in col_name:
                            row_vals.append(f"{col_name}: {val}")
                        else:
                            row_vals.append(str(val))
                if row_vals:
                    sheet_lines.append(" - " + ", ".join(row_vals))
                    
            text = "\n".join(sheet_lines)
            if text.strip():
                pages.append({
                    "text": text.strip(),
                    "source": filename,
                    "page": -1,
                    "sheet": sheet_name
                })
    except Exception as e:
        print(f"   ⚠️ Error parsing {filename}: {e}")
        
    return pages


# ─── Chunking ─────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    source: str,
    page: int,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    **kwargs
) -> list[dict]:
    """
    Split a block of text into overlapping chunks of roughly `chunk_size`
    characters.  Each chunk inherits the source filename and page number.
    """
    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size
        chunk_text_slice = text[start:end]

        if chunk_text_slice.strip():
            chunk_data = {
                "text": chunk_text_slice.strip(),
                "source": source,
                "page": page,
            }
            # Add any additional metadata (like sheet name)
            for k, v in kwargs.items():
                chunk_data[k] = v
                
            chunks.append(chunk_data)

        start += chunk_size - chunk_overlap

    return chunks


# ─── Ingest all Documents ─────────────────────────────────────────────

def ingest_all(directory: str = DOCUMENTS_DIR) -> list[dict]:
    """
    Scan `directory` for supported files, extract text, chunk it, and return
    the full list of chunks.
    """
    all_chunks = []

    files = sorted(os.listdir(directory))
    supported_files = [f for f in files if f.lower().endswith((".pdf", ".docx", ".xlsx"))]

    if not supported_files:
        print(f"⚠️  No supported files found in {directory}")
        return all_chunks

    for file in supported_files:
        path = os.path.join(directory, file)
        print(f"📄 Processing: {file}")

        if file.lower().endswith(".pdf"):
            pages = extract_text_from_pdf(path)
        elif file.lower().endswith(".docx"):
            pages = extract_text_from_docx(path)
        elif file.lower().endswith(".xlsx"):
            pages = extract_text_from_xlsx(path)
        else:
            continue
            
        print(f"   → {len(pages)} logical page(s) with text")

        for page_info in pages:
            # We pop standard fields and pass any remaining as kwargs (like sheet)
            text = page_info.pop("text")
            source = page_info.pop("source")
            page = page_info.pop("page")
            
            page_chunks = chunk_text(
                text=text,
                source=source,
                page=page,
                **page_info
            )
            all_chunks.extend(page_chunks)

        print(f"   → {sum(1 for c in all_chunks if c['source'] == file)} chunk(s) created")

    print(f"\n✅ Total chunks across all documents: {len(all_chunks)}")
    return all_chunks

# Keep ingest_pdfs name for backward compatibility with older scripts if needed
def ingest_pdfs(directory: str = DOCUMENTS_DIR) -> list[dict]:
    return ingest_all(directory)

# ─── CLI entry-point ──────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    chunks = ingest_all()

    if chunks:
        print("\n── Preview of first 3 chunks ──")
        for i, chunk in enumerate(chunks[:3]):
            print(f"\nChunk {i + 1}:")
            print(f"  Source : {chunk['source']}")
            print(f"  Page   : {chunk['page']}")
            print(f"  Length : {len(chunk['text'])} chars")
            print(f"  Text   : {chunk['text'][:120]}...")

        out_path = os.path.join("data", "chunks.json")
        os.makedirs("data", exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)
        print(f"\n💾 All chunks saved to {out_path}")
