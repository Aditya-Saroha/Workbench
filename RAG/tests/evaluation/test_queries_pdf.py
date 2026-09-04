import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from rag import query_rag

queries = [
    "What is the purpose of NIST Special Publication 800-172?",
    "How does a system security plan assist with protecting CUI?",
    "When organizations deploy advanced cyber defense mechanisms, what role does threat intelligence play?",
    "What specific type of analysis is mentioned for analyzing organizational systems?",
    "What is the recommended period for reassessing risk?",
    "Who is the CEO of NIST?"
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
