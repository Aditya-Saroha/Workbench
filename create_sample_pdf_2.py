"""
create_sample_pdf_2.py — Generate a second test PDF with different content
to verify multi-document ingestion.

Creates documents/safety_manual.pdf with 2 pages of safety manual text.
"""

import pymupdf
import os

DOCUMENTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "documents")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

PAGES = [
    # Page 1
    (
        "WORKPLACE SAFETY MANUAL — CHEMICAL HANDLING\n\n"
        "1. INTRODUCTION\n"
        "This manual provides comprehensive guidelines for the safe handling, "
        "storage, and disposal of hazardous chemicals used in the manufacturing "
        "process. All employees who work with or near chemicals must read this "
        "manual and complete the associated training program before commencing work.\n\n"
        "2. CHEMICAL CLASSIFICATION\n"
        "Chemicals are classified according to the Globally Harmonized System (GHS). "
        "Categories include: flammable liquids, corrosive substances, oxidizing agents, "
        "acute toxins, and environmental hazards. Each chemical container must display "
        "the appropriate GHS pictogram, signal word, and hazard statement.\n\n"
        "3. PERSONAL PROTECTIVE EQUIPMENT\n"
        "Required PPE for chemical handling includes: chemical-resistant gloves "
        "(nitrile or neoprene), safety goggles with splash guards, lab coat or "
        "chemical-resistant apron, closed-toe shoes, and a respirator when working "
        "with volatile compounds. PPE must be inspected before each use and replaced "
        "if damaged."
    ),
    # Page 2
    (
        "4. SPILL RESPONSE PROCEDURES\n\n"
        "4.1 Minor Spills (less than 500 mL)\n"
        "For minor spills of non-volatile, non-toxic chemicals: alert nearby workers, "
        "don appropriate PPE, contain the spill with absorbent materials, collect "
        "contaminated materials in a labeled waste bag, and clean the area with "
        "appropriate neutralizing solution. Report the incident to the shift supervisor.\n\n"
        "4.2 Major Spills (500 mL or greater)\n"
        "For major spills or spills involving highly hazardous chemicals: evacuate "
        "the immediate area, activate the chemical spill alarm, contact the Emergency "
        "Response Team (ERT) at extension 5555, do NOT attempt cleanup without ERT "
        "guidance, secure ventilation by opening fume hoods and exterior doors. The "
        "ERT leader will determine if external emergency services are required.\n\n"
        "5. CHEMICAL STORAGE\n"
        "Store chemicals in designated cabinets according to compatibility groups. "
        "Never store acids with bases. Flammable solvents must be kept in approved "
        "flammable storage cabinets. Maximum container size for bench storage is 2.5 L. "
        "All storage areas must have secondary containment."
    ),
]


def create_safety_pdf():
    output_path = os.path.join(DOCUMENTS_DIR, "safety_manual.pdf")

    doc = pymupdf.open()
    for page_text in PAGES:
        page = doc.new_page(width=595, height=842)
        text_rect = pymupdf.Rect(50, 50, 545, 792)
        page.insert_textbox(text_rect, page_text, fontsize=11, fontname="helv")

    doc.save(output_path)
    doc.close()
    print(f"✅ Sample PDF created: {output_path}")
    print(f"   Pages: {len(PAGES)}")


if __name__ == "__main__":
    create_safety_pdf()
