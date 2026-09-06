from vector_store import search, get_all_chunks
from config import TOP_K, RERANKING_ENABLED, CANDIDATE_POOL_SIZE, CONTEXT_EXPANSION_ENABLED, CONTEXT_EXPANSION_CHUNKS, MAX_CONTEXT_CHARS, MIN_RELEVANCE_SCORE
import re

def extract_page_number(query: str, all_chunks: list[dict]):
    """Detect if the user is explicitly asking for a specific page."""
    if re.search(r'\blast page\b', query, re.IGNORECASE):
        max_page = 1
        for c in all_chunks:
            p = c.get("page")
            if isinstance(p, int) and p > max_page:
                max_page = p
        return max_page

    match = re.search(r'\bpage\s*(\d+)\b', query, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    word_to_num = {
        "first": 1, "second": 2, "third": 3, "fourth": 4, 
        "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, 
        "ninth": 9, "tenth": 10
    }
    for word, num in word_to_num.items():
        if re.search(fr'\b{word}\s+page\b', query, re.IGNORECASE):
            return num
    return None

def merge_overlapping_text(texts: list[str]) -> str:
    if not texts:
        return ""
    merged = texts[0]
    for i in range(1, len(texts)):
        nxt = texts[i]
        overlap_len = 0
        max_search = min(len(merged), len(nxt), 200)
        for size in range(max_search, 0, -1):
            if merged[-size:] == nxt[:size]:
                overlap_len = size
                break
        
        if overlap_len > 0:
            merged += nxt[overlap_len:]
        else:
            merged += " " + nxt
    return merged

def get_expansion_bounds(c_idx, chunks_map, max_expand, requested_page=None):
    start = c_idx
    end = c_idx
    
    # Expand backwards
    for _ in range(max_expand):
        if start - 1 not in chunks_map:
            break
        prev_chunk = chunks_map[start - 1]
        curr_chunk = chunks_map[start]
        
        if requested_page and prev_chunk.get("page") != requested_page:
            break
            
        # We only strictly need prev_chunk if curr_chunk starts mid-sentence
        curr_text = curr_chunk["text"].lstrip()
        if not curr_text:
            break
        # If it starts with lowercase or continuation punctuation, it's mid-sentence
        if curr_text[0].islower() or curr_text[0] in (',', '-', ';', ':', ')', '”', '’'):
            start -= 1
        else:
            break
        
    # Expand forwards
    for _ in range(max_expand):
        if end + 1 not in chunks_map:
            break
        curr_chunk = chunks_map[end]
        next_chunk = chunks_map[end + 1]
        
        if requested_page and next_chunk.get("page") != requested_page:
            break
            
        # We only strictly need next_chunk if curr_chunk ends mid-sentence
        curr_text = curr_chunk["text"].rstrip()
        if not curr_text:
            break
        # If it doesn't end with a sentence-terminating punctuation, it's cut off
        if not curr_text.endswith(('.', '!', '?', '"', '\'', '”', '’', '\n')):
            end += 1
        else:
            break
            
    return start, end

def retrieve(query: str, top_k: int = TOP_K) -> dict:
    try:
        if RERANKING_ENABLED:
            from reranker import hybrid_search
            pool_size = max(CANDIDATE_POOL_SIZE, top_k)
            dense_results = search(query, top_k=pool_size)
            results = hybrid_search(query, top_k=pool_size, dense_results=dense_results)
        else:
            raw_results = search(query, top_k=max(CANDIDATE_POOL_SIZE, top_k))
            results = [
                {
                    "text": r["text"],
                    "source": r["source"],
                    "page": r["page"],
                    "score": round(r["score"], 4),
                    "chunk_index": r.get("chunk_index")
                }
                for r in raw_results
            ]
    except FileNotFoundError:
        return {"query": query, "context": [], "sources": []}

    all_chunks = get_all_chunks()

    # ─── Change 3: Page-Aware Retrieval ──────────────────────────────
    requested_page = extract_page_number(query, all_chunks)
    if requested_page is not None:
        boosted = False
        for r in results:
            if r.get("page") == requested_page:
                r["score"] = r.get("score", 0) + 10.0
                boosted = True
        
        if not boosted and all_chunks:
            for chunk in all_chunks:
                if chunk.get("page") == requested_page:
                    chunk["score"] = 10.0
                    results.append(chunk)
                    break

    # ─── Change 2: Relevance Filtering ───────────────────────────────
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    results = [r for r in results if r.get("score", 0) >= MIN_RELEVANCE_SCORE]
    results = results[:top_k]

    # ─── Change 6: No-Answer / Out-of-Scope Behavior ─────────────────
    if not results:
        return {"query": query, "context": [], "sources": []}

    # ─── Change 1: Conditional Context Expansion ─────────────────────
    context = []
    
    if CONTEXT_EXPANSION_ENABLED and all_chunks:
        source_to_chunks = {}
        for c in all_chunks:
            src = c.get("source")
            idx = c.get("chunk_index")
            if src and idx is not None:
                if src not in source_to_chunks:
                    source_to_chunks[src] = {}
                source_to_chunks[src][idx] = c
        
        source_to_intervals = {}
        unindexed_results = []
        
        for r in results:
            src = r.get("source")
            c_idx = r.get("chunk_index")
            if src is None or c_idx is None:
                unindexed_results.append(r)
                continue
                
            chunks_map = source_to_chunks.get(src, {})
            
            # Disable automatic expansion for Excel files to prevent mixing unrelated rows
            current_max_expand = 0 if src.lower().endswith('.xlsx') else CONTEXT_EXPANSION_CHUNKS
            
            start, end = get_expansion_bounds(c_idx, chunks_map, current_max_expand, requested_page)
            
            if src not in source_to_intervals:
                source_to_intervals[src] = []
            source_to_intervals[src].append({
                "start": start,
                "end": end,
                "max_score": r.get("score", 0.0),
                "original_pages": {r.get("page")} if r.get("page") else set()
            })
        
        expanded_blocks = []
        
        for src, intervals in source_to_intervals.items():
            intervals.sort(key=lambda x: x["start"])
            merged = []
            for current in intervals:
                if not merged:
                    merged.append(current)
                else:
                    last = merged[-1]
                    if current["start"] <= last["end"] + 1:
                        last["end"] = max(last["end"], current["end"])
                        last["max_score"] = max(last["max_score"], current["max_score"])
                        last["original_pages"].update(current["original_pages"])
                    else:
                        merged.append(current)
                        
            chunks_map = source_to_chunks.get(src, {})
            for m in merged:
                block_chunks = []
                for i in range(m["start"], m["end"] + 1):
                    if i in chunks_map:
                        block_chunks.append(chunks_map[i])
                        
                if not block_chunks:
                    continue
                    
                texts_to_merge = []
                total_chars = 0
                actual_start = block_chunks[0]["chunk_index"]
                actual_end = block_chunks[-1]["chunk_index"]
                pages = set()
                
                for bc in block_chunks:
                    t = bc["text"]
                    if total_chars + len(t) > MAX_CONTEXT_CHARS:
                        break
                    texts_to_merge.append(t)
                    total_chars += len(t)
                    pages.add(bc.get("page"))
                    actual_end = bc["chunk_index"]
                    
                merged_text = merge_overlapping_text(texts_to_merge)
                
                pages_list = list(pages)
                primary_page = pages_list[0] if len(pages_list) == 1 else pages_list
                
                expanded_blocks.append({
                    "text": merged_text,
                    "source": src,
                    "page": primary_page,
                    "score": round(m["max_score"], 4),
                    "context_type": "expanded",
                    "expanded_chunk_range": f"{actual_start}-{actual_end}"
                })
                
        for r in unindexed_results:
            r["context_type"] = "raw"
            expanded_blocks.append(r)
            
        expanded_blocks.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        context = expanded_blocks
    else:
        context = results

    # Deduplicated sources, preserving retrieval order
    seen = set()
    sources = []
    for r in context:
        src = r.get("source")
        pg = r.get("page")
        
        if isinstance(pg, list):
            for p in pg:
                key = (src, p)
                if key not in seen:
                    seen.add(key)
                    sources.append({"source": src, "page": p})
        else:
            key = (src, pg)
            if key not in seen:
                seen.add(key)
                sources.append({"source": src, "page": pg})

    return {
        "query": query,
        "context": context,
        "sources": sources,
    }

if __name__ == "__main__":
    import json
    query = "What safety equipment is needed for inspections?"
    print(f"Query: {query}\n")
    result = retrieve(query, top_k=3)
    print(json.dumps(result, indent=2, ensure_ascii=False))
