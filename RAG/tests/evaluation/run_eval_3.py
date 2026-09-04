import os
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import rag
from config import DATA_DIR

PDF_FILENAME = "mepnn_cybersecurity_guide_10919-508.pdf"
SOURCE_PDF = os.path.join("documents", PDF_FILENAME)
EVAL_DIR = "eval_docs_3"
EVAL_PDF = os.path.join(EVAL_DIR, PDF_FILENAME)

def setup_isolated_env():
    if not os.path.exists(SOURCE_PDF):
        print(f"Error: {SOURCE_PDF} not found.")
        sys.exit(1)
    
    if os.path.exists(EVAL_DIR):
        shutil.rmtree(EVAL_DIR)
    os.makedirs(EVAL_DIR)
    
    shutil.copy(SOURCE_PDF, EVAL_PDF)
    print(f"✅ Isolated environment ready with {PDF_FILENAME}")

def run_evaluation():
    print("\n--- INGESTING PDF ---")
    rag.ingest_documents(EVAL_DIR)
    
    queries = [
        # DIRECT (1-4)
        {"q": "What are the five broad categories of the NIST Cybersecurity Framework?", "expected_pg": 8, "type": "Direct"},
        {"q": "Why should you not broadcast the Service Set Identifier (SSID) on your wireless access point?", "expected_pg": 14, "type": "Direct"},
        {"q": "What should you do if you send sensitive documents or emails at your SMM firm?", "expected_pg": 15, "type": "Direct"},
        {"q": "Why is it important to require individual user accounts for each employee?", "expected_pg": 10, "type": "Direct"},
        
        # PARAPHRASED (5-8)
        {"q": "What kind of router encryption standard is recommended for securing company Wi-Fi?", "expected_pg": 14, "type": "Paraphrased"},
        {"q": "How long should audit records or system event files be preserved?", "expected_pg": 18, "type": "Paraphrased"},
        {"q": "Who should we call if we suspect intellectual property has been stolen?", "expected_pg": 20, "type": "Paraphrased"},
        {"q": "Is it necessary to scrutinize the backgrounds of business owners themselves?", "expected_pg": 9, "type": "Paraphrased"},
        
        # NUMERICAL / SPECIFIC (9-10)
        {"q": "What is the minimum number of years some types of log information must be stored?", "expected_pg": 18, "type": "Numerical"},
        {"q": "Which outdated wireless privacy protocol should never be used?", "expected_pg": 14, "type": "Numerical"},
        
        # PROCEDURAL (11-12)
        {"q": "What steps should be taken when setting up a secure wireless access point?", "expected_pg": 14, "type": "Procedural"},
        {"q": "What actions are required when purchasing new computers or installing new software?", "expected_pg": 12, "type": "Procedural"},
        
        # UNANSWERABLE (13-14)
        {"q": "What is the recommended maximum budget a small manufacturer should allocate to cybersecurity software?", "expected_pg": -1, "type": "Unanswerable"},
        {"q": "Which specific anti-virus software brand does the NIST framework recommend for small manufacturers?", "expected_pg": -1, "type": "Unanswerable"},
        
        # UNRELATED (15)
        {"q": "How do you properly tie a double Windsor knot for a tie?", "expected_pg": -1, "type": "Unrelated"}
    ]
    
    print("\n--- RUNNING QUERIES ---")
    results = []
    
    for item in queries:
        query = item["q"]
        res = rag.query_rag(query, top_k=5)
        results.append({"q": query, "type": item["type"], "expected_pg": item["expected_pg"], "response": res})
        
    print("\n\n====== DETAILED RESULTS ======\n")
    for r in results:
        print(f"QUERY [{r['type']}]: {r['q']}")
        print(f"Expected Page: {r['expected_pg']}")
        contexts = r["response"].get("context", [])
        if contexts:
            top_1 = contexts[0]
            print(f"TOP 1: Page {top_1['page']} | Score: {top_1['score']:.4f}")
            print(f"TEXT: {top_1['text'][:200]}...")
            
            pages_retrieved = [(c["page"], round(c["score"], 4)) for c in contexts]
            print(f"TOP 5 PAGES: {pages_retrieved}")
            
            if r['expected_pg'] != -1:
                # print all texts just to make evaluation easier for the agent
                for i, c in enumerate(contexts):
                    print(f"  Rank {i+1} [Pg {c['page']}] Score {c['score']:.4f}: {c['text'][:150]}")
        else:
            print("NO CONTEXT RETURNED")
        print("-" * 50)

if __name__ == "__main__":
    setup_isolated_env()
    run_evaluation()
