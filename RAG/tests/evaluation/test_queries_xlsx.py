import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from rag import query_rag

queries = [
    "Which NIST SP 800-171 requirement maps to ID.RA-3 regarding periodically assessing risk?",
    "What requirement maps to identifying, reporting, and correcting information system flaws?",
    "Which CSF subcategory is associated with requirement 3.14.3 for monitoring security alerts?",
    "What is the intent of this mapping document according to the disclaimer?",
    "Which requirement maps to deploying AI-based firewalls for ID.RA-3?"
]

for q in queries:
    res = query_rag(q, top_k=1)
    print("====================")
    print("QUERY:", q)
    if res["context"]:
        print("SCORE:", res["context"][0]["score"])
        print("TEXT:", res["context"][0]["text"].replace("\n", "\\n")[:200])
    else:
        print("NO RESULT")
