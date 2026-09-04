import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
"""
create_sample_pdf.py — Generate a small test PDF so you can verify
that ingestion + chunking work without needing a real document.

Usage:
    python create_sample_pdf.py

Creates documents/sample_inspection_sop.pdf with 3 pages of realistic
industrial SOP text.
"""

import pymupdf  # PyMuPDF
import os

DOCUMENTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "documents")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

# ─── Realistic sample content (industrial inspection SOP) ─────────────
PAGES = [
    # Page 1
    (
        "Standard Operating Procedure: Industrial Equipment Inspection\n\n"
        "1. PURPOSE\n"
        "This document establishes the standard operating procedure for the "
        "inspection of industrial equipment at the manufacturing facility. "
        "All personnel involved in equipment maintenance and quality assurance "
        "must follow these guidelines to ensure workplace safety, regulatory "
        "compliance, and operational reliability.\n\n"
        "2. SCOPE\n"
        "This SOP applies to all rotating machinery, pressure vessels, "
        "electrical panels, and conveyor systems within Plant A and Plant B. "
        "It covers routine visual inspections, scheduled preventive maintenance "
        "checks, and unscheduled breakdown investigations.\n\n"
        "3. RESPONSIBILITIES\n"
        "The Plant Manager is responsible for ensuring that all inspections are "
        "carried out on schedule. The Maintenance Supervisor assigns inspection "
        "tasks to qualified technicians. Each technician must hold a valid "
        "certification for the equipment category they inspect. The Quality "
        "Assurance department reviews inspection reports within 48 hours."
    ),
    # Page 2
    (
        "4. INSPECTION PROCEDURE\n\n"
        "4.1 Pre-Inspection Preparation\n"
        "Before beginning any inspection, the technician must: (a) review the "
        "equipment maintenance history from the CMMS database, (b) gather all "
        "required tools and personal protective equipment, (c) obtain a valid "
        "work permit if the equipment is in a hazardous zone, (d) notify the "
        "control room operator that the equipment will be taken offline.\n\n"
        "4.2 Visual Inspection\n"
        "Examine the external surfaces for corrosion, cracks, leaks, or "
        "unusual discoloration. Check all fasteners for tightness. Verify that "
        "safety guards and covers are properly secured. Inspect wiring and "
        "cable trays for damage or overheating. Document findings with "
        "photographs.\n\n"
        "4.3 Functional Testing\n"
        "After visual inspection, perform functional tests as specified in the "
        "equipment manual. Record vibration levels using a portable analyzer. "
        "Measure operating temperature with an infrared thermometer. Compare "
        "readings against baseline values from the equipment commissioning report."
    ),
    # Page 3
    (
        "5. REPORTING AND DOCUMENTATION\n\n"
        "All inspection findings must be recorded in the Inspection Report Form "
        "(IRF-2024). The report must include: date and time of inspection, "
        "equipment ID and location, inspector name and certification number, "
        "detailed findings with severity classification (Critical, Major, Minor), "
        "recommended corrective actions, and a follow-up schedule.\n\n"
        "6. SAFETY REQUIREMENTS\n"
        "Lockout/Tagout (LOTO) procedures must be followed before inspecting "
        "any energized equipment. Confined space entry permits are required for "
        "internal vessel inspections. Fall protection equipment must be used "
        "when working at heights above 1.8 meters. Emergency procedures must be "
        "reviewed before entering any hazardous area.\n\n"
        "7. REVISION HISTORY\n"
        "Rev 1.0 — Initial release, January 2024\n"
        "Rev 1.1 — Added confined space entry requirements, March 2024\n"
        "Rev 1.2 — Updated vibration analysis thresholds, July 2024"
    ),
]


def create_sample_pdf():
    output_path = os.path.join(DOCUMENTS_DIR, "sample_inspection_sop.pdf")

    doc = pymupdf.open()  # new empty PDF

    for page_text in PAGES:
        page = doc.new_page(width=595, height=842)  # A4 size in points
        # Insert text with a simple font
        text_rect = pymupdf.Rect(50, 50, 545, 792)  # margins
        page.insert_textbox(
            text_rect,
            page_text,
            fontsize=11,
            fontname="helv",  # Helvetica (built-in)
        )

    doc.save(output_path)
    doc.close()
    print(f"✅ Sample PDF created: {output_path}")
    print(f"   Pages: {len(PAGES)}")


if __name__ == "__main__":
    create_sample_pdf()
