import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
import json
from rag import ingest_documents, query_rag

queries = [
    # Direct Queries
    {
        "q": "When should blacksmith aprons be worn?", 
        "desc": "1. Direct: Blacksmith aprons",
        "expected_page": 1,
        "expected_section": "2-02"
    },
    {
        "q": "What type of fire extinguisher should be used for fires involving oil or grease?", 
        "desc": "2. Direct: Fire extinguishers (CO2)",
        "expected_page": 12,
        "expected_section": "2-21 (c)"
    },
    {
        "q": "When are respirators required to be worn?", 
        "desc": "3. Direct: Respirators",
        "expected_page": 5,
        "expected_section": "2-11"
    },
    {
        "q": "What are the rules for using a double-bit axe?", 
        "desc": "4. Direct: Double-Bit axes",
        "expected_page": 9,
        "expected_section": "2-16 (d)"
    },
    {
        "q": "How should chains be inspected before use?", 
        "desc": "5. Direct: Chains inspection",
        "expected_page": 10,
        "expected_section": "2-17 (a)"
    },
    {
        "q": "Where should carbon tetrachloride extinguishers be placed?", 
        "desc": "6. Direct: Carbon Tetrachloride placement",
        "expected_page": 11,
        "expected_section": "2-21 (b)"
    },
    {
        "q": "How do you properly position the base of a ladder?", 
        "desc": "7. Direct: Ladder base positioning",
        "expected_page": 14,
        "expected_section": "2-24 (b) 3"
    },
    
    # Substantially Different Wording
    {
        "q": "Is it okay to use a cylinder lubricant on my leather safety harness?", 
        "desc": "8. Different Wording: Leather belts/harness cylinder oil",
        "expected_page": 4,
        "expected_section": "2-09 (i)"
    },
    {
        "q": "What's the proper way to transport a hand axe up a tree to cut some branches?", 
        "desc": "9. Different Wording: Transporting axe up a tree",
        "expected_page": 8,
        "expected_section": "2-16 (b) 3"
    },
    
    # Unrelated
    {
        "q": "What is the company policy on remote work and telecommuting?", 
        "desc": "10. Unrelated: Remote work policy",
        "expected_page": "N/A",
        "expected_section": "N/A"
    }
]

print("Ingesting documents (this will build the FAISS index)...")
chunk_count = ingest_documents()
print(f"Indexed {chunk_count} chunks.\n")

for idx, item in enumerate(queries, 1):
    print(f"\n{'='*80}")
    print(f"QUERY {idx}: {item['desc']}")
    print(f"Text: '{item['q']}'")
    print(f"Expected Location: Page {item['expected_page']}, Section {item['expected_section']}")
    print(f"{'-'*80}")
    
    result = query_rag(item['q'], top_k=3)
    
    # Print the raw JSON output
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Analyze the result
    if result['context']:
        top = result['context'][0]
        print(f"\n=> TOP MATCH: Page {top['page']} (Score: {top['score']:.4f}) from '{top['source']}'")
    else:
        print("\n=> NO MATCHES FOUND")

