import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
import json
from rag import query_rag

queries = [
    "What column tracks the responsible group?",
    "What are the options for the resource estimate?",
    "How is the timeline broken down?",
    "Where do we document the origin of the problem?",
    "What are the valid states for status?",
    "What is the specific weakness identified for Server A?"
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
