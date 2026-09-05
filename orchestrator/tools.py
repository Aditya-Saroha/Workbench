import json
import traceback
import sys
import os
import urllib.request
import urllib.error

# Add RAG folder to path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rag_dir = os.path.join(root_dir, "RAG")
sys.path.append(rag_dir)

try:
    from rag import query_rag
except ImportError as e:
    print(f"Warning: Could not import query_rag. Error: {e}")
    query_rag = None

def execute_tool(tool_name: str, tool_args: dict) -> str:
    """Dispatcher for all agent tools."""
    
    if tool_name == "direct_chat":
        prompt = tool_args.get("prompt", "")
        payload = json.dumps({"model": "llama3.2:1b", "prompt": prompt, "stream": False}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=payload, headers={"Content-Type": "application/json"})
        
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result.get("response", "No response generated.")
        except urllib.error.URLError as e:
            return f"Failed to reach Ollama: {str(e)}"
            
    elif tool_name == "search_rag":
        query = tool_args.get("query", "")
        if not query: return "Error: No query provided to search_rag tool."
        if not query_rag: return f"[MOCK] RAG results for: {query}"
            
        try:
            result = query_rag(query, top_k=5)
            contexts = result.get("context", [])
            if not contexts: return f"No relevant documents found for query: '{query}'"
                
            formatted_context = [f"Found {len(contexts)} relevant document excerpts:\n"]
            for i, chunk in enumerate(contexts):
                text = chunk.get("text", "")
                source = chunk.get("source", "Unknown Document")
                page = chunk.get("page", "Unknown Page")
                formatted_context.append(f"--- Excerpt {i+1} ---\nSource: {source} (Page: {page})\nContent: {text.strip()}\n")
                
            return "\n".join(formatted_context)
        except Exception as e:
            return f"Error executing RAG search: {str(e)}\n{traceback.format_exc()}"
            
    elif tool_name == "read_file":
        filepath = tool_args.get("filepath", "")
        return f"[MOCK] Contents of {filepath}"
        
    elif tool_name == "python_sandbox":
        return f"[MOCK] Execution success. Output: 42"
        
    elif tool_name == "write_docx":
        return f"[MOCK] Successfully saved to {tool_args.get('filename')}"
        
    else:
        raise ValueError(f"Unknown tool: {tool_name}")