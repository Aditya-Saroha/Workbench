import os
import json
import shutil
import sys
from pathlib import Path

# Add rag directory to path so we can import its modules
sys.path.insert(0, str(Path(__file__).parent))

import rag
from config import DATA_DIR

PDF_FILENAME = "GOVPUB-PR32_4400-a5ee6869cbfedb8adb584c63e8d25605.pdf"
SOURCE_PDF = os.path.join("documents", PDF_FILENAME)
EVAL_DIR = "eval_docs"
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
    # 1. Ingest
    print("\n--- INGESTING PDF ---")
    rag.ingest_documents(EVAL_DIR)
    
    queries = [
        # Direct
        {"q": "How often should automatic oilers on pump bearings be checked?", "expected": 21, "type": "Direct"},
        {"q": "How can jute packing material be disinfected before use?", "expected": 67, "type": "Direct"},
        {"q": "What is the recommended chlorine concentration for swabbing new pipes and valves?", "expected": 67, "type": "Direct"},
        {"q": "What methods should be used to warn the community if the water supply is rendered unsafe by a disaster?", "expected": 106, "type": "Direct"},
        {"q": "What is the estimated minimum water requirement per capita per day when water must be hauled?", "expected": 107, "type": "Direct"},
        {"q": "How should water tank trucks that previously contained gasoline be cleaned before use?", "expected": 107, "type": "Direct"},
        # Paraphrased
        {"q": "If someone can't spin the pump's axis manually, what is likely wrong?", "expected": 21, "type": "Paraphrased"},
        {"q": "How much drinking and cooking liquid does one person need daily during an emergency?", "expected": 107, "type": "Paraphrased"},
        {"q": "What concentration of chemical should be used for the initial concentrated blast when cleaning heavily contaminated lines?", "expected": 67, "type": "Paraphrased"},
        # Section Specific
        {"q": "According to the Disinfection of Water Mains and Appurtenances procedure, what should be done before treating the mains to minimize foreign matter?", "expected": 67, "type": "Specific"},
        {"q": "When preparing Temporary Water Service plans, what specific facilities and locations need to be included?", "expected": 106, "type": "Specific"},
        # Unrelated
        {"q": "What are the tax implications of declaring a federal emergency?", "expected": -1, "type": "Unrelated"}
    ]
    
    results_data = []
    
    print("\n--- RUNNING QUERIES ---")
    for i, item in enumerate(queries):
        query = item["q"]
        expected_page = item["expected"]
        
        result = rag.query_rag(query, top_k=1)
        
        # Determine top retrieved page
        top_page = -1
        score = 0.0
        if result["context"]:
            top_page = result["context"][0]["page"]
            score = result["context"][0]["score"]
            
        correct = (top_page == expected_page)
        if item["type"] == "Unrelated":
            correct = (score < 0.2)  # heuristic for unrelated
        
        results_data.append({
            "query": query,
            "type": item["type"],
            "expected_page": expected_page,
            "retrieved_page": top_page,
            "score": score,
            "correct": correct,
            "full_json": result
        })
    
    # Dump full JSON
    print("\n\n====== COMPLETE JSON OUTPUT ======\n")
    all_json = [r["full_json"] for r in results_data]
    print(json.dumps(all_json, indent=2, ensure_ascii=False))
    
    # Print Markdown Table
    print("\n\n====== RESULTS TABLE ======\n")
    print("| Query Type | Query | Expected Page | Retrieved Page | Correct? | Score |")
    print("|---|---|---|---|---|---|")
    correct_count = 0
    total = len(queries)
    for r in results_data:
        c_mark = "✅" if r["correct"] else "❌"
        if r["correct"]:
            correct_count += 1
        print(f"| {r['type']} | {r['query']} | {r['expected_page']} | {r['retrieved_page']} | {c_mark} | {r['score']:.4f} |")
        
    acc = (correct_count / total) * 100
    print(f"\nRetrieval Accuracy: {correct_count}/{total} ({acc:.1f}%)")

if __name__ == "__main__":
    setup_isolated_env()
    run_evaluation()
