import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from rag import query_rag

q = "identifying, reporting, and correcting information system flaws"
res = query_rag(q, top_k=5)
for i, c in enumerate(res["context"]):
    print(f"Rank {i} | Score {c['score']}")
    print(c["text"])
